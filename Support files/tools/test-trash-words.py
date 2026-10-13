#!/usr/bin/env python3
"""Host-side check of the trash wordings. Intent: "get my file back", "put back what I deleted" -> show the trash
(~/.Trash); "undo delete", "restore the last thing I deleted", "bring back what I just deleted" -> the undo tool.
Phrases that routed before stay as they were (the "before" column is what match() returned before this change).
show_files: a model asking for "~/Trash" (or "~/Recycle Bin", "~/bin", "~/trash") when no such folder exists
shows the real trash (~/.Trash); when that folder exists, it shows that folder. Uses a temp LLMOS_HOME only.
Run: python3 tools/test-trash-words.py  (no VM needed)."""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent, tools as T  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

SHOW_TRASH = ("show_files", {"path": "~/.Trash"})
UNDO = ("undo", {})
EMPTY = ("empty_trash", {})

# (phrase, before, after). before = what match() returned before this change.
TABLE = [
    ("get my file back", None, SHOW_TRASH),
    ("get my files back", None, SHOW_TRASH),
    ("put back what I deleted", None, SHOW_TRASH),
    ("where did my deleted files go", SHOW_TRASH, SHOW_TRASH),
    ("open the bin", SHOW_TRASH, SHOW_TRASH),
    ("show the recycle bin", SHOW_TRASH, SHOW_TRASH),
    ("restore from trash", SHOW_TRASH, SHOW_TRASH),
    ("restore my deleted file", SHOW_TRASH, SHOW_TRASH),
    ("undo delete", None, UNDO),
    ("undo that delete", None, UNDO),
    ("restore the last thing I deleted", None, UNDO),
    ("bring back what I just deleted", None, UNDO),
    ("undo", UNDO, UNDO),
    ("oops", UNDO, UNDO),
    ("empty the trash", EMPTY, EMPTY),
    ("show the trash", SHOW_TRASH, SHOW_TRASH),
    ("restore report.pdf from trash", ("restore_file", {"name": "report.pdf"}), ("restore_file", {"name": "report.pdf"})),
    ("throw it in the bin", None, None),          # not a trash-view phrase: stays unrouted
    ("I want to get my money back", None, None),  # must not match "get my ... back"
    ("bin day reminder", None, None),             # must not match "open/show the bin"
]

fails = 0


def check(cond, msg):
    global fails
    if cond:
        print("ok " + msg)
    else:
        fails += 1
        print("FAIL " + msg)


for phrase, before, after in TABLE:
    got = intent.match(phrase)
    check(got == after, f"intent {phrase!r} -> {got!r} (before {before!r}, want {after!r})")


class Ctx:
    """Captures the window spec show_files puts on screen."""
    def __init__(self):
        self.spec = None

    def show_ui(self, spec):
        self.spec = spec
        return ""


def titles(spec):
    out = []
    for b in spec.get("blocks", []):
        if b.get("type") == "list":
            out += [i.get("title") for i in b.get("items", [])]
    return out


def fresh_home():
    home = tempfile.mkdtemp(prefix="llmos-trash-words-")
    os.environ["LLMOS_HOME"] = home
    return home


# 1. the folder does not exist: each trash-like name shows ~/.Trash
for name in ("Trash", "trash", "Recycle Bin", "bin"):
    home = fresh_home()
    os.makedirs(os.path.join(home, ".Trash"))
    with open(os.path.join(home, ".Trash", "gone.txt"), "w") as f:
        f.write("x")
    T._LAST_FOLDER = None
    ctx = Ctx()
    T.show_files({"path": "~/" + name}, ctx)
    want = os.path.join(home, ".Trash")
    check(T._LAST_FOLDER == want and "gone.txt" in titles(ctx.spec or {}),
          f"show_files ~/{name} (absent) -> {T._LAST_FOLDER} lists gone.txt")

# 2. the folder exists: it is shown, not the trash
home = fresh_home()
os.makedirs(os.path.join(home, "Trash"))
os.makedirs(os.path.join(home, ".Trash"))
with open(os.path.join(home, "Trash", "mine.txt"), "w") as f:
    f.write("x")
with open(os.path.join(home, ".Trash", "gone.txt"), "w") as f:
    f.write("x")
T._LAST_FOLDER = None
ctx = Ctx()
T.show_files({"path": "~/Trash"}, ctx)
check(T._LAST_FOLDER == os.path.join(home, "Trash") and "mine.txt" in titles(ctx.spec or {}) and "gone.txt" not in titles(ctx.spec or {}),
      f"show_files ~/Trash (exists) -> {T._LAST_FOLDER} lists mine.txt, not gone.txt")

# 3. a real folder that is not a trash name is untouched when absent (no remap)
home = fresh_home()
os.makedirs(os.path.join(home, ".Trash"))
T._LAST_FOLDER = None
ctx = Ctx()
T.show_files({"path": "~/Downloads"}, ctx)
check(T._LAST_FOLDER == os.path.join(home, "Downloads"),
      f"show_files ~/Downloads (absent, not a trash name) -> {T._LAST_FOLDER} is not remapped")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
