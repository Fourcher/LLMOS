#!/usr/bin/env python3
"""Host-side test of the wait between the first and the second step of a compound request ("X, then Y").
After an app opens, run() takes a snapshot of the read bridge before the open, then polls it every 0.1 s and goes on
as soon as it shows a page different from that snapshot (2 s at most). Screen-acting first steps (_FIRST_SCREEN_TOOLS) keep that wait; other first steps (make_folder, remember, ...) continue at once.
time.sleep and time.monotonic are replaced by a fake clock.
Run: python3 tools/test-compound-wait.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
from unittest.mock import patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent


PAGE_CALC = {"text": "Calculator 0", "controls": ["display value: 0", "7", "+"]}
PAGE_NOTES = {"text": "Notes", "controls": ["New note"]}


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
    """A fake agent context. app_read() counts its calls in `reads`. Read 1 is the snapshot taken before the open
    (when there is one); from read `new_from` on it returns `new`, before that `old`. None means no page.
    new_from=None means the page never changes. has_bridge=False means the context has no app_read at all."""
    def __init__(self, clock, old=None, new=None, new_from=None, has_bridge=True):
        self.clock = clock
        self.old = old
        self.new = new
        self.new_from = new_from
        self.reads = 0
        if has_bridge:
            self.app_read = self._app_read

    def _app_read(self):
        self.reads += 1
        if self.new_from is not None and self.reads >= self.new_from:
            return self.new
        return self.old

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


# Case A: no page before, the calculator's page shows on the 3rd poll check -> about 0.3 s, second step runs
clock = Clock()
ctx = Ctx(clock, old=None, new=PAGE_CALC, new_from=4)      # read 1 = snapshot, reads 2-4 = polls 1-3
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran:
    _fail("case A: second step did not run")
if abs(waited - 0.3) > 0.05:
    _fail(f"case A: waited {waited:.2f}s, wanted about 0.3s")
print(f"ok case A: no page before, new page on poll 3, waited {waited:.2f}s, second step ran")

# Case B: the page never shows -> waits 2 s in total, then the second step still runs
clock = Clock()
ctx = Ctx(clock, old=None, new=None)
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran:
    _fail("case B: second step did not run")
if abs(waited - 2.0) > 0.05:
    _fail(f"case B: waited {waited:.2f}s, wanted 2.0s")
print(f"ok case B: never ready, waited {waited:.2f}s, second step ran")

# Case C: the first step is a non-screen tool (make_folder) -> no wait at all, the second step runs at once
clock = Clock()
ctx = Ctx(clock, old=None, new=None)
waited, ran = run_case("make a folder called Test, then open it", ctx, clock)
if not ran:
    _fail("case C: second step did not run")
if waited > 1e-9 or clock.sleeps or ctx.reads > 1:   # read 1 is the snapshot run() always takes
    _fail(f"case C: waited {waited:.2f}s, sleeps {clock.sleeps}, page reads {ctx.reads}; wanted no wait")
print(f"ok case C: non-screen first step (make_folder), waited {waited:.2f}s, {ctx.reads} page read (snapshot), second step ran")

# Case C2: the first step is a non-screen tool and the page would change at 0.3 s -> still no wait
clock = Clock()
ctx = Ctx(clock, old=None, new=PAGE_CALC, new_from=4)
waited, ran = run_case("make a folder called Test, then open it", ctx, clock)
if not ran:
    _fail("case C2: second step did not run")
if waited > 1e-9 or clock.sleeps:
    _fail(f"case C2: waited {waited:.2f}s, sleeps {clock.sleeps}; wanted no wait")
print(f"ok case C2: non-screen first step, page would change, waited {waited:.2f}s, second step ran")

# Case C3: remember (non-screen) as the first step -> no wait, the second step runs
clock = Clock()
ctx = Ctx(clock, old=None, new=None)
waited, ran = run_case("remember my dog is Rex, then open the calculator", ctx, clock)
if not ran:
    _fail("case C3: second step did not run")
if waited > 1e-9 or clock.sleeps:
    _fail(f"case C3: waited {waited:.2f}s, sleeps {clock.sleeps}; wanted no wait")
print(f"ok case C3: remember first step, waited {waited:.2f}s, second step ran")

# Case D: an open step with no read bridge at all -> waits 0.1 s steps, 2 s in total, then the second step runs
clock = Clock()
ctx = Ctx(clock, has_bridge=False)
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran:
    _fail("case D: second step did not run")
if abs(waited - 2.0) > 0.05:
    _fail(f"case D: no read bridge, waited {waited:.2f}s, wanted 2.0s")
if clock.sleeps.count(2) != 0 or set(clock.sleeps) != {0.1}:
    _fail(f"case D: sleeps {clock.sleeps}; wanted 0.1 s steps, no 2 s sleep")
print(f"ok case D: no read bridge, waited {waited:.2f}s in 0.1 s steps, second step ran")

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

# Case F: an old page is already open and does not change (the open is 'already open', or a program window)
# -> the full 2 s passes, then the second step runs
clock = Clock()
ctx = Ctx(clock, old=PAGE_NOTES, new=None)
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran:
    _fail("case F: second step did not run")
if abs(waited - 2.0) > 0.05:
    _fail(f"case F: old page unchanged, waited {waited:.2f}s, wanted 2.0s")
print(f"ok case F: old page unchanged, waited {waited:.2f}s, second step ran")

# Case G: an old page is open, the calculator's page replaces it on the 4th poll check -> about 0.4 s
clock = Clock()
ctx = Ctx(clock, old=PAGE_NOTES, new=PAGE_CALC, new_from=5)   # read 1 = snapshot, reads 2-5 = polls 1-4
waited, ran = run_case("open the calculator, then press 7", ctx, clock)
if not ran:
    _fail("case G: second step did not run")
if abs(waited - 0.4) > 0.05:
    _fail(f"case G: waited {waited:.2f}s, wanted about 0.4s")
print(f"ok case G: old page before, different page on poll 4, waited {waited:.2f}s, second step ran")

# Case H: a window-opening first step (make_document, in _FIRST_SCREEN_TOOLS) then a typing step -> waits for the page
# change (the word processor page shows on the 3rd poll check, about 0.3 s), then the typing step runs
real_match = agent.intent.match

def match_make_document(text):
    if text.strip().lower() == "make a document":
        return ("make_document", {"name": "Letter"})
    return real_match(text)

clock = Clock()
ctx = Ctx(clock, old=None, new=PAGE_NOTES, new_from=4)      # read 1 = snapshot, reads 2-4 = polls 1-3
with patch.object(agent.intent, "match", match_make_document):
    waited, ran = run_case("make a document, then type hello", ctx, clock)
if not ran:
    _fail("case H: typing step did not run")
if abs(waited - 0.3) > 0.05:
    _fail(f"case H: waited {waited:.2f}s, wanted about 0.3s (page change on poll 3)")
print(f"ok case H: make_document then type, page changes on poll 3, waited {waited:.2f}s, typing step ran")

# Case I: open_app first step with the read bridge raising on every call -> the full 2.0 s wait, no exception,
# and the second step still runs. Real run() and _wait_ready (only time is faked).
class RaisingCtx(Ctx):
    def _app_read(self):
        self.reads += 1
        raise RuntimeError("bridge down")

clock = Clock()
ctx = RaisingCtx(clock)
try:
    waited, ran = run_case("open the calculator, then press 7", ctx, clock)
except Exception as e:
    _fail(f"case I: run() raised {type(e).__name__}: {e}")
if not ran:
    _fail("case I: second step did not run")
if abs(waited - 2.0) > 0.05:
    _fail(f"case I: bridge raising, waited {waited:.2f}s, wanted 2.0s")
print(f"ok case I: open_app with raising bridge, waited {waited:.2f}s, no exception, second step ran")

# Case J: show_files as the first step (it opens a desk-drawn window, not an app, so the read bridge never changes)
# -> no wait at all, the second step runs at once
def match_show_files(text):
    if text.strip().lower() == "show my files":
        return ("show_files", {"folder": "Downloads"})
    return real_match(text)

clock = Clock()
ctx = Ctx(clock, old=None, new=None)
with patch.object(agent.intent, "match", match_show_files):
    waited, ran = run_case("show my files, then type hello", ctx, clock)
if not ran:
    _fail("case J: second step did not run")
if waited > 1e-9 or clock.sleeps:
    _fail(f"case J: waited {waited:.2f}s, sleeps {clock.sleeps}; wanted no wait")
print(f"ok case J: show_files first step, waited {waited:.2f}s, second step ran")

print("all good")
