#!/usr/bin/env python3
"""Host-side test of the disk-space words in everyday.py (reads the disk only through a stub; touches nothing).
Run: python3 tools/test-free-space.py"""
import collections
import os
import sys
from unittest import mock

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


Usage = collections.namedtuple("Usage", "total used free")
USAGE = Usage(total=34e9, used=12e9, free=22e9)
PLAIN = "You have 22.0 GB free out of 34.0 GB (35% used)."
HINT = PLAIN + " Say \"show my biggest files\" to see what's using it."

print("the phrases that get the disk numbers")
plain = ["disk space", "storage", "free space", "how much storage do i have", "check disk space",
         "how much space is left", "how much free space do i have", "how much disk space is left on my computer"]
full = ["is my disk full", "why is my disk full", "is my computer full", "why is my computer full",
        "how full is my disk", "free up space", "free up disk space"]
with mock.patch("shutil.disk_usage", return_value=USAGE):
    for q in plain + full:
        for suffix in ("", "?", "."):
            text = q + suffix
            check(everyday.MATCH.search(text.lower()) is not None, f"{text!r} matches MATCH")
            dk = Desk()
            handled = everyday.free_space(dk, text, text.lower())
            want = HINT if q in full else PLAIN
            check(handled is not False and dk.said == want, f"{text!r} -> {dk.said!r}")

print("the same words in capitals still match")
check(everyday.MATCH.search("WHY IS MY DISK FULL".lower()) is not None, "'WHY IS MY DISK FULL' matches MATCH")

print("what is not the disk numbers")
for q in ("what's taking up space", "disk space of /mnt/x", "storage settings", "open storage"):
    check(everyday.MATCH.search(q) is None, f"{q!r} does not match MATCH")

print("the disk cannot be read")
with mock.patch("shutil.disk_usage", side_effect=OSError("gone")):
    dk = Desk()
    everyday.free_space(dk, "disk space", "disk space")
    check(dk.said == "I couldn't read the disk just now.", f"OSError -> {dk.said!r}")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
