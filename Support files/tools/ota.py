#!/usr/bin/env python3
"""Over-the-air updates for LLM OS devices, served from this computer.

    tools/ota.py keygen                 make the signing key (once; kept in Support files/ota-keys/, never in git)
    tools/ota.py serve                  serve updates on the local network (port 8781); leave it running
    tools/ota.py publish [--version V] [--restart desk,llmos-scheduler] [--apk pkg,...] [--note TEXT]
                                        sign the current src/rootfs as a new update; paired devices install it at once
    tools/ota.py info                   this server's address and key fingerprint (to compare when pairing)
    tools/ota.py reports                what devices said after installing

On the device, the owner says "get updates from my computer" (or "get updates from 192.168.1.20") once.
The server serves only the published updates folder: never the source tree, the key or anything else.
"""
import argparse
import hashlib
import http.server
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.parse

PROJECT = "/Volumes/Files/Claude Work Area/LLMOS/Support files"   # the key and the feed live in the main checkout
KEYDIR = os.path.join(PROJECT, "ota-keys")
KEY = os.path.join(KEYDIR, "ota_ed25519")
FEED = os.path.join(PROJECT, "run", "ota", "feed")
REPORTS = os.path.join(PROJECT, "run", "ota", "reports.jsonl")
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "rootfs")  # this tree's source
PORT = 8781
NAMESPACE = "llmos-ota"
EXEC = {"usr/bin/llmos", "usr/bin/llmos-model-run", "usr/libexec/llmos-login", "usr/libexec/llmos-desk"}
ALLOWED = ("usr/lib/llmos/", "usr/share/llmos/", "usr/bin/llmos", "usr/libexec/llmos-", "etc/init.d/llmos-", "etc/xdg/")
SKIP = {"etc/nftables.nft"}
ID_RE = re.compile(r"[A-Za-z0-9._-]{1,80}")


def pubkey():
    with open(KEY + ".pub") as f:
        return " ".join(f.read().split()[:2])


def fingerprint(key):
    h = hashlib.sha256(key.strip().encode()).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}"


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.0.1", 9))           # no packet is sent; this picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def cmd_keygen(a):
    if os.path.exists(KEY):
        print(f"key already exists: {KEY}  (fingerprint {fingerprint(pubkey())})")
        return
    os.makedirs(KEYDIR, mode=0o700, exist_ok=True)
    ignored = subprocess.run(["git", "-C", PROJECT, "check-ignore", "-q", KEY]).returncode == 0
    if not ignored:
        sys.exit("refusing: ota-keys/ is not git-ignored")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", NAMESPACE, "-f", KEY], check=True)
    os.chmod(KEY, 0o600)
    print(f"made {KEY}  (fingerprint {fingerprint(pubkey())})")


def _version():
    with open(os.path.join(SRC, "usr/lib/llmos/llmos/__init__.py")) as f:
        return re.search(r'^VERSION = "([^"]+)"', f.read(), re.M).group(1)


def build_payload(version):
    """The rootfs as a root-owned tar (like tools/push.sh), with __init__.py's VERSION set to version."""
    buf = io.BytesIO()
    n = 0
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for dirpath, dirnames, filenames in os.walk(SRC):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for fn in sorted(filenames):
                if fn == ".DS_Store" or fn.endswith(".pyc"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, SRC)
                if rel in SKIP or not rel.startswith(ALLOWED):
                    continue
                ti = tf.gettarinfo(full, arcname=rel)
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = "root"
                if ti.isreg():
                    ti.mode = 0o755 if (rel in EXEC or rel.startswith("etc/init.d/")) else 0o644
                    data = open(full, "rb").read()
                    if rel == "usr/lib/llmos/llmos/__init__.py":
                        data = re.sub(rb'^VERSION = "[^"]+"', f'VERSION = "{version}"'.encode(), data, flags=re.M)
                        ti.size = len(data)
                    tf.addfile(ti, io.BytesIO(data))
                elif ti.issym():
                    tf.addfile(ti)
                n += 1
    return buf.getvalue(), n


def cmd_publish(a):
    if not os.path.exists(KEY):
        sys.exit("no signing key: run tools/ota.py keygen first")
    for dirpath, _, filenames in os.walk(os.path.join(SRC, "usr/lib/llmos")):     # never ship code that can't load
        for fn in filenames:
            if fn.endswith(".py"):
                path = os.path.join(dirpath, fn)
                compile(open(path, "rb").read(), path, "exec")
    version = a.version or _version()
    data, n = build_payload(version)
    digest = hashlib.sha256(data).hexdigest()
    uid = time.strftime("%Y%m%d-%H%M%S") + "-" + digest[:8]
    os.makedirs(FEED, exist_ok=True)
    with open(os.path.join(FEED, f"payload-{uid}.tar"), "wb") as f:
        f.write(data)
    m = {"format": 1, "id": uid, "version": version, "payload": f"payload-{uid}.tar", "sha256": digest,
         "size": len(data), "files": n, "created": int(time.time()), "from": socket.gethostname(),
         "restart": [s for s in (a.restart or "llmos-rootd,llmos-scheduler,desk").split(",") if s],
         "apk": [p for p in (a.apk or "").split(",") if p], "note": a.note or ""}
    mpath = os.path.join(FEED, f"manifest-{uid}.json")
    with open(mpath, "w") as f:
        json.dump(m, f, indent=1)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", KEY, "-n", NAMESPACE, mpath], check=True,
                   stdout=subprocess.DEVNULL)
    with open(os.path.join(FEED, "latest.tmp"), "w") as f:
        f.write(uid)
    os.replace(os.path.join(FEED, "latest.tmp"), os.path.join(FEED, "latest"))
    # keep the last 5 updates
    ids = sorted(fn[9:-5] for fn in os.listdir(FEED) if fn.startswith("manifest-") and fn.endswith(".json"))
    for old in ids[:-5]:
        for fn in (f"manifest-{old}.json", f"manifest-{old}.json.sig", f"payload-{old}.tar"):
            try:
                os.unlink(os.path.join(FEED, fn))
            except OSError:
                pass
    print(f"published {version} as {uid}: {n} files, {len(data) / 1e6:.1f} MB, restart {','.join(m['restart'])}")


def latest():
    try:
        with open(os.path.join(FEED, "latest")) as f:
            uid = f.read().strip()
        return uid if ID_RE.fullmatch(uid) else ""
    except OSError:
        return ""


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "llmos-ota"

    def log_message(self, fmt, *args):
        sys.stderr.write(time.strftime("%H:%M:%S ") + self.client_address[0] + " " + (fmt % args) + "\n")

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/ota/hello":
            key = pubkey()
            return self._send(200, json.dumps({"name": socket.gethostname(), "key": key, "fp": fingerprint(key)}).encode())
        if u.path == "/ota/wait":
            have = urllib.parse.parse_qs(u.query).get("have", [""])[0]
            end = time.time() + 50
            while time.time() < end:
                cur = latest()
                if cur and cur != have:
                    return self._send(200, json.dumps({"id": cur}).encode())
                time.sleep(1)
            return self._send(200, b"{}")
        m = re.fullmatch(r"/ota/((?:manifest-[A-Za-z0-9._-]+\.json(?:\.sig)?)|(?:payload-[A-Za-z0-9._-]+\.tar))", u.path)
        if m:
            path = os.path.join(FEED, m.group(1))
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return self._send(200, f.read(), "application/octet-stream")
        self._send(404, b"{}")

    def do_POST(self):
        if self.path != "/ota/report":
            return self._send(404, b"{}")
        n = min(int(self.headers.get("Content-Length", 0) or 0), 16384)
        try:
            body = json.loads(self.rfile.read(n))
        except ValueError:
            return self._send(400, b"{}")
        body["from_ip"], body["at"] = self.client_address[0], time.strftime("%Y-%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(REPORTS), exist_ok=True)
        with open(REPORTS, "a") as f:
            f.write(json.dumps(body) + "\n")
        print(f"REPORT {body.get('host')} {body.get('version', '')} {'OK' if body.get('ok') else 'NOT INSTALLED'}: "
              f"{body.get('detail', '')}", flush=True)
        self._send(200, b"{}")


def cmd_serve(a):
    if not os.path.exists(KEY):
        sys.exit("no signing key: run tools/ota.py keygen first")
    os.makedirs(FEED, exist_ok=True)
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    print(f"serving LLM OS updates at http://{lan_ip()}:{PORT}  key {fingerprint(pubkey())}  latest {latest() or '-'}",
          flush=True)
    srv.serve_forever()


def cmd_info(a):
    print(f"http://{lan_ip()}:{PORT}  key {fingerprint(pubkey())}  latest {latest() or '-'}")


def cmd_reports(a):
    try:
        lines = open(REPORTS).read().splitlines()[-a.n:]
    except OSError:
        lines = []
    for ln in lines:
        r = json.loads(ln)
        print(f"{r.get('at')} {r.get('host')} ({r.get('from_ip')}) {r.get('version', '')} "
              f"{'OK' if r.get('ok') else 'NOT INSTALLED'}: {r.get('detail', '')}  now {r.get('now', '?')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    sub.add_parser("serve")
    p = sub.add_parser("publish")
    p.add_argument("--version")
    p.add_argument("--restart")
    p.add_argument("--apk")
    p.add_argument("--note")
    sub.add_parser("info")
    r = sub.add_parser("reports")
    r.add_argument("-n", type=int, default=10)
    a = ap.parse_args()
    {"keygen": cmd_keygen, "serve": cmd_serve, "publish": cmd_publish, "info": cmd_info, "reports": cmd_reports}[a.cmd](a)


if __name__ == "__main__":
    main()
