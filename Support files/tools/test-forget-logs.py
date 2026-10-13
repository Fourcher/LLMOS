#!/usr/bin/env python3
"""Host-side test of the owner's clear options: store.clear_routines / store.clear_audit, the audit log trim
(newest ~1 MB kept once it would pass 2 MB, mode 0600, a symlink never followed), and the desk phrases that call them.
Run: python3 tools/test-forget-logs.py"""
import ast
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import py_compile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "src/rootfs")
_LLMOS = os.path.join(_ROOT, "usr/lib/llmos")
_DESK = os.path.join(_LLMOS, "llmos", "desk.py")
_STORE = os.path.join(_LLMOS, "llmos", "store.py")

home = tempfile.mkdtemp(prefix="llmos-forget-home-")
etc = os.path.join(home, "etc")
os.makedirs(etc)
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=etc, LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
sys.path.insert(0, _LLMOS)
from llmos import store  # noqa: E402

MAX, KEEP = store.AUDIT_MAX, store.AUDIT_KEEP
assert MAX == 2 * 1024 * 1024 and KEEP == 1024 * 1024, "audit limits changed"
LOG = os.path.join(home, ".llmos", "audit.log")
ROUT = os.path.join(home, ".llmos", "routines.json")


def check(cond, label):
    assert cond, "FAIL: " + label
    print("ok " + label)


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


try:
    # routines
    check(store.clear_routines() is True, "clear_routines with routines.json missing succeeds quietly")
    store.save_routine("open the notes", [{"tool": "open_app", "args": {"app": "notes"}}])
    check(store.routine("open the notes") is not None, "a routine is saved before clearing")
    check(store.clear_routines() is True and not os.path.exists(ROUT), "clear_routines removes routines.json")
    check(store.routine("open the notes") is None and store.routines() == {}, "routines are gone after clearing")

    # audit: missing and cleared
    check(store.clear_audit() is True, "clear_audit with audit.log missing succeeds quietly")
    store.audit("t_one", {"q": "first"}, "done")
    check(os.path.getsize(LOG) > 0, "an audit entry is written")
    check(store.clear_audit() is True and os.path.getsize(LOG) == 0, "clear_audit empties audit.log")
    check(mode(LOG) == 0o600, "cleared audit.log keeps mode 0600")
    store.audit("t_after", {}, "x")
    check(len(open(LOG, encoding="utf-8").read().splitlines()) == 1, "appends work again after clearing")
    store.clear_audit()

    # trim: exactly 2 MB of 1024-byte lines, then one more append
    prefix_len = len('{"id": "000000", "pad": "')
    pad = "x" * (1024 - prefix_len - len('"}\n'))
    n_lines = MAX // 1024
    with open(LOG, "w", encoding="utf-8") as f:
        for i in range(n_lines):
            f.write('{"id": "%06d", "pad": "%s"}\n' % (i, pad))
    check(os.path.getsize(LOG) == MAX, "audit.log is exactly 2 MB before the next append")
    store.audit("t_new", {"q": "newest"}, "ok")
    size = os.path.getsize(LOG)
    check(size <= MAX, "after the trim audit.log is <= 2 MB (%d bytes)" % size)
    check(size <= KEEP + 1024, "after the trim only about 1 MB is kept (%d bytes)" % size)
    check(mode(LOG) == 0o600, "trimmed audit.log has mode 0600")
    lines = open(LOG, encoding="utf-8").read().splitlines()
    recs = [json.loads(x) for x in lines]  # every kept line is whole JSON
    check(recs[-1]["tool"] == "t_new", "the new entry is the last line")
    ids = [int(r["id"]) for r in recs[:-1]]
    check(ids and ids[-1] == n_lines - 1, "the newest old line is kept")
    check(ids == list(range(ids[0], n_lines)), "kept lines are consecutive, no gaps or partial lines")
    check(ids[0] > 0, "the oldest lines were dropped")
    check(all(r.get("id") is not None or r.get("tool") for r in recs), "no broken lines in the trimmed log")

    # under the limit: no trim
    store.clear_audit()
    store.audit("t_a", {}, "1")
    store.audit("t_b", {}, "2")
    check(len(open(LOG, encoding="utf-8").read().splitlines()) == 2, "a small log is appended to, not trimmed")

    # symlink: never followed, never rewritten
    store.clear_audit()
    target = os.path.join(home, "outside.txt")
    body = ("y" * 1000 + "\n") * (MAX // 1000 + 10)
    with open(target, "w", encoding="utf-8") as f:
        f.write(body)
    os.remove(LOG) if os.path.lexists(LOG) else None
    os.symlink(target, LOG)
    before = open(target, encoding="utf-8").read()
    store.audit("t_link", {}, "linked")
    after = open(target, encoding="utf-8").read()
    check(os.path.islink(LOG), "audit.log is still a symlink after an append")
    check(after == before, "an append to a symlinked audit.log is skipped: the link target is NOT written")
    check(store.audit("t_link2", {}, "linked") is None, "the append to a symlinked audit.log returns without error")
    check(store.clear_audit() is False, "clear_audit refuses a symlinked audit.log")
    check(open(target, encoding="utf-8").read() == after, "clear_audit leaves the link target untouched")
    os.remove(LOG)

    # desk phrases, read from the source with ast (desk.py needs GTK to import)
    with open(_DESK, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    pats = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "fullmatch" \
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            pats.append(node.args[0].value)
    rout = [p for p in pats if "routines" in p]
    audit_p = [p for p in pats if "activity" in p]
    check(len(rout) == 1 and len(audit_p) == 1, "desk has one routines pattern and one activity-log pattern")
    rx_r = re.compile(rout[0])
    rx_a = re.compile(audit_p[0])
    for p in ["forget my routines", "clear my routines", "delete my routines", "forget the routines", "clear routines"]:
        check(rx_r.fullmatch(p) is not None, "routine phrase matches: %r" % p)
    for p in ["clear the activity log", "clear the audit log", "delete my activity log", "forget what you did"]:
        check(rx_a.fullmatch(p) is not None, "activity phrase matches: %r" % p)
    for p in ["forget my routines now", "forget my wifi", "clear my history", "forget everything we said", "clear the chat"]:
        check(rx_r.fullmatch(p) is None and rx_a.fullmatch(p) is None, "phrase does not match a clear option: %r" % p)
    check("store.clear_routines()" in src and "store.clear_audit()" in src, "desk calls store.clear_routines and store.clear_audit")
    check("Done. I've forgotten the routines I learned." in src, "routine reply text is in desk.py")
    check("Done. The activity log is empty." in src, "activity log reply text is in desk.py")
    fa = src.index("n = conversation.forget_all()")
    check("clear_routines" not in src[fa:fa + 300] and "clear_audit" not in src[fa:fa + 300],
          "'forget everything' still only clears the conversations (left unchanged)")

    py_compile.compile(_STORE, doraise=True)
    py_compile.compile(_DESK, doraise=True)
    print("ok store.py and desk.py compile")
finally:
    shutil.rmtree(home, ignore_errors=True)
print("all good")
