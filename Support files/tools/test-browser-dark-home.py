#!/usr/bin/env python3
"""Browser dark-mode phrasing (intent.match) and browser home-page how-to match; desk.py carries the home-page fragment."""
import os
import py_compile
import re
import sys

HOME = r"(?:how (?:do|can) i )?(?:change|set|pick) (?:the |my )?(?:browser'?s? |firefox'?s? )?(?:home ?page|start ?page|start-up page)"

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(HERE, "..", "src", "rootfs")
sys.path.insert(0, os.path.normpath(os.path.join(_ROOT, "usr", "lib", "llmos")))
os.environ.setdefault("LLMOS_SHARE", os.path.normpath(os.path.join(_ROOT, "usr", "share", "llmos")))
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True

DESK = os.path.normpath(os.path.join(_ROOT, "usr", "lib", "llmos", "llmos", "desk.py"))

for s in ["make browser dark", "turn firefox dark", "dark mode for the browser"]:
    got = intent.match(s)
    assert got == ("set_appearance", {"theme": "dark"}), f"{s!r} -> {got!r}"
    print("ok dark", repr(s), got)

for s in ["make the browser bigger"]:
    got = intent.match(s)
    assert not (got and got[0] == "set_appearance" and got[1].get("theme") == "dark"), f"{s!r} -> {got!r}"
    print("ok not-dark", repr(s), got)

for s in ["change homepage", "how do i change my browser's home page", "set the start page"]:
    assert re.fullmatch(HOME, s.rstrip(".!")) is not None, f"no fullmatch: {s!r}"
    print("ok home", repr(s))

src = open(DESK, encoding="utf-8").read()
assert 'line = low = "dark mode"' not in src, "desk.py still rewrites to dark mode"
assert "(?:how (?:do|can) i )?(?:change|set|pick) (?:the |my )?(?:browser'?s? |firefox'?s? )?(?:home ?page|start ?page|start-up page)" in src, "home-page fragment missing from desk.py"
print("ok desk.py: no dark-mode rewrite, home-page fragment present")

py_compile.compile(DESK, doraise=True)
print("ok py_compile desk.py")
print("all good")
