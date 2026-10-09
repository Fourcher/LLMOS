#!/usr/bin/env python3
"""Check the small-reply fixes in desk.py: skip with nothing playing, unlock when not locked, hello."""
import os
import py_compile

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py")

with open(D, encoding="utf-8") as f:
    src = f.read()

checks = [
    ('"Nothing is playing."' in src, "skip with nothing playing says 'Nothing is playing.'"),
    ('"The screen isn\'t locked."' in src, "unlock when not locked says 'The screen isn't locked.'"),
    ('hello\\?+' in src, "are-you-there check uses hello\\?+"),
    ('hello\\?*' not in src, "old hello\\?* pattern is gone"),
    ('"Hi. What would you like to do?"' in src, "hello greeting reply present"),
]
for ok, label in checks:
    assert ok, "FAIL: " + label
    print("ok " + label)

py_compile.compile(D, doraise=True)
print("ok desk.py compiles")
print("all good")
