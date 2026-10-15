#!/usr/bin/env python3
"""Host-side checks of what the 2026-10-15 test rounds (real laptop and VM) found in plain requests and replies:
"draw me a cat" is a picture, "make a packing list with A, B and C" makes exactly that list, the Scheduled window's
Cancel button never reaches the model (it answered with the task code), a timer is "Pasta (2 minutes)", the reply
for a timer within the hour reads "it rings in 1 minute (03:36)", an alarm is called an alarm, and search snippets
lose their footnote marks. Run: python3 tools/test-hw-sweep-words.py (no VM)"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC", tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import agent, everyday, intent  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


M = intent.match
check(M("draw me a cat") == ("show_image", {"subject": "cat", "drawn": True}), "draw me a cat: a picture, said plainly")
check(M("can you draw me a dog?") == ("show_image", {"subject": "dog", "drawn": True}), "can you draw me a dog?")
check(M("draw the curtains") is None and M("draw a line") is None, "draw the curtains / a line: not pictures")
check(M("make a packing list with socks, charger and toothbrush") ==
      ("note_add", {"text": "socks, charger and toothbrush", "list": "packing"}), "packing list with named items: exactly those")
check(M("create a list called packing with socks and charger") ==
      ("note_add", {"text": "socks and charger", "list": "packing"}), "a list called packing with …")
check(M("make a to-do list for moving house")[0] == "make_list", "a list for a topic is still written by the model")
check(M("cancel the task 70e93e") == ("manage_tasks", {"action": "cancel", "which": "70e93e"}),
      "the Cancel button's words go straight to the cancel")
check(M("set a 2 minute timer for the pasta")[1]["task"] == "Pasta (2 minutes)", "timer named 'Pasta (2 minutes)'")
check(M("3 minute timer")[1]["task"] == "3 minutes", "timer without a name: its length")

W = agent._shortcut_words
r = W("schedule_task", {"task": "Tea (1 minute)", "kind": "timer"}, "scheduled [ab12cd] in 1 minute (03:36): Tea (1 minute)")
check(r == "Timer set — Tea (1 minute), it rings in 1 minute (03:36).", f"timer within the hour: {r!r}")
r = W("schedule_task", {"task": "Alarm", "kind": "reminder"}, "scheduled [ab12cd] Thu 15 Oct 07:00: Alarm")
check(r.startswith("Alarm set for") and "Reminder" not in r, f"an alarm is called an alarm: {r!r}")
r = W("schedule_task", {"task": "call mum", "kind": "reminder"}, "scheduled [ab12cd] in 20 minutes (04:00): call mum")
check(r == "Reminder set in 20 minutes (04:00): call mum.", f"reminder within the hour: {r!r}")

s = everyday._first_sentences("Paris[b] is the capital and largest city of France.[4] It has 2 million people [citation needed].")
check("[" not in s and s.startswith("Paris is the capital"), f"snippet without footnote marks: {s!r}")

# round 19 (real laptop): folders by the names people use, episode renames, a budget sheet, memory, convert words
from llmos import tools, config  # noqa: E402
home = config.home().rstrip("/")
os.makedirs(os.path.join(home, "Videos", "test19"), exist_ok=True)
for i in (1, 2, 3):
    open(os.path.join(home, "Videos", "test19", f"Show s01 e0{i} raw.mp4"), "w").write(str(i))
open(os.path.join(home, "Videos", "test19", "copy1.mp4"), "w").write("x")
want = os.path.join(home, "Videos", "test19")
for name in ("videos/test19", "Videos/test19", "my test19 folder", "test19", "the test19 folder"):
    check(tools._dir(name) == want, f"folder {name!r} -> Videos/test19")
tools._LAST_FOLDER = want
check(tools._dir("this folder") == want, "'this folder' is the one on screen")


class _C:
    headless = True

    def show_box(self, *a):
        pass

    def display(self, *a):
        pass

    def status(self, *a):
        pass


tools.rename_series({"name": "Show - S01E01", "kind": "videos", "folder": "videos/test19"}, _C())
got = sorted(os.listdir(want))
check(got == ["Show - S01E01.mp4", "Show - S01E02.mp4", "Show - S01E03.mp4", "copy1.mp4"], f"episodes renamed by their own numbers, the stray copy left: {got}")
check(M("rename the episodes in Videos/test19 so they are named like Show - S01E01") ==
      ("rename_series", {"name": "Show - S01E01", "kind": "videos", "folder": "videos/test19"}), "rename '... named like Show - S01E01'")
check(M("rename these photos to Holiday 1, 2, 3") == ("rename_series", {"name": "Holiday", "kind": "photos"}), "rename to Holiday 1, 2, 3 still")
r = M("make a spreadsheet for a monthly budget with rent, food and transport")
check(r and r[0] == "make_spreadsheet" and [x[0] for x in r[1]["rows"]] == ["Item", "Rent", "Food", "Transport", "Total"],
      f"budget spreadsheet with those rows and a total: {r}")
for fact, req, ok in [("Jordan prefers Kokoro voice models", "what models can I use?", False),
                      ("Today is Wednesday, 2026-10-14", "what day is it", False),
                      ("OS is Alpine Linux with no GUI", "what resolution is my screen", False),
                      ("owner likes jazz", "remember that I like jazz", True),
                      ("owner prefers dark mode", "I prefer dark mode", True),
                      ("owner's dog is called Rex", "my dog is called Rex", True)]:
    check((tools._not_memory(fact, req) is None) == ok, f"memory {'kept' if ok else 'refused'}: {fact!r} after {req!r}")
check(W("convert_media", {}, "converted 1 file(s) to mp3: copy1.mp3. Done: reply in one sentence.") == "Made copy1.mp3; the original is kept.",
      "convert reply: made, original kept")
src = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py"), encoding="utf-8").read()
import re as _re  # noqa: E402
ns = {}
exec("import re\n" + "\n".join(l for l in src.splitlines() if l.startswith(("_VOICES_Q = ", "_MODELS_Q = "))), ns)
check(bool(ns["_VOICES_Q"].fullmatch("which voices can you speak with")), "'which voices can you speak with' answered here")
check(bool(ns["_MODELS_Q"].fullmatch("what models can i use")), "'what models can I use' opens the models")

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
