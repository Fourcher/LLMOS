#!/usr/bin/env python3
"""Host-side test of three more plain-words routes in desk.py: a frozen program (stop it, asks first), the bare
"voice memo" / "voice note" words, and "add <language> keyboard" (keyboard layout). The patterns are read with ast from
desk.py (it needs GTK). The program-window route runs with stubs only: no keys, no recording, nothing is killed.
Run: python3 tools/test-desk-words2.py"""
import ast
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos")
SRC = os.path.join(LIB, "llmos", "desk.py")
src = open(SRC, encoding="utf-8").read()
tree = ast.parse(src)
sys.path.insert(0, LIB)
import llmos.syspanels as syspanels  # stdlib only

fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


def pattern(marker):
    """The regex literal (implicit concatenation included) of the re.compile/re.fullmatch call that contains marker."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("compile", "fullmatch") and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and marker in node.args[0].value:
            return node.args[0].value
    raise SystemExit(f"pattern with {marker!r} not found in desk.py")


# ---------------------------------------------------------------- frozen programs: the window route, stopped with stubs
WIN = pattern("(?P<frozen>")
body = src[src.index("    _WIN = re.compile"): src.index("    def _howto")]
calls = []
ask_titles = []
ns = {"re": re, "wm": None, "threading": None}
ns["wm"] = types.SimpleNamespace(
    app_id=lambda s: "firefox" if s in ("firefox", "browser") else None,
    last_program=lambda: "firefox",
    NAMES={"firefox": "Firefox"},
    force_quit=lambda t: (calls.append(("force_quit", t)), (True, "stopped"))[1],
    act=lambda *a: (calls.append(("act",) + a), (True, ""))[1],
    browser_key=lambda *a: (calls.append(("key",) + a), (True, ""))[1])
ns["threading"] = types.SimpleNamespace(Thread=lambda target, daemon=False: types.SimpleNamespace(start=target))
exec("class X:\n" + body, ns)
X = ns["X"]


def desk():
    d = X()
    d.GLib = types.SimpleNamespace(idle_add=lambda f: None)
    d.webview = None
    d.last_reply = d._said = ""
    d.instant_reply = lambda line, text: calls.append(("reply", text))
    def ask(spec, consent=False):
        ask_titles.append(spec.get("title"))
        return False                          # the owner is asked; the stub says no, so nothing is stopped
    d.ask = ask
    return d


def window(q):
    del calls[:], ask_titles[:]
    r = desk()._window_shortcut(q)
    return r, list(ask_titles), [c for c in calls if c[0] == "force_quit"]


print("frozen program: stop it (last program, asks first)")
for q in ("this app is frozen", "the app is frozen", "this program froze", "my app stopped responding"):
    r, asked, killed = window(q)
    check(r is True and asked == ["Stop Firefox?"] and not killed, f"{q!r} -> stop the last program, asked first")
for q in ("it's frozen", "its frozen"):
    r, asked, killed = window(q)
    check(r is False and not asked and not killed, f"{q!r} is ambiguous: not the stop route (assistant route)")
r, asked, killed = window("force quit this")
check(r is True and asked == ["Stop Firefox?"] and not killed, "'force quit this' still reaches the stop path")
for q, g in (("firefox is frozen", "frozen"), ("force quit firefox", "killw"), ("new tab", "key"),
             ("close the browser window", "closew"), ("switch to the files app", "focus"), ("maximize the browser", "maxw")):
    m = re.fullmatch(WIN, q.rstrip(".!?"))
    check(bool(m and m.group(g)), f"existing {q!r} still sets group {g}")
for q in ("the lake is frozen", "frozen pizza"):
    r, asked, killed = window(q)
    check(r is False and not asked and not killed, f"{q!r} is not a frozen program")
check(not re.fullmatch(WIN, "the lake is frozen").groupdict().get("stopf"), "'the lake is frozen' has no stop group")

print("voice memo / voice note")
VOICE = pattern("(?P<k3>voice memo|voice note)")


def voice_kind(q):
    m = re.fullmatch(VOICE, q)
    if not m:
        return None
    k = m.group("k") or m.group("k2") or m.group("k3") or ""
    return "screen" if re.search(r"screen|desktop", k) else "voice"


for q in ("voice memo", "voice note", "record a voice memo", "record a voice note", "make a voice memo", "start a voice note"):
    check(voice_kind(q) == "voice", f"{q!r} -> voice recording")
for q in ("voice memos are great", "voice notes", "record my screen"):
    kind = voice_kind(q)
    check(kind != "voice", f"{q!r} is not the voice-memo route (got {kind!r})")
check(voice_kind("record my screen") == "screen", "'record my screen' is still the screen recording")

print("add <language> keyboard (keyboard layout route)")
KB = pattern("keyboard layout|use an?")


def layout(q):
    m = re.fullmatch(KB, q)
    if not m or not syspanels.layout_code(m.group("k")):
        return None
    return syspanels.layout_code(m.group("k"))


for q, want in (("add french keyboard", "fr"), ("add a german keyboard", "de"), ("add the spanish keyboard layout", "es"),
                ("add the french layout", "fr")):
    check(layout(q) == want, f"{q!r} -> {want}")
for q in ("add it", "add in", "add us", "add no", "add french", "add german"):
    check(layout(q) is None, f"{q!r} is not the keyboard route (no question, no change)")
for q, want in (("use a german keyboard", "de"), ("keyboard layout french", "fr"), ("switch keyboard to spanish", "es"),
                ("change keyboard layout to german", "de")):
    check(layout(q) == want, f"existing {q!r} -> {want} unchanged")
for q in ("add french to my languages", "add a keyboard shortcut"):
    check(layout(q) is None, f"{q!r} is not a keyboard layout")

print("_instant gate (what may run at once while the model is busy)")
sys.path.insert(0, os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos"))
from llmos.desk import Desk


def instant(q):
    return bool(Desk.__new__(Desk)._instant(q))


for q in ("add french keyboard", "add the french layout", "this app is frozen", "my program froze",
          "the app stopped responding", "voice memo", "voice note"):
    check(instant(q) is True, f"{q!r} runs at once while busy")
for q in ("news", "logs", "what time is it", "open firefox", "settings", "help", "stop", "lock", "wifi", "battery"):
    check(instant(q) is True, f"existing {q!r} still runs at once")
for q in ("add it", "add in", "my hands are frozen"):
    check(instant(q) is False, f"{q!r} does not run at once")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
