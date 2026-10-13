#!/usr/bin/env python3
"""Host-side test: find_by_meaning falls back to find_files when meaning search is not available.
(a) meaning unavailable: find_by_meaning finds the file by name through find_files, a no-match gives
    find_files' own reply, an empty query gives find_files' empty reply, and the runtime message is gone;
(b) meaning available: find_by_meaning still calls the meaning code (recorded by patches), not find_files.
Run: python3 tools/test-find-fallback.py  (no VM needed). Exit status 0 = pass."""
import os
import shutil
import sys
import tempfile

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, meaning

failures = []


def check(label, got, want_in=None, want_not_in=None):
    ok = True
    if want_in is not None and want_in not in got:
        ok = False
    if want_not_in is not None and want_not_in in got:
        ok = False
    if ok:
        print(f"ok {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}: got {got!r}")


class Ctx:
    def __init__(self):
        self.shown = []
        self.statuses = []

    def show_ui(self, spec):
        self.shown.append(spec)

    def status(self, text):
        self.statuses.append(text)


home = tempfile.mkdtemp(prefix="llmos-find-fallback-")
try:
    for name in ("taxes-2025.pdf", "resume.docx"):
        with open(os.path.join(home, name), "w") as f:
            f.write("x")

    real_home = tools.config.home
    tools.config.home = lambda: home
    real_available = meaning.available
    try:
        # (a) meaning search not available
        meaning.available = lambda: False
        ctx = Ctx()

        r = tools.find_by_meaning({"query": "taxes", "kind": "documents"}, ctx)
        check("unavailable: taxes/documents finds taxes-2025.pdf", r, want_in="1 file(s) are listed",
              want_not_in="newer model runtime")
        titles = [i["title"] for s in ctx.shown for b in s["blocks"] for i in b["items"]]
        check("unavailable: the listed file is taxes-2025.pdf", " ".join(titles), want_in="taxes-2025.pdf")

        ctx = Ctx()
        r = tools.find_by_meaning({"query": "resume", "kind": "any"}, ctx)
        check("unavailable: resume/any finds resume.docx", r, want_in="1 file(s) are listed",
              want_not_in="newer model runtime")
        titles = [i["title"] for s in ctx.shown for b in s["blocks"] for i in b["items"]]
        check("unavailable: the listed file is resume.docx", " ".join(titles), want_in="resume.docx")

        ctx = Ctx()
        r = tools.find_by_meaning({"query": "zzzqqq", "kind": "any"}, ctx)
        check("unavailable: no match gives find_files' no-match reply", r,
              want_in="no file in the home folder matches 'zzzqqq'", want_not_in="newer model runtime")

        ctx = Ctx()
        r = tools.find_by_meaning({"query": "", "kind": "any"}, ctx)
        want_empty = tools.find_files({"query": ""}, Ctx())
        check("unavailable: empty query gives find_files' empty reply", r, want_in=want_empty)
        check("unavailable: empty query is not the old error", r, want_not_in="what should I look for")

        # (b) meaning search available: the meaning code runs, find_files does not
        meaning.available = lambda: True
        calls = []
        real_ready, real_index, real_search, real_cands = meaning.ready, meaning.index, meaning.search, meaning._candidates
        meaning.ready = lambda vision=False: True
        meaning.index = lambda kinds, limit=None, progress=None: calls.append(("index", tuple(kinds)))
        meaning._candidates = lambda kinds: []
        meaning.search = lambda q, kind="any", matches_only=False: (calls.append(("search", q, kind)) or [])
        real_find_files = tools.find_files
        tools.find_files = lambda a, ctx: (_ for _ in ()).throw(AssertionError("find_files called while available"))
        try:
            ctx = Ctx()
            r = tools.find_by_meaning({"query": "taxes", "kind": "documents"}, ctx)
            check("available: meaning search is called", str(calls), want_in="('search', 'taxes', 'documents')")
            check("available: reply is the meaning reply", r, want_in="nothing about 'taxes' among your files")
        finally:
            tools.find_files = real_find_files
            meaning.ready, meaning.index, meaning.search, meaning._candidates = real_ready, real_index, real_search, real_cands
    finally:
        tools.config.home = real_home
        meaning.available = real_available
finally:
    shutil.rmtree(home, ignore_errors=True)

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
