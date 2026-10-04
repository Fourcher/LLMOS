#!/usr/bin/env python3
"""Fuzz the window-spec validator with the kind of junk a small model can
produce (wrong types, nesting, huge strings, script/URL tricks): it must
never raise, never exceed its size caps, and never let a non-web URL through.
Run: python3 tools/test-uispec.py  (no VM needed)."""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
from llmos import uispec  # noqa: E402

KEYS = ["type", "text", "title", "items", "rows", "blocks", "actions", "say", "label", "src", "url", "link", "fields",
        "submit", "columns", "fraction", "on", "kind", "size", "id", "options", "thumbnail", "source", "selected"]
ATOMS = [None, 0, 1.5, True, False, "", "x" * 5000, "<script>alert(1)</script>", "javascript:alert(1)",
         "data:text/html,hi", "https://example.org/a", "/tmp/a.jpg", "‮\U0001F600", ["a"] * 3, {"z": 1}, -7, 1e30]
TYPES = list(uispec.BLOCK_TYPES) + ["paragraph", "bullet", "chart", "", None, 3]


def junk(depth=0):
    r = random.random()
    if depth > 3 or r < 0.25:
        return random.choice(ATOMS)
    if r < 0.5:
        return [junk(depth + 1) for _ in range(random.randint(0, 6))]
    d = {random.choice(KEYS): junk(depth + 1) for _ in range(random.randint(0, 7))}
    if random.random() < 0.6:
        d["type"] = random.choice(TYPES)
    return d


def check(n):
    json.dumps(n)
    uispec.to_rows(n)
    assert len(n["blocks"]) <= uispec.MAX_BLOCKS and len(n["title"]) <= 80
    for b in n["blocks"]:
        assert b["type"] in uispec.BLOCK_TYPES
        for k in ("src", "link", "thumbnail", "source"):
            if b.get(k):
                assert b[k].startswith(("http://", "https://", "file:///", "/")), b[k]
        for it in (b.get("items") or []):
            if isinstance(it, dict):
                for a in it.get("actions", []):
                    assert a["say"] and len(a["say"]) <= 400
                if "url" in it:
                    assert it["url"].startswith(("http://", "https://", "file:///", "/"))


random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
N = 5000
for i in range(N):
    spec = junk()
    try:
        n = uispec.normalize(spec)
        if n is not None:
            check(n)
    except Exception as e:
        print(f"FAIL on {str(spec)[:200]}\n   -> {e!r}")
        sys.exit(1)
# the model's usual mistakes must still render something sensible
common = {"title": "Dashboard", "blocks": [
    {"type": "paragraph", "content": "hello"}, {"type": "bullet", "items": ["a", "b"]},
    {"type": "list", "items": "just a string"}, {"type": "stat", "label": "CPU", "value": "12%", "fraction": "0.12"},
    {"type": "table", "rows": [{"a": 1, "b": 2}], "columns": ["a", "b"]}, {"type": "buttons", "items": ["Refresh"]}]}
n = uispec.normalize(common)
assert [b["type"] for b in n["blocks"]] == ["text", "text", "list", "stat", "table", "buttons"], n
assert uispec.normalize({"title": "t", "blocks": [{"type": "image", "src": "javascript:alert(1)"}]}) is None
assert uispec.normalize({"title": "t", "blocks": [{"type": "image", "src": "/tmp/y.jpg", "link": "javascript:1"}]})["blocks"][0]["link"] == ""
# an image the page would fetch by itself must be a local file: a remote address is dropped (no silent network request)
assert uispec.normalize({"title": "t", "blocks": [{"type": "image", "src": "https://x/y.jpg"}]}) is None
assert uispec.normalize({"title": "t", "blocks": [{"type": "image", "src": "/root/Pictures/My Photo.jpg"}]})["blocks"][0]["src"] == "/root/Pictures/My Photo.jpg"
print(f"uispec: {N} random specs + the usual mistakes handled; no crash, sizes capped, only web/file URLs kept")
