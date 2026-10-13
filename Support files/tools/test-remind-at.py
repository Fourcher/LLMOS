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
    # "remind me to <task> at|in|on|tomorrow <time>": was {when, task "remind me to …"} with no kind before this change
    ("remind me to take my pills at 3", ("schedule_task", {"when": "at 3", "task": "take my pills", "kind": "reminder"})),
    ("remind me to call mum at 3pm", ("schedule_task", {"when": "at 3pm", "task": "call mum", "kind": "reminder"})),
    ("remind me to stretch in 20 minutes", ("schedule_task", {"when": "in 20 minutes", "task": "stretch", "kind": "reminder"})),
    ("remind me to pay rent tomorrow at 9", ("schedule_task", {"when": "tomorrow at 9", "task": "pay rent", "kind": "reminder"})),
    ("remind me to take my pills at 3 please", ("schedule_task", {"when": "at 3", "task": "take my pills", "kind": "reminder"})),
    ("remind me to meet in the park at 5", ("schedule_task", {"when": "at 5", "task": "meet in the park", "kind": "reminder"})),
    ("remind me to pay rent on Friday", ("schedule_task", {"when": "on friday", "task": "pay rent", "kind": "reminder"})),
    ("remind me to check the oven", None),
    # unchanged by this change: other scheduling with "at <time>" and the non-reminder phrases
    ("turn on dark mode at 9", ("schedule_task", {"when": "at 9", "task": "turn on dark mode"})),
    ("lock the screen at 10", ("schedule_task", {"when": "at 10", "task": "lock the screen"})),
    ("set an alarm for 7am", ("schedule_task", {"when": "7am", "task": "Alarm", "kind": "reminder"})),
    # trailing filler: a bare please/pls or a comma + filler is dropped; "thanks"/"now"/"for me" without a comma stay (they can be the task)
    ("remind me at 3 to take my pills please", ("schedule_task", {"when": "at 3", "task": "take my pills", "kind": "reminder"})),
    ("remind me at 3 to take my pills, please", ("schedule_task", {"when": "at 3", "task": "take my pills", "kind": "reminder"})),
    ("remind me at 3 to call mum, thanks.", ("schedule_task", {"when": "at 3", "task": "call mum", "kind": "reminder"})),
    # a task that is only filler is no task: None (the model decides)
    ("remind me at 3 to please", None),
    ("remind me at 3 to thanks", None),
    ("remind me at 3 to now.", None),
    ("remind me at 3 to say thanks", ("schedule_task", {"when": "at 3", "task": "say thanks", "kind": "reminder"})),
    ("remind me at 7 to call now", ("schedule_task", {"when": "at 7", "task": "call now", "kind": "reminder"})),
    ("remind me at 7 to call mum for me", ("schedule_task", {"when": "at 7", "task": "call mum for me", "kind": "reminder"})),
    # NEW: "tonight", "this morning/afternoon/evening", "next <weekday>" as the when (each one store.parse_when accepts)
    ("remind me to look at the stars tonight", ("schedule_task", {"when": "tonight", "task": "look at the stars", "kind": "reminder"})),
    ("remind me to call mum this evening please", ("schedule_task", {"when": "this evening", "task": "call mum", "kind": "reminder"})),
    ("remind me to call mum this afternoon at 3", ("schedule_task", {"when": "this afternoon at 3", "task": "call mum", "kind": "reminder"})),
    ("remind me to call mum next monday", ("schedule_task", {"when": "next monday", "task": "call mum", "kind": "reminder"})),
    # the time is only the tail: "tonight's game" is part of the task, the "at 8" is the when
    ("remind me to watch tonight's game at 8", ("schedule_task", {"when": "at 8", "task": "watch tonight's game", "kind": "reminder"})),
    # not split on (parse_when rejects "next week"; "later today" parses to 09:00): still None
    ("remind me to call mum next week", None),
    ("remind me to call mum later today", None),
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
