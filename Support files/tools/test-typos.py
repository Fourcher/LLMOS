#!/usr/bin/env python3
"""Host-side check that typo'd command phrases route the same as their corrected
forms (no slow model), and that correct or non-command words are untouched.
Run: python3 tools/test-typos.py"""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402

PAIRS = [
    ("opn firefox", "open firefox"),
    ("wat time is it", "what time is it"),
    ("chang the volum up", "change the volume up"),
    ("hwo do i print", "how do i print"),
    ("whats the time", "what's the time"),
    ("opn, firefox", "open, firefox"),
]

for typo, corrected in PAIRS:
    got = intent.match(typo)
    want = intent.match(corrected)
    assert got == want, f"{typo!r}: got {got!r}, corrected {corrected!r} gives {want!r}"
    print(f"ok {typo!r} -> {got!r} (corrected form gives {want!r})")

# whole words only: "watch" and "whatsapp" are never changed
assert intent._retype("watch a video") == "watch a video", intent._retype("watch a video")
assert intent._retype("whatsapp messages") == "whatsapp messages", intent._retype("whatsapp messages")
print("ok 'watch a video' and 'whatsapp' unchanged by the typo table")

# "watch a video" routes exactly as it did before the typo retry existed
saved = intent.TYPOS
try:
    intent.TYPOS = {}
    before = intent.match("watch a video")
finally:
    intent.TYPOS = saved
after = intent.match("watch a video")
assert after == before, f"watch a video: before {before!r}, after {after!r}"
print(f"ok 'watch a video' unchanged: {after!r}")

# a correctly spelled phrase whose first pass routes is not changed by the retry
saved = intent.TYPOS
try:
    intent.TYPOS = {}
    before = intent.match("open firefox")
finally:
    intent.TYPOS = saved
assert intent.match("open firefox") == before
print(f"ok 'open firefox' unchanged: {before!r}")

print("all good")
