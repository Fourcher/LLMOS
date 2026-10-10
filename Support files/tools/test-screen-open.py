#!/usr/bin/env python3
"""Shortcut for 'what's on my screen' / 'what's open' answers from window names, no OCR."""
import os
import py_compile
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deskre

PATTERN = deskre.pattern_containing("which (?:windows|apps|programs) are open")
print("pattern:", PATTERN)

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.normpath(os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py"))


def check(name, cond):
    if not cond:
        print("FAIL " + name)
        sys.exit(1)
    print("ok " + name)


def norm(s):
    return s.lower().strip().rstrip("?.! ")


for phrase in ["what's on my screen", "what is on the screen right now", "what's open", "which apps are open"]:
    check("match: " + phrase, re.fullmatch(PATTERN, norm(phrase)) is not None)

check("no match: what's on my screen saver settings",
      re.fullmatch(PATTERN, norm("what's on my screen saver settings")) is None)

with open(DESK, encoding="utf-8") as f:
    src = f.read()
check("desk.py has 'Open now: '", "Open now: " in src)
check("desk.py has 'Nothing is open, just the desk.'", "Nothing is open, just the desk." in src)
check("desk.py no longer says 'read the screen'", "read the screen" not in src)

NAME_EXPR = '.split(".")[-1].replace("-", " ").replace("_", " ").title()'
for raw, want in [("org.mozilla.firefox", "Firefox"), ("foot", "Foot"), ("org.gnome.Calculator", "Calculator")]:
    got = eval("str(raw)" + NAME_EXPR, {"raw": raw})
    check("name: %s -> %s" % (raw, want), got == want)

names = ["Calculator", "calculator", "Firefox", "Firefox", ""]
seen, uniq = set(), []
for n in names:
    if n.strip() and n.lower() not in seen:
        seen.add(n.lower())
        uniq.append(n)
names = uniq
check("dedup: case and repeats -> %s" % names, names == ["Calculator", "Firefox"])

py_compile.compile(DESK, doraise=True)
check("py_compile desk.py", True)

print("all good")
