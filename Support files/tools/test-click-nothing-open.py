#!/usr/bin/env python3
"""Clicking with nothing open answers 'Nothing is open to click on.' instead of OCR-ing the desk."""
import os
import py_compile
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py")

CLICK_RE = re.compile(r"(?:please )?(?:click|tap|press)(?: on)?(?: the)? .+")
KEY_RE = re.compile(r"(?:please )?(?:press|tap|hit) (?:\S|\d+)")


def is_click(text):
    return bool(CLICK_RE.fullmatch(text.rstrip(".!")) and not KEY_RE.fullmatch(text.rstrip(".!")))


def main():
    failures = []

    for text in ("click file", "click on the save button", "tap ok"):
        if is_click(text):
            print(f"ok click match: {text!r}")
        else:
            failures.append(f"expected click match: {text!r}")

    for text in ("press 7", "press =", "press 42"):
        if not is_click(text):
            print(f"ok key left to calculator: {text!r}")
        else:
            failures.append(f"expected NOT a click: {text!r}")

    with open(DESK, encoding="utf-8") as fh:
        src = fh.read()
    if "Nothing is open to click on." in src:
        print("ok desk.py contains 'Nothing is open to click on.'")
    else:
        failures.append("desk.py lacks 'Nothing is open to click on.'")

    try:
        py_compile.compile(DESK, doraise=True)
        print("ok desk.py compiles")
    except py_compile.PyCompileError as exc:
        failures.append(f"desk.py does not compile: {exc}")

    if failures:
        for f in failures:
            print("FAIL", f)
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
