#!/usr/bin/env python3
"""Host-side unit test: "show my biggest files" in the owner's home skips hidden files and folders.
Hidden entries (names starting with ".") such as ~/.ash_history or ~/.cache are not the owner's files.
Run: python3 tools/test-biggest-hidden.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
import tempfile

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

home = tempfile.mkdtemp()
os.environ["LLMOS_HOME"] = home

from llmos import tools  # noqa: E402


def _write(rel, size):
    p = os.path.join(home, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * size)


_write(".ash_history", 10 * 1024)
_write(".cache/big.bin", 50 * 1024)
_write("Documents/report.pdf", 20 * 1024)

result = tools.REGISTRY["biggest_files"].fn({"folder": "~"}, None)
print(f"result: {result}")


def _check(label, cond):
    if not cond:
        print(f"FAIL {label}")
        sys.exit(1)
    print(f"ok   {label}")


_check("report.pdf is listed", "report.pdf" in result)
_check(".ash_history is not listed", ".ash_history" not in result)
_check("big.bin (inside hidden folder) is not listed", "big.bin" not in result)
print("all good")
