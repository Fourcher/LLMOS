#!/usr/bin/env python3
"""launch_app (desk.py) returns as soon as the started program's window is up, instead of always waiting 3 s.
Host-side: desk.py needs GTK, so launch_app and _launch_window_up are read from its source and run against a
Desk.__new__ stub, a fake subprocess.Popen (poll() returns None / a code at chosen times) and a fake wm.windows().
Run: python3 tools/test-launch-fast.py"""
import os
import re
import sys
import tempfile
import time
import types

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
src = open(SRC, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


# the two methods, exactly as desk.py has them
block = src[src.index("    def launch_app(self, argv, name=\"\"):"):src.index("    def _reap(self, p):")]
RUN = tempfile.mkdtemp(prefix="llmos-launch-test-")
clock = {"t0": 0.0}
state = {"windows": [], "exit_at": None, "code": 0, "pop_argv": None}


class FakeProc:
    pid = 4242

    def __init__(self, argv, **kw):
        self.t0 = time.monotonic()
        state["pop_argv"] = argv

    def poll(self):
        if state["exit_at"] is not None and time.monotonic() - self.t0 >= state["exit_at"]:
            return state["code"]
        return None


def fake_windows():
    # state["windows"]: list of (app_id, appears_at_seconds or None for "already open"), relative to the launch
    out = []
    for aid, at in state["windows"]:
        if at is None or time.monotonic() - clock["t0"] >= at:
            out.append(aid)
    return out


fake_subprocess = types.SimpleNamespace(Popen=FakeProc, DEVNULL=None)
fake_wm = types.SimpleNamespace(PROCS={"firefox": "firefox", "foot": "foot", "org.xfce.mousepad": "mousepad"},
                                windows=fake_windows)
fake_config = types.SimpleNamespace(RUN=RUN, settings={}, home=lambda: "/tmp")
ns = {"os": os, "time": time, "subprocess": fake_subprocess, "threading": __import__("threading"),
      "json": __import__("json"), "config": fake_config, "wm": fake_wm, "vault": None,
      "_root_ok": lambda a: a}
exec("class Desk:\n" + block, ns)
Desk = ns["Desk"]


class Stub(Desk):
    pass


def make_desk():
    d = Stub.__new__(Stub)
    d.apps = {}
    d._child_env = lambda: {}
    d._push_apps = lambda: None
    d.emit = lambda msg: None
    d._reap = lambda p: None
    return d


def run(argv, windows, exit_at=None, code=0):
    state["windows"] = windows
    state["exit_at"] = exit_at
    state["code"] = code
    clock["t0"] = time.monotonic()
    d = make_desk()
    t = time.monotonic()
    r = d.launch_app(argv, "")
    return r, time.monotonic() - t


# 1. window appears at 0.4 s: success well before 3 s
r, dt = run(["firefox", "https://example.org"], [("firefox", 0.4)])
check(isinstance(r, int) and dt <= 0.7, f"window at 0.4 s -> pid {r} in {dt:.2f} s (need pid and <= 0.7 s)")

# 2. no window, process stays alive: waits the same 3.0 s as before, then the usual success
r, dt = run(["firefox"], [])
check(isinstance(r, int) and 2.9 <= dt <= 3.3, f"no window ever -> pid {r} after {dt:.2f} s (need 2.9-3.3 s)")

# 3. process exits at 0.3 s with code 1: the failure message, quickly
r, dt = run(["firefox"], [], exit_at=0.3, code=1)
check(isinstance(r, str) and r.startswith("could not start firefox: it closed at once") and dt <= 0.6,
      f"exits at 0.3 s with code 1 -> {r!r} in {dt:.2f} s (need the failure text and <= 0.6 s)")

# 4. window already open before the launch: not counted, so the full 3 s wait runs
r, dt = run(["firefox"], [("firefox", None)])
check(isinstance(r, int) and 2.9 <= dt <= 3.3, f"pre-existing window only -> pid {r} after {dt:.2f} s (need 2.9-3.3 s, not early)")

# 5. a different program's window appears: not counted
r, dt = run(["foot", "--title", "x"], [("org.xfce.mousepad", 0.2)])
check(isinstance(r, int) and dt >= 2.9, f"other program's window at 0.2 s -> {dt:.2f} s (need the full wait)")

# 6. handoff to an existing instance: exits 0 at once, same result as before (pid, no failure)
r, dt = run(["firefox"], [], exit_at=0.3, code=0)
check(isinstance(r, int) and dt <= 0.6, f"exits 0 at 0.3 s (handoff) -> pid {r} in {dt:.2f} s (same as before: pid, no wait)")

# 7. window tools missing: wm.windows() returns nothing, and an exception in it is not an error
state["windows"] = []
orig = fake_wm.windows
fake_wm.windows = lambda: (_ for _ in ()).throw(OSError("lswt missing"))
r, dt = run(["firefox"], [], exit_at=None)
fake_wm.windows = orig
check(isinstance(r, int) and 2.9 <= dt <= 3.3, f"window tool raises -> pid {r} after {dt:.2f} s (fallback to 3 s, no exception)")

# 8. the argv handed to Popen is unchanged
r, dt = run(["firefox", "https://example.org"], [("firefox", 0.1)])
check(state["pop_argv"] == ["firefox", "https://example.org"], f"Popen argv unchanged: {state['pop_argv']}")

# 9. wm.windows() hangs forever: the launch still returns within 3.4 s with the base result (pid, process alive)
def hang_windows():
    time.sleep(30)
    return []


fake_wm.windows = hang_windows
r, dt = run(["firefox"], [])
check(isinstance(r, int) and dt <= 3.4, f"windows() hangs -> pid {r} in {dt:.2f} s (need pid and <= 3.4 s)")

# 10. windows() hangs and the program exits 1 at 0.3 s: the failure message still comes back quickly
r, dt = run(["firefox"], [], exit_at=0.3, code=1)
check(isinstance(r, str) and r.startswith("could not start firefox: it closed at once") and dt <= 0.8,
      f"windows() hangs, exit 1 at 0.3 s -> {r!r} in {dt:.2f} s (need failure text and <= 0.8 s)")

# 11. windows() takes 1 s per call: detection is switched off after the first slow call, total <= 3.4 s, pid
calls = {"n": 0}


def slow_windows():
    calls["n"] += 1
    if calls["n"] > 1:
        time.sleep(1.0)
    return []


fake_wm.windows = slow_windows
r, dt = run(["firefox"], [])
check(isinstance(r, int) and dt <= 3.4 and calls["n"] <= 2,
      f"windows() 1 s per call -> pid {r} in {dt:.2f} s with {calls['n']} calls (need pid, <= 3.4 s, <= 2 calls)")

# 12. windows() takes 1 s on the pre-launch snapshot: no window checks after it, total <= 3.4 s, pid
calls = {"n": 0}


def slow_snapshot():
    calls["n"] += 1
    time.sleep(1.0)
    return ["firefox"]


fake_wm.windows = slow_snapshot
r, dt = run(["firefox"], [])
check(isinstance(r, int) and dt <= 3.4 and calls["n"] == 1,
      f"slow snapshot -> pid {r} in {dt:.2f} s with {calls['n']} call (need pid, <= 3.4 s, 1 call)")
fake_wm.windows = fake_windows

# 13. windows() is fast and a new window appears: early return as before
r, dt = run(["firefox"], [("firefox", 0.2)])
check(isinstance(r, int) and dt <= 0.7, f"fast windows(), window at 0.2 s -> pid {r} in {dt:.2f} s")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
