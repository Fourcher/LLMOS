#!/usr/bin/env python3
"""Host-side check of the desk's turn() routing for typo'd lines: the fast paths (shortcut, which holds everyday.handle)
get the typed line first and, only if nothing handled it, the typo-fixed copy; the model runs once and gets the line as
typed. desk.py needs GTK, so turn() is read from its source and run against a stub desk.
Run: python3 tools/test-desk-typos.py"""
import os
import re
import sys
import threading
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "src", "rootfs")
SRC = os.path.join(ROOT, "usr", "lib", "llmos", "llmos", "desk.py")
sys.path.insert(0, os.path.join(ROOT, "usr", "lib", "llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(ROOT, "usr", "share", "llmos"))
from llmos import intent  # noqa: E402

src = open(SRC, encoding="utf-8").read()
fails = []


def check(cond, label):
    if cond:
        print("ok " + label)
    else:
        print("FAIL " + label)
        fails.append(label)


# (a) structural: turn() computes the typo-fixed copy, retries the shortcut on it, and calls the model once
start = src.index("    def turn(self, text, chat=")
end = src.index("    # ---- voice", start)
turn_src = src[start:end]
check("fixed = intent._retype(text)" in turn_src, "turn() computes intent._retype(text)")
check("self.shortcut(fixed)" in turn_src, "turn() retries shortcut on the fixed copy")
check(turn_src.index("self.shortcut(text)") < turn_src.index("self.shortcut(fixed)") < turn_src.index("agent.run("),
      "order: shortcut(text), shortcut(fixed), then the model")
check(turn_src.count("agent.run(") == 1, "the model call (agent.run) appears once in turn()")
check("agent.run(self.ctx, text, replay)" in turn_src, "the model receives the line as typed (text)")


# (b) behaviour: run turn() with a stub desk and stub agent/llm/config
class Stop(Exception):
    pass


class Cancel:
    def clear(self):
        pass


class Chat:
    msgs = []

    def continues(self, text):
        return False

    def context(self, text):
        return None, ""

    def record(self, *a):
        pass


def run_turn(line, handled):
    """handled: the lines the stub shortcut answers. Returns (shortcut calls, model calls)."""
    calls = {"shortcut": [], "model": []}

    class Desk:
        busy = False
        last_activity = []
        sources = []
        last_reply = ""
        ctx = types.SimpleNamespace(after_turn=None, cancel=Cancel(), chat_id="main", topic_note="")

        def _split_compound(self, text):
            return None

        def shortcut(self, text):
            calls["shortcut"].append(text)
            if text in handled:
                self._said = "stub answer"
                return True
            return False

        def chat(self, chat="main"):
            return Chat()

        def emit(self, msg):
            pass

        def push_status(self):
            pass

    stub_agent = types.SimpleNamespace(
        run=lambda ctx, text, replay: calls["model"].append(text) or "model answer",
        _plain_error=str, Cancelled=Stop)
    stub_llm = types.SimpleNamespace(ModelError=Stop, ModelDown=Stop)
    stub_config = types.SimpleNamespace(settings={})
    stub_voice = types.SimpleNamespace(speak=lambda t: None)
    ns = {"re": re, "threading": threading, "intent": intent, "agent": stub_agent, "llm": stub_llm,
          "config": stub_config, "voice": stub_voice, "T": str, "sys": sys}
    exec("class X:\n" + turn_src, ns)
    desk = Desk()
    ns["X"].turn(desk, line)
    return calls["shortcut"], calls["model"]


# a typo the shortcut answers only once it is fixed: shortcut runs on the typed line, then on the fixed one; no model
sc, md = run_turn("wat time is it", handled={"what time is it"})
check(sc == ["wat time is it", "what time is it"] and md == [],
      f"'wat time is it' handled by the fixed pass: shortcut {sc!r}, model {md!r}")

# a correctly spelled line the shortcut answers: one shortcut call, no second pass, no model
sc, md = run_turn("what time is it", handled={"what time is it"})
check(sc == ["what time is it"] and md == [], f"correct spelling answered once: shortcut {sc!r}, model {md!r}")

# a typo nothing answers: the original then the fixed line through the fast path, then the model once with the typed line
sc, md = run_turn("hwo do i print", handled=set())
check(sc == ["hwo do i print", "how do i print"], f"typo not handled: both fast passes ran, shortcut {sc!r}")
check(md == ["hwo do i print"], f"typo not handled: model once with the typed line, model {md!r}")

# a correct line nothing answers: one fast pass, the model once
sc, md = run_turn("tell me a joke", handled=set())
check(sc == ["tell me a joke"] and md == ["tell me a joke"], f"correct unhandled line: shortcut {sc!r}, model {md!r}")

if fails:
    print("FAIL " + str(len(fails)) + " check(s)")
    sys.exit(1)
print("all good")
