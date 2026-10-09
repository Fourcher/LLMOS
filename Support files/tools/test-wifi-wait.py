#!/usr/bin/env python3
"""Host-side unit test for wifi_connect's address wait: it polls for the address every 0.25 s
(up to 8 s) and stops as soon as one appears, instead of sleeping a fixed 4 s.
Run: python3 tools/test-wifi-wait.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools

FAILS = []


def check(cond, msg):
    if cond:
        print("ok " + msg)
    else:
        print("FAIL " + msg)
        FAILS.append(msg)


ip_calls = {"n": 0}
sleeps = []


def fake_run(argv, *args, **kwargs):
    if argv and argv[0] == "iwctl":
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    if argv and argv[0] == "ip":
        ip_calls["n"] += 1
        out = ""
        if ip_calls["n"] >= 3:
            out = "3: wlan0    inet 192.168.1.7/24 brd 192.168.1.255 scope global wlan0"
        return SimpleNamespace(returncode=0, stdout=out, stderr="")
    raise AssertionError(f"unexpected command {argv}")


def fake_sleep(seconds):
    sleeps.append(seconds)


connect = tools.REGISTRY["wifi_connect"].fn

with patch.object(tools, "_wifi_device", lambda: "wlan0"), \
        patch.object(tools.subprocess, "run", fake_run), \
        patch.object(tools.time, "sleep", fake_sleep):
    result = connect({"ssid": "HomeNet", "password": "x"}, None)

print(result)
check("address 192.168.1.7/24" in result, "the address is reported once it appears")
check(ip_calls["n"] == 3, f"the address is polled until it shows up (ip calls: {ip_calls['n']})")
check(sum(sleeps) < 1.0, f"the wait stays under 1 s (slept {sum(sleeps)} s in {len(sleeps)} steps)")

if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("all good")
