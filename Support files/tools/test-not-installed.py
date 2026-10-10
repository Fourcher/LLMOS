#!/usr/bin/env python3
"""Host-side test: a program that is not installed is reported in plain words, not in internal tool wording.
The old text "install it with install_app first" must not reach the owner.
Run: python3 tools/test-not-installed.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent

with open(os.path.join(_ROOT, "usr/lib/llmos/llmos/tools.py"), encoding="utf-8") as f:
    src = f.read()

NEW_LINE = 'return f"error: {prog} isn\'t on this computer yet. Say “install {prog}” to get it."'
OLD_TEXT = "install it with install_app first"

assert NEW_LINE in src, "new not-installed line is missing from tools.py"
print("ok tools.py has the new not-installed line")
assert OLD_TEXT not in src, "old internal wording still present in tools.py"
print("ok old 'install it with install_app first' wording is absent from tools.py")

got = agent._shortcut_words("open_app", {}, "error: files isn't on this computer yet. Say “install files” to get it.")
want = "Files isn't on this computer yet. Say “install files” to get it."
print("actual:", repr(got))
assert got == want, f"_shortcut_words returned {got!r}"
print("ok _shortcut_words gives plain words:", got)

print("all good")
