#!/usr/bin/env python3
"""Host-side test: while the model is busy, a desk button or an instant-looking request that the OS cannot answer at
once goes to the queue exactly once (no thread loop), and an instant answer is not queued. Also: instant_reply skips
translation while busy. The desk is a Desk.__new__ stub; threading.Thread runs its target inline with a depth counter.
Run: python3 tools/test-busy-fallthrough.py  (exit status 0 = pass)"""
import os
import sys
import threading

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent, config, desk, intent, replytr  # noqa: E402

fails = []


def check(name, ok, detail=""):
    if ok:
        print("ok", name)
    else:
        print("FAIL", name, detail)
        fails.append(name)


class Recorder(list):
    def put(self, item):
        self.append(item)


class Event:
    def __init__(self):
        self.sets = 0

    def set(self):
        self.sets += 1


class InlineThread:
    """Runs its target at start(), counting starts and the deepest nesting seen."""
    starts = 0
    depth = 0
    max_depth = 0

    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        InlineThread.starts += 1
        InlineThread.depth += 1
        InlineThread.max_depth = max(InlineThread.max_depth, InlineThread.depth)
        try:
            if InlineThread.depth < 20:          # a loop would show as depth 20 (or the test would hang)
                self.target()
        finally:
            InlineThread.depth -= 1


def reset_counts():
    InlineThread.starts = 0
    InlineThread.depth = 0
    InlineThread.max_depth = 0


def make_desk(busy, instant, shortcut_answers=False, match=None):
    d = desk.Desk.__new__(desk.Desk)
    d.busy = busy
    d._pending_lock = threading.Lock()
    d._req_pending = 0
    d._req_done = 0
    d.requests = Recorder()
    d.last_active = 0
    d.last_reply = ""
    d.emitted = []
    d.emit = d.emitted.append
    d._instant = lambda text: instant
    d.shortcut = lambda text: shortcut_answers
    d.ctx = None
    return d


saved = (threading.Thread, intent.match, agent.execute)
threading.Thread = InlineThread
intent.match = lambda text: None
try:
    # busy, instant-looking words the OS cannot answer: one queue put, one thread, done set by the worker only
    for text in ("news", "screen time", "logs"):
        reset_counts()
        d = make_desk(busy=True, instant=True)
        done = Event()
        d.say(text, done)
        check(f"busy fall-through {text!r}: one queue put", len(d.requests) == 1, f"puts={len(d.requests)}")
        check(f"busy fall-through {text!r}: one thread started", InlineThread.starts == 1, f"starts={InlineThread.starts}")
        check(f"busy fall-through {text!r}: no nested threads", InlineThread.max_depth == 1, f"depth={InlineThread.max_depth}")
        check(f"busy fall-through {text!r}: done not set before the turn", done.sets == 0, f"sets={done.sets}")
        item = d.requests[0]
        check(f"busy fall-through {text!r}: queued text and done are kept", item[0] == text and item[1] is done and item[2] == "main",
              f"item={item!r}")
        item[1].set()                            # what _worker does when the turn ends
        check(f"busy fall-through {text!r}: done set exactly once", done.sets == 1, f"sets={done.sets}")
        check(f"busy fall-through {text!r}: pending count is 1", d._req_pending == 1, f"pending={d._req_pending}")

    # busy, a button the OS answers at once: no queue put, done set once by say's finally
    reset_counts()
    d = make_desk(busy=True, instant=True, shortcut_answers=True)
    done = Event()
    d.say("pause the music", done)
    check("busy instant answer: no queue put", len(d.requests) == 0, f"puts={len(d.requests)}")
    check("busy instant answer: one thread", InlineThread.starts == 1, f"starts={InlineThread.starts}")
    check("busy instant answer: done set exactly once", done.sets == 1, f"sets={done.sets}")

    # busy, intent matches but the app says the words are not an app: queued once, from the thread
    reset_counts()
    d = make_desk(busy=True, instant=True, match=("open_thing", {}))
    intent.match = lambda text: ("open_thing", {})
    agent.execute = lambda ctx, name, args: agent._NOT_AN_APP + " x"
    done = Event()
    d.say("tell me a poem about rain", done)
    check("busy not-an-app: one queue put", len(d.requests) == 1, f"puts={len(d.requests)}")
    check("busy not-an-app: one thread", InlineThread.starts == 1 and InlineThread.max_depth == 1,
          f"starts={InlineThread.starts} depth={InlineThread.max_depth}")
    check("busy not-an-app: done not set by say", done.sets == 0, f"sets={done.sets}")
    intent.match = lambda text: None
    agent.execute = saved[2]

    # not busy: say queues directly, no thread
    reset_counts()
    d = make_desk(busy=False, instant=True)
    done = Event()
    d.say("pause the music", done)
    check("not busy: one queue put, no thread", len(d.requests) == 1 and InlineThread.starts == 0,
          f"puts={len(d.requests)} starts={InlineThread.starts}")
    check("not busy: done not set by say", done.sets == 0, f"sets={done.sets}")

    # busy but not instant: queued directly, no thread
    reset_counts()
    d = make_desk(busy=True, instant=False)
    d.say("write me a letter", Event())
    check("busy not instant: one queue put, no thread", len(d.requests) == 1 and InlineThread.starts == 0,
          f"puts={len(d.requests)} starts={InlineThread.starts}")

    # translation: skipped while busy, done when idle
    calls = []
    saved_translate, saved_lang = replytr.translate, config.llm_language
    replytr.translate = lambda text, lang: (calls.append(text), "[tr] " + text)[1]
    config.llm_language = lambda: "es"
    try:
        d = make_desk(busy=True, instant=True)
        d.chat = lambda: type("C", (), {"record": lambda self, *a: None})()
        d.instant_reply("what time is it", "It is noon.")
        check("busy instant_reply: translation skipped", calls == [], f"calls={calls}")
        check("busy instant_reply: English shown", d.last_reply == "It is noon.", f"reply={d.last_reply!r}")
        d = make_desk(busy=False, instant=True)
        d.chat = lambda: type("C", (), {"record": lambda self, *a: None})()
        d.instant_reply("what time is it", "It is noon.")
        check("idle instant_reply: translation called once", calls == ["It is noon."], f"calls={calls}")
        check("idle instant_reply: translated reply shown", d.last_reply == "[tr] It is noon.", f"reply={d.last_reply!r}")
    finally:
        replytr.translate, config.llm_language = saved_translate, saved_lang
finally:
    threading.Thread, intent.match, agent.execute = saved

if fails:
    print("FAILED:", ", ".join(fails))
    sys.exit(1)
print("all good")
