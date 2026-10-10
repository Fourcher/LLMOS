#!/usr/bin/env python3
"""Host-side test of everyday.py's instant percentage answers (no files touched).
Run: python3 tools/test-percent.py"""
import os
import re
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


def ask(q):
    dk = Desk()
    got = everyday.quick(dk, q, q.lower().strip().rstrip("?.!"))
    return got, dk.said


CASES = (
    ("what's 15 percent of 240", "15% of 240 is 36."),
    ("whats 15 percent of 240", "15% of 240 is 36."),
    ("15% of 240", "15% of 240 is 36."),
    ("15% of 1,200", "15% of 1,200 is 180."),
    ("what is 12.5 percent of 80", "12.5% of 80 is 10."),
    ("calculate 7 percent of 1,000", "7% of 1,000 is 70."),
    ("what's 33.3 percent of 1,000", "33.3% of 1,000 is 333."),
    ("what percent is 45 of 240", "45 is 18.75% of 240."),
    ("what percentage of 240 is 45", "45 is 18.75% of 240."),
)

print("percentages are answered instantly")
for q, want in CASES:
    got, said = ask(q)
    check(got is True and said == want, f"{q!r} -> {said!r} (want {want!r})")

print("what falls through to the model")
for q in ("15 percent of my salary", "what percent is 45 of 0"):
    got, said = ask(q)
    check(got is False and said is None, f"{q!r} is left to the model")

print("the desk's instant test sees the new forms")
for q in ("whats 15 percent of 240", "15 percent of 240", "what percent is 45 of 240", "what percentage of 240 is 45"):
    check(everyday.MATCH.search(q) is not None, f"{q!r} is instant")

if fails:
    print(f"{fails} failed")
    sys.exit(1)
print("all good")
