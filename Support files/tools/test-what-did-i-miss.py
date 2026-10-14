#!/usr/bin/env python3
"""Host-side test of the Desk.shortcut route that opens "While you were away" on request: "what did I miss",
"what'd I miss", "anything new", "any notifications", "show my notifications",
"what happened while I was away", "while I was away". "show notifications" is not one of them: it means
"turn notifications back on" (intent._dnd, do-not-disturb off). It calls show_away(force=True) when something is unseen,
and replies "Nothing new since you last looked." when nothing is. Phrases that only mention missing or
notifications in another sense (a file, a call, a bus, "notifications off") do not match.
desk.py needs GTK, so the shortcut method is read from its source and run against stubs.
Run: python3 tools/test-what-did-i-miss.py"""
import os
import re
import sys
import textwrap

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import intent  # noqa: E402

SRC = os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py")
src = open(SRC, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


# the shortcut up to the first route after the new one (everything before it is the part under test)
method = src[src.index("    def shortcut(self, line):"):src.index("        hit = self._app_question(low)")]
ns = {"re": re, "intent": intent, "store": None,
      "media": type("NoPlayer", (), {"playing": staticmethod(lambda: None)})}   # nothing playing: the player phrases step aside
exec("class Desk:\n" + method, ns)
Desk = ns["Desk"]


class Store:
    def __init__(self):
        self.items = []

    def unseen(self):
        return list(self.items)


store_stub = Store()
ns["store"] = store_stub


def make_desk():
    d = Desk.__new__(Desk)
    d.calls = []
    d.replies = []
    d.windows = {}
    d.open_panel = lambda name: d.calls.append(("open_panel", name))
    d.close_window = lambda wid: d.calls.append(("close_window", wid))
    d.emit = lambda msg: d.calls.append(("emit", msg))
    d._app_question = lambda low: None
    d.show_away = lambda force=False: d.calls.append(("show_away", force))
    d.instant_reply = lambda request, text: d.replies.append(text)
    return d


POS = ["what did i miss", "what did I miss?", "what'd i miss", "what’d I miss?", "anything new",
       "any notifications", "show my notifications",
       "what happened while I was away", "while I was away"]
NEG = ["what did i miss in the meeting notes", "did i miss a call", "i missed the bus",
       "notifications off", "turn off notifications", "show notifications"]

print("the card opens on request")
for q in POS:
    store_stub.items = [{"id": 1, "title": "Mail", "text": "A parcel arrived."}]
    d = make_desk()
    got = d.shortcut(q)
    check(got is True and d.calls == [("show_away", True)] and d.replies == [],
          f"unseen present, show_away(force=True) once, no reply: {q!r}")

print("nothing unseen gets a reply")
for q in POS:
    store_stub.items = []
    d = make_desk()
    got = d.shortcut(q)
    check(got is True and d.calls == [] and d.replies == ["Nothing new since you last looked."],
          f"nothing unseen: {q!r}")

print("other phrases keep their old routing")
for q in NEG:
    store_stub.items = [{"id": 1, "title": "Mail", "text": "A parcel arrived."}]
    d = make_desk()
    got = d.shortcut(q)
    check(not got and d.calls == [] and d.replies == [],
          f"not matched, show_away not called: {q!r}")

check(intent._dnd("turn off notifications") is None and intent._dnd("notifications off") is None,
      "intent DND route unchanged for 'turn off notifications' / 'notifications off'")
check(intent.match("show notifications") == ("change_setting", {"setting": "do_not_disturb", "value": "off"}),
      "intent.match 'show notifications' still gives DND off (base result)")
check(intent.match("show my notifications") is None,
      "intent.match 'show my notifications' still gives None (base result)")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
