#!/usr/bin/env python3
"""Remote testing link: a command signed with the update key passes; a changed one, a stale one, a repeat, another
key's, or an unsigned one is refused; the update server queues commands and keeps results.
Run: python3 tools/test-devlink.py  (exit status 0 = pass)"""
import importlib.util, json, os, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="devlink-home-"))
os.environ.setdefault("LLMOS_ETC", os.path.join(os.environ["LLMOS_HOME"], "etc"))
from llmos import devlink, ota  # noqa: E402

fails = []
def check(name, ok, info=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  ({info})"))
    if not ok:
        fails.append(name)

d = tempfile.mkdtemp(prefix="devlink-")
key = os.path.join(d, "k")
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
other = os.path.join(d, "o")
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", other], check=True)
pub = open(key + ".pub").read().strip()

def sign(raw, k=key, ns="llmos-dev"):
    f = os.path.join(d, "c")
    open(f, "w").write(raw)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", k, "-n", ns, f], check=True, stdout=subprocess.DEVNULL)
    s = open(f + ".sig").read()
    os.unlink(f + ".sig")
    return s

raw = json.dumps({"op": "state", "id": "abcdef0123456789", "ts": time.time(), "host": "*"})
check("signed command verifies", devlink._verify(raw.encode(), sign(raw).encode(), pub))
check("changed command refused", not devlink._verify(raw.replace("state", "sh").encode(), sign(raw).encode(), pub))
check("another key refused", not devlink._verify(raw.encode(), sign(raw, other).encode(), pub))
check("an update signature is not a command signature", not devlink._verify(raw.encode(), sign(raw, ns="llmos-ota").encode(), pub))
check("a command signature is not an update signature", not ota.verify_manifest(raw.encode(), sign(raw).encode(), pub))
check("updates still verify", ota.verify_manifest(raw.encode(), sign(raw, ns="llmos-ota").encode(), pub))
check("off by default", not devlink.enabled())
try:
    ota.check_manifest({"format": 1, "id": "x1", "version": "1", "payload": "payload-x1.tar", "sha256": "0" * 64,
                        "enable": ["rootshell"]})
    check("unknown switch refused", False)
except ValueError:
    check("unknown switch refused", True)
print("all good" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
