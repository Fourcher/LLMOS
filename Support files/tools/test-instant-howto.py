#!/usr/bin/env python3
"""Desk._instant: a typed how-to (desk._HOWTO table) answers at once, even while the desk is busy.
Model-only requests still return False. Runs without a display: desk imports headless."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos"))

import llmos.desk as desk  # noqa: E402

cls = desk.Desk
o = cls.__new__(cls)   # bare instance: _instant only reads class-level tables and intent helpers

HOWTO_NOW_INSTANT = [
    "change homepage",
    "print",
    "can two people use this computer",
    "install alongside windows",
    "voice mode",
    "where are files",
    "list shortcuts",
    "print this",
    "clone this repo",
    "give me root",
    "do i have a firewall",
    "blur my background",
    "import my bookmarks from chrome",
    "add a user account",
    "virtual background",
    "what is the capital of france",
    "how tall is mount everest",
]

PREVIOUSLY_ACCEPTED = [
    "lock the screen",
    "what time is it",
    "what's the battery at",
    "close the window",
    "turn on airplane mode",
    "what did you say",
    "is the wifi down",
    "read this aloud",
    "mute the speaker",
    "what's open",
]

MODEL_ONLY = [
    "write me a poem",
    "what's a good name for a cat",
    "tell me a joke about cats",
    "explain quantum physics simply",
    "write a haiku about rain",
    "give me a recipe for pancakes",
    "what should i name my dog",
    "compose a limerick about a banana",
    "write a short story about a robot",
    "summarise the plot of hamlet in three paragraphs",
]

failures = []


def check(phrase, want):
    got = o._instant(phrase)
    if got is not want:
        failures.append(f"{phrase!r}: _instant={got}, want {want}")
        print(f"FAIL {phrase!r}: _instant={got}, want {want}")
    else:
        print(f"ok {phrase!r} -> {got}")


for p in HOWTO_NOW_INSTANT:
    check(p, True)
for p in PREVIOUSLY_ACCEPTED:
    check(p, True)
for p in MODEL_ONLY:
    check(p, False)

# Odd input must not raise.
for odd in ["", "   ", "🙂", "?", "how do i delete everything"]:
    try:
        r = o._instant(odd)
        print(f"ok no-raise {odd!r} -> {r}")
    except Exception as e:  # noqa: BLE001
        failures.append(f"{odd!r} raised {type(e).__name__}: {e}")
        print(f"FAIL {odd!r} raised {type(e).__name__}: {e}")

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)
print("all good")
