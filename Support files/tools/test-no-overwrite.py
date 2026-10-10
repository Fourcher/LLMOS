#!/usr/bin/env python3
"""Host-side test that the tools which write a new file never overwrite the owner's files:
_free_path (llmos/tools.py) picks 'name.ext', then 'name 2.ext', 'name 3.ext' ... ; and the
edit_image, edit_images, convert_to_pdf and rename_series bodies all go through it.
Run: python3 tools/test-no-overwrite.py"""
import os
import re
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos.tools import _free_path  # noqa: E402

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print(f"ok {name}")
    else:
        fails += 1
        print(f"FAIL {name} {detail}")


d = tempfile.mkdtemp(prefix="llmos-nooverwrite-")
try:
    p = os.path.join(d, "a.pdf")
    check("free path: nonexistent is unchanged", _free_path(p) == p, _free_path(p))

    open(p, "w").close()
    check("free path: existing a.pdf -> a 2.pdf", _free_path(p) == os.path.join(d, "a 2.pdf"), _free_path(p))

    open(os.path.join(d, "a 2.pdf"), "w").close()
    check("free path: a.pdf and a 2.pdf exist -> a 3.pdf", _free_path(p) == os.path.join(d, "a 3.pdf"), _free_path(p))
finally:
    shutil.rmtree(d, ignore_errors=True)

tools_src = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/tools.py"), encoding="utf-8").read()
for name in ("edit_image", "edit_images", "convert_to_pdf", "rename_series"):
    m = re.search(rf"\ndef {name}\(", tools_src)
    if not m:
        check(f"{name} exists", False, "def not found")
        continue
    end = tools_src.find("\n@tool(", m.end())
    body = tools_src[m.end(): end if end != -1 else len(tools_src)]
    check(f"{name} uses _free_path(", "_free_path(" in body)

if fails:
    print(f"{fails} FAIL(s)")
    sys.exit(1)
print("all good")
