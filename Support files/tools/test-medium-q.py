#!/usr/bin/env python3
"""Check the live-vs-installed question pattern (_MEDIUM_Q) in desk.py.

Reads desk.py as text so no GTK import is needed.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py")

with open(DESK, encoding="utf-8") as f:
    text = f.read()

m = re.search(r"_MEDIUM_Q = (re\.compile\(.*?, re\.I\))", text, re.S)
if not m:
    print("FAIL could not find _MEDIUM_Q in desk.py")
    sys.exit(1)

pattern = eval(m.group(1), {"re": re})

YES = [
    "how do I keep this without the usb",
    "how can i keep everything without the stick",
    "is this running off the usb?",
    "will my files be kept",
]
NO = [
    "how do I keep my files backed up",
]

failed = False
for s in YES:
    if pattern.search(s.lower()):
        print("ok match", repr(s))
    else:
        print("FAIL no match", repr(s))
        failed = True
for s in NO:
    if pattern.search(s.lower()):
        print("FAIL unexpected match", repr(s))
        failed = True
    else:
        print("ok no-match", repr(s))

if failed:
    sys.exit(1)
print("all good")
