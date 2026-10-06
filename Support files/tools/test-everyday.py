#!/usr/bin/env python3
"""Host-side test of everyday.py's words and dates (no files touched: the parts that change the computer are tested
in the VM). Run: python3 tools/test-everyday.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import everyday  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Desk:
    def __init__(self):
        self.said = None

    def instant_reply(self, line, text):
        self.said = text


print("days until")
today = dt.date.today()
for words, want in (("christmas", dt.date(today.year if today <= dt.date(today.year, 12, 25) else today.year + 1, 12, 25)),
                    ("2030-01-02", dt.date(2030, 1, 2)), ("3 march 2031", dt.date(2031, 3, 3))):
    d, _ = everyday._date_of(words, today)
    check(d == want, f"{words!r} -> {d}")
check(everyday._easter(2027) == dt.date(2027, 3, 28), "easter 2027 is 28 March")
check(everyday._thanksgiving(2026) == dt.date(2026, 11, 26), "thanksgiving 2026 is 26 November")
for q in ("how many days until christmas", "countdown to new year", "days until 2030-01-02", "how long until halloween"):
    dk = Desk()
    check(everyday.MATCH.search(q) is not None and everyday.days_until(dk, q, q) and "day" in (dk.said or "") or "today" in (dk.said or ""), f"{q!r}: {dk.said}")
dk = Desk()
everyday.days_until(dk, "countdown to my holiday", "countdown to my holiday")
check("When is it" in (dk.said or ""), "an unknown date is asked for, not guessed")

print("the words reach the right helper")
for q in ("start work timer", "track my hours", "clock out", "what's listening on port 8080", "kill whatever's on 3000",
          "start a local web server here", "preview this html", "computer is hot", "temperature", "is my battery dying",
          "why is the battery draining fast", "check my hard drive health", "track my parcel", "check my order status",
          "teach me to type", "typing practice", "learn spanish", "change the computer name", "focus mode for an hour",
          "block youtube while i study", "end focus mode", "my hands shake, double clicks are hard", "sticky keys",
          "turn off the startup sound", "no clicking sounds", "start firefox when i log in", "stop x from starting automatically",
          "connect to my work vpn", "set up a proxy/vpn", "rip this cd", "play this dvd", "play this on my tv", "cast to chromecast",
          "color blind mode", "change my profile picture", "set a screensaver", "show a clock when idle",
          "can i run this windows program (.exe)", "install this .deb/.appimage", "keep this on top", "picture in picture"):
    check(everyday.MATCH.search(q.lower()) is not None, f"{q!r} is instant")
for q in ("turn the volume up", "open my documents", "what's the weather", "play some music"):
    check(everyday.MATCH.search(q) is None, f"{q!r} is not")

print("questions and commands that only look alike are left to the model")
for q, fn in (("what is a vpn", everyday.vpn), ("cd ~/projects", everyday.discs), ("why do people use a vpn", everyday.vpn)):
    dk = Desk()
    check(not fn(dk, q, q), f"{q!r} is not acted on")
dk = Desk()
check(everyday.howto(dk, "color blind mode", "color blind mode") and "filter" in dk.said, "colour blind: an honest answer, not dark mode")
dk = Desk()
check(everyday.howto(dk, "close the lid", "close the lid") is False, "'close the lid' alone is not a how-to")

print("a custom style can change the look but never hide or move the request box and the frame")
from llmos import tools  # noqa: E402
css = tools._clean_css("#cmd { display: none !important; color: lime } html { height: 1px; filter: sepia(1) } "
                       ".win { clip-path: polygon(50% 0,100% 100%,0 100%) !important } @import url(http://x); a { background: url(http://evil/x.png) }")
check("display" not in css and "lime" in css, "the request box keeps showing; its colour may change")
check("height" not in css and "sepia" in css, "the page keeps its size; a whole-screen effect stays")
check("clip-path" in css, "windows may take any shape")
check("http://" not in css, "nothing is fetched from the network")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
