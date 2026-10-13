#!/usr/bin/env python3
"""Desk: "sign out" / "log out" lock the screen and say why (there is no separate sign-in to leave). Only the sign-out
phrases get the extra sentence; the existing lock phrases keep their reply; look-alikes (log out of a site, sign out
sheet, logs, how do I log out) do not lock. Runs headless: desk imports without a display.
Run: python3 tools/test-sign-out.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos"))

import llmos.desk as desk  # noqa: E402

fails = 0
SIGNOUT_REPLY = "Locked. There is no separate sign-in to leave, so signing out locks the screen."


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class NoVault:
    """config.settings stand-in: no passphrase set, so the lock route takes the set_screen branch."""

    def get(self, key, default=None):
        return default

    def all(self):
        return {}


desk.config.settings = NoVault()


def run(line):
    """A bare Desk with lock, set_screen and instant_reply recording what the route did."""
    o = desk.Desk.__new__(desk.Desk)
    rec = {"lock": 0, "screen": 0, "replies": []}
    o.lock = lambda: rec.__setitem__("lock", rec["lock"] + 1)
    o.set_screen = lambda *a, **k: rec.__setitem__("screen", rec["screen"] + 1)
    o._keybinds = lambda *a, **k: None
    o.instant_reply = lambda r, t: rec["replies"].append(t)
    result = o.shortcut(line)
    return o, result, rec


positives = ["sign out", "log out", "sign me out", "log me out", "sign off", "please sign out", "log out please",
             "sign out now", "please log out now", "sign me out please"]
print("sign-out phrases lock once and say why")
for q in positives:
    o, result, rec = run(q)
    check(rec["lock"] + rec["screen"] == 1, f"{q!r}: locked once (lock={rec['lock']}, screen={rec['screen']})")
    check(rec["replies"] == [SIGNOUT_REPLY], f"{q!r}: reply is the sign-out sentence (got {rec['replies']!r})")
    check(result is True, f"{q!r}: shortcut handled it")
    check(bool(o._instant(q)), f"{q!r}: answered at once while the desk is busy")

print("look-alikes do not lock")
for q in ("log out of facebook", "sign out of gmail", "sign out sheet", "logs", "how do i log out", "sign in", "log in"):
    _, _, rec = run(q)
    check(rec["lock"] + rec["screen"] == 0, f"{q!r}: no lock")
    check(SIGNOUT_REPLY not in rec["replies"], f"{q!r}: no sign-out sentence")

print("existing lock phrases keep their behaviour")
for q in ("lock", "lock the screen", "lock it up", "i'm stepping away"):
    _, _, rec = run(q)
    check(rec["screen"] == 1 and rec["replies"] == [], f"{q!r}: locks with no sign-out sentence")
o = desk.Desk.__new__(desk.Desk)
check(bool(o._instant("lock")), "'lock' still answered at once")

print("how do I log out still gets the how-to")
_, _, rec = run("how do i log out")
check(rec["lock"] + rec["screen"] == 0 and len(rec["replies"]) == 1 and rec["replies"][0].startswith("Press Super+L"),
      "how-to reply, no lock")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
