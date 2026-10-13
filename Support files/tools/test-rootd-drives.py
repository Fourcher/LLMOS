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
    "/dev/mmcblk0p2": stat.S_IFBLK,
    "/dev/nvme0n1p2": stat.S_IFBLK,
    "/dev/nvme0n1p5": stat.S_IFBLK,
    "/dev/sda3": stat.S_IFBLK,
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
    for mp in ("/etc", "/media/../etc", "/media/a b", "/media/.", "/media/..", "/media/", "/media/usb2\n", "/run/media", "/run/media/alice/../../etc", None):
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

    # ---- 9. /run/media drives: mount table decoding and umount_mp checks ----
    # /proc/mounts writes a space as \040. The fixture stores the escaped text, as the kernel does.
    DRIVE_MOUNTS = (DEFAULT_MOUNTS
                    + "/dev/sdb1 /run/media/alice/My\\040USB vfat rw 0 0\n"
                    + "/dev/mapper/root /media/alice/x ext4 rw 0 0\n"
                    + "/dev/sdc1 /run/media/alice/bad\\012name vfat rw 0 0\n"
                    + "/dev/sdc1 /run/media vfat rw 0 0\n"
                    + "/dev/sdc1 /media vfat rw 0 0\n"
                    + "/dev/sdd1 /run/media/alice/Dot..x vfat rw 0 0\n")
    set_mounts(DRIVE_MOUNTS, "drive")
    as_uid(0)
    reset()
    check("mount table decodes \\040 to a space",
          ("/dev/sdb1", "/run/media/alice/My USB") in rootd._mounts(), rootd._mounts())
    check("mount table decodes \\012 to a newline",
          ("/dev/sdc1", "/run/media/alice/bad\nname") in rootd._mounts(), rootd._mounts())

    reset()
    reply = verb("umount_mp", {"mountpoint": "/run/media/alice/My USB"})
    check("verb umounts /run/media/alice/My USB from /dev/sdb1",
          reply.get("ok") is True and run_calls[-1][0] == ["umount", "/run/media/alice/My USB"], (reply, run_calls))

    reset()
    reply = verb("umount_mp", {"mountpoint": "/run/media/alice/Dot..x"})
    check("verb umounts a label holding .. inside a name",
          reply.get("ok") is True and run_calls[-1][0] == ["umount", "/run/media/alice/Dot..x"], (reply, run_calls))

    adversarial_mp = [
        "/media/alice/x",                    # source is /dev/mapper/root, not a removable partition
        "/run/media/alice/../../etc",        # traversal
        "/run/media/alice/..",               # dot-dot as the label
        "/run/media/alice/.",                # dot as the label
        "/run/media",                        # bare folder
        "/media",                            # bare folder
        "/run/media/",                       # trailing slash
        "/",                                 # the system root
        "/run/media/alice/bad\nname",        # label with a newline (fullmatch, not $)
        "/run/media/alice/My\\040USB",       # the raw escaped text is not the decoded name
        "/run/media/alice/Other",            # not in the mount table
        "/run/media/alice/a/b/c",            # three levels
        "/run/media/alice/" + "a" * 65,      # label too long
        "/run/media/alice/bad_mp!",          # character outside the allowed set
    ]
    for mp in adversarial_mp:
        reset()
        reply = verb("umount_mp", {"mountpoint": mp})
        check(f"verb rejects /run/media mountpoint {mp!r}", reply.get("ok") is False and "Traceback" not in reply.get("error", ""), reply)
        check(f"verb /run/media mountpoint {mp!r} runs nothing", run_calls == [], run_calls)

    # Mounted, but the source is not a removable partition: refused, nothing run.
    reset()
    reply = verb("umount_mp", {"mountpoint": "/media/alice/x"})
    check("verb refuses /media/alice/x from /dev/mapper/root", reply.get("ok") is False and run_calls == [], reply)
    check("umount_mp refuses /media/alice/x from /dev/mapper/root", "not a drive" in reply.get("error", ""), reply)
    check("media_mp_ok accepts /run/media/alice/My USB", rootd.media_mp_ok("/run/media/alice/My USB") is True)
    check("media_mp_ok rejects /media/alice/..", rootd.media_mp_ok("/media/alice/..") is False)

    # Public helper: the same shape rule, so a valid /run/media name reaches rootd.
    as_uid(1000)
    reset()
    rootd_reply.update(value=json.dumps([0, "", ""]))
    r = system.umount_mp("/run/media/alice/My USB")
    check("public umount_mp /run/media/alice/My USB calls rootd",
          rootd_calls == [("umount_mp", 40, {"mountpoint": "/run/media/alice/My USB"})] and r == (0, "", ""), (rootd_calls, r))
    reset()
    r = system.umount_mp("/run/media/alice/../../etc")
    check("public umount_mp refuses traversal before rootd", r[0] == 1 and rootd_calls == [], (r, rootd_calls))
    rootd_reply.update(value=None)

    # ---- 10. syspanels eject: udisksctl unmount first, then system.umount_mp ----
    real_removable = syspanels.removable
    EJECT_PARTS = [{"path": "/dev/sdb1", "disk": "/dev/sdb", "mountpoint": "/run/media/alice/My USB", "label": "", "size": "", "fstype": "vfat"},
                   {"path": "/dev/sdb2", "disk": "/dev/sdb", "mountpoint": "", "label": "", "size": "", "fstype": "vfat"}]
    syspanels.removable = lambda: EJECT_PARTS
    system.shutil.which = lambda name: "/usr/bin/" + name
    try:
        as_uid(1000)
        reset()
        run_result.update(rc=0, out="", err="")
        r = syspanels.eject("/dev/sdb1")
        unmounts = [c for c in run_calls if c[0][:2] == ["udisksctl", "unmount"]]
        check("eject udisks unmount argv",
              unmounts and unmounts[0][0] == ["udisksctl", "unmount", "-b", "/dev/sdb1", "--no-user-interaction"]
              and unmounts[0][1].get("timeout") == 30, run_calls)
        check("eject udisks success -> no rootd call", rootd_calls == [], rootd_calls)
        check("eject udisks success -> safe to remove", r == (True, "safe to remove"), r)

        reset()
        run_result.update(rc=1, out="", err="udisks busy")
        rootd_reply.update(value=json.dumps([0, "", ""]))
        r = syspanels.eject("/dev/sdb1")
        check("eject falls back to umount_mp after udisks fails",
              rootd_calls == [("umount_mp", 40, {"mountpoint": "/run/media/alice/My USB"})], rootd_calls)
        check("eject fallback success -> safe to remove", r == (True, "safe to remove"), r)

        reset()
        run_result.update(rc=1, out="", err="udisks busy")
        rootd_reply.update(value=None, **{"raise": rootd_client.RootdError("bad args: mountpoint")})
        r = syspanels.eject("/dev/sdb1")
        check("eject both fail -> still in use",
              r[0] is False and r[1].startswith("still in use"), r)
        rootd_reply.update(**{"raise": None})
        run_result.update(rc=0, out="", err="")
    finally:
        syspanels.removable = real_removable
        system.shutil.which = real_which

    # ---- 11. system disk: the whole disk of the root filesystem is refused, by both verbs ----
    # The mount table is a temp file per case: root on one device, then the extra line under test.
    as_uid(0)

    def sysdisk_table(root_src, extra):
        set_mounts(f"{root_src} / ext4 rw 0 0\nproc /proc proc rw 0 0\n" + extra, "sysdisk")

    sysdisk_cases = [
        # (label, root source, extra mount line, verb, args, expect accepted)
        ("umount bind of root partition", "/dev/sda2", "/dev/sda2 /media/x ext4 rw 0 0\n", "umount_mp", {"mountpoint": "/media/x"}, False),
        ("umount other partition of root disk", "/dev/sda2", "/dev/sda3 /media/y ext4 rw 0 0\n", "umount_mp", {"mountpoint": "/media/y"}, False),
        ("umount stick on another disk", "/dev/sda2", "/dev/sdb1 /run/media/alice/USB vfat rw 0 0\n", "umount_mp", {"mountpoint": "/run/media/alice/USB"}, True),
        ("umount nvme partition of root disk", "/dev/nvme0n1p2", "/dev/nvme0n1p5 /media/z ext4 rw 0 0\n", "umount_mp", {"mountpoint": "/media/z"}, False),
        ("umount mmcblk partition of root disk", "/dev/mmcblk0p2", "/dev/mmcblk0p1 /media/boot vfat rw 0 0\n", "umount_mp", {"mountpoint": "/media/boot"}, False),
        ("umount with root source /dev/root (unknown disk)", "/dev/root", "/dev/sda2 /media/x ext4 rw 0 0\n", "umount_mp", {"mountpoint": "/media/x"}, True),
        ("umount with root source overlay (unknown disk)", "overlay", "/dev/sda2 /media/x ext4 rw 0 0\n", "umount_mp", {"mountpoint": "/media/x"}, True),
        ("mount_dev other partition of root disk", "/dev/sda2", "", "mount_dev", {"dev": "/dev/sda3"}, False),
        ("mount_dev nvme partition of root disk", "/dev/nvme0n1p2", "", "mount_dev", {"dev": "/dev/nvme0n1p5"}, False),
        ("mount_dev mmcblk partition of root disk", "/dev/mmcblk0p2", "", "mount_dev", {"dev": "/dev/mmcblk0p1"}, False),
        ("mount_dev stick on another disk", "/dev/sda2", "", "mount_dev", {"dev": "/dev/sdb1"}, True),
        ("mount_dev with root source /dev/root (unknown disk)", "/dev/root", "", "mount_dev", {"dev": "/dev/sda2"}, True),
    ]
    for label, root_src, extra, vname, vargs, accepted in sysdisk_cases:
        sysdisk_table(root_src, extra)
        reset()
        reply = verb(vname, vargs)
        if accepted:
            if vname == "umount_mp":
                ran = run_calls and run_calls[-1][0] == ["umount", vargs["mountpoint"]]
            else:
                dev = vargs["dev"]
                ran = run_calls and run_calls[-1][0] == ["mount", dev, "/media/" + os.path.basename(dev)]
            check(f"sysdisk accepts: {label}", reply.get("ok") is True and bool(ran), (reply, run_calls))
        else:
            # umount_mp says "system disk"; mount_dev keeps its existing "dev is the system disk" reply.
            want_error = "bad args: system disk" if vname == "umount_mp" else "bad args: dev is the system disk"
            check(f"sysdisk refuses: {label}",
                  reply.get("ok") is False and reply.get("error") == want_error and run_calls == [] and makedirs_calls == [],
                  (reply, run_calls, makedirs_calls))
    set_mounts(DEFAULT_MOUNTS, "default")

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
