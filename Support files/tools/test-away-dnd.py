#!/usr/bin/env python3
"""Host-side test of desk.py show_away ("While you were away").
With do-not-disturb on, the card is not opened, and no toast, chime or speech is sent, and nothing is recorded
(the items stay unseen, _inbox_key is not set), so the first call after do-not-disturb is off shows the card.
With it off (or unset) the card, toast and chime go out, and speech only when speak_replies is on.
An explicit owner request (force=True) opens the card even under do-not-disturb, still with no toast, chime or speech.
desk.py needs GTK, so show_away is read from its source and run against stubs.
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


method = src[src.index("    def show_away(self, force=False):"):src.index("    def sleep_now(self):")]
show_away = textwrap.dedent(method)

tmp = tempfile.mkdtemp(prefix="away-dnd-")
inbox = os.path.join(tmp, "inbox.json")
MSG = [{"id": 1, "title": "Mail", "text": "Your parcel has arrived at the front desk."},
       {"id": 2, "title": "Timer", "text": "The tea timer is done."}]


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


class Store:
    """Records seen-state the way the store does: items stay unseen until mark_seen."""
    def __init__(self):
        self.seen = set()
        self.rung = set()

    def unseen(self):
        return [dict(m, rung=m["id"] in self.rung) for m in MSG if m["id"] not in self.seen]

    def mark_seen(self, ids):
        self.seen.update(ids)

    def mark_rung(self, ids):
        self.rung.update(ids)


class Ui:
    def strip(self, t):
        return t


class Desk:
    def __init__(self):
        self.ctx = Ctx()
        self.emitted = []
        self.windows = []
        self.ready = True

    def emit(self, msg):
        self.emitted.append(msg)

    def open_window(self, spec):
        self.windows.append(spec)


DEV = Devices()
VOICE = Voice()
STORE = Store()


def reset_stubs():
    """Fresh chime/speech/window/seen counters and an inbox with both items unseen."""
    global STORE
    DEV.chimes = 0
    VOICE.spoken = []
    STORE = Store()
    with open(inbox, "w", encoding="utf-8") as f:
        json.dump(MSG, f)
    return Desk()


def call(desk, settings, force=False):
    """Run show_away once on the given desk (the same desk across polls keeps _inbox_key, away_ids)."""
    g = {"os": os, "re": re, "threading": type("T", (), {"Timer": staticmethod(lambda t, fn: type("X", (), {"start": lambda self: fn()})())}), "config": Config(settings), "devices": DEV, "voice": VOICE,
         "store": STORE, "ui": Ui(), "T": lambda k: k}
    exec(compile(show_away, "show_away", "exec"), g)
    desk.show_away = g["show_away"].__get__(desk, Desk)
    desk.show_away(force=force)
    return desk


def titles(desk):
    return [i["title"] for w in desk.windows for b in w["blocks"] for i in b["items"]]


print("do not disturb off")
d = call(reset_stubs(), Settings(do_not_disturb=False, chime=True, speak_replies=True))
check(len(d.windows) == 1 and d.windows[0]["id"] == "away", "card opened")
check([m["t"] for m in d.emitted] == ["toast"], "toast sent")
check(DEV.chimes == 1, "chime sent")
check(VOICE.spoken == ["The tea timer is done."], "speech sent for the newest item (speak_replies on)")
check(d.away_ids == [1, 2] and STORE.seen == set(), "away_ids set; nothing marked seen until the card closes")

print("do not disturb off, speak_replies off")
d = call(reset_stubs(), Settings(do_not_disturb=False, chime=True, speak_replies=False))
check([m["t"] for m in d.emitted] == ["toast"] and DEV.chimes == 1 and VOICE.spoken == [], "toast + chime, no speech")

print("do not disturb unset (None)")
d = call(reset_stubs(), Settings(do_not_disturb=None, chime=True, speak_replies=True))
check([m["t"] for m in d.emitted] == ["toast"] and DEV.chimes == 1 and len(VOICE.spoken) == 1,
      "treated as off: toast, chime, speech")

print("do not disturb on at boot (desk entry and polls)")
d = reset_stubs()
call(d, Settings(do_not_disturb=True, chime=True, speak_replies=True))
check(d.windows == [], "no window on desk entry")
check(d.emitted == [] and DEV.chimes == 0 and VOICE.spoken == [], "no toast, chime or speech")
check(STORE.seen == set() and len(STORE.unseen()) == 2, "items stay unseen")
check(getattr(d, "_inbox_key", "unset") == "unset" and not hasattr(d, "away_ids"),
      "_inbox_key and away_ids untouched")
call(d, Settings(do_not_disturb=True, chime=True, speak_replies=True))
check(d.windows == [] and d.emitted == [] and DEV.chimes == 0, "still nothing on the next 20 s poll")

print("do not disturb turned off between polls")
DEV.chimes = 0
VOICE.spoken = []
d.emitted = []
call(d, Settings(do_not_disturb=False, chime=True, speak_replies=False))
check(len(d.windows) == 1 and d.windows[0]["id"] == "away", "card shows on the first poll after DND is off")
check(titles(d) == ["Mail", "Timer"], "card lists all unseen items")
check([m["t"] for m in d.emitted] == ["toast"] and DEV.chimes == 1, "one toast, one chime")
call(d, Settings(do_not_disturb=False, chime=True, speak_replies=False))
check(len(d.windows) == 1 and DEV.chimes == 1 and len(d.emitted) == 1,
      "next poll with the same inbox adds nothing (no second card, chime or toast)")

print("explicit owner request under do not disturb (force=True)")
d = call(reset_stubs(), Settings(do_not_disturb=True, chime=True, speak_replies=True), force=True)
check(len(d.windows) == 1 and d.windows[0]["id"] == "away" and titles(d) == ["Mail", "Timer"],
      "card opens with all unseen items")
check(d.emitted == [] and DEV.chimes == 0 and VOICE.spoken == [], "no toast, chime or speech")
check(d.away_ids == [1, 2] and STORE.seen == set(), "away_ids set; still nothing marked seen until closed")

print("unchanged poll under do not disturb off after an explicit request")
call(d, Settings(do_not_disturb=False, chime=True, speak_replies=False))
check(len(d.windows) == 1, "no duplicate card on the normal poll")

print("desk started again (an update or a reboot) with the card never closed")
d = call(reset_stubs(), Settings(do_not_disturb=False, chime=True, speak_replies=True))
check(STORE.rung == {1, 2}, "both items recorded as announced")
DEV.chimes = 0
VOICE.spoken = []
d2 = call(Desk(), Settings(do_not_disturb=False, chime=True, speak_replies=True))
check(len(d2.windows) == 1 and titles(d2) == ["Mail", "Timer"], "the card comes back with the unseen items")
check(d2.emitted == [] and DEV.chimes == 0 and VOICE.spoken == [], "no second toast, chime or speech")
MSG.append({"id": 3, "title": "Reminder", "text": "Stand up.", "alarm": True})
d3 = call(Desk(), Settings(do_not_disturb=False, chime=True, speak_replies=False))
check([m.get("text") for m in d3.emitted] == ["Stand up."] and DEV.chimes == 2, "a new item rings (toast; chime twice for an alarm)")
check([w["id"] for w in d3.windows] == ["away", "alarm"], "a new reminder gets its own window")
d4 = call(Desk(), Settings(do_not_disturb=False, chime=True, speak_replies=False))
check([w["id"] for w in d4.windows] == ["away"], "after a restart the reminder's window does not open again")
MSG.pop()

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
