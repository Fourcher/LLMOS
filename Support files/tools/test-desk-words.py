#!/usr/bin/env python3
"""Host-side test of the words the desk answers at once, without the model (desk.py: battery, clipboard, camera and
microphone, program windows, mouse/keyboard in plain words, rotate, resolution, USB, show the desktop). desk.py needs
GTK, so the patterns are read from its source. Run: python3 tools/test-desk-words.py"""
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
src = open(SRC, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def module_block(start, end):
    ns = {"re": re}
    exec(src[src.index(start):src.index(end)], ns)
    return ns


def class_block(start, end):
    ns = {"re": re}
    exec("class X:\n" + src[src.index(start):src.index(end)], ns)
    return ns["X"]


top = module_block("_BATTERY_Q = re.compile", "_LOCK_WORDS = {")
X = class_block("    _CANON = [", "    def _system_shortcut")
W = class_block("    _WIN = re.compile", "    def _window_shortcut")

print("answered at once")
for q in ("how much battery do i have", "battery", "is it charging"):
    check(bool(top["_BATTERY_Q"].fullmatch(q)), f"battery: {q!r}")
check(not top["_BATTERY_Q"].fullmatch("battery saver on"), "'battery saver on' is not a battery question")
for q, g in (("what did i copy", "what"), ("clipboard history", "hist"), ("clear the clipboard", "clear"), ("copy clip 17", "item")):
    m = top["_CLIP_Q"].fullmatch(q)
    check(bool(m and m.group(g)), f"clipboard: {q!r}")
for q, g in (("is my webcam working", "cam"), ("my camera isnt working in the call", "cam"), ("test my mic", "mic"), ("they can't hear me", "mic")):
    m = top["_DEV_Q"].fullmatch(q)
    check(bool(m and m.group(g)), f"camera/mic: {q!r}")

print("plain words for the panels' buttons")
for q, want in (("make the mouse faster", "mouse faster"), ("the mouse is too slow", "mouse faster"), ("slow down the mouse", "mouse slower"),
                ("reverse scrolling", "natural scrolling on"), ("i'm left-handed", "left handed mouse on"), ("turn off tap to click", "tap to click off")):
    got = next((c for r, c in X._CANON if r.fullmatch(q)), None)
    check(got == want, f"{q!r} -> {want!r}" + ("" if got == want else f" (got {got!r})"))
for q, rx in (("rotate the screen", "_ROTATE"), ("the screen is upside down", "_ROTATE"), ("set the resolution to 1920x1080", "_RES"),
              ("eject the usb stick", "_EJECT"), ("is it safe to remove the usb", "_EJECT"), ("show the desktop", "_DESKTOP"),
              ("minimize everything", "_DESKTOP"), ("put the browser on the left", "_TILE")):
    check(bool(getattr(X, rx).fullmatch(q)), f"{q!r} is understood")

print("program windows")
for q, g in (("close the browser window", "closew"), ("switch to the files app", "focus"), ("maximize the browser", "maxw"),
             ("new tab", "key"), ("go back", "key"), ("firefox is frozen", "frozen"), ("force quit firefox", "killw")):
    m = W._WIN.fullmatch(q)
    check(bool(m and m.group(g)), f"{q!r}")
check(not W._WIN.fullmatch("close the door"), "'close the door' is not a window")

print("help shortcut speaks a how-to, not just done")
help_match = re.search(r'if low in \("help", "\?"\):\s+self\._said = "([^"]+)"', src)
check(bool(help_match), "help shortcut sets self._said")
if help_match:
    said = help_match.group(1)
    has_hint = any(hint in said for hint in ("F1", "Esc", "Type what you want", "close"))
    check(has_hint, f"help _said contains helpful cue: {said!r}")

print("every tool's decorator sits on its own function (a helper slipped in between takes the tool's place)")
tsrc = open(os.path.join(os.path.dirname(SRC), "tools.py"), encoding="utf-8").read()
for m in re.finditer(r'@tool\("(\w+)"', tsrc):
    nxt = re.search(r"\ndef (\w+)\(", tsrc[m.end():])
    check(nxt and nxt.group(1) == m.group(1), f"@tool {m.group(1)!r} -> def {nxt and nxt.group(1)}") if not nxt or nxt.group(1) != m.group(1) else None
check(True, "decorators checked")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
