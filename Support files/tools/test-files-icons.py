#!/usr/bin/env python3
"""Host test: list blocks with view:"icons" render as a tile grid (desk.js + desk.css)."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DESK = os.path.join(ROOT, "src", "rootfs", "usr", "share", "llmos", "desk")
JS = os.path.join(DESK, "desk.js")
CSS = os.path.join(DESK, "desk.css")

failures = []


def check(cond, msg):
    if cond:
        print("ok " + msg)
    else:
        print("FAIL " + msg)
        failures.append(msg)


with open(JS, encoding="utf-8") as f:
    js = f.read()

m = re.search(r'case "list":\s*\{(.*?)\n\s*return e;', js, re.S)
check(m is not None, "found case \"list\" block in desk.js")
if m:
    body = m.group(1)
    check('b.view === "icons"' in body and '" icons"' in body,
          "case \"list\" adds \"icons\" class when b.view === \"icons\"")
    check('" cols-"' in body, "case \"list\" keeps existing cols-N class logic")

with open(CSS, encoding="utf-8") as f:
    css = f.read()

rules = [(sel.strip(), decl) for sel, decl in re.findall(r"([^{}]+)\{([^}]*)\}", css)]
icon_rules = [(s, d) for s, d in rules if ".list.icons" in s]
check(len(icon_rules) > 0, "desk.css has .list.icons rules")
grid = [d for s, d in icon_rules if s.startswith(".list.icons") and re.search(r"display:\s*grid", d)]
check(len(grid) > 0, ".list.icons rule sets display: grid")
hexes = []
for s, d in icon_rules:
    hexes += re.findall(r"#[0-9a-fA-F]{3,8}\b", d)
check(not hexes, "no hex colours inside .list.icons rules" + (" (found %s)" % hexes if hexes else ""))

if failures:
    print("%d failure(s)" % len(failures))
    sys.exit(1)
print("all good")
