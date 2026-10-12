#!/usr/bin/env python3
"""Tests for the drive fallback path: system.mount_dev / umount_mp, rootd's mount_dev and umount_mp verbs, and syspanels' callers.

mount, umount and udisksctl are never run for real: subprocess.run, os.makedirs, os.stat (for the fake device
nodes), the rootd client and the mount table (PROC_MOUNTS) are replaced. Nothing is mounted, nothing is created.
"""
import ast
import json
import os
import stat
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.abspath(os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos"))

# Load the real package files under the name "llmos" so their relative imports work.
pkg = types.ModuleType("llmos")
pkg.__path__ = [PKG_DIR]
sys.modules["llmos"] = pkg
version_line = types.ModuleType("llmos.version_line")
version_line.version_line = lambda: "test"
sys.modules["llmos.version_line"] = version_line
pkg.version_line = version_line
from llmos import rootd, rootd_client, syspanels, system  # noqa: E402

rootd.LOG_PATH = os.path.join(tempfile.mkdtemp(prefix="rootd-drives-test-"), "rootd.log")
mount_table_dir = tempfile.mkdtemp(prefix="rootd-drives-mounts-")

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"ok {label}")
    else:
        failures.append(label)
        print(f"FAIL {label} {detail}")


# ---- fakes -------------------------------------------------------------------
# Fake device nodes: block devices, and one regular file that sits where a device name would be.
FAKE_MODES = {
    "/dev/sdb1": stat.S_IFBLK,
    "/dev/sdb2": stat.S_IFBLK,
    "/dev/sda2": stat.S_IFBLK,
    "/dev/nvme0n1p1": stat.S_IFBLK,
    "/dev/mmcblk0p1": stat.S_IFBLK,
    "/dev/sdc1": stat.S_IFREG,
}
real_stat = os.stat


def fake_stat(path, *a, **k):
    if isinstance(path, str) and path in FAKE_MODES:
        return types.SimpleNamespace(st_mode=FAKE_MODES[path] | 0o660)
    return real_stat(path, *a, **k)


class FakeProc:
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err


run_calls = []
run_result = {"rc": 0, "out": "", "err": "", "raise": None}


def fake_run(argv, **kw):
    run_calls.append((list(argv), kw))
    if run_result["raise"]:
        raise run_result["raise"]
    return FakeProc(run_result["rc"], run_result["out"], run_result["err"])


makedirs_calls = []


def fake_makedirs(path, *a, **k):
    makedirs_calls.append(path)


rootd_calls = []
rootd_reply = {"value": None, "raise": None}


def fake_rootd_call(verb, _timeout=None, **args):
    if uid["value"] == 0:
        # Root runs the real in-process verb (the same checks), so only subprocess and makedirs are faked.
        return real_call(verb, _timeout, **args)
    rootd_calls.append((verb, _timeout, args))
    if rootd_reply["raise"]:
        raise rootd_reply["raise"]
    return rootd_reply["value"]


uid = {"value": 0}
real_run = subprocess.run
real_makedirs = os.makedirs
real_geteuid = os.geteuid
real_call = rootd_client.call
real_which = system.shutil.which
real_proc_mounts = rootd.PROC_MOUNTS


def set_mounts(text, name):
    path = os.path.join(mount_table_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    rootd.PROC_MOUNTS = path


# Default table: the system disk on sda2, a stick already mounted at /media/usb2 from sdb2.
DEFAULT_MOUNTS = ("/dev/sda2 / ext4 rw,relatime 0 0\n"
                  "proc /proc proc rw 0 0\n"
                  "/dev/sdb2 /media/usb2 vfat rw 0 0\n")
set_mounts(DEFAULT_MOUNTS, "default")


def reset():
    del run_calls[:]
    del rootd_calls[:]
    del makedirs_calls[:]
    run_result.update({"rc": 0, "out": "", "err": "", "raise": None})
    rootd_reply.update({"value": None, "raise": None})


def as_uid(n):
    uid["value"] = n
    os.geteuid = lambda: n


os.stat = fake_stat
subprocess.run = fake_run
os.makedirs = fake_makedirs
rootd_client.call = fake_rootd_call


def verb(name, args):
    return json.loads(rootd.handle(json.dumps({"verb": name, "args": args}).encode()))


try:
    # ---- 1. root path: argv, timeout, mount folder --------------------------
    as_uid(0)
    reset()
    r = system.mount_dev("/dev/sdb1")
    check("root mount argv", run_calls and run_calls[-1][0] == ["mount", "/dev/sdb1", "/media/sdb1"], run_calls)
    check("root mount timeout 30", run_calls and run_calls[-1][1].get("timeout") == 30, run_calls)
    check("root mount makes /media/sdb1", makedirs_calls == ["/media/sdb1"], makedirs_calls)
    check("root mount returns (0,'','')", r == (0, "", ""), r)
    check("root mount runs no udisksctl", not any(c[0][0] == "udisksctl" for c in run_calls), run_calls)

    run_result["raise"] = subprocess.TimeoutExpired(cmd="mount", timeout=30)
    r = system.mount_dev("/dev/sdb1")
    check("root mount timeout -> 124", r == (124, "", "timed out after 30 s"), r)
    run_result["raise"] = None

    run_result.update(rc=32, out="", err="mount: bad fs")
    r = system.mount_dev("/dev/sdb1")
    check("root mount nonzero rc passed through", r == (32, "", "mount: bad fs"), r)
    run_result.update(rc=0, err="")

    reset()
    r = system.umount_mp("/media/usb2")
    check("root umount argv", run_calls and run_calls[-1][0] == ["umount", "/media/usb2"], run_calls)
    check("root umount timeout 30", run_calls and run_calls[-1][1].get("timeout") == 30, run_calls)
    check("root umount returns (0,'','')", r == (0, "", ""), r)

    run_result["raise"] = subprocess.TimeoutExpired(cmd="umount", timeout=30)
    r = system.umount_mp("/media/usb2")
    check("root umount timeout -> 124", r == (124, "", "timed out after 30 s"), r)
    run_result["raise"] = None

    # ---- 2. non-root path: rootd call args ----------------------------------
    as_uid(1000)
    reset()
    rootd_reply.update(value=json.dumps([0, "x", "y"]))
    r = system.mount_dev("/dev/sdb1")
    check("non-root mount call verb and args", rootd_calls == [("mount_dev", 40, {"dev": "/dev/sdb1"})], rootd_calls)
    check("non-root mount returns rootd tuple", r == (0, "x", "y"), r)
    check("non-root mount never runs mount", run_calls == [] and makedirs_calls == [], (run_calls, makedirs_calls))

    reset()
    rootd_reply.update(value=json.dumps([0, "", ""]))
    system.umount_mp("/media/usb2")
    check("non-root umount call verb and args", rootd_calls == [("umount_mp", 40, {"mountpoint": "/media/usb2"})], rootd_calls)
    check("non-root umount never runs umount", run_calls == [], run_calls)

    reset()
    rootd_reply.update(value=None, **{"raise": rootd_client.RootdError("boom")})
    r = system.mount_dev("/dev/sdb1")
    check("mount refused by rootd -> (1,'','')", r == (1, "", ""), r)
    r = system.umount_mp("/media/usb2")
    check("umount refused by rootd -> (1,'','boom')", r == (1, "", "boom"), r)
    rootd_reply.update(**{"raise": None})

    # ---- 3. public helpers reject bad input before rootd is called ----------
    reset()
    for dev in ("/dev/sda", "/dev/sda1;x", "/dev/../etc/passwd", "/dev/mapper/root", "/dev/sdb1\n", "", None, 5):
        try:
            system.mount_dev(dev)
            check(f"public mount_dev {dev!r} rejected", False, "accepted")
        except ValueError:
            check(f"public mount_dev {dev!r} rejected", True)
    for mp in ("/etc", "/media/../etc", "/media/a b", "/media/.", "/media/..", "/media/", "/media/usb2\n", "/media/sdb1/x", None):
        r = system.umount_mp(mp)
        check(f"public umount_mp {mp!r} refused", r[0] == 1 and r[1] == "", r)
    check("bad input never reaches rootd or subprocess", rootd_calls == [] and run_calls == [], (rootd_calls, run_calls))

    # ---- 4. rootd mount_dev verb: accepted good call -------------------------
    as_uid(0)
    reset()
    reply = verb("mount_dev", {"dev": "/dev/sdb1"})
    check("verb good mount ok", reply.get("ok") is True, reply)
    check("verb good mount argv", run_calls and run_calls[-1][0] == ["mount", "/dev/sdb1", "/media/sdb1"], run_calls)
    check("verb good mount reply is [rc,out,err]", json.loads(reply.get("out", "null")) == [0, "", ""], reply)

    for dev in ("/dev/nvme0n1p1", "/dev/mmcblk0p1"):
        reset()
        reply = verb("mount_dev", {"dev": dev})
        base = os.path.basename(dev)
        check(f"verb accepts {dev}", reply.get("ok") is True and run_calls[-1][0] == ["mount", dev, f"/media/{base}"], (reply, run_calls))

    # ---- 5. rootd mount_dev verb: adversarial inputs rejected ---------------
    bad_dev = [
        "/dev/sda",                      # no partition number
        "/dev/sda1;x",                   # shell metacharacters
        "/dev/../etc/passwd",            # traversal
        "/dev/mapper/root",              # not a partition node we allow
        "/dev/sdb1\n",                   # trailing newline (fullmatch, not $)
        "/dev/sdd1",                     # does not exist (stat fails)
        "/dev/sdc1",                     # a regular file, not a block device
        "/dev/sda2",                     # the root filesystem device
        "/dev/sdb2",                     # already mounted at /media/usb2
        "-o",                            # looks like an option
        "",
        None,
        5,
        ["/dev/sdb1"],
    ]
    for dev in bad_dev:
        reset()
        reply = verb("mount_dev", {"dev": dev})
        check(f"verb rejects dev {dev!r}", reply.get("ok") is False and "Traceback" not in reply.get("error", ""), reply)
        check(f"verb dev {dev!r} runs nothing", run_calls == [] and makedirs_calls == [], (run_calls, makedirs_calls))

    reset()
    reply = verb("mount_dev", {"dev": "/dev/sdb1", "mountpoint": "/etc"})
    check("verb rejects extra mountpoint arg", reply.get("ok") is False and "unexpected" in reply.get("error", ""), reply)
    reply = verb("mount_dev", {"dev": "/dev/sdb1", "argv": ["sh"]})
    check("verb rejects extra argv arg", reply.get("ok") is False, reply)
    reply = verb("mount_dev", {})
    check("verb rejects missing dev", reply.get("ok") is False, reply)
    check("verb rejects never run anything", run_calls == [] and makedirs_calls == [], (run_calls, makedirs_calls))

    # A stick already mounted somewhere else, or the /media folder in use: refused.
    set_mounts(DEFAULT_MOUNTS + "/dev/sdx9 /media/sdb1 vfat rw 0 0\n", "mp-in-use")
    reset()
    reply = verb("mount_dev", {"dev": "/dev/sdb1"})
    check("verb refuses when /media/sdb1 is in use", reply.get("ok") is False and run_calls == [], reply)
    set_mounts(DEFAULT_MOUNTS, "default")

    # ---- 6. rootd umount_mp verb: good and adversarial ----------------------
    reset()
    reply = verb("umount_mp", {"mountpoint": "/media/usb2"})
    check("verb good umount ok", reply.get("ok") is True and run_calls[-1][0] == ["umount", "/media/usb2"], (reply, run_calls))

    for mp in ("/etc", "/media/../etc", "/media/a b", "/media/.", "/media/..", "/media/",
               "/media/usb2/x", "/media/usb2\n", "/media/" + "a" * 65, "/media/nothere", "/tmp/usb2", "", None, 5):
        reset()
        reply = verb("umount_mp", {"mountpoint": mp})
        check(f"verb rejects mountpoint {mp!r}", reply.get("ok") is False and "Traceback" not in reply.get("error", ""), reply)
        check(f"verb mountpoint {mp!r} runs nothing", run_calls == [], run_calls)

    reset()
    reply = verb("umount_mp", {"mountpoint": "/media/usb2", "dev": "/dev/sdb2"})
    check("verb rejects extra dev arg on umount", reply.get("ok") is False and run_calls == [], reply)
    reply = verb("umount_mp", {})
    check("verb rejects missing mountpoint", reply.get("ok") is False and run_calls == [], reply)

    # ---- 7. syspanels: udisksctl first, fallback through system ------------
    as_uid(1000)
    system.shutil.which = lambda name: "/usr/bin/" + name

    reset()
    run_result.update(rc=0, out="Mounted /dev/sdb1 at /media/sdb1.", err="")
    r = syspanels.mount("/dev/sdb1")
    check("syspanels tries udisksctl first", run_calls and run_calls[0][0][0] == "udisksctl", run_calls)
    check("syspanels udisks success -> no fallback", r == (True, "/media/sdb1") and rootd_calls == [], (r, rootd_calls))

    reset()
    run_result.update(rc=1, out="", err="udisks failed")
    rootd_reply.update(value=json.dumps([0, "", ""]))
    r = syspanels.mount("/dev/sdb1")
    check("syspanels fallback after udisks failure", run_calls[0][0][0] == "udisksctl", run_calls)
    check("syspanels fallback calls mount_dev with dev only", rootd_calls == [("mount_dev", 40, {"dev": "/dev/sdb1"})], rootd_calls)
    check("syspanels fallback reply", r == (True, "/media/sdb1"), r)
    check("syspanels never runs mount itself", not any(c[0][0] == "mount" for c in run_calls), run_calls)

    reset()
    run_result.update(rc=1, out="", err="udisks failed")
    rootd_reply.update(value=None, **{"raise": rootd_client.RootdError("bad args: dev")})
    r = syspanels.mount("/dev/sdb1")
    check("syspanels refused -> could not open the drive", r == (False, "could not open the drive"), r)
    rootd_reply.update(**{"raise": None})

    reset()
    run_result.update(rc=1, out="", err="udisks failed")
    rootd_reply.update(value=None, **{"raise": rootd_client.RootdError("x")})
    r = syspanels.mount("/dev/sda")
    check("syspanels bad drive name -> could not open the drive", r == (False, "could not open the drive"), r)
    system.shutil.which = real_which
    run_result.update(rc=0, out="", err="")

    # ---- 8. syspanels source: no direct mount or umount left -------------
    sp_src = open(os.path.join(PKG_DIR, "syspanels.py"), encoding="utf-8").read()
    tree = ast.parse(sp_src)
    heads = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_run"
                and n.args and isinstance(n.args[0], ast.List) and n.args[0].elts
                and isinstance(n.args[0].elts[0], ast.Constant)):
            heads.add(n.args[0].elts[0].value)
    heads = sorted(heads)
    check("syspanels runs no literal mount or umount", "mount" not in heads and "umount" not in heads, heads)
    check("syspanels keeps udisksctl and sync calls", {"udisksctl", "sync"} <= set(heads), heads)
    check("syspanels keeps fuser check", '"fuser"' in sp_src)
    check("syspanels calls system.mount_dev and system.umount_mp",
          "system.mount_dev(" in sp_src and "system.umount_mp(" in sp_src)
    check("syspanels keeps udisks power-off", '"power-off"' in sp_src)

finally:
    subprocess.run = real_run
    os.makedirs = real_makedirs
    os.geteuid = real_geteuid
    os.stat = real_stat
    rootd_client.call = real_call
    rootd.PROC_MOUNTS = real_proc_mounts
    system.shutil.which = real_which

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
