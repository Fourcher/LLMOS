#!/usr/bin/env python3
"""Host-side test of LLM OS Setup (dist/setup/llmos-setup.py, formerly the Exporter): its CSRF / cross-origin
protection, and how it recognises a computer and recommends the way in. Setup is a local web app on 127.0.0.1
that can write USB sticks and run programs, so a web page the owner happens to have open must not be able to
drive it: every /api endpoint (read-only ones included) must require the per-launch token in a custom header;
cross-origin requests, DNS-rebinding hosts and CORS preflights must be refused; the page must carry
anti-framing / no-store headers. Run: python3 tools/test-setup-csrf.py (no network beyond a loopback server;
nothing is launched and no browser is opened)."""
import http.client
import http.server
import importlib.util
import json
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("llmos_setup", os.path.join(ROOT, "dist/setup/llmos-setup.py"))
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

print("recognising the computer and recommending the way in")
s, b, _ = req("GET", "/api/status", TOK)
st = json.loads(b)
check(s == 200 and "host" in st and "recommend" in st, "/api/status reports this computer and a recommendation")
real = ex.host()
check(isinstance(real["ram_gb"], float) and real["system"] in ("Darwin", "Windows", "Linux"), f"this computer: {real['system']} {real['machine']}, {real['ram_gb']} GB")
if real["system"] == "Darwin" and real["arm"]:
    check(real["apple_silicon"] and ex.recommend(real)["section"] == "apple-silicon", "this Apple Silicon Mac is recognised as one")


def rec_for(system, arm, ram=16.0):
    saved = ex.SYSTEM
    ex.SYSTEM = system
    try:
        return ex.recommend({"system": system, "arm": arm, "apple_silicon": system == "Darwin" and arm, "ram_gb": ram})
    finally:
        ex.SYSTEM = saved


r = rec_for("Darwin", True)
check(r["section"] == "apple-silicon" and r["iso"] == "llmos-arm64.iso" and r["goal"] == "vm" and "UTM" in r["headline"],
      "Apple Silicon Mac -> in a window (UTM), arm64 ISO; never the Intel/USB path")
r = rec_for("Darwin", False)
check(r["section"] == "intel-mac" and r["iso"] == "llmos-x86_64.iso", "Intel Mac -> x86_64 ISO, Intel Mac steps")
r = rec_for("Windows", False)
check(r["section"] == "pc" and r["goal"] == "usb" and r["iso"] == "llmos-x86_64.iso", "Windows PC -> USB stick first, x86_64 ISO")
r = rec_for("Linux", False)
check(r["section"] == "pc" and r["goal"] == "vm", "Linux PC -> in a window first")
check("note" in rec_for("Darwin", True, ram=8.0 - 0.1) and "note" not in rec_for("Darwin", True, ram=16.0),
      "a computer with under 8 GB gets a memory note, a 16 GB one does not")

instr = json.load(open(os.path.join(ROOT, "dist/setup/instructions.json")))
ids = {sec["id"] for sec in instr["sections"]}
check({"vm", "apple-silicon", "intel-mac", "pc"} <= ids, f"the instructions have every section a recommendation can open: {sorted(ids)}")
check(not any("double-click <b>run-llmos.sh" in st for sec in instr["sections"] for st in sec["steps"]),
      "no step tells a Mac user to double-click a .sh file (Finder opens those in a text editor)")
check(any("UTM" in st for sec in instr["sections"] if sec["id"] == "vm" for st in sec["steps"]), "the window steps cover UTM on a Mac")

s, b, _ = req("GET", "/")
check(b"Welcome" in b and b"2 - Set up with AI.md" in b and b"LLM OS Setup" in b, "the page opens with the welcome card and points to the AI setup file")
for name in ("1 - START HERE (Mac).command", "1 - START HERE (Windows).bat", "1 - START HERE (Linux).sh"):
    path = os.path.join(ROOT, "dist", name)
    check(os.path.exists(path) and "setup" in open(path, encoding="utf-8").read() and "llmos-setup.py" in open(path, encoding="utf-8").read(),
          f"'{name}' exists and opens setup/llmos-setup.py")
check(open(os.path.join(ROOT, "dist", "1 - START HERE (Windows).bat"), "rb").read().count(b"\r\n") > 10, "the Windows launcher has CRLF line endings")
check(os.access(os.path.join(ROOT, "dist", "1 - START HERE (Mac).command"), os.X_OK), "the Mac launcher is executable")

srv.shutdown()
print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
