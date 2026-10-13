#!/usr/bin/env python3
"""Host-side test of "remind me at <time> to <task>" (same route and fields as "remind me in <n> <unit> to <task>").
Rows marked BEFORE were already routed this way before the change (kept identical); rows marked NEW did not match.
Phrases that must stay unmatched (None) are listed too. Run: python3 tools/test-remind-at.py (no VM needed)."""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402

CASES = [
    # NEW: the "at <time> to <task>" order
    ("remind me at 3 to take my pills", ("schedule_task", {"when": "at 3", "task": "take my pills", "kind": "reminder"})),
    ("remind me at 3pm to call mum", ("schedule_task", {"when": "at 3pm", "task": "call mum", "kind": "reminder"})),
    ("remind me at 15:30 to stretch", ("schedule_task", {"when": "at 15:30", "task": "stretch", "kind": "reminder"})),
    ("Remind me at 3PM to call mum", ("schedule_task", {"when": "at 3pm", "task": "call mum", "kind": "reminder"})),
    ("please remind me at 9:15 am to ring the bank", ("schedule_task", {"when": "at 9:15 am", "task": "ring the bank", "kind": "reminder"})),
    # BEFORE: the order the route already supported (same fields)
    ("remind me in 20 minutes to check the oven", ("schedule_task", {"when": "in 20 minutes", "task": "check the oven", "kind": "reminder"})),
    ("remind me to take my pills at 3", ("schedule_task", {"when": "at 3", "task": "remind me to take my pills"})),
    ("remind me to call mum at 3pm", ("schedule_task", {"when": "at 3pm", "task": "remind me to call mum"})),
    # Not changed by this test (tomorrow-at is not in the at-order route): still None
    ("remind me tomorrow at 9 to pay rent", None),
    # must NOT match
    ("remind me what time it is", None),
    ("remind me how to do this", None),
    ("remind me at some point", None),
    ("remind me at three to pay", None),
]


def main():
    bad = 0
    for phrase, want in CASES:
        got = intent.match(phrase)
        if got == want:
            print(f"ok   {phrase!r} -> {got}")
        else:
            bad += 1
            print(f"FAIL {phrase!r}: got {got}, want {want}")
    if bad:
        print(f"{bad} failed")
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
