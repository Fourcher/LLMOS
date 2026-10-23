#!/usr/bin/env python3
"""The self-development loop (tools/selfdev.py) keeps its seatbelt. It parses a model's edits, applies them to the real
files ONLY while the test suite runs and always restores them, rejects edits that don't match, stages a tested change
rather than shipping it, and NEVER ships on its own (applying, and shipping via OTA, are separate human steps). This
guards those properties against drift. Does NOT run the full suite (do_task does). Run: python3 tools/test-selfdev.py"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import selfdev  # noqa: E402

fails = 0


def check(c, w):
    global fails
    print(("  ok   " if c else "  FAIL ") + w)
    if not c:
        fails += 1


# --- parse a model's edit blocks ---
text = ("blah\n=== FILE: src/x.py\n<<<<<<< SEARCH\nold line\n=======\nnew line\n>>>>>>> REPLACE\n"
        "=== FILE: tools/y.py\n<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n")
edits = selfdev.parse_edits(text)
check(len(edits) == 2 and edits[0]["path"] == "src/x.py" and edits[0]["search"] == "old line"
      and edits[1]["replace"] == "bar", "parses each FILE/SEARCH/REPLACE block")
check(selfdev.parse_edits("no blocks here") == [], "chatter with no blocks yields no edits")

# --- apply to the real file transiently, then restore puts it back byte-for-byte ---
rel = "run/selfdev-selftest.py"
full = os.path.join(ROOT, rel)
os.makedirs(os.path.dirname(full), exist_ok=True)
original = "alpha\nbeta\nbeta\n"
open(full, "w").write(original)
try:
    applied, probs, backups, newtext = selfdev.apply_live([{"path": rel, "search": "alpha", "replace": "ALPHA"}])
    check(applied == 1 and open(full).read().startswith("ALPHA"), "applies a matching edit to the real file")
    check(backups.get(rel) == original, "it backs up the original first")
    selfdev.restore(backups)
    check(open(full).read() == original, "restore() puts the file back exactly as it was")
    _, p2, _, _ = selfdev.apply_live([{"path": rel, "search": "beta", "replace": "B"}])
    selfdev.restore({rel: original})
    check(p2 and "unique" in p2[0], "rejects an edit whose SEARCH text is not unique")
    _, p3, _, _ = selfdev.apply_live([{"path": "no/such/file.py", "search": "x", "replace": "y"}])
    check(p3 and "no such file" in p3[0], "rejects an edit to a missing file")
finally:
    os.remove(full)

# --- the seatbelt, by static analysis of the source ---
src = open(os.path.join(HERE, "selfdev.py"), encoding="utf-8").read()
tree = ast.parse(src)
funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
do_task_src = ast.get_source_segment(src, funcs["do_task"])
check("ota" not in do_task_src and "publish" not in do_task_src, "do_task never ships (no OTA / publish in it)")
check("finally:" in do_task_src and "restore(backups)" in do_task_src,
      "do_task always restores the live source after the run (edited only transiently)")
check("if not new_fails:" in do_task_src and 'json.dump' in do_task_src and "baseline_fails()" in do_task_src,
      "a change is staged only when it adds no NEW failures beyond the clean-tree baseline")
rt = ast.get_source_segment(src, funcs["run_tests"])
check('l.startswith("FAIL ")' in rt, "run_tests reports exactly which test files FAILED (for the baseline comparison)")
check("def apply_staged" in src and 'json.load(open(sj)).get("files"' in ast.get_source_segment(src, funcs["apply_staged"]),
      "writing the tested change to the real source is a separate, explicit step")
check("Never weaken a safety check" in src, "the model is told never to weaken a safeguard")
check("config.cloud()" in src and "cloud_chat" in src, "the loop uses the configured online coder when there is one")
check("worktree" not in src, "no leftover git-worktree path (the repo root is the parent dir; that approach was wrong)")

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
