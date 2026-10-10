#!/usr/bin/env python3
"""Host-side test: the Wi-Fi scan and connect waits poll every 0.25 s instead of sleeping a fixed time.
The scan reads the network list once BEFORE starting the scan (iwd can keep showing the previous list),
so a cached list only counts as a result once it changes.
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
CHANGING = NETS.replace("Neighbour", "Neighbour2")


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
    """subprocess.run stand-in: 'scan' succeeds; get-networks returns the canned texts in order (last one repeats).
    An Exception item in the list is raised instead of returned."""
    outs = list(get_networks_outputs)

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[-1] == "scan":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        item = outs.pop(0) if len(outs) > 1 else outs[0]
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(returncode=0, stdout=item, stderr="")
    return run


def run_tools_scan(outputs):
    clk, calls = Clock(), []
    with mock.patch.object(tools, "_wifi_device", return_value="wlan0"), \
         mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep), \
         mock.patch("subprocess.run", fake_iwctl(outputs, calls)):
        result = tools.wifi_scan({}, None)
    gets = sum(1 for c in calls if c[-1] == "get-networks")
    return result, clk.t, gets, calls


def run_desk_scan(outputs):
    clk, calls = Clock(), []
    with mock.patch.object(desk, "_wifi_device", return_value="wlan0"), \
         mock.patch("time.monotonic", clk.monotonic), mock.patch("time.sleep", clk.sleep), \
         mock.patch("subprocess.run", fake_iwctl(outputs, calls)):
        nets = desk._wifi_scan()
    return nets, clk.t, calls


def order_ok(calls):
    """The list is read before the scan command, and again after it."""
    first_get = next(i for i, c in enumerate(calls) if c[-1] == "get-networks")
    scan_at = next(i for i, c in enumerate(calls) if c[-1] == "scan")
    return first_get < scan_at < len(calls) - 1


def check(name, cond, detail=""):
    if not cond:
        print("FAIL", name, detail)
        sys.exit(1)
    print("ok", name)


# A. no cached list before the scan (before = ""): results appear on poll 2 (t=0.25), unchanged on poll 3 (t=0.5)
result, elapsed, gets, calls = run_tools_scan(["", "", NETS, NETS])
check("A tools: no cache, stable on poll 3 -> returns at ~0.5 s",
      abs(elapsed - 0.5) < 1e-9 and gets == 4 and "HomeWifi" in result and order_ok(calls),
      f"elapsed={elapsed} gets={gets} result={result!r}")

# B. no cache, list still changing: keep polling until it settles (poll 4 at t=0.75)
result, elapsed, gets, calls = run_tools_scan(["", "", NETS, CHANGING, CHANGING])
check("B tools: no cache, waits while the list still changes -> ~0.75 s",
      abs(elapsed - 0.75) < 1e-9 and gets == 5, f"elapsed={elapsed} gets={gets}")

# C. no networks at all: waits the full 1.5 s limit and says nothing found, as before
result, elapsed, gets, calls = run_tools_scan(["", ""])
check("C tools: no networks -> full 1.5 s, 'nothing found'",
      abs(elapsed - 1.5) < 1e-9 and result == "nothing found", f"elapsed={elapsed} result={result!r}")

# H. cached list before the scan, and iwd keeps returning that same list: full 1.5 s, then the list is returned
result, elapsed, gets, calls = run_tools_scan([NETS])
check("H tools: cached list never changes -> full 1.5 s, returns it",
      abs(elapsed - 1.5) < 1e-9 and "HomeWifi" in result and "Neighbour" in result and order_ok(calls),
      f"elapsed={elapsed} result={result!r}")

# I. cached list before the scan; a new list appears on poll 3 (t=0.5) and is unchanged on poll 4 (t=0.75)
result, elapsed, gets, calls = run_tools_scan([NETS, NETS, NETS, CHANGING, CHANGING])
check("I tools: cached list, new list appears on poll 3 and is stable on poll 4 -> ~0.75 s",
      abs(elapsed - 0.75) < 1e-9 and "Neighbour2" in result, f"elapsed={elapsed} result={result!r}")

# J. no cache (before = ""): list ready and stable from poll 1 (t=0) and poll 2 (t=0.25) -> returns at 0.25 s
result, elapsed, gets, calls = run_tools_scan(["", NETS, NETS])
check("J tools: no cache, list stable on poll 2 -> ~0.25 s",
      0.25 - 1e-9 <= elapsed <= 0.5 + 1e-9 and "HomeWifi" in result, f"elapsed={elapsed} result={result!r}")

# K. the pre-scan read itself fails: treated as no cache, so the old rule applies
result, elapsed, gets, calls = run_tools_scan([OSError("iwctl busy"), NETS, NETS])
check("K tools: pre-scan read fails -> old rule, ~0.25 s",
      abs(elapsed - 0.25) < 1e-9 and "HomeWifi" in result, f"elapsed={elapsed} result={result!r}")

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

# 5. desk._wifi_scan: same settle logic, same parsing, same before-scan read
# D. no cache: stable on poll 2 (t=0.25) -> two networks parsed
nets, elapsed, calls = run_desk_scan(["", NETS, NETS])
check("D desk: no cache, stable on poll 2 -> ~0.25 s, parsed networks",
      [n["ssid"] for n in nets] == ["HomeWifi", "Neighbour"] and abs(elapsed - 0.25) < 1e-9 and order_ok(calls),
      f"nets={nets} t={elapsed}")

# E. cached list before the scan, never changes: full 3 s, the cached list is returned
nets, elapsed, calls = run_desk_scan([NETS])
check("E desk: cached list never changes -> full 3 s, returns it",
      [n["ssid"] for n in nets] == ["HomeWifi", "Neighbour"] and abs(elapsed - 3.0) < 1e-9 and order_ok(calls),
      f"nets={nets} t={elapsed}")

# F. cached list before the scan, new list on poll 3 and stable on poll 4 -> ~0.75 s
nets, elapsed, calls = run_desk_scan([NETS, NETS, NETS, CHANGING, CHANGING])
check("F desk: cached list, new list on poll 3, stable on poll 4 -> ~0.75 s",
      [n["ssid"] for n in nets] == ["HomeWifi", "Neighbour2"] and abs(elapsed - 0.75) < 1e-9,
      f"nets={nets} t={elapsed}")

# G. no networks at all: full 3 s, empty list
nets, elapsed, calls = run_desk_scan([""])
check("G desk: no networks -> full 3 s, empty list", nets == [] and abs(elapsed - 3.0) < 1e-9,
      f"nets={nets} t={elapsed}")

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
