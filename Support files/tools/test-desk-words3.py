#!/usr/bin/env python3
"""Host-side test of two desk.py routes (no GTK, no real windows):
- the no-internet route in shortcut(): "connected but no internet", "wifi connected but no internet",
  "it says connected but nothing loads", "connected to wifi but not online" match; the old forms still match.
- _system_shortcut two-window tiling: "<A> (on the )?left(,| and) <B> (on the )?right" and the mirrored form
  tile A and B with wm.tile (the same call the one-window form uses); a name that is not an open window
  falls through (no tiling, as the one-window form does). The wm module is the real wm.py with tile() recorded.
- negatives: "turn left at the lights", "left or right?", "no internet explorer jokes", "I left my notes on the right shelf".
desk.py is read with ast and exec of its source only. Run: python3 tools/test-desk-words3.py"""
import ast
import importlib.util
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos")
SRC_PATH = os.path.join(ROOT, "desk.py")
WM = os.path.join(ROOT, "wm.py")
src = open(SRC_PATH, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("ok " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


# --- 1. the no-internet route: the fullmatch pattern that tests the lowercased line -----------------
pats = []
for node in ast.walk(ast.parse(src)):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "fullmatch"
            and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            and "no (?:internet" in node.args[0].value):
        pats.append(node.args[0].value)
check(len(pats) == 1, "the no-internet route pattern is found once in desk.py")
NET = re.compile(pats[0]) if pats else re.compile(r"(?!)")

print("no-internet route: new forms")
for q in ("connected but no internet", "wifi connected but no internet", "it says connected but nothing loads",
          "connected to wifi but not online", "wi-fi connected but no internet", "connected to the internet but nothing loads"):
    check(bool(NET.fullmatch(q.rstrip("?.!"))), f"{q!r} -> no-internet route")
print("no-internet route: existing forms unchanged")
for q in ("no internet", "no wifi", "no wi-fi", "no connection", "wifi isn't working", "the internet is down",
          "i can't get online", "cannot connect to the internet", "network stopped working"):
    check(bool(NET.fullmatch(q.rstrip("?.!"))), f"{q!r} -> no-internet route")
print("no-internet route: not matched")
for q in ("connected to wifi", "wifi connected", "no internet explorer jokes", "turn left at the lights"):
    check(not NET.fullmatch(q.rstrip("?.!")), f"{q!r} is not the no-internet route")

# --- 2. two-window tiling: the regex and the handler ----------------------------------------------
# the class attributes (_TILE, _TILE2) and _system_shortcut, exec'd on their own
SYS_AT = src.index("    def _system_shortcut")
cls_src = "class Desk:\n" + src[src.index("    _CANON = ["):src.index("\n    def ", SYS_AT + 10) + 1]
ns = {"re": re, "shutil": shutil}
# wm: the real wm.py (for app_id); tile() is replaced by a recorder so no window moves
spec = importlib.util.spec_from_file_location("wm_under_test", WM)
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)
calls = []


def fake_tile(target, side):
    calls.append((target, side))
    return True, f"Put {wm.NAMES.get(target, target)} on the {side}."


wm.tile = fake_tile
ns["wm"] = wm
ns["os"] = os
exec(cls_src, ns)
Desk = ns["Desk"]
TILE2 = Desk._TILE2

WLRCTL = {"which": lambda name: "/usr/bin/" + name if name in ("wlrctl", "wtype") else None}


class FakeShutil:
    which = staticmethod(WLRCTL["which"])


ns["shutil"] = FakeShutil


class Stub(Desk):
    def __init__(self):
        self.replies = []
        self.windows = {}

    def instant_reply(self, request, text):
        self.replies.append(text)

    def _window_shortcut(self, low):      # the one-window keys: not under test here
        return False


def run(line):
    """Run the handler's tiling part with the real wm.app_id and the recorded tile(); returns (handled, replies, calls)."""
    del calls[:]
    st = Stub()
    try:
        handled = bool(Desk._system_shortcut(st, line.lower().strip(), line))
    except AttributeError:      # fell through past the tiling part into branches this stub does not model
        handled = False
    return handled, list(st.replies), list(calls)


print("two-window tiling: regex")
for q in ("browser left, notes right", "firefox on the left and files on the right", "put the browser left and notes right",
          "browser on the left and files on the right", "put firefox on the right, files on the left", "browser right and files left"):
    check(bool(TILE2.fullmatch(q)), f"{q!r} matches the two-window form")
for q in ("turn left at the lights", "left or right?", "I left my notes on the right shelf", "put the browser on the left",
          "no internet explorer jokes"):
    check(not TILE2.fullmatch(q.rstrip("?.!")), f"{q!r} is not a two-window tile")

print("two-window tiling: handler (wm.tile recorded)")
h, rep, c = run("browser left, files right")
check(h and c == [("firefox", "left"), ("thunar", "right")], f"'browser left, files right' -> tile calls {c}")
h, rep, c = run("browser left, notes right")
check(not c, f"'browser left, notes right': 'notes' is not a window wm knows, so no tiling ({c})")
h, rep, c = run("firefox on the left and files on the right")
check(h and c == [("firefox", "left"), ("thunar", "right")], f"'firefox on the left and files on the right' -> {c}")
check(rep == ["Put the browser on the left. Put Files on the right."], f"reply: {rep}")
h, rep, c = run("put the browser left and files right")
check(h and c == [("firefox", "left"), ("thunar", "right")], f"'put the browser left and files right' -> {c}")
h, rep, c = run("files on the left and browser on the right")
check(h and c == [("thunar", "left"), ("firefox", "right")], f"mirror: 'files on the left and browser on the right' -> {c}")
h, rep, c = run("browser right and files left")
check(h and c == [("firefox", "right"), ("thunar", "left")], f"mirror: 'browser right and files left' -> {c}")
h, rep, c = run("browser left and mystery right")
check(not c and not rep, "'browser left and mystery right': unknown window, no tiling, no reply (as the one-window form)")
h, rep, c = run("browser left and browser right")
check(not c, "same window named twice: no tiling")
print("one-window tiling unchanged")
h, rep, c = run("put the browser on the left")
check(h and c == [("firefox", "left")], f"'put the browser on the left' -> {c}")
print("negatives do not tile")
for q in ("turn left at the lights", "left or right?", "I left my notes on the right shelf", "no internet explorer jokes"):
    h, rep, c = run(q)
    check(not c, f"{q!r} tiles nothing ({c})")

# --- 3. _instant: the two-window tiling and the no-internet forms answer at once while the model is busy -----
# the real desk module (as test-busy-fallthrough.py imports it); _instant is called on a Desk.__new__ stub
sys.path.insert(0, os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(HERE, "..", "src/rootfs/usr/share/llmos"))
from llmos import desk as desk_mod  # noqa: E402

inst = desk_mod.Desk.__new__(desk_mod.Desk)
print("_instant: two-window tiling")
for q in ("browser left, notes right", "firefox on the left and files on the right", "browser right and files left",
          "put the browser left and files right"):
    check(inst._instant(q) is True, f"_instant({q!r}) is True")
print("_instant: no-internet forms")
for q in ("connected but no internet", "wifi connected but no internet", "it says connected but nothing loads",
          "connected to wifi but not online"):
    check(inst._instant(q) is True, f"_instant({q!r}) is True")
print("_instant: everything else unchanged (values as at 0f9fb4f)")
for q, want in (("turn left at the lights", False), ("left or right?", False), ("I left my notes on the right shelf", False),
                ("I'm connected and it works", False), ("connected to wifi", False), ("connected but nothing works", False),
                ("connected and offline", False), ("I'm connected but no internet", False), ("connected but slow", False),
                ("news", True), ("logs", True), ("no internet explorer jokes", True), ("wifi connected", True),
                ("what time is it", True)):
    check(inst._instant(q) is want, f"_instant({q!r}) is {want}")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
