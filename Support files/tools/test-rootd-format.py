#!/usr/bin/env python3
"""Tests for erasing a USB drive: system._format_root / system.format_drive, rootd's format_drive verb, and tools.format_drive.

subprocess.run, shutil.which, time.sleep, os.stat (for the fake device nodes), the rootd client, the mount table
(PROC_MOUNTS) and the sysfs block folder (SYS_BLOCK) are replaced. No umount, wipefs, sfdisk or mkfs runs for real,
and no VM is touched.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import types

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import rootd, rootd_client, syspanels, system, tools  # noqa: E402

rootd.LOG_PATH = os.path.join(tempfile.mkdtemp(prefix="rootd-format-test-"), "rootd.log")
mount_table_dir = tempfile.mkdtemp(prefix="rootd-format-mounts-")
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"ok {label}")
    else:
        failures.append(label)
        print(f"FAIL {label} {detail}")


# ---- fakes -------------------------------------------------------------------
FAKE_MODES = {name: stat.S_IFBLK for name in (
    "/dev/sda", "/dev/sda2", "/dev/sdb", "/dev/sdb1", "/dev/sdc", "/dev/sdd", "/dev/nvme0n1", "/dev/sde1")}
FAKE_MODES["/dev/sde1"] = stat.S_IFREG  # a regular file where a device node would be
real_stat = os.stat


def fake_stat(path, *a, **k):
    if isinstance(path, str) and path in FAKE_MODES:
        return types.SimpleNamespace(st_mode=FAKE_MODES[path] | 0o660)
    return real_stat(path, *a, **k)


class FakeProc:
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err


run_calls = []
run_fail = {}  # argv[0] -> (rc, err) for a step that should fail


def fake_run(argv, **kw):
    run_calls.append((list(argv), kw))
    rc, err = run_fail.get(argv[0], (0, ""))
    return FakeProc(rc, "", err)


rootd_calls = []
rootd_reply = {"value": None, "raise": None}
uid = {"value": 0}
real_call = rootd_client.call


def fake_rootd_call(verb, _timeout=None, **args):
    if uid["value"] == 0:
        return real_call(verb, _timeout, **args)
    rootd_calls.append((verb, _timeout, args))
    if rootd_reply["raise"]:
        raise rootd_reply["raise"]
    return rootd_reply["value"]


def fake_which(name, *a, **k):
    return {"mkfs.exfat": "/usr/sbin/mkfs.exfat"}.get(name)


def set_mounts(text):
    path = os.path.join(mount_table_dir, "mounts")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    rootd.PROC_MOUNTS = path


# sysfs: sdb and sdd are removable (sdd through a USB path), sda is marked removable only so the system-disk
# refusal is what stops it, sdc and nvme0n1 are internal.
sys_block = tempfile.mkdtemp(prefix="sysblock-")
usb_path = os.path.join(tempfile.mkdtemp(prefix="sysdev-"), "usb1", "3-1", "sdd")
os.makedirs(usb_path)
for name, flag in (("sda", "1"), ("sdb", "1"), ("sdc", "0"), ("nvme0n1", "0")):
    os.makedirs(os.path.join(sys_block, name))
    with open(os.path.join(sys_block, name, "removable"), "w") as f:
        f.write(flag + "\n")
os.symlink(usb_path, os.path.join(sys_block, "sdd"))
rootd.SYS_BLOCK = sys_block

DEFAULT_MOUNTS = "/dev/sda2 / ext4 rw,relatime 0 0\nproc /proc proc rw 0 0\n"
set_mounts(DEFAULT_MOUNTS + "/dev/sdb1 /media/usb1 vfat rw 0 0\n")

# Patch the process-wide functions the code under test calls, and restore them at the end.
real_run = subprocess.run
real_which = system.shutil.which
real_geteuid = os.geteuid
real_sleep = system.time.sleep
subprocess.run = fake_run
system.shutil.which = fake_which
os.stat = fake_stat
system.time = types.SimpleNamespace(sleep=lambda s: None)
rootd_client.call = fake_rootd_call
os.geteuid = lambda: uid["value"]

try:
    # ---- 1. root path: the argv sequence, the script on stdin, no shell ------
    del run_calls[:]
    uid["value"] = 0
    rc, out, err = system.format_drive("/dev/sdb", "USB")
    check("root: format succeeds", (rc, out, err) == (0, "", ""), (rc, out, err))
    argvs = [c[0] for c in run_calls]
    check("root: steps in order, argv lists only",
          argvs == [["umount", "/media/usb1"], ["wipefs", "-a", "/dev/sdb"], ["sfdisk", "-q", "/dev/sdb"],
                    ["/usr/sbin/mkfs.exfat", "-L", "USB", "/dev/sdb1"]], argvs)
    check("root: no shell anywhere", all(a[0] != "sh" and "sh" not in a for a in argvs), argvs)
    sfdisk_kw = run_calls[2][1]
    check("root: sfdisk gets the partition script on stdin", sfdisk_kw.get("input") == "label: dos\n,,7\n", sfdisk_kw)
    check("root: timeouts are 60 / 60 / 60 / 600",
          [c[1].get("timeout") for c in run_calls] == [60, 60, 60, 600], [c[1].get("timeout") for c in run_calls])

    # A failing step stops the sequence and its error is returned.
    del run_calls[:]
    run_fail["sfdisk"] = (1, "sfdisk: bad table\n")
    rc, out, err = system.format_drive("/dev/sdb", "USB")
    check("root: first failing step is returned", (rc, err) == (1, "sfdisk: bad table\n"), (rc, err))
    check("root: mkfs is not run after a failed step", not any(c[0][0].endswith("mkfs.exfat") for c in run_calls),
          [c[0] for c in run_calls])
    run_fail.clear()

    # No mkfs program: nothing is unmounted or wiped.
    del run_calls[:]
    system.shutil.which = lambda name, *a, **k: None
    rc, out, err = system._format_root("/dev/sdb", "USB")
    system.shutil.which = fake_which
    check("root: missing mkfs refuses before wiping", rc == 127 and run_calls == [], (rc, run_calls))

    # ---- 2. non-root: the request goes to rootd -----------------------------
    uid["value"] = 1000
    del rootd_calls[:]
    rootd_reply["value"] = json.dumps([0, "", ""])
    rc, out, err = system.format_drive("/dev/sdb", "USB")
    check("non-root: sends format_drive to rootd with a 900 s wait",
          rootd_calls == [("format_drive", 900, {"disk": "/dev/sdb", "label": "USB"})], rootd_calls)
    check("non-root: rootd's reply comes back", (rc, out, err) == (0, "", ""), (rc, out, err))
    rootd_reply["raise"] = rootd_client.RootdError("the system helper did not answer")
    rc, out, err = system.format_drive("/dev/sdb", "USB")
    check("non-root: a refused request is (1, '', message)", (rc, out, err) == (1, "", "the system helper did not answer"),
          (rc, out, err))
    rootd_reply["raise"] = None
    uid["value"] = 0

    # ---- 3. the verb accepts a removable whole disk and refuses the adversarial set
    del run_calls[:]
    reply = rootd._run(json.dumps({"verb": "format_drive", "args": {"disk": "/dev/sdd", "label": "STICK"}}).encode())[1]
    check("verb: USB disk through sysfs path is accepted", reply.get("ok") is True and json.loads(reply["out"])[0] == 0,
          reply)
    check("verb: accepted disk runs the steps (no partition mounted, so no umount)",
          [c[0] for c in run_calls] == [["wipefs", "-a", "/dev/sdd"], ["sfdisk", "-q", "/dev/sdd"],
                                        ["/usr/sbin/mkfs.exfat", "-L", "STICK", "/dev/sdd1"]], run_calls)

    adversarial = [
        ("system disk: /dev/sda with root on sda2", {"disk": "/dev/sda", "label": "USB"}),
        ("partition: /dev/sdb1", {"disk": "/dev/sdb1", "label": "USB"}),
        ("shell injection in disk: /dev/sdb;x", {"disk": "/dev/sdb;x", "label": "USB"}),
        ("internal disk: /dev/sdc", {"disk": "/dev/sdc", "label": "USB"}),
        ("internal nvme: /dev/nvme0n1", {"disk": "/dev/nvme0n1", "label": "USB"}),
        ("label with shell text: x;rm", {"disk": "/dev/sdb", "label": "x;rm"}),
        ("label of 12 characters", {"disk": "/dev/sdb", "label": "ABCDEFGHIJKL"}),
        ("empty label", {"disk": "/dev/sdb", "label": ""}),
        ("extra argument", {"disk": "/dev/sdb", "label": "USB", "force": True}),
        ("missing label", {"disk": "/dev/sdb"}),
        ("regular file where a disk is", {"disk": "/dev/sde1", "label": "USB"}),
    ]
    for name, args in adversarial:
        del run_calls[:]
        reply = rootd._run(json.dumps({"verb": "format_drive", "args": args}).encode())[1]
        check(f"verb refuses {name}", reply.get("ok") is False and not run_calls, reply)
    check("verb is registered", rootd.VERBS.get("format_drive") is rootd.format_drive)

    # ---- 4. tools.format_drive: calls system.format_drive and keeps its replies
    calls = []
    scripted = {"result": (0, "", "")}

    def fake_system_format(disk, label):
        calls.append((disk, label))
        return scripted["result"]

    real_system_format = system.format_drive
    system.format_drive = fake_system_format
    real_removable = syspanels.removable
    syspanels.removable = lambda: [{"path": "/dev/sdb1", "disk": "/dev/sdb", "mountpoint": "/media/usb1"}]
    try:
        ok_reply = tools.format_drive({"name": "my:stick!!name-long"}, None)
        check("tool: calls system.format_drive with the sanitised label", calls == [("/dev/sdb", "mystickname")], calls)
        check("tool: success reply kept",
              ok_reply.startswith("the drive is empty and ready, named mystickname"), ok_reply)
        scripted["result"] = (1, "", "boom\n")
        check("tool: failure reply kept", tools.format_drive({}, None) == "could not format it: boom",
              tools.format_drive({}, None))
        syspanels.removable = lambda: []
        del calls[:]
        check("tool: no drive reply kept", tools.format_drive({}, None) == "no USB stick or drive is plugged in")
        check("tool: no drive calls nothing", calls == [], calls)
        syspanels.removable = lambda: [{"path": "/dev/sdb1", "disk": "/dev/sdb", "mountpoint": ""}]
        system.shutil.which = lambda name, *a, **k: None
        del calls[:]
        check("tool: missing program reply kept",
              tools.format_drive({}, None) == "the formatting program is missing (say 'install exfatprogs')")
        check("tool: missing program calls nothing", calls == [], calls)
        system.shutil.which = fake_which
    finally:
        system.format_drive = real_system_format
        syspanels.removable = real_removable
        system.shutil.which = fake_which
    import inspect
    src = inspect.getsource(tools.format_drive)
    check("tool: no subprocess in the body", "subprocess" not in src and "sfdisk" not in src, src)
finally:
    subprocess.run = real_run
    system.shutil.which = real_which
    os.stat = real_stat
    system.time = types.SimpleNamespace(sleep=real_sleep)
    rootd_client.call = real_call
    os.geteuid = real_geteuid

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
