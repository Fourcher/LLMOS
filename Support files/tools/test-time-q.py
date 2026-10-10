#!/usr/bin/env python3
"""Host-side check that the desk's time/date question pattern (_TIME_Q in desk.py) accepts the common wordings.
Run: python3 tools/test-time-q.py  (no VM needed; reads the regex literal straight from desk.py)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deskre  # noqa: E402

TIME_Q = re.compile(deskre.pattern_containing("whats the (?:time|date)"))
CASES = ["whats the date", "whats today", "what's the time", "what day is it"]
bad = 0
for text in CASES:
    if TIME_Q.fullmatch(text):
        print(f"ok {text!r}")
    else:
        bad += 1
        print(f"MISMATCH {text!r}: _TIME_Q does not fullmatch")
if bad:
    sys.exit(1)
print("all good")
