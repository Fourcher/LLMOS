#!/usr/bin/env python3
"""Host-side test of the widened intent regexes (alarm verb optional, bare 24/12-hour clock,
restore/put back from the trash, keep awake). Each row is the route the phrase took before the
widening (or None), or the new route for the new wordings. Run: python3 tools/test-intent-widen2.py
(no VM needed)."""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))   # the model catalog
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

ALARM = ("schedule_task", {"when": "7am", "task": "Alarm", "kind": "reminder"})
CLOCK24 = ("change_setting", {"setting": "clock", "value": "24"})
CLOCK12 = ("change_setting", {"setting": "clock", "value": "12"})
TRASH = ("show_files", {"path": "~/.Trash"})
SCREEN_NEVER = ("change_setting", {"setting": "screen_off", "value": "never"})

# (phrase, wanted route). Rows marked NEW did not match before this change.
CASES = [
    # alarm: verb optional (NEW rows first, then the verb forms that always matched)
    ("alarm for 7am", ALARM),                                   # NEW
    ("alarm at 7am", ALARM),                                    # NEW
    ("an alarm for 6:30", ("schedule_task", {"when": "6:30", "task": "Alarm", "kind": "reminder"})),  # NEW
    ("set an alarm for 7am", ALARM),                            # existing
    ("make an alarm at 6:30 am", ("schedule_task", {"when": "6:30 am", "task": "Alarm", "kind": "reminder"})),  # existing
    ("add an alarm for 7am", ALARM),                            # existing
    ("alarm for noon", ("schedule_task", {"when": "noon", "task": "Alarm", "kind": "reminder"})),  # NEW
    ("alarm for tomorrow at 7", ("schedule_task", {"when": "tomorrow at 7", "task": "Alarm", "kind": "reminder"})),  # NEW
    ("set an alarm for the meeting tomorrow", ("schedule_task", {"when": "the meeting tomorrow", "task": "Alarm", "kind": "reminder"})),  # existing verb form
    ("make an alarm for my sister", ("schedule_task", {"when": "my sister", "task": "Alarm", "kind": "reminder"})),  # existing verb form
    ("alarm for the meeting tomorrow", None),                   # verbless, no clock: unchanged (None)
    ("alarm for my sister", None),                              # verbless, no clock: unchanged (None)
    ("alarm for school", None),                                 # verbless, no clock: unchanged (None)
    ("alarm clock", None),                                      # negative
    ("false alarm", None),                                      # negative
    ("what alarm apps are there", None),                        # negative
    ("my alarm didn't go off", None),                           # negative

    # 24/12-hour clock: bare form NEW, verb form existing
    ("24 hour clock", CLOCK24),                                 # NEW
    ("24-hour clock", CLOCK24),                                 # NEW
    ("12 hour clock", CLOCK12),                                 # NEW
    ("switch to 24 hour clock", CLOCK24),                       # existing
    ("use 12-hour clock", CLOCK12),                             # existing
    ("set 24 hour clock", CLOCK24),                             # existing
    ("is it a 24 hour pharmacy", None),                         # negative
    ("I'd like a 24 hour clock", None),                         # contraction: unchanged (None); matching it later is allowed

    # trash: restore/put back from the trash NEW; open/show the trash already matched
    ("restore from the trash", TRASH),                          # NEW
    ("restore from my trash", TRASH),                           # NEW
    ("put back from trash", TRASH),                             # NEW
    ("open the trash", TRASH),                                  # existing
    ("show my trash", TRASH),                                   # existing
    ("show the trash", TRASH),                                  # existing
    ("open the recycle bin", TRASH),                            # existing
    ("restore my deleted file", TRASH),                         # existing
    ("restore report.pdf from the trash", ("restore_file", {"name": "report.pdf"})),  # existing
    ("empty the trash", ("empty_trash", {})),                   # negative: keeps its own route
    ("take out the trash reminder at 7", ("schedule_task", {"when": "at 7", "task": "take out the trash reminder"})),  # negative: unchanged

    # keep awake: bare and with a during/while tail NEW, verb form existing
    ("keep awake", SCREEN_NEVER),                               # NEW
    ("keep the screen awake during the movie", SCREEN_NEVER),   # NEW
    ("keep my computer awake while I watch", SCREEN_NEVER),     # NEW
    ("keep the screen awake", SCREEN_NEVER),                    # existing
    ("keep the screen on", SCREEN_NEVER),                       # existing
    ("don't turn off the screen", SCREEN_NEVER),                # existing
    ("keep awake tips", None),                                  # negative
    ("I can't keep awake", None),                               # negative
]

bad = 0
for phrase, want in CASES:
    got = intent.match(phrase)
    if got == want:
        print(f"ok {phrase!r} -> {got!r}")
    else:
        bad += 1
        print(f"MISMATCH {phrase!r}\n   got    {got!r}\n   wanted {want!r}")
if bad:
    print(f"{bad} FAILED")
    sys.exit(1)
print("all good")
