#!/usr/bin/env python3
"""Host-side test of the installer's one irreversible step: which partition it formats when installing next
to another system. The disk is simulated (sfdisk's JSON and the commands are stubbed); nothing touches a real
disk. Partition numbers can have gaps (one was deleted to make room), so the new partition must be found by
where it starts, never as "count + 1". Run: python3 tools/test-installer.py (no VM)"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import installer  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Stop(Exception):
    pass


GB = 1024 ** 3 // 512
ESP = installer.ESP_GUID
WIN = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
before = {"label": "gpt", "sector": 512, "last": 200 * GB, "first": 2048, "parts": [
    {"node": "/dev/sda1", "start": 2048, "size": 1024 * 512, "type": ESP, "name": "EFI"},
    {"node": "/dev/sda2", "start": 1050624, "size": 60 * GB, "type": WIN, "name": "Windows"},
    # partition 3 was deleted to make room; partition 4 (Windows recovery) sits at the end of the disk
    {"node": "/dev/sda4", "start": 190 * GB, "size": 5 * GB, "type": WIN, "name": "Recovery"}]}


def simulate(new_parts):
    """Run installer.run() on the simulated disk; return the node mkfs.ext4 was pointed at (or the error)."""
    state = {"appended": False, "formatted": None}

    def fake_layout(dev):
        if not state["appended"]:
            return before
        return dict(before, parts=before["parts"] + new_parts(state["script"]))

    def fake_sh(cmd, check=True, input=None, timeout=3600):
        if cmd[:3] == ["sfdisk", "-q", "--append"]:
            state["appended"], state["script"] = True, input
            return ""
        if cmd[0] == "mkfs.ext4":
            state["formatted"] = cmd[-1]
            raise Stop()
        return ""

    installer.layout, installer._sh = fake_layout, fake_sh
    installer._wait_node = lambda node: None
    installer.subprocess.run = lambda *a, **k: None
    installer.os.makedirs = lambda *a, **k: None
    tok = "t1"
    installer._plans[tok] = {"mode": "alongside", "disk": "/dev/sda", "start": 62 * GB, "size": 100 * GB, "esp": "/dev/sda1",
                             "need_esp": False, "need_biosboot": False, "arch": "x86_64", "uefi": True, "apple": False, "others": []}
    try:
        installer.run(tok)
    except Stop:
        return state["formatted"]
    except installer.InstallError as e:
        return f"refused: {e}"
    return None


def start_of(script):
    return int(script.strip().splitlines()[-1].split("start=")[1].split(",")[0])


got = simulate(lambda script: [{"node": "/dev/sda3", "start": start_of(script), "size": 100 * GB, "type": installer.LINUX_GUID, "name": "llmos"}])
check(got == "/dev/sda3", f"gap at 3: the new partition (3) is formatted, never the recovery partition 4 -> {got}")
got = simulate(lambda script: [{"node": "/dev/sda5", "start": start_of(script), "size": 100 * GB, "type": installer.LINUX_GUID, "name": "llmos"}])
check(got == "/dev/sda5", f"numbered after the last: partition 5 is formatted -> {got}")
got = simulate(lambda script: [])
check(str(got).startswith("refused"), f"new partition not found: nothing is formatted -> {got}")
got = simulate(lambda script: [{"node": "/dev/sda4", "start": start_of(script), "size": 1, "type": WIN, "name": "?"}])
check(str(got).startswith("refused"), f"a node that already existed is never formatted -> {got}")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
