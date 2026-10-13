#!/usr/bin/env python3
"""Host-side test of desk.py show_away ("While you were away"): with do-not-disturb on, the card is still
updated but no toast, chime or speech is sent; with it off (or unset) the toast and chime go out, and speech
only when speak_replies is on. desk.py needs GTK, so show_away is read from its source and run against stubs.
Run: python3 tools/test-away-dnd.py"""
import json
import os
import re
import sys
import tempfile
import textwrap

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
src = open(SRC, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


method = src[src.index("    def show_away(self):"):src.index("    def sleep_now(self):")]
show_away = textwrap.dedent(method)

tmp = tempfile.mkdtemp(prefix="away-dnd-")
inbox = os.path.join(tmp, "inbox.json")
MSG = [{"id": 1, "title": "Mail", "text": "Your parcel has arrived at the front desk."}]


class Settings:
    def __init__(self, **kw):
        self.d = kw

    def get(self, key, default=None):
        return self.d.get(key, default)


class Config:
    def __init__(self, settings):
        self.settings = settings

    def data(self, name):
        return os.path.join(tmp, name)


class Devices:
    def __init__(self):
        self.chimes = 0

    def chime(self):
        self.chimes += 1


class Voice:
    def __init__(self):
        self.spoken = []

    def speak(self, t):
        self.spoken.append(t)


class Ctx:
    def background(self, fn):
        fn()


def run(settings):
    """Run show_away once on a fresh Desk stub; returns what it sent."""
    with open(inbox, "w", encoding="utf-8") as f:
        json.dump(MSG, f)
    desk = Desk()
    desk.ready = True
    g = {"os": os, "re": re, "config": Config(settings), "devices": DEV, "voice": VOICE,
         "store": Store(), "ui": Ui(), "T": lambda k: k}
    exec(compile(show_away, "show_away", "exec"), g)
    desk.show_away = g["show_away"].__get__(desk, Desk)
    desk.show_away()
    return desk


class Store:
    def unseen(self):
        return list(MSG)


class Ui:
    def strip(self, t):
        return t


class Desk:
    def __init__(self):
        self.ctx = Ctx()
        self.emitted = []
        self.windows = []

    def emit(self, msg):
        self.emitted.append(msg)

    def open_window(self, spec):
        self.windows.append(spec)


DEV = Devices()
VOICE = Voice()


def reset_stubs():
    DEV.chimes = 0
    VOICE.spoken = []


print("do not disturb off")
reset_stubs()
d = run(Settings(do_not_disturb=False, chime=True, speak_replies=True))
check(len(d.windows) == 1 and d.windows[0]["id"] == "away", "card opened")
check([m["t"] for m in d.emitted] == ["toast"], "toast sent")
check(DEV.chimes == 1, "chime sent")
check(VOICE.spoken == ["Your parcel has arrived at the front desk."], "speech sent (speak_replies on)")

print("do not disturb off, speak_replies off")
reset_stubs()
d = run(Settings(do_not_disturb=False, chime=True, speak_replies=False))
check([m["t"] for m in d.emitted] == ["toast"] and DEV.chimes == 1 and VOICE.spoken == [], "toast + chime, no speech")

print("do not disturb unset (None)")
reset_stubs()
d = run(Settings(do_not_disturb=None, chime=True, speak_replies=True))
check([m["t"] for m in d.emitted] == ["toast"] and DEV.chimes == 1 and len(VOICE.spoken) == 1, "treated as off: toast, chime, speech")

print("do not disturb on")
reset_stubs()
d = run(Settings(do_not_disturb=True, chime=True, speak_replies=True))
check(len(d.windows) == 1 and d.windows[0]["id"] == "away" and d.windows[0]["blocks"][0]["items"][0]["title"] == "Mail",
      "card still updated with the mail")
check(d.emitted == [], "no toast")
check(DEV.chimes == 0, "no chime")
check(VOICE.spoken == [], "no speech")
check(d.away_ids == [1], "card still marks the item for seen-on-close")

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
