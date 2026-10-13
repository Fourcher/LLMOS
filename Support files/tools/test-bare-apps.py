#!/usr/bin/env python3
"""Host-side test of the bare app-name route in llmos/intent.py (_BARE_APP, at the end of _apps):
"discord", "scientific calculator please", "open the discord". Names that matched before keep their result
(open firefox, open calculator, stopwatch...); phrases that only mention a name keep no route (discord is down...).
Run: python3 tools/test-bare-apps.py  (no VM needed)."""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))   # the model catalog
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

CASES = {
    # new: bare names routed to the OS's own program or built-in kind
    "discord": ("open_app", {"command": "discord"}),
    "open discord": ("open_app", {"command": "discord"}),
    "open the discord": ("open_app", {"command": "discord"}),
    "scientific calculator please": ("make_app", {"what": "scientific calculator"}),
    "scientific calculator": ("make_app", {"what": "scientific calculator"}),
    # kept: matched before this change, same result
    "open firefox": ("browse", {}),
    "open my documents": ("show_files", {"path": "~/Documents"}),
    "open the file manager": None,
    "open calculator": ("open_app", {"command": "calculator"}),
    "open the calculator": ("open_app", {"command": "calculator"}),
    "stopwatch": ("open_app", {"command": "stopwatch"}),
    "open stopwatch": ("open_app", {"command": "stopwatch"}),
    "open the stopwatch": ("open_app", {"command": "stopwatch"}),
    "unit converter": ("open_app", {"command": "unit converter"}),
    "open unit converter": ("open_app", {"command": "unit converter"}),
    "open scientific calculator": ("open_app", {"command": "scientific calculator"}),
    # must NOT match (no route; the model handles them)
    "messenger": None,
    "open messenger": None,
    "youtube music": None,
    "open youtube music": None,
    "podcasts": None,
    "open podcasts": None,
    "discord is down": None,
    "my discord friend said hi": None,
    "how does a stopwatch work": None,
    "calculator broken": None,
    "messenger bag": None,
    "podcasts about history": None,
    "open the calculator, please": None,
}

fails = 0
for text, want in CASES.items():
    got = intent.match(text)
    if got == want:
        print(f"ok {text!r} -> {got}")
    else:
        fails += 1
        print(f"FAIL {text!r}: got {got}, want {want}")
if fails:
    print(f"{fails} failed")
    sys.exit(1)
print("all good")
