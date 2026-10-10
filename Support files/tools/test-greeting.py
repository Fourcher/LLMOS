#!/usr/bin/env python3
"""Host-side check that the desk's greeting pattern (desk.py, the fullmatch on l2 with "good (?:morning") accepts
plain greetings and lets everything else fall through to the model.
Run: python3 tools/test-greeting.py  (no VM needed; reads the regex literal straight from desk.py)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deskre  # noqa: E402

GREET = re.compile(deskre.pattern_containing("good (?:morning"))

YES = ["hello world", "hi there!", "hey everyone", "good morning", "hello", "hi", "hey", "hiya", "good day"]
NO = ["hello, open firefox", "hi can you help me", "hey turn off wifi", "hello kitty wallpaper", "hi mom"]

bad = []
for t in YES:
    if GREET.fullmatch(t.lower()):
        print(f"ok greeting {t!r}")
    else:
        bad.append(f"expected greeting: {t!r}")
for t in NO:
    if not GREET.fullmatch(t.lower()):
        print(f"ok fallthrough {t!r}")
    else:
        bad.append(f"expected fall-through: {t!r}")

if bad:
    for b in bad:
        print("FAIL", b)
    sys.exit(1)
print("all good")
