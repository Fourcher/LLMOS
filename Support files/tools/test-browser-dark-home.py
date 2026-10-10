#!/usr/bin/env python3
"""Browser dark-mode phrasing and browser home-page how-to match; desk.py carries both fragments."""
import os
import py_compile
import re

DARK = r"(?:make|turn|switch|put|set) (?:the |my )?(?:web )?(?:browser|firefox|internet)(?: to)? dark(?: mode)?|dark mode (?:for|in|on) (?:the |my )?(?:browser|firefox)"
HOME = r"(?:how (?:do|can) i )?(?:change|set|pick) (?:the |my )?(?:browser'?s? |firefox'?s? )?(?:home ?page|start ?page|start-up page)"

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.normpath(os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py"))

for s in ["make browser dark", "turn firefox dark", "dark mode for the browser", "change homepage",
          "how do i change my browser's home page", "set the start page"]:
    tgt = DARK if ("dark" in s and "dark" in s) and "page" not in s else HOME
    if "dark" in s:
        ok = re.fullmatch(DARK, s.rstrip(".!")) is not None
    else:
        ok = re.fullmatch(HOME, s.rstrip(".!")) is not None
    assert ok, f"no fullmatch: {s!r}"
    print("ok", repr(s))

for s in ["make the browser bigger", "change my password"]:
    assert re.fullmatch(DARK, s) is None and re.fullmatch(HOME, s) is None, f"should not match: {s!r}"
    print("ok no-match", repr(s))

src = open(DESK, encoding="utf-8").read()
frag1 = 'line = low = "dark mode"'
frag2 = "(?:how (?:do|can) i )?(?:change|set|pick) (?:the |my )?(?:browser'?s? |firefox'?s? )?(?:home ?page|start ?page|start-up page)"
assert frag1 in src, "dark-mode fragment missing from desk.py"
assert frag2 in src, "home-page fragment missing from desk.py"
print("ok desk.py fragments present")

py_compile.compile(DESK, doraise=True)
print("ok py_compile desk.py")
print("all good")
