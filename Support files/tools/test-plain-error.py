#!/usr/bin/env python3
"""Host-side unit test for tool errors shown to the owner: errno codes, Python exception names and
'no such tool' must become plain words. Run: python3 tools/test-plain-error.py (no VM needed).
Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent

CASES = [
    ("error: no such tool 'foo'", "I can't do that on this computer yet."),
    ("error: could not read a.txt: [Errno 2] No such file or directory: '/root/a.txt'",
     "Could not read a.txt: that file or folder isn't there."),
    ("error: [Errno 13] Permission denied: '/etc/shadow'", "The system won't allow that."),
    ("error: ValueError: bad thing", "Bad thing."),
    ("error: the disk is busy", "The disk is busy."),
]

failed = 0
for raw, want in CASES:
    got = agent._shortcut_words("x", {}, raw)
    if got == want:
        print("ok", repr(raw), "->", repr(got))
    else:
        failed += 1
        print("FAIL", repr(raw), "got", repr(got), "want", repr(want))

if failed:
    print("%d failed" % failed)
    sys.exit(1)
print("all good")
