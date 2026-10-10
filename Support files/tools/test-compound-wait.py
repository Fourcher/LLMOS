#!/usr/bin/env python3
"""Host-side test of the wait between the first and the second step of a compound request ("X, then Y").
After an app opens, run() polls the open app's read bridge every 0.1 s and goes on as soon as it shows a page
(2 s at most). Other first steps keep the fixed 2 s sleep. time.sleep and time.monotonic are replaced by a fake clock.
Run: python3 tools/test-compound-wait.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
from unittest.mock import patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent


class Clock:
    """A fake clock: sleep() advances it, monotonic() reads it."""
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s

    def monotonic(self):
        return self.now


class Ctx:
    """A fake agent context. app_read() returns None (no page yet) until the `ready_on`-th call, then a page.
    ready_on=None means the page never shows. has_bridge=False means the context has no app_read at all."""
    def __init__(self, clock, ready_on=None, has_bridge=True):
        self.clock = clock
        self.ready_on = ready_on
        self.reads = 0
        if has_bridge:
            self.app_read = self._app_read

    def _app_read(self):
        self.reads += 1
        if self.ready_on is not None and self.reads >= self.ready_on:
            return {"text": "Calculator 0", "controls": ["display value: 0", "7", "+"]}
        return None

    def new_stream(self):
        return "s"

    def on_text(self, stream, text):
        pass

    def end_stream(self, stream):
        pass

    def status(self, msg):
        pass


def fake_execute(ctx, name, args):
    """Every step succeeds. The second step is recorded by the stub _screen_steps below."""
    return "opened the calculator. Done: ok" if name == "open_app" else "made the folder. Done: ok"


def run_case(user_text, ctx, clock):
    """Run agent.run() on the fake clock. Returns (seconds waited before the second step, whether it ran)."""
    seen = {}

    def fake_screen_steps(c, text):
        seen["waited"] = clock.now
        seen["rest"] = text
        return "", [], None, None          # nothing left for the model: run() answers directly

    with patch.object(agent.time, "sleep", clock.sleep), \
            patch.object(agent.time, "monotonic", clock.monotonic), \
            patch.object(agent, "execute", fake_execute), \
            patch.object(agent, "_screen_steps", fake_screen_steps):
        agent.run(ctx, user_text, [])
    return seen.get("waited"), "rest" in seen


def _fail(msg):
    print("FAIL " + msg)
    sys.exit(1)


# Case A: the app shows its page on the 3rd check -> about 0.3 s waited, and the second step still runs
clock = Clock()
ctx = Ctx(clock, ready_on=3)
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran:
    _fail("case A: second step did not run")
if abs(waited - 0.3) > 0.05:
    _fail(f"case A: waited {waited:.2f}s, wanted about 0.3s")
print(f"ok case A: app ready on check 3, waited {waited:.2f}s, second step ran")

# Case B: the page never shows -> waits 2 s in total, then the second step still runs
clock = Clock()
ctx = Ctx(clock, ready_on=None)
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran:
    _fail("case B: second step did not run")
if abs(waited - 2.0) > 0.05:
    _fail(f"case B: waited {waited:.2f}s, wanted 2.0s")
print(f"ok case B: never ready, waited {waited:.2f}s, second step ran")

# Case C: the first step is not an app open -> the old fixed 2 s sleep, and the second step runs
clock = Clock()
ctx = Ctx(clock, ready_on=1)
waited, ran = run_case("make a folder called Test, then open it", ctx, clock)
if not ran:
    _fail("case C: second step did not run")
if clock.sleeps.count(2) != 1 or ctx.reads != 0:
    _fail(f"case C: sleeps {clock.sleeps}, app_read calls {ctx.reads}; wanted one 2 s sleep and no polling")
print(f"ok case C: non-open first step, sleeps {clock.sleeps}, no polling")

# Case D: an open step with no read bridge at all -> the old fixed 2 s sleep
clock = Clock()
ctx = Ctx(clock, has_bridge=False)
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran or clock.sleeps.count(2) != 1:
    _fail(f"case D: ran={ran}, sleeps {clock.sleeps}; wanted one 2 s sleep")
print(f"ok case D: no read bridge, sleeps {clock.sleeps}")

# Case E: _wait_ready directly. An exception counts as not ready; the limit is never passed by more than one step.
clock = Clock()
calls = []

def flaky():
    calls.append(1)
    if len(calls) < 3:
        raise RuntimeError("bridge not up")
    return True

with patch.object(agent.time, "sleep", clock.sleep), patch.object(agent.time, "monotonic", clock.monotonic):
    got = agent._wait_ready(flaky)
if got is not True or len(calls) != 3 or abs(clock.now - 0.3) > 0.05:
    _fail(f"case E: got {got}, calls {len(calls)}, waited {clock.now:.2f}s")
print(f"ok case E: exceptions are not ready, waited {clock.now:.2f}s")

print("all good")
