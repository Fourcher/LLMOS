#!/usr/bin/env python3
"""Host-side test: the Wi-Fi scan and connect waits poll every 0.25 s instead of sleeping a fixed time.
iwctl and the clock are faked; no VM, no real Wi-Fi.
Run: python3 tools/test-wifi-scan-wait.py  (exit status 0 = pass)."""
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest import mock

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import waits, tools, desk

NETS = ("                 Available networks\n"
        "-----------------------------------------------------\n"
        "      Network name                    Security            Signal\n"
        "-----------------------------------------------------\n"
        "      HomeWifi                        psk                 ****\n"
        "      Neighbour                       psk                 **\n")


class Clock:
    """Fake time: sleep() advances monotonic time, so elapsed time is exact."""
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def fake_iwctl(get_networks_outputs, calls):
    """subprocess.run stand-in: 'scan' succeeds, get-networks returns the canned texts in order (last one repeats)."""
    outs = list(get_networks_outputs)

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[-1] == "scan":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        text = outs.pop(0) if len(outs) > 1 else outs[0]
        return SimpleNamespace(returncode=0, stdout=text, stderr="")
    return run


def run_scan(outputs):
    clk, calls = Clock(), []
    with mock.patch.object(tools, "_wifi_device", return_value="wlan0"), \
         mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep), \
         mock.patch("subprocess.run", fake_iwctl(outputs, calls)):
        result = tools.wifi_scan({}, None)
    gets = sum(1 for c in calls if c[-1] == "get-networks")
    return result, clk.t, gets


def check(name, cond, detail=""):
    if not cond:
        print("FAIL", name, detail)
        sys.exit(1)
    print("ok", name)


# 1. results appear on poll 2 (t=0.25) and are unchanged on poll 3 (t=0.5): return at ~0.5 s
result, elapsed, gets = run_scan(["", NETS, NETS, NETS])
check("scan returns at ~0.5 s when stable on poll 3", abs(elapsed - 0.5) < 1e-9 and gets == 3, f"elapsed={elapsed} gets={gets}")
check("scan result is the listed networks", "HomeWifi" in result and "Neighbour" in result, result)

# 2. list still changing: keep polling until it settles
CHANGING = NETS.replace("Neighbour", "Neighbour2")
result, elapsed, gets = run_scan(["", NETS, CHANGING, CHANGING])
check("scan waits while the list still changes", abs(elapsed - 0.75) < 1e-9 and gets == 4, f"elapsed={elapsed} gets={gets}")

# 3. no networks at all: waits the full 1.5 s limit and returns "nothing found" as before
result, elapsed, gets = run_scan([""])
check("no networks: waits the full 1.5 s and says nothing found",
      abs(elapsed - 1.5) < 1e-9 and result == "nothing found", f"elapsed={elapsed} result={result!r}")

# 4. the read helper: an exception counts as not ready, and the limit still ends the wait
clk = Clock()
calls_n = {"n": 0}

def flaky():
    calls_n["n"] += 1
    if calls_n["n"] < 3:
        raise OSError("iwctl busy")
    return ["HomeWifi"]

with mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep):
    got = waits.scan_settled(flaky, limit=3.0, step=0.25, default=[])
check("exceptions count as not ready, then a stable result is returned",
      got == ["HomeWifi"] and abs(clk.t - 0.75) < 1e-9, f"got={got} t={clk.t}")

clk = Clock()
with mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep):
    got = waits.scan_settled(lambda: (_ for _ in ()).throw(OSError("x")), limit=3.0, step=0.25, default=[])
check("always-failing read: full 3 s, returns default", got == [] and abs(clk.t - 3.0) < 1e-9, f"got={got} t={clk.t}")

# 5. desk._wifi_scan uses the same settle logic and parses the same way
clk, calls = Clock(), []
with mock.patch.object(desk, "_wifi_device", return_value="wlan0"), \
     mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep), \
     mock.patch("subprocess.run", fake_iwctl(["", NETS, NETS], calls)):
    nets = desk._wifi_scan()
check("desk scan returns parsed networks at ~0.5 s",
      [n["ssid"] for n in nets] == ["HomeWifi", "Neighbour"] and abs(clk.t - 0.5) < 1e-9,
      f"nets={nets} t={clk.t}")

clk, calls = Clock(), []
with mock.patch.object(desk, "_wifi_device", return_value="wlan0"), \
     mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep), \
     mock.patch("subprocess.run", fake_iwctl([""], calls)):
    nets = desk._wifi_scan()
check("desk scan with no networks: full 3 s, empty list", nets == [] and abs(clk.t - 3.0) < 1e-9, f"nets={nets} t={clk.t}")

# 6. _wifi_connect: 60 checks 0.25 s apart; exits as soon as _online() is true
def connect_run(cmd, **kw):
    return SimpleNamespace(returncode=0, stdout="", stderr="")

clk = Clock()
online_seq = iter([False, False, True])
with mock.patch.object(desk, "_wifi_device", return_value="wlan0"), \
     mock.patch.object(desk, "_online", side_effect=lambda: next(online_seq, True)), \
     mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep), \
     mock.patch("subprocess.run", connect_run):
    ok, msg = desk._wifi_connect("HomeWifi", "")
check("_wifi_connect exits early when _online() turns True", ok and msg == "" and abs(clk.t - 0.5) < 1e-9,
      f"ok={ok} msg={msg!r} t={clk.t}")
check("_wifi_connect step is 0.25 s", set(clk.sleeps) == {0.25}, f"sleeps={set(clk.sleeps)}")

clk = Clock()
checks = {"n": 0}

def never():
    checks["n"] += 1
    return False

with mock.patch.object(desk, "_wifi_device", return_value="wlan0"), \
     mock.patch.object(desk, "_online", side_effect=never), \
     mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep), \
     mock.patch("subprocess.run", connect_run):
    ok, msg = desk._wifi_connect("HomeWifi", "")
check("_wifi_connect never online: 60 checks over 15 s, then the old message",
      ok and msg == "connected, waiting for an address" and checks["n"] == 60 and abs(clk.t - 15.0) < 1e-9,
      f"checks={checks['n']} t={clk.t} msg={msg!r}")

print("all good")
