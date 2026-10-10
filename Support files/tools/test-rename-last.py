#!/usr/bin/env python3
"""Host-side unit test: "make a folder called Taxes 2026" then "call it Budget instead" renames that folder.
The rename goes straight to rename_file with name "it"; the tool resolves it to the folder made last.
Run: python3 tools/test-rename-last.py  (no VM needed). Exit status 0 = pass."""
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


class FakeCtx:
    def __getattr__(self, name):
        return lambda *a, **k: None


ctx = FakeCtx()
docs = os.path.join(home, "Documents")
os.makedirs(docs, exist_ok=True)

r = tools.REGISTRY["make_folder"].fn({"name": "Taxes 2026"}, ctx)
print("make_folder:", r)
made = os.path.join(docs, "Taxes 2026")
assert os.path.isdir(made), "Taxes 2026 was not made"

r = tools.REGISTRY["rename_file"].fn({"name": "it", "to": "Budget"}, ctx)
print("rename_file:", r)
assert not os.path.exists(made), "Taxes 2026 still exists"
assert os.path.isdir(os.path.join(docs, "Budget")), "Budget folder does not exist"
print("ok rename of the folder made last")

tools._LAST_MADE["at"] = 0
r = tools.REGISTRY["rename_file"].fn({"name": "it", "to": "X"}, ctx)
print("rename_file (stale):", r)
assert r.startswith("error: which one?"), r
print("ok stale reference refused")
print("all good")
