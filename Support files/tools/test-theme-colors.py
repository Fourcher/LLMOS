#!/usr/bin/env python3
"""The textarea and switch knob in desk.css must use theme variables, not hex colours.

Hard-coded colours break the light theme: the textarea box stays near-black and the
switch knob stays white on a light track.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "..", "src", "rootfs", "usr", "share", "llmos", "desk", "desk.css")

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
TARGETS = [".form textarea", ".sw::after"]


def rules(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for m in RULE.finditer(text):
        selectors = [s.strip() for s in m.group(1).split(",")]
        yield selectors, m.group(2)


def main():
    with open(CSS, encoding="utf-8") as f:
        text = f.read()
    failures = []
    for target in TARGETS:
        body = None
        for selectors, decl in rules(text):
            if target in selectors:
                body = decl
                break
        if body is None:
            failures.append(f"{target}: rule not found")
            continue
        if "#" in body:
            failures.append(f"{target}: hex colour still present")
            continue
        if not re.search(r"var\(--[\w-]+\)", body):
            failures.append(f"{target}: no var(--...) used")
            continue
        print(f"ok {target} uses theme variables and no hex colour")
    if failures:
        for line in failures:
            print("FAIL " + line)
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
