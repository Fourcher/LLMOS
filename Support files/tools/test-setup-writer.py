#!/usr/bin/env python3
"""Tests of LLM OS Setup's USB writer (dist/setup/llmos-setup.py), on this Mac, without touching a real stick.

  * the shared write-and-verify core: first chunk written last, padding, read-back check, image-changed check
  * the macOS password hand-off: authopen's descriptor passing, cancel, refusal (tools/fake-authopen.py stands in
    for /usr/libexec/authopen, which needs an administrator password)
  * the drive list never offers the disk this setup runs from, nor a Time Machine backup
  * a whole job through Setup's own web API onto a real raw block device (a RAM disk), including a damaged
    image (refused before anything is erased), a cancelled prompt, and the CSRF gate

Run: python3 tools/test-setup-writer.py
"""
import hashlib
import importlib.util
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
SETUP = os.path.join(ROOT, "dist", "setup", "llmos-setup.py")
FAKE = os.path.join(TOOLS, "fake-authopen.py")
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what, flush=True)
    if not cond:
        fails += 1


def load():
    spec = importlib.util.spec_from_file_location("llmos_setup", SETUP)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S = load()
CH = S.CHUNK


def image(path, size, seed=1):
    import random
    rnd = random.Random(seed)
    with open(path, "wb") as f:
        left = size
        while left:
            n = min(left, 1 << 20)
            f.write(rnd.randbytes(n) if hasattr(rnd, "randbytes") else bytes(rnd.getrandbits(8) for _ in range(n)))
            left -= n
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


tmp = tempfile.mkdtemp(prefix="llmos-writer-")

print("the shared core (a regular file stands in for the device)")
src = os.path.join(tmp, "img")
size = 2 * CH + 777                               # not a whole number of sectors
want = image(src, size)
dst = os.path.join(tmp, "dev")
open(dst, "wb").close()
order = []
fd = os.open(dst, os.O_RDWR)
pw, pr = S._fd_io(fd)
seen = []
got = S.write_and_verify(src, size, want, lambda v, o: (order.append(o), pw(v, o)), pr, lambda ph, d: seen.append(ph))
os.close(fd)
data = open(dst, "rb").read()
check(got == want, "returns the image's SHA-256")
check(order[0] == CH and order[-1] == 0, f"first chunk written last (offsets in order: {order})")
check(data[:size] == open(src, "rb").read(), "the device holds the image byte for byte")
check(len(data) % S.ALIGN == 0 and data[size:] == bytes(len(data) - size), "the tail is padded with zeros to a whole 4 KiB")
check("writing" in seen and "verifying" in seen and seen[-1] == "verifying", "reports writing, then verifying")

small = os.path.join(tmp, "small")
w2 = image(small, 5000, seed=2)
d2 = os.path.join(tmp, "dev2")
open(d2, "wb").close()
fd = os.open(d2, os.O_RDWR)
order2 = []
pw, pr = S._fd_io(fd)
S.write_and_verify(small, 5000, w2, lambda v, o: (order2.append(o), pw(v, o)), pr, lambda *a: None)
os.close(fd)
check(order2 == [0] and open(d2, "rb").read()[:5000] == open(small, "rb").read(), "an image smaller than one chunk is one write at 0")

fd = os.open(dst, os.O_RDWR)
pw, pr = S._fd_io(fd)


def bad_read(view, off):
    pr(view, off)
    if off == CH:
        view[10] = view[10] ^ 0xFF               # one byte comes back different
try:
    S.write_and_verify(src, size, want, pw, bad_read, lambda *a: None)
    check(False, "a stick that reads back differently is reported")
except RuntimeError as e:
    check("read back" in str(e), "a stick that reads back differently is reported")
try:
    S.write_and_verify(src, size, "0" * 64, pw, pr, lambda *a: None)
    check(False, "an image that doesn't match its checksum is refused")
except RuntimeError as e:
    check("changed" in str(e), "an image that doesn't match the checked checksum is refused")
os.close(fd)

print("the macOS password hand-off (authopen passes the open device back)")
S.AUTHOPEN = FAKE
f3 = os.path.join(tmp, "handoff")
with open(f3, "wb") as f:
    f.write(b"\0" * 8192)
fd = S._authopen(f3, os.O_RDWR)
os.pwrite(fd, b"LLMOS", 4096)
check(os.pread(fd, 5, 4096) == b"LLMOS", "a working read/write descriptor comes back over the socket")
os.close(fd)
for mode, expect in (("cancel", "Cancelled"), ("denied", "Full Disk Access")):
    os.environ["FAKE_AUTHOPEN"] = mode
    try:
        S._authopen(f3, os.O_RDWR)
        check(False, f"{mode}: reported")
    except S.Cancelled:
        check(expect == "Cancelled", f"{mode}: reported as cancelled (nothing written)")
    except RuntimeError as e:
        check(expect in str(e), f"{mode}: reported with the fix ({str(e)[:70]}…)")
    os.environ.pop("FAKE_AUTHOPEN", None)

print("the drive list on this Mac")
if not shutil.which("diskutil"):
    print("SKIP: the drive list needs macOS diskutil, which is not on this machine")
else:
    def physical_disk_of(path):
        """The physical whole disk holding `path`, found independently of the code under test."""
        dev = subprocess.run(["df", "-P", path], capture_output=True, text=True).stdout.splitlines()[-1].split()[0]
        info = plistlib.loads(subprocess.run(["diskutil", "info", "-plist", dev], capture_output=True).stdout)
        whole = info.get("ParentWholeDisk", "")
        apfs = plistlib.loads(subprocess.run(["diskutil", "apfs", "list", "-plist"], capture_output=True).stdout)
        for c in apfs.get("Containers", []):
            if c.get("ContainerReference") == whole:
                store = c["PhysicalStores"][0]["DeviceIdentifier"]
                return plistlib.loads(subprocess.run(["diskutil", "info", "-plist", store], capture_output=True).stdout).get("ParentWholeDisk", whole)
        return whole

    own = physical_disk_of(S.FILES)
    ids = [d["id"] for d in S.list_drives()["drives"]]
    external = plistlib.loads(subprocess.run(["diskutil", "list", "-plist", "external", "physical"], capture_output=True).stdout).get("WholeDisks", [])
    print(f"    (this setup runs from {own}; external disks: {external}; offered: {ids})")
    check(own not in ids, f"the disk this setup runs from ({own}) is never offered")
    for b in S._mac_backup_mounts():
        check(physical_disk_of(b) not in ids, f"the Time Machine backup on {b} is never offered")
    check("test" not in ids, "no test drive unless a test asks for one")

print("a whole job through Setup's web API, onto a raw block device (a RAM disk)")
if not shutil.which("hdiutil"):
    print("SKIP: the USB write through Setup needs macOS hdiutil to attach a RAM disk, which is not on this machine")
    print("all good" if not fails else f"{fails} FAILED")
    sys.exit(1 if fails else 0)
ram = subprocess.run(["hdiutil", "attach", "-nomount", "ram://131072"], capture_output=True, text=True).stdout.split()[0]   # 64 MiB
raw = ram.replace("/dev/disk", "/dev/rdisk")
files = os.path.join(tmp, "files")
os.makedirs(files)
img = os.path.join(files, S.USB_IMAGE)
isz = 5 * CH + 4321
isha = image(img, isz, seed=3)
with open(os.path.join(files, "VERSION"), "w") as f:
    f.write("9.9.9\n")


def server(extra):
    env = dict(os.environ, LLMOS_SETUP_NO_BROWSER="1", LLMOS_SETUP_FILES=files, LLMOS_SETUP_TEST_DEVICE=raw,
               LLMOS_SETUP_TEST_SIZE=str(16 * 10**9), LLMOS_SETUP_AUTHOPEN=FAKE, **extra)
    p = subprocess.Popen([sys.executable, SETUP], env=env, stdout=subprocess.PIPE, text=True)
    deadline = time.time() + 15
    while time.time() < deadline:
        line = p.stdout.readline()
        m = re.search(r"(http://127\.0\.0\.1:(\d+))/#(\S+?)\)", line)
        if m:
            return p, m.group(1), m.group(3)
    p.kill()
    raise SystemExit("setup did not start")


def call(base, token, path, body=None, headers=None):
    h = {"X-LLMOS-Token": token}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def job(base, token):
    phases = []
    for _ in range(600):
        _, st = call(base, token, "/api/progress")
        if not phases or phases[-1] != st["phase"]:
            phases.append(st["phase"])
        if st["phase"] in ("done", "error", "cancelled"):
            return st, phases
        time.sleep(0.1)
    return st, phases


def device_head(n):
    fd = os.open(raw, os.O_RDONLY)
    try:
        return os.pread(fd, S._aligned(n), 0)[:n]
    finally:
        os.close(fd)


try:
    # a damaged image is refused before the device is touched
    with open(os.path.join(files, "SHA256SUMS"), "w") as f:
        f.write(f"{'0' * 64}  {S.USB_IMAGE}\n")
    p, base, token = server({})
    _, st = call(base, token, "/api/status")
    check(st["host"]["os"] == "mac" and st["version"] == "9.9.9", "status answers (this Mac, the folder's version)")
    code, r = call(base, token, "/api/write", {"drive": "test"})
    st, phases = job(base, token)
    check(st["phase"] == "error" and "damaged" in st["error"], f"a damaged image is refused ({st['error'][:60]}…)")
    check(device_head(4096) == bytes(4096), "…and the device was not touched")
    p.kill()

    # the real thing
    with open(os.path.join(files, "SHA256SUMS"), "w") as f:
        f.write(f"{isha}  {S.USB_IMAGE}\n")
    p, base, token = server({})
    code, r = call(base, token, "/api/write", {"drive": "nope"})
    check(not r.get("ok") and "isn't connected" in r.get("error", ""), "a drive that isn't listed can't be written")
    code, r = call(base, token, "/api/write", {"drive": "test"})
    check(r.get("ok"), "the write starts")
    st, phases = job(base, token)
    check(st["phase"] == "done", f"the job finishes (phases: {' > '.join(phases)})")
    check(device_head(isz) == open(img, "rb").read(), "the raw device holds the image byte for byte")
    code, _ = call(base, "wrong-token", "/api/write", {"drive": "test"})
    check(code == 403, "a request without the launch token is refused")
    code, _ = call(base, token, "/api/status", headers={"Host": "evil.example:80"})
    check(code == 403, "a request for another host name is refused (DNS rebinding)")
    code, _ = call(base, token, "/api/status", headers={"Origin": "http://evil.example"})
    check(code == 403, "a request from another site is refused")
    p.kill()

    # a cancelled password prompt writes nothing
    fd = os.open(raw, os.O_RDWR)
    os.pwrite(fd, bytes(S.CHUNK), 0)
    os.close(fd)
    p, base, token = server({"FAKE_AUTHOPEN": "cancel"})
    call(base, token, "/api/write", {"drive": "test"})
    st, phases = job(base, token)
    check(st["phase"] == "cancelled", "a cancelled password prompt ends as cancelled")
    check(device_head(4096) == bytes(4096), "…and nothing was written")
    p.kill()
finally:
    subprocess.run(["hdiutil", "detach", ram, "-quiet"])

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
