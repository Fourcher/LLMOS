#!/usr/bin/env python3
"""Host-side test of two phrasings: "why is my disk full" style questions route to storage (llmos/desk.py), and
"open my bookmarks" / "show me the bookmarks" open Firefox's Library window through the wm.KEYS "bookmarks" entry.
Run: python3 tools/test-disk-bookmarks.py"""
import os
import re
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
DESK = os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py")
WM = os.path.join(_ROOT, "usr/lib/llmos/llmos/wm.py")

STORAGE = (r"(?:open (?:the )?)?(?:storage|disk space|disk usage|free (?:up )?(?:some )?space|(?:my )?disk is full|clean ?up(?: the computer| my computer| disk)?|"
           r"what'?s (?:using|filling|taking up) (?:my |the )?(?:disk|space|storage)|running out of space|"
           r"why(?: is|'s) (?:my |the )?(?:disk|drive|storage|computer|hard drive) (?:so )?full|why am i (?:out of|running out of|low on) (?:space|storage)|"
           r"how much (?:free |disk |storage )?(?:space|storage)(?: do i have| is left| left| have i got)?|how full is (?:my |the )?(?:disk|computer|drive))[?.!]*")

BROWSER = (r"(?P<zin>(?:make )?(?:the )?(?:text|page|words|font) bigger on (?:this|the) (?:page|website|site)|zoom in(?: on)?(?: (?:this|the) (?:page|website|site))?)|"
           r"(?P<zout>(?:make )?(?:the )?(?:text|page|words|font) smaller on (?:this|the) (?:page|website|site)|zoom out(?: on)?(?: (?:this|the) (?:page|website|site))?)|"
           r"(?P<bm>bookmark (?:this|it|this page|the page|this site)|add (?:this|it|this page) to (?:my )?(?:bookmarks|favou?rites)|save this page)|"
           r"(?P<bms>(?:open|show)(?: me)? (?:my |the )?(?:bookmarks|favou?rites))")

fails = 0


def check(cond, msg):
    global fails
    if cond:
        print("ok " + msg)
    else:
        fails += 1
        print("FAIL " + msg)


for phrase in ["why is my disk full", "why's the drive so full", "why am i running out of space"]:
    check(re.fullmatch(STORAGE, phrase) is not None, f"storage matches {phrase!r}")

for phrase, group in [("open my bookmarks", "bms"), ("show me the bookmarks", "bms"),
                      ("bookmark this page", "bm"), ("zoom in", "zin")]:
    m = re.fullmatch(BROWSER, phrase)
    check(m is not None and m.group(group) is not None, f"browser {phrase!r} -> group {group}")

wm_src = open(WM, encoding="utf-8").read()
check('"bookmarks":' in wm_src, "wm.py has the \"bookmarks\" KEYS entry")
desk_src = open(DESK, encoding="utf-8").read()
check("Your bookmarks are open in the browser." in desk_src, "desk.py has the bookmarks reply")
check('why(?: is|\'s) (?:my |the )?(?:disk|drive|storage|computer|hard drive) (?:so )?full' in desk_src,
      "desk.py storage regex has the why-full alternative")
check('(?P<bms>(?:open|show)(?: me)? (?:my |the )?(?:bookmarks|favou?rites))' in desk_src,
      "desk.py browser regex has the bms alternative")

import py_compile  # noqa: E402
for path in (DESK, WM):
    try:
        py_compile.compile(path, doraise=True)
        check(True, "py_compile " + os.path.basename(path))
    except py_compile.PyCompileError as e:
        check(False, "py_compile " + os.path.basename(path) + ": " + str(e))

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
