#!/usr/bin/env python3
"""Host-side unit test: a second "make a spreadsheet called Budget" must not overwrite the first file,
and the reply says "opened it" only when the file was actually opened (open=false here, so never).
Run: python3 tools/test-spreadsheet-safe.py  (no VM needed). Exit status 0 = pass."""
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

docs = os.path.join(home, "Documents")
fn = tools.REGISTRY["make_spreadsheet"].fn


def _exists(stem):
    return [e for e in (stem + ".csv", stem + ".xlsx") if os.path.exists(os.path.join(docs, e))]


def _read(name):
    with open(os.path.join(docs, name), "rb") as f:
        return f.read()


r1 = str(fn({"name": "Budget", "rows": [["a", "b"]], "open": False}, None))
first = _exists("Budget")
assert first, f"first file missing: {r1}"
first_name = first[0]
first_bytes = _read(first_name)
print("ok first:", r1)

r2 = str(fn({"name": "Budget", "rows": [["x", "y"], ["1", "2"]], "open": False}, None))
second = _exists("Budget 2")
assert second, f"second file missing: {r2}"
assert _read(first_name) == first_bytes, "first Budget file was overwritten"
print("ok second:", r2)

assert "opened it" not in r1 and "opened it" not in r2, "reply claims opened it although open=false"
print("ok reply does not claim opened")

print("all good")
