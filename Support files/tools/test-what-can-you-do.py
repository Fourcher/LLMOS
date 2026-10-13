#!/usr/bin/env python3
"""Host-side test of the "what can you do" reply (desk.py). The reply is read from desk.py with ast (desk.py needs GTK
to import). Checks: at most 2 sentences, at most 320 characters, and every example phrase quoted in it routes at once
(intent.match, everyday.MATCH, or desk's _LOCK_WORDS). Run: python3 tools/test-what-can-you-do.py"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LLMOS = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos")
DESK = os.path.join(LLMOS, "llmos", "desk.py")
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


tree = ast.parse(open(DESK, encoding="utf-8").read())
reply = None
lock_words = None
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("Here's what I can do"):
        reply = node.value
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LOCK_WORDS" for t in node.targets):
        lock_words = ast.literal_eval(node.value)
check(reply is not None, "reply found in desk.py")
reply = reply or ""
print(f"     reply ({len(reply)} chars): {reply}")

sentences = [s for s in re.split(r"(?<=[.!?])\s+", reply.strip()) if s]
check(len(sentences) <= 2, f"at most 2 sentences ({len(sentences)})")
check(len(reply) <= 320, f"at most 320 characters ({len(reply)})")

sys.path.insert(0, os.path.abspath(LLMOS))
from llmos import everyday, intent  # noqa: E402  (these import without GTK)

phrases = re.findall(r"“([^”]+)”", reply)
check(len(phrases) >= 1, f"example phrases quoted ({len(phrases)})")
for p in phrases:
    low = p.lower()
    routed = (intent.match(p) is not None) or bool(everyday.MATCH.search(low)) or (lock_words is not None and low in lock_words)
    check(routed, f"{p!r} routes at once")

print("\nall good" if not fails else f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
