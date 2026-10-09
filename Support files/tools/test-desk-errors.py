#!/usr/bin/env python3
"""Host-side test: the desk never shows a raw "Error: <exception>" to the owner.
Every error toast/reply in desk.py goes through agent._plain_error(str(e)).
Run: python3 tools/test-desk-errors.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

DESK = os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py")

from llmos import agent

failures = []


def check(name, ok, detail=""):
    if ok:
        print("ok", name)
    else:
        print("FAIL", name, detail)
        failures.append(name)


with open(DESK, encoding="utf-8") as f:
    src = f.read()

check("no raw T('error'): {e} left in desk.py",
      "T('error')}: {e}" not in src)
n = src.count("agent._plain_error(")
check("agent._plain_error( used at least 8 times in desk.py", n >= 8, "count=%d" % n)

got = agent._plain_error(str(OSError(2, "No such file or directory")))
check("plain error for ENOENT", got == "That file or folder isn't there", "got=%r" % got)

if failures:
    print("FAILED:", ", ".join(failures))
    sys.exit(1)
print("all good")
