#!/usr/bin/env python3
"""Recall shortcut: 'what did I say a minute ago' reads the chat directly (no model call)."""
import os
import py_compile
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py")

PATTERN = (r"what (?:did|was it) i (?:just )?(?:say|ask|type|write)(?: (?:you|to you))?(?: (?:a (?:minute|moment|second|bit) ago|before|earlier|last|just now|before that))?|"
           r"what was my (?:last|previous) (?:question|request|message)|what did i ask you(?: (?:before|last|earlier))?")

for phrase in ["what did i say a minute ago", "what did i just say", "what was my last question", "what did i ask you before"]:
    assert re.fullmatch(PATTERN, phrase), "should match: " + phrase
    print("ok match", repr(phrase))

assert not re.fullmatch(PATTERN, "what did i say to mum"), "should not match"
print("ok no-match 'what did i say to mum'")

with open(DESK, encoding="utf-8") as f:
    src = f.read()
for s in ["You said: “", "You haven't asked me anything yet in this conversation."]:
    assert s in src, "missing in desk.py: " + s
    print("ok desk.py contains", repr(s))

py_compile.compile(DESK, doraise=True)
print("ok py_compile desk.py")
print("all good")
