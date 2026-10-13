#!/usr/bin/env python3
"""Host test for over-the-air updates: tools/ota.py (the owner's computer) against llmos/ota.py (the device).

A throwaway key and a fake device root in a temporary folder: publish, serve, verify, install, roll back, and the
refusals (another key's signature, a changed archive, paths outside LLM OS's own files)."""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="ota-test-")
ROOT = os.path.join(TMP, "device")
os.makedirs(os.path.join(ROOT, "etc/llmos"), exist_ok=True)
os.environ.update(LLMOS_OTA_ROOT=ROOT, LLMOS_OTA_DIR=os.path.join(TMP, "state"), LLMOS_ETC=os.path.join(ROOT, "etc/llmos"))
sys.path.insert(0, os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos"))
from llmos import ota  # noqa: E402

spec = importlib.util.spec_from_file_location("hostota", os.path.join(HERE, "ota.py"))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
host.KEYDIR = os.path.join(TMP, "keys")
host.KEY = os.path.join(host.KEYDIR, "k")
host.FEED = os.path.join(TMP, "feed")
host.REPORTS = os.path.join(TMP, "reports.jsonl")
host.PORT = ota.PORT = 18781

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


# key (bypassing keygen's git-ignore guard, which is about the real key folder)
os.makedirs(host.KEYDIR)
import subprocess  # noqa: E402
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "t", "-f", host.KEY], check=True)
key = host.pubkey()
check("fingerprints agree on both sides", host.fingerprint(key) == ota.fingerprint(key))


class A:
    version = "9.9.9"
    restart = "desk"
    apk = ""
    note = ""


host.cmd_publish(A())
uid = host.latest()
check("publish writes a latest pointer", bool(uid))
mpath = os.path.join(host.FEED, f"manifest-{uid}.json")
raw, sig = open(mpath, "rb").read(), open(mpath + ".sig", "rb").read()
m = json.loads(raw)
check("signature verifies with the paired key", ota.verify_manifest(raw, sig, key))
check("manifest passes the device's checks", ota.check_manifest(m)["id"] == uid)
payload = os.path.join(host.FEED, m["payload"])
check("payload matches the signed checksum", hashlib.sha256(open(payload, "rb").read()).hexdigest() == m["sha256"])
names = ota.check_payload(payload)
check("payload holds only LLM OS files", names and all(n.startswith(ota.ALLOWED) or "/" not in n.rstrip("/") for n in names))
check("payload never carries the generated firewall file", "etc/nftables.nft" not in names)
with tarfile.open(payload) as tf:
    init = tf.extractfile("usr/lib/llmos/llmos/__init__.py").read().decode()
    owners = {(t.uid, t.gid) for t in tf.getmembers()}
check("payload VERSION is the published version", 'VERSION = "9.9.9"' in init)
check("payload files belong to root", owners == {(0, 0)})

# another key's signature is refused
other = os.path.join(TMP, "other")
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "x", "-f", other], check=True)
os.unlink(mpath + ".sig")                     # ssh-keygen will not overwrite a signature
subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", other, "-n", "llmos-ota", mpath], check=True, stdout=subprocess.DEVNULL)
forged = open(mpath + ".sig", "rb").read()
check("the forged signature really is a different one", forged != sig)
check("a signature by another key is refused", not ota.verify_manifest(raw, forged, key))
check("a changed manifest is refused", not ota.verify_manifest(raw.replace(b"9.9.9", b"9.9.8"), sig, key))
with open(mpath + ".sig", "wb") as f:
    f.write(sig)

# archives with paths outside LLM OS's own files are refused
for bad in ("../etc/passwd", "/etc/shadow", "etc/llmos/settings.json", "root/.ssh/authorized_keys", "etc/nftables.nft"):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w") as tf:
        ti = tarfile.TarInfo(bad)
        ti.size = 1
        tf.addfile(ti, io.BytesIO(b"x"))
    p = os.path.join(TMP, "bad.tar")
    open(p, "wb").write(b.getvalue())
    try:
        ota.check_payload(p)
        check(f"refuses {bad}", False)
    except ValueError:
        check(f"refuses {bad}", True)
b = io.BytesIO()
with tarfile.open(fileobj=b, mode="w") as tf:
    ti = tarfile.TarInfo("usr/lib/llmos/llmos/evil")
    ti.type, ti.linkname = tarfile.SYMTYPE, "/etc/shadow"
    tf.addfile(ti)
open(os.path.join(TMP, "bad.tar"), "wb").write(b.getvalue())
try:
    ota.check_payload(os.path.join(TMP, "bad.tar"))
    check("refuses a link pointing outside", False)
except ValueError:
    check("refuses a link pointing outside", True)
for bad_m in ({**m, "restart": ["sshd"]}, {**m, "apk": ["evil; rm -rf /"]}, {**m, "payload": "../../x.tar"}):
    try:
        ota.check_manifest(bad_m)
        check(f"refuses manifest {list(bad_m.items())[-1]}", False)
    except ValueError:
        check("refuses an unsafe manifest field", True)

# install onto the fake device root, then roll back
old = os.path.join(ROOT, "usr/lib/llmos/llmos/__init__.py")
os.makedirs(os.path.dirname(old))
open(old, "w").write('VERSION = "1.0.0"\n')
open(os.path.join(ROOT, "etc/llmos-release"), "w").write("VERSION=1.0.0\nBUILD=2026-01-01\nARCH=x\nMEDIUM=disk\n")
rec = ota.apply_files(payload, os.path.join(TMP, "backup.tar"))
check("install replaces the files", ota.current_version() == "9.9.9")
check("install adds new files", os.path.exists(os.path.join(ROOT, "usr/lib/llmos/llmos/ota.py")))
ota._stamp_release("9.9.9")
check("release file stamped in lockstep", "VERSION=9.9.9" in open(os.path.join(ROOT, "etc/llmos-release")).read())
ota.rollback(rec)
check("rollback restores the old file", ota.current_version() == "1.0.0")
check("rollback removes files the update added", not os.path.exists(os.path.join(ROOT, "usr/lib/llmos/llmos/ota.py")))

# the server: hello, wait, files, report; and nothing else is served
srv = host.http.server.ThreadingHTTPServer(("127.0.0.1", host.PORT), host.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{host.PORT}"
h = ota.hello(base)
check("hello gives the key and fingerprint", h and h["key"] == key and h["fp"] == ota.fingerprint(key))
check("wait answers at once when there is a newer update", json.loads(ota._get(f"{base}/ota/wait?have=old"))["id"] == uid)
check("manifest is served", ota._get(f"{base}/ota/manifest-{uid}.json") == raw)
for path in ("/ota/../keys/k", "/ota/k", "/ota/latest", "/tools/ota.py", "/ota/manifest-x/../../keys/k.json"):
    try:
        urllib.request.urlopen(base + path, timeout=5)
        check(f"does not serve {path}", False)
    except Exception:
        check(f"does not serve {path}", True)
ota._report(base, {"host": "t", "ok": True, "version": "9.9.9", "detail": "x"})
check("reports are recorded", '"host": "t"' in open(host.REPORTS).read())
srv.shutdown()

# firewall exception only while paired
check("no firewall exception unpaired", ota.firewall_rule() == "")
ota.config.settings.set("ota", {"url": "http://192.168.1.20:8781", "key": key, "fp": "x", "name": "m"})
check("firewall exception for the paired server only", ota.firewall_rule() == "    ip daddr 192.168.1.20 tcp dport 8781 accept\n")
ota.config.settings.set("ota", {})

print("all good" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
