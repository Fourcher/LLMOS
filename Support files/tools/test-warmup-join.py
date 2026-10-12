#!/usr/bin/env python3
"""Host-side test: a model turn sent while the background warm-up is still prefilling waits for it (so the one
model slot is not asked to prefill the same prefix twice); the wait is bounded (WARM_WAIT); a warm-up that raises
still releases waiting turns; with no warm-up there is no wait; a later warm-up clears and re-sets the event.
llm.chat is replaced by a fake, so no model is called.
Run: python3 "Support files/tools/test-warmup-join.py"  (no VM needed). Exit status 0 = pass."""
import os
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"),
                  LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import llm, agent  # noqa: E402

fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


calls = []                      # call order: "warm-start", "warm-end", "turn:<text>"
calls_lock = threading.Lock()
gate = threading.Event()        # the warm-up blocks on this until the test releases it
errors = []


def record(entry):
    with calls_lock:
        calls.append(entry)


def fake_chat(msgs, tools=None, on_text=None, max_tokens=None, think=None, **kw):
    if max_tokens == 1:                              # the warm-up request
        record("warm-start")
        gate.wait(20)
        record("warm-end")
        return {"content": "", "tool_calls": [], "raw": None, "timings": {}}
    record("turn:" + msgs[-1]["content"].rsplit("\n", 1)[-1])
    return {"content": "Here is an answer.", "tool_calls": [], "raw": None, "timings": {}}


def fake_ctx():
    stream = SimpleNamespace()
    return SimpleNamespace(new_stream=lambda: stream, on_text=lambda s, t: None, end_stream=lambda s: None,
                           status=lambda *a, **k: None, cancel=None)


def turn(text):
    def go():
        try:
            agent.run(fake_ctx(), text, [])
        except Exception as e:           # a turn that crashes must show up in the checks
            errors.append(repr(e))
    th = threading.Thread(target=go, daemon=True)
    th.start()
    return th


def reset():
    global calls
    with calls_lock:
        calls = []
    gate.clear()
    agent._warm_started = False
    agent._warm_done.clear()


def start_warm():
    th = threading.Thread(target=agent.warm_up, daemon=True)
    th.start()
    t0 = time.time()
    while "warm-start" not in calls and time.time() - t0 < 5:
        time.sleep(0.01)
    return th


with patch.object(llm, "chat", fake_chat), patch.object(llm, "context_size", lambda fresh=False: 4096):

    # 1. a turn sent during warm-up waits for it
    reset()
    w = start_warm()
    t = turn("tell me about rivers")
    time.sleep(0.3)
    check(calls == ["warm-start"], "turn during warm-up: no model call while warm-up is prefilling")
    gate.set()
    w.join(10)
    t.join(10)
    check(calls == ["warm-start", "warm-end", "turn:tell me about rivers"],
          f"turn during warm-up: its call comes after warm-up's ({calls})")

    # 2. two turns during warm-up both wait for the same event
    reset()
    w = start_warm()
    t1, t2 = turn("first question"), turn("second question")
    time.sleep(0.3)
    gate.set()
    w.join(10)
    t1.join(10)
    t2.join(10)
    check(calls[:2] == ["warm-start", "warm-end"] and len(calls) == 4,
          f"two turns during warm-up: both after warm-up's end ({calls})")

    # 3. warm-up raises: the event is still set and the turn proceeds
    reset()
    with patch.object(agent, "_warm_prefix", side_effect=RuntimeError("boom")):
        try:
            agent.warm_up()
        except RuntimeError:
            pass
    check(agent._warm_done.is_set() and agent._warm_started, "warm-up raising: event is set")
    t0 = time.time()
    t = turn("after a failed warm-up")
    t.join(10)
    el = time.time() - t0
    check(not t.is_alive() and el < 5 and calls == ["turn:after a failed warm-up"],
          f"warm-up raising: the turn proceeds at once ({el:.2f} s, {calls})")

    # 4. no warm-up ever started: no wait
    reset()
    t0 = time.time()
    agent._wait_warm()
    check(time.time() - t0 < 0.2, "no warm-up: _wait_warm returns at once")
    t = turn("no warm-up at all")
    t.join(10)
    check(calls == ["turn:no warm-up at all"], "no warm-up: the turn sends its call without waiting")

    # 5. warm-up hangs: the turn proceeds after WARM_WAIT
    reset()
    old_wait = agent.WARM_WAIT
    agent.WARM_WAIT = 0.2
    try:
        w = start_warm()
        t0 = time.time()
        t = turn("during a hang")
        t.join(10)
        el = time.time() - t0
        check(not t.is_alive() and 0.15 <= el < 3 and "turn:during a hang" in calls,
              f"hang: the turn proceeds after the cap ({el:.2f} s, WARM_WAIT=0.2)")
    finally:
        gate.set()
        w.join(10)
        agent.WARM_WAIT = old_wait

    # 6. a later warm-up (model restart) clears the event while it runs and sets it when done
    reset()
    agent.warm_up()
    check(agent._warm_done.is_set(), "warm-up done: event is set")
    seen = []
    with patch.object(agent, "_warm_prefix", side_effect=lambda: seen.append(agent._warm_done.is_set())):
        agent.warm_up()
    check(seen == [False] and agent._warm_done.is_set(),
          f"second warm-up: event cleared while running, set after ({seen})")

check(not errors, f"no turn crashed {errors}")
if fails:
    print(f"FAIL {len(fails)} check(s)")
    sys.exit(1)
print("all good")
