#!/usr/bin/env python3
"""Host-side test of everyday.py's "time in a city" route (world clock phrasings). system.find_timezone is patched to a
fake mapping, so no zone database is read and nothing on this computer changes. Run: python3 tools/test-world-clock.py"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import everyday, system  # noqa: E402

fails = 0
ZONES = {"tokyo": "Asia/Tokyo", "paris": "Europe/Paris", "london": "Europe/London", "new york": "America/New_York"}


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


def fake_find_timezone(name):
    return ZONES.get(str(name).strip())


system.find_timezone = fake_find_timezone
system.apply_timezone_env = lambda: None


def route(line):
    """Run the everyday routes on one typed line (the way desk.handle lowers it). Returns what was said, or None."""
    desk = Desk()
    low = line.lower().strip().rstrip("?.!")
    everyday.quick(desk, line, low)
    return desk.said


def world_clock_answer(said):
    """True when the reply is the city-time answer (never true for the other everyday answers)."""
    return bool(said) and bool(re.search(r"^It's \d\d:\d\d on \w+ in .+ \((the same time as here|\d+(\.\d+)? hours? (ahead of|behind) you)\)\.$", said))


def normal(said):
    return re.sub(r"\d\d:\d\d", "HH:MM", said or "")


print("positives: the city-time answer, same as the existing 'what time is it in' route")
reference = normal(route("what time is it in tokyo"))
check(world_clock_answer(route("what time is it in tokyo")), f"existing 'what time is it in tokyo' still answers: {reference!r}")
positives = ["world clock tokyo", "world clock in tokyo", "world clock for new york", "time in tokyo", "tokyo time",
             "what's the time in paris", "what is the time in paris", "current time in london", "time in new york",
             "what time is it in tokyo", "world clock paris?"]
for p in positives:
    said = route(p)
    gate = everyday.MATCH.search(p.lower().strip()) is not None
    check(gate and world_clock_answer(said), f"{p!r} -> {said!r} (gate {gate})")
for p, city in [("world clock tokyo", "Tokyo"), ("world clock in tokyo", "Tokyo"), ("world clock for new york", "New York"),
                ("tokyo time", "Tokyo"), ("what's the time in paris", "Paris"), ("current time in london", "London")]:
    said = route(p) or ""
    check(f" in {city} (" in said, f"{p!r} names {city}")

print("unknown city: no city-time reply, falls through as before")
for p in ["world clock atlantis", "time in atlantis", "atlantis time", "what time is it in atlantis", "current time in atlantis"]:
    said = route(p)
    check(not world_clock_answer(said), f"{p!r} -> no city reply ({said!r})")

print("negatives: never the city-time answer")
negatives = ["set the time zone to tokyo", "time in tokyo next week flights", "what time is it", "world clock app",
             "is it bedtime in tokyo", "world clock apps", "what's the time", "my time", "lunch time", "bed time"]
for n in negatives:
    said = route(n)
    check(not world_clock_answer(said), f"{n!r} -> not a city reply ({said!r})")

print("unicode city names: the route does not take them (find_timezone never sees them)")
for u in ["world clock zürich", "time in zürich", "time in são paulo", "world clock são paulo", "zürich time"]:
    said = route(u)
    check(not world_clock_answer(said), f"{u!r} -> no city reply ({said!r})")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
