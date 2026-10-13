#!/usr/bin/env python3
"""Keyboard focus must stay visible in desk.css, including forced-colours / high-contrast themes.

The base text-input rule removes the UA outline (so mouse clicks show none). Focus for keyboard users
comes from a :focus-visible outline in the accent colour, and a forced-colors block gives the outline a
system colour, because box-shadow focus rings are dropped in those themes.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "..", "src", "rootfs", "usr", "share", "llmos", "desk", "desk.css")

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
REQUIRED = ["input", "button", "textarea", "select"]
# The base text-input rule keeps its outline:none on purpose: text inputs match :focus-visible on a
# mouse click too, so scoping it to :focus:not(:focus-visible) would show a ring on click. The new
# :focus-visible outline (later in the file, equal or higher specificity) replaces it for keyboard focus.
EXEMPT_SELECTOR = "input[type=text], input[type=password], input[type=email], select, textarea"


def rules(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for m in RULE.finditer(text):
        head = m.group(1).strip()
        selectors = [s.strip() for s in head.split(",")]
        # strip any @media prefix from the first selector so block rules are still seen
        if "@" in head:
            head = head.split("{")[-1]
            selectors = [s.strip() for s in head.split(",")]
        yield head, selectors, m.group(2)


def media_blocks(text):
    """Return the body text of every @media (forced-colors: active) block (brace-matched)."""
    out = []
    for m in re.finditer(r"@media\s*\(\s*forced-colors:\s*active\s*\)\s*\{", text):
        depth = 1
        i = m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out.append(text[m.end():i - 1])
    return out


def main():
    with open(CSS, encoding="utf-8") as f:
        text = f.read()
    failures = []

    # 1. a :focus-visible rule covers input/button/textarea/select with a non-none outline
    fv_ok = False
    for head, selectors, decl in rules(text):
        fv = [s for s in selectors if ":focus-visible" in s]
        if not fv:
            continue
        covered = all(any(name in s for s in fv) for name in REQUIRED)
        outline = re.search(r"outline\s*:\s*([^;]+)", decl)
        if covered and outline and outline.group(1).strip() not in ("none", "0"):
            fv_ok = True
            break
    if fv_ok:
        print("ok :focus-visible rule covers input/button/textarea/select with an outline")
    else:
        failures.append(":focus-visible rule with a non-none outline covering input/button/textarea/select not found")

    # 2. a forced-colors block gives :focus-visible controls an outline
    fc_ok = False
    for body in media_blocks(text):
        for m in RULE.finditer(body):
            sel = m.group(1)
            if ":focus-visible" in sel and re.search(r"outline\s*:\s*2px\s+solid\s+CanvasText", m.group(2)):
                fc_ok = True
    if fc_ok:
        print("ok @media (forced-colors: active) gives :focus-visible controls an outline")
    else:
        failures.append("no @media (forced-colors: active) block with a :focus-visible outline")

    # 3. no bare outline:none outside :focus:not(:focus-visible) selectors (except the exempt base rule)
    bare = []
    for head, selectors, decl in rules(text):
        if not re.search(r"outline\s*:\s*(none|0)\s*(;|$)", decl):
            continue
        if all(":focus:not(:focus-visible)" in s for s in selectors):
            continue
        if head == EXEMPT_SELECTOR:
            continue
        bare.append(head)
    if not bare:
        print("ok no bare outline:none outside :focus:not(:focus-visible) (base text-input rule exempt)")
    else:
        failures.append("bare outline:none remains: " + " | ".join(bare))

    for f in failures:
        print("FAIL " + f)
    if failures:
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
