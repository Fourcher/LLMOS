#!/usr/bin/env python3
"""Host-side test: the system prompt tells the model to address the owner as "you".
The sentence must be in agent.SYSTEM_PROMPT_BASE exactly once.
Run: python3 tools/test-address-you.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent

SENTENCE = ('You are talking to the owner directly: say "you" and "your", never "the owner" or "the user". '
            'Tool results call them "the owner"; that word is for you, not for your reply.')

count = agent.SYSTEM_PROMPT_BASE.count(SENTENCE)
assert count == 1, f"expected the sentence exactly once in SYSTEM_PROMPT_BASE, found {count}"
print("ok the address-you sentence is in SYSTEM_PROMPT_BASE exactly once")
print("all good")
