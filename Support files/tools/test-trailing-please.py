#!/usr/bin/env python3
"""Host-side test of the trailing-filler fallback in llmos/intent.py match():
"open firefox please" gets the same route as "open firefox" when the plain text
matched nothing. Phrases come from the routed CASES of test-intent.py.
Run: python3 tools/test-trailing-please.py  (no VM needed)."""
import ast
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))   # the model catalog
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

FILLERS = [" please", ", please", " thanks"]
N_PHRASES = 40


def routed_phrases():
    """Keys of CASES in test-intent.py whose expected value is a route (not None), in file order."""
    with open(os.path.join(_HERE, "test-intent.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CASES" for t in node.targets):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and not (isinstance(v, ast.Constant) and v.value is None):
                    out.append(k.value)
    return out


phrases = []
for p in routed_phrases():
    if p.lower().rstrip(" .!?").endswith(("please", "thanks", "pls")):
        continue
    if intent.match(p) is None:
        continue
    phrases.append(p)
    if len(phrases) == N_PHRASES:
        break

bad = 0
gained = 0
kept = 0
checked = 0
if len(phrases) < N_PHRASES:
    bad += 1
    print(f"FAIL only {len(phrases)} routed phrases found, wanted {N_PHRASES}")

for p in phrases:
    want = intent.match(p)
    for f in FILLERS:
        form = p + f
        checked += 1
        first_pass = intent._fix_schedule(intent._match(form))   # the plain first pass, before the fallback
        got = intent.match(form)
        if first_pass is not None:
            # the first pass matched (the filler may sit inside a name or path): its result is kept unchanged
            if got != first_pass:
                bad += 1
                print(f"CHANGED {form!r}: first pass {first_pass!r} now {got!r}")
            else:
                kept += 1
        elif got != want:
            bad += 1
            print(f"MISMATCH {form!r}\n   got    {got!r}\n   wanted {want!r}")
        else:
            gained += 1

# the filler-only and empty shapes give nothing, and a filler that is part of a name is not stripped
for text in ["please", "thanks", "  please  ", "", None]:
    checked += 1
    if intent.match(text) is not None:
        bad += 1
        print(f"FAIL {text!r} should be None, got {intent.match(text)!r}")
checked += 1
if intent.match("open /tmp/please.txt") != intent._fix_schedule(intent._match("open /tmp/please.txt")):
    bad += 1
    print("FAIL 'open /tmp/please.txt' changed by the fallback")

print(f"checked {checked} forms of {len(phrases)} routed phrases x {len(FILLERS)} fillers")
print(f"gained a route (plain first pass gave None, now the phrase's route): {gained}")
print(f"kept unchanged (first pass already matched, filler left as typed): {kept}")
if bad:
    print(f"{bad} FAILED")
    sys.exit(1)
print("ok trailing filler matches the phrase's route")
print("all good")
