#!/usr/bin/env python3
"""Host-side test of the Exporter's CSRF / cross-origin protection (dist/exporter/exporter.py). The Exporter
is a local web app on 127.0.0.1 that can write USB sticks and run programs, so a web page the owner happens
to have open must not be able to drive it. Every /api endpoint (read-only ones included) must require the
per-launch token in a custom header; cross-origin requests, DNS-rebinding hosts, and CORS preflights must be
refused; and the page must carry anti-framing / no-store headers. Run: python3 tools/test-exporter-csrf.py
(no network beyond a loopback server)."""
import http.client
import http.server
import importlib.util
import json
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("exporter", os.path.join(ROOT, "dist/exporter/exporter.py"))
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)

ex.TOKEN = "a" * 32
BAD = "b" * 32
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ex.Handler)
PORT = srv.server_address[1]
HOST = f"127.0.0.1:{PORT}"
threading.Thread(target=srv.serve_forever, daemon=True).start()

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def req(method, path, headers=None, body=None, host=HOST):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    h = {"Host": host}
    if headers:
        h.update(headers)
    c.request(method, path, body, h)
    r = c.getresponse()
    data = r.read()
    hd = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, data, hd


TOK = {"X-LLMOS-Token": ex.TOKEN}
ORIGIN = {"Origin": f"http://{HOST}"}

print("the page")
s, b, h = req("GET", "/")
check(s == 200 and ex.TOKEN.encode() in b, "GET / serves the page with the per-launch token baked in")
check(h.get("x-frame-options") == "DENY" and "frame-ancestors 'none'" in h.get("content-security-policy", ""),
      "the page refuses framing (X-Frame-Options + CSP frame-ancestors)")
check(h.get("cache-control") == "no-store" and h.get("x-content-type-options") == "nosniff",
      "the token-bearing page is no-store + nosniff")

print("every /api endpoint requires the token (not only POST)")
for ep in ("/api/status", "/api/drives", "/api/progress", "/api/instructions"):
    s, _, _ = req("GET", ep, TOK)
    check(s == 200, f"GET {ep} WITH the token -> 200 ({s})")
    s, _, _ = req("GET", ep)
    check(s == 403, f"GET {ep} WITHOUT the token -> 403 ({s})")

print("cross-origin and DNS-rebinding are refused even with the token")
check(req("GET", "/api/status", {**TOK, "Origin": "http://evil.example"})[0] == 403, "token + cross-origin Origin -> 403")
check(req("GET", "/api/status", {**TOK, "Referer": "http://evil.example/x"})[0] == 403, "token + cross-site Referer -> 403")
check(req("GET", "/api/status", TOK, host=f"evil.example:{PORT}")[0] == 403, "Host: evil.example (DNS rebinding) -> 403")
check(req("GET", "/api/status", {"X-LLMOS-Token": BAD})[0] == 403, "a wrong token -> 403 (constant-time compare)")

print("the write / save / open actions require the token")
s, b, h = req("POST", "/api/save", {**TOK, **ORIGIN, "Content-Type": "application/json"}, b'{"file":"__nope__.iso"}')
check(s == 200 and not json.loads(b).get("ok"), "POST /api/save WITH the token runs, and rejects a bogus file name")
check(h.get("cache-control") == "no-store" and h.get("x-content-type-options") == "nosniff", "JSON responses are no-store + nosniff")
check(req("POST", "/api/save", {"Content-Type": "application/json"}, b'{"file":"__nope__.iso"}')[0] == 403, "POST /api/save WITHOUT the token -> 403")
check(req("POST", "/api/write", {"Content-Type": "application/json"}, b'{"file":"x.iso","drive":"/dev/x"}')[0] == 403, "POST /api/write WITHOUT the token -> 403")
check(req("POST", "/api/quit", {})[0] == 403, "POST /api/quit WITHOUT the token -> 403")

print("CORS preflight is refused (so a cross-origin call that needs one is blocked by the browser)")
s, _, h = req("OPTIONS", "/api/save", {"Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Headers": "x-llmos-token"})
check(s == 403 and not any(k.startswith("access-control-allow") for k in h), "OPTIONS -> 403 with no Access-Control-Allow-* headers")

srv.shutdown()
print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
