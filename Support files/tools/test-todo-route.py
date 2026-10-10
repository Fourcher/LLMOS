#!/usr/bin/env python3
"""Host-side check that 'show my to do list' / 'show my reading list' / 'show the list' route to the
notes lists (notes_show), not to open_app of a program called 'to do list'. 'open my playlist' is not
a notes list. Run: python3 tools/test-todo-route.py"""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402


def check(text, want):
    got = intent.match(text)
    assert got == want, f"{text!r}: got {got!r}, want {want!r}"
    print(f"ok {text!r} -> {got!r}")


# to-do and reading lists go to the notes route
check("show my to do list", ("notes_show", {"list": "to do"}))
check("show my reading list", ("notes_show", {"list": "reading"}))
check("open the reading list", ("notes_show", {"list": "reading"}))

# 'show the list' has no list name: all the lists
check("show the list", ("notes_show", {}))

# a playlist is one word, not a notes list
got = intent.match("open my playlist")
assert not (isinstance(got, tuple) and got[0] == "notes_show"), f"'open my playlist' became notes: {got!r}"
print(f"ok 'open my playlist' -> {got!r}")

# programs still open as before
check("open the calculator", ("open_app", {"command": "calculator"}))
check("open firefox", ("browse", {}))  # unchanged from before this fix

print("all good")
