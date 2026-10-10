#!/usr/bin/env python3
"""Host-side test for the Wi-Fi on/off shortcut regex in desk.py shortcut().
Checks the phrasings that should match and compute on/off, the phrasings that must not match,
and that desk.py carries the no-adapter reply and compiles.
Run: python3 tools/test-wifi-toggle.py  (no VM needed). Exit status 0 = pass."""
import os
import py_compile
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deskre

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
DESK = os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py")

WIFI_RE = deskre.pattern_containing("(?P<v3>enable|disable) (?:the )?wi-?fi")
print("pattern:", WIFI_RE)

failures = []


def check(label, ok):
    if ok:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}")
        failures.append(label)


def computed(m):
    return m.group("v") or m.group("v2") or ("on" if m.group("v3") == "enable" else "off")


for phrase, want in [
    ("turn wifi off", "off"),
    ("turn off the wifi", "off"),
    ("wifi on", "on"),
    ("disable wifi", "off"),
    ("enable wi-fi", "on"),
    ("switch on wifi", "on"),
]:
    m = re.fullmatch(WIFI_RE, phrase.rstrip(".!"))
    got = computed(m) if m else None
    check(f"{phrase!r} -> {want}", got == want)

for phrase in ["turn wifi off at 10pm", "is wifi on"]:
    check(f"{phrase!r} no match", re.fullmatch(WIFI_RE, phrase.rstrip(".!")) is None)

with open(DESK, encoding="utf-8") as fh:
    src = fh.read()
check('desk.py has "This computer has no Wi-Fi adapter."', "This computer has no Wi-Fi adapter." in src)
check("desk.py has the wifi regex", WIFI_RE in src)

try:
    py_compile.compile(DESK, doraise=True)
    check("py_compile desk.py", True)
except py_compile.PyCompileError as e:
    check(f"py_compile desk.py ({e})", False)

if failures:
    print(f"{len(failures)} FAIL")
    sys.exit(1)
print("all good")
