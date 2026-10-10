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

# behaviour: rename_series must not overwrite a non-series entry that already holds the planned name,
# and its reply must name the files as they really ended up on disk.
from llmos import tools as llmos_tools  # noqa: E402

f = tempfile.mkdtemp(prefix="llmos-series-")
try:
    for n in ("x1.jpg", "x2.jpg"):
        open(os.path.join(f, n), "wb").write(b"series " + n.encode())
    # an existing entry named exactly 'Holiday 1.jpg' that rename_series does not pick up (it is not a
    # regular file, so pick() skips it); a regular file of that name would itself be swept into the series
    unrelated = os.path.join(f, "Holiday 1.jpg")
    os.mkdir(unrelated)
    keep = os.path.join(unrelated, "keep.txt")
    open(keep, "wb").write(b"owner bytes \x00\x01")
    before = open(keep, "rb").read()
    reply = str(llmos_tools.REGISTRY["rename_series"].fn({"name": "Holiday", "folder": f, "kind": "photos"}, None))
    check("series: reply is not an error", not reply.startswith("error"), reply)
    check("series: unrelated entry bytes unchanged", os.path.isfile(keep) and open(keep, "rb").read() == before)
    m = re.search(r"in .*?: (.+?) … (.+?)\. Done", reply)
    names = [m.group(1), m.group(2)] if m else []
    check("series: reply names parsed", len(names) == 2, reply)
    check("series: every name in reply exists on disk",
          bool(names) and all(os.path.lexists(os.path.join(f, n)) for n in names), reply)
    check("series: first name is not the unrelated entry", bool(names) and names[0] != "Holiday 1.jpg", reply)
    print(f"ok series reply: {reply}")
finally:
    shutil.rmtree(f, ignore_errors=True)

if fails:
    print(f"{fails} FAIL(s)")
    sys.exit(1)
print("all good")
