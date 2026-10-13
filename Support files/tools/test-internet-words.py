#!/usr/bin/env python3
"""Host-side test of the internet on/off wordings in llmos/intent.py (_INTERNET, the off group).

Every phrase that routed before must route the same way; the new off wordings ("turn off the internet",
"disconnect from the internet", "stay offline", "offline mode", ...) must route to internet=no; phrases that
merely mention the internet or offline mode for another reason must not route.
Judgment calls: "turn off the internet router" stays unrouted (a router is a device, not the internet switch);
"offline mode for games" stays unrouted (the phrase is about games, not the network).
Run: python3 tools/test-internet-words.py  (no VM needed)."""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))   # the model catalog
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

OFF = ("change_setting", {"setting": "internet", "value": "no"})
ON = ("change_setting", {"setting": "internet", "value": "yes"})
ASK = ("change_setting", {"setting": "internet", "value": "ask"})

CASES = [
    # kept identical: these routed before the change
    ("turn the internet off", OFF, "was"),
    ("go offline", OFF, "was"),
    ("block the internet", OFF, "was"),
    ("no internet", OFF, "was"),
    ("internet off", OFF, "was"),
    ("switch the internet off", OFF, "was"),
    ("disable internet access", OFF, "was"),
    ("cut the internet", OFF, "was"),
    ("no internet access", OFF, "was"),
    ("no internet use", OFF, "was"),
    ("internet on", ON, "was"),
    ("turn the internet back on", ON, "was"),
    ("always ask before going online", ASK, "was"),
    ("ask me before going online", ("change_setting", {"setting": "brain", "value": "ask"}), "was"),
    ("go online", ("browse", {}), "was"),
    # new: these returned None before
    ("turn off the internet", OFF, "new"),
    ("switch off the internet", OFF, "new"),
    ("disconnect from the internet", OFF, "new"),
    ("disconnect the internet", OFF, "new"),
    ("disconnect internet", OFF, "new"),
    ("kill the internet", OFF, "new"),
    ("kill internet", OFF, "new"),
    ("stay offline", OFF, "new"),
    ("work offline", OFF, "new"),
    ("offline mode", OFF, "new"),
    ("no internet please", OFF, "new"),
    # must not route
    ("my internet is off", None, "none"),
    ("turn off the internet router", None, "none"),
    ("is the internet off?", None, "none"),
    ("offline mode for games", None, "none"),
]

failed = 0
print(f"{'phrase':34} {'expected':34} {'got':34} status")
for phrase, want, kind in CASES:
    got = intent.match(phrase)
    good = got == want
    failed += 0 if good else 1
    status = "ok" if good else "FAIL"
    print(f"{phrase!r:34} {str(want):34} {str(got):34} {status} ({kind})")
    if not good:
        print(f"FAIL {phrase!r}: expected {want!r}, got {got!r}")

if failed:
    print(f"{failed} failed")
    sys.exit(1)
print("ok internet wordings: %d phrases" % len(CASES))
print("all good")
