#!/usr/bin/env python3
"""Host-side check that 'show ... list' wordings route to notes_show with the right list name,
and that a trailing 'as a list' is not part of the list name. Run: python3 tools/test-notes-show.py"""
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


# unchanged: values captured before the edit
check("show my shopping list", ("notes_show", {"list": "shopping"}))
check("show my notes", ("notes_show", {"list": "notes"}))

# fixed: the trailing view phrase is no longer part of the list name
check("show my notes as a list", ("notes_show", {"list": "notes"}))
check("show the groceries list as a list", ("notes_show", {"list": "groceries"}))

print("all good")
