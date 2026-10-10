#!/usr/bin/env python3
"""Host-side check that everyday photo wordings route to find_by_meaning
(kind=photos) without the slow model. Run: python3 tools/test-photo-route.py"""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402


def photo(text, query):
    got = intent._everyday2(text)
    want = ("find_by_meaning", {"query": query, "kind": "photos"})
    assert got == want, f"{text!r}: got {got!r}, want {want!r}"
    print(f"ok {text!r} -> {query!r}")


photo("my pics from christmas", "christmas")
photo("show my photos from the beach", "the beach")
photo("show me all my pictures of grandma", "grandma")
photo("find the photos of the lake", "the lake")

# no my/our before pictures: must not take the new branch
r = intent._everyday2("pictures of my dog")
print("pictures of my dog ->", r)
assert not (r and r[0] == "find_by_meaning" and r[1].get("query") == "my dog" and r[1].get("kind") == "photos"), r

# must not crash; any result is acceptable here
r = intent._everyday2("what's in my photos from 2019")
print("what's in my photos from 2019 ->", r)
assert r is None or r[0] != "find_by_meaning" or r[1].get("query") != "2019", r
print("ok what's in my photos from 2019 (no crash)")

print("all good")
