#!/usr/bin/env python3
"""Host-side test of the private-window browser key, read from source with ast (desk.py needs GTK):
- wm.KEYS has "private window" = Ctrl+Shift+P (Firefox, the shipped browser; wm.browser_key focuses firefox only).
- the browser-key regex in llmos/desk.py maps "private window" / "open a private window" / "new private window" /
  "open incognito" / "incognito" to that key, and does not match "is this window private", "make my files private",
  "private browsing is useless". The existing groups still match their phrases ("bookmark this", and "open a new tab"
  from the _WIN route).
Matching is the desk's own: l2 = low.rstrip("?.!") with low = text.lower().strip().
Run: python3 tools/test-private-window.py"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos/llmos")
DESK = os.path.join(ROOT, "desk.py")
WM = os.path.join(ROOT, "wm.py")
fails = 0


def check(cond, msg):
    global fails
    if cond:
        print("ok " + msg)
    else:
        fails += 1
        print("FAIL " + msg)


def norm(text):
    low = text.lower().strip()
    return low, low.rstrip("?.!")


# --- wm.KEYS entry -------------------------------------------------------------------------------
wm_tree = ast.parse(open(WM, encoding="utf-8").read())
keys = None
for node in ast.walk(wm_tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "KEYS" for t in node.targets):
        keys = ast.literal_eval(node.value)
check(keys is not None and "private window" in keys, "wm.KEYS has a 'private window' entry")
want = ["-M", "ctrl", "-M", "shift", "-k", "p", "-m", "shift", "-m", "ctrl"]
check(keys is not None and keys.get("private window") == want, "private window key is Ctrl+Shift+P (Firefox): " + str(keys.get("private window") if keys else None))
check(keys is not None and keys.get("bookmarks") == ["-M", "ctrl", "-M", "shift", "-k", "o", "-m", "shift", "-m", "ctrl"], "existing 'bookmarks' key unchanged")

# --- desk.py browser-key regex -------------------------------------------------------------------
desk_tree = ast.parse(open(DESK, encoding="utf-8").read())
pattern = None
for node in ast.walk(desk_tree):
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and getattr(node.value.func, "attr", "") == "fullmatch":
        arg = node.value.args[0] if node.value.args else None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "(?P<zin>" in arg.value:
            pattern = arg.value
check(pattern is not None and "(?P<priv>" in pattern, "desk browser-key regex has a (?P<priv>) group")
rx = re.compile(pattern)


def route(text):
    """The k the desk's chain would pick for text, or None when the browser-key route does not match."""
    low, l2 = norm(text)
    m = rx.fullmatch(l2)
    if not m:
        return None
    if m.group("zin"):
        return "zoom in"
    if m.group("zout"):
        return "zoom out"
    if m.group("bms") or m.group("bms2"):
        return "bookmarks"
    if m.group("priv"):
        return "private window"
    return "bookmark"


for phrase in ["private window", "open a private window", "new private window", "open incognito", "incognito",
               "Open a Private Window?", "open an incognito window", "start a new private window"]:
    got = route(phrase)
    check(got == "private window", f"{phrase!r} -> private window (got {got!r})")

for phrase in ["is this window private", "make my files private", "private browsing is useless"]:
    got = route(phrase)
    check(got is None, f"{phrase!r} does not match the browser-key route (got {got!r})")

# existing groups still match their phrases
check(route("bookmark this") == "bookmark", f"'bookmark this' -> bookmark (got {route('bookmark this')!r})")
check(route("zoom in") == "zoom in", f"'zoom in' -> zoom in (got {route('zoom in')!r})")
check(route("open my browser bookmarks") == "bookmarks", f"'open my browser bookmarks' -> bookmarks (got {route('open my browser bookmarks')!r})")

# the _WIN route (open a new tab) is unchanged
win = None
for node in ast.walk(desk_tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_WIN" for t in node.targets):
        win = node.value.args[0].value
check(win is not None and re.fullmatch(win, "open a new tab") is not None, "'open a new tab' still matches the _WIN route")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
