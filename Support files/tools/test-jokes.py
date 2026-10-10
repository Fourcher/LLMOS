#!/usr/bin/env python3
"""Host-side test of everyday.py's instant jokes (no files touched).
Run: python3 tools/test-jokes.py"""
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


def ask(q):
    dk = Desk()
    got = everyday.jokes(dk, q, q.lower().strip().rstrip("?.!"))
    return got, dk.said


JOKE_FORMS = ("tell me a joke", "give me a joke please", "tell me another joke", "say a joke",
              "know any jokes?", "make me laugh")
NOT_JOKE_FORMS = ("tell me a joke about cats", "don't tell me a joke")

check(len(everyday.JOKES) == 30 and len(set(everyday.JOKES)) == 30, "JOKES holds 30 different jokes")

print("the joke forms get a reply from JOKES")
for q in JOKE_FORMS:
    got, said = ask(q)
    check(got is True and said in everyday.JOKES, f"{q!r} -> {said!r}")

print("11 jokes in a row never repeat within any 10-window")
seen = []
for _ in range(11):
    got, said = ask("tell me a joke")
    seen.append(said)
windows_ok = all(len(set(seen[i:i + 10])) == 10 for i in range(len(seen) - 9))
check(windows_ok and all(s in everyday.JOKES for s in seen), f"{len(seen)} replies, no repeat in any 10-window")

print("topical and negative forms fall through to the model")
for q in NOT_JOKE_FORMS:
    got, said = ask(q)
    check(got is False and said is None, f"{q!r} is left to the model")

print("the desk's instant test (MATCH) gates them correctly")
for q in JOKE_FORMS:
    low = q.lower().strip().rstrip("?.!")
    check(everyday.MATCH.search(low) is not None, f"{q!r} is instant")
for q in NOT_JOKE_FORMS:
    low = q.lower().strip().rstrip("?.!")
    check(everyday.MATCH.search(low) is None, f"{q!r} is not instant")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
