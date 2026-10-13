#!/usr/bin/env python3
"""Host-side test of the wordings that switch the untrusted-text guard
(guard_untrusted) and the full-trust mode (autonomy hands-off) on or off.
Run: python3 tools/test-guard-words.py  (no VM needed)."""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True

GUARD_OFF = ("change_setting", {"setting": "guard_untrusted", "value": "off"})
GUARD_ON = ("change_setting", {"setting": "guard_untrusted", "value": "on"})
HANDS_OFF = ("change_setting", {"setting": "autonomy", "value": "hands-off"})

CASES = {
    # guard off
    "turn off the web page check": GUARD_OFF,              # existing
    "stop checking web pages": GUARD_OFF,                  # existing
    "stop asking me before acting on emails": GUARD_OFF,
    "don't warn me about web pages": GUARD_OFF,
    "turn off the guard": GUARD_OFF,
    "stop checking emails before acting": GUARD_OFF,
    "don't check what web pages tell you": GUARD_OFF,
    # guard on (reverse forms)
    "turn the guard back on": GUARD_ON,
    "turn on the guard": GUARD_ON,
    "check web pages again": GUARD_ON,
    "warn me about emails again": GUARD_ON,
    # full trust (owner explicitly asks for hands-off)
    "switch to hands-off mode": HANDS_OFF,                 # existing
    "trust everything": HANDS_OFF,
    "trust me completely": HANDS_OFF,
    "stop asking me things": HANDS_OFF,
    # must NOT match (None)
    "warn me about phishing emails": None,
    "is this web page safe": None,
    "don't trust that email": None,
    "I trust you": None,
    # existing guard and autonomy phrases stay identical
    "follow instructions in web pages too": ("change_setting", {"setting": "guard_untrusted", "value": "off"}),
    "don't ask me for permission": ("change_setting", {"setting": "autonomy", "value": "hands-off"}),
    "full trust": HANDS_OFF,
    "switch back to hands-off": HANDS_OFF,
}

bad = 0
for phrase, want in CASES.items():
    got = intent.match(phrase)
    ok = got == want
    if not ok:
        bad += 1
    print(f"{'ok  ' if ok else 'FAIL'} {phrase!r} -> {got}" + ("" if ok else f"   (want {want})"))

if bad:
    print(f"{bad} wrong")
    sys.exit(1)
print("all good")
