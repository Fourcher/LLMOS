#!/usr/bin/env python3
"""Host-side test of the last_saved tool: where the newest file in the owner's home is.
Run: python3 tools/test-last-saved.py  (no VM needed)."""
import os
import sys
import tempfile
import time

os.environ["LLMOS_HOME"] = tempfile.mkdtemp()      # before importing tools: config.home() reads it
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import tools, config  # noqa: E402

home = config.home()
bad = 0


def check(label, got, want_prefix=None, want=None):
    global bad
    ok = (got == want) if want is not None else got.startswith(want_prefix)
    if ok:
        print(f"ok {label}: {got}")
    else:
        bad += 1
        print(f"FAIL {label}: got {got!r}")


empty = "Nothing new was saved in the last two hours."
check("empty home", tools.last_saved({}, None), want=empty)

docs = os.path.join(home, "Documents")
os.makedirs(docs)
os.makedirs(os.path.join(home, ".hidden"))
csv = os.path.join(docs, "Budget.csv")
with open(csv, "w") as f:
    f.write("item,amount\n")
with open(os.path.join(home, ".hidden", "x"), "w") as f:
    f.write("x")
os.utime(os.path.join(home, ".hidden", "x"), (time.time() + 60, time.time() + 60))   # hidden file is newest, must be skipped
check("newest visible file", tools.last_saved({}, None), want_prefix="It's ~/Documents/Budget.csv")

three_hours = time.time() - 3 * 3600
os.utime(csv, (three_hours, three_hours))
check("file older than two hours", tools.last_saved({}, None), want=empty)

if bad:
    print(f"{bad} FAILED")
    sys.exit(1)
print("all good")
