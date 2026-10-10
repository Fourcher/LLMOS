#!/usr/bin/env python3
"""Host-side check that PDF conversion wordings route without the slow model:
a path gives convert_to_pdf, a described document gives which_file, and
longer sentences do not match. Run: python3 tools/test-pdf-route.py"""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402


def check(text, want):
    got = intent._files(text)
    assert got == want, f"{text!r}: got {got!r}, want {want!r}"
    print(f"ok {text!r} -> {got!r}")


def which(text):
    return ("which_file", {"request": text.strip()})


# described documents -> which_file
check("turn word doc into pdf", which("turn word doc into pdf"))
check("convert my word document to a pdf", which("convert my word document to a pdf"))
check("save the spreadsheet as pdf", which("save the spreadsheet as pdf"))
check("export my essay into a pdf", which("export my essay into a pdf"))
check("make this letter into pdf", which("make this letter into pdf"))

# it / this / that unchanged -> which_file
check("turn it into a pdf", which("turn it into a pdf"))

# a path -> convert_to_pdf
check("convert ~/a.docx to pdf", ("convert_to_pdf", {"path": "~/a.docx"}))

# anchored: a longer sentence must not match this route
r = intent._files("turn my word doc into a pdf and email it to bob")
print("turn my word doc into a pdf and email it to bob ->", r)
assert r != which("turn my word doc into a pdf and email it to bob"), r
assert not (r and r[0] == "convert_to_pdf"), r
print("ok longer sentence not matched by pdf route")

# contraction: print result only
r = intent._files("can't you turn this doc into pdf")
print("can't you turn this doc into pdf ->", r)

print("all good")
