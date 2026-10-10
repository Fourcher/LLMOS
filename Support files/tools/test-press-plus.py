#!/usr/bin/env python3
"""Host test for control.press(): the plus key ("+", "ctrl++", "ctrl+shift++") and minus ("ctrl+-") are pressed,
and an empty spec presses nothing and returns False. The command runner is patched to record argv; no key is sent.

Run: python3 tools/test-press-plus.py
"""
import os
import subprocess
import sys
from unittest.mock import patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import control  # noqa: E402

FAILS = []


def run_press(spec):
    calls = []

    def fake_run(argv, timeout=20, text=True):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    with patch.object(control, "_run", side_effect=fake_run), patch.object(control.time, "sleep", lambda s: None):
        ok, err = control.press(spec)
    return ok, calls


def check(spec, expected_argv):
    ok, calls = run_press(spec)
    if calls == [expected_argv] and ok is True:
        print(f"ok {spec!r} -> {' '.join(expected_argv)}")
    else:
        FAILS.append(spec)
        print(f"FAIL {spec!r}: ok={ok} calls={calls} expected={[expected_argv]}")


check("+", ["wtype", "-k", "plus"])
check("ctrl++", ["wtype", "-M", "ctrl", "-k", "plus", "-m", "ctrl"])
check("ctrl+shift++", ["wtype", "-M", "ctrl", "-M", "shift", "-k", "plus", "-m", "shift", "-m", "ctrl"])
check("ctrl+-", ["wtype", "-M", "ctrl", "-k", "minus", "-m", "ctrl"])
check("ctrl+a", ["wtype", "-M", "ctrl", "-k", "a", "-m", "ctrl"])
check("a", ["wtype", "-k", "a"])

ok, calls = run_press("")
if ok is False and calls == []:
    print("ok '' -> False, nothing run")
else:
    FAILS.append("")
    print(f"FAIL '': ok={ok} calls={calls}")

if FAILS:
    print("FAILED: " + ", ".join(repr(f) for f in FAILS))
    sys.exit(1)
print("all good")
