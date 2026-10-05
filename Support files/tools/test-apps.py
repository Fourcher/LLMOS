#!/usr/bin/env python3
"""Host-side test of the ready-made apps (llmos/apps.py, usr/share/llmos/apps/) and whole looks (llmos/themes.py):
every template is valid and its script parses; what people ask for finds the right app; an app made with a look keeps
it and is sealed off from the network; the system look reaches apps without their own; app data is kept; themes read
"dark mode", "ocean", "make everything purple", "serif", "default theme" the way a person means them.
Run: python3 tools/test-apps.py"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import apps, themes  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


print("ready-made apps")
ts = apps.templates()
check(len(ts) >= 16, f"{len(ts)} ready-made apps")
node = shutil.which("node")
for t in ts:
    with open(os.path.join(apps.SHARE, t["id"] + ".html"), encoding="utf-8") as f:
        src = f.read()
    scripts = re.findall(r"(?is)<script>(.*?)</script>", src)
    bad = re.search(r"(?i)\bfetch\(|XMLHttpRequest|WebSocket|localStorage|<script[^>]+src=|<link", src)
    ok = bool(t.get("title")) and bool(scripts) and not bad
    if ok and node:
        p = subprocess.run([node, "--check", "-"], input="\n".join(scripts), capture_output=True, text=True)
        ok = p.returncode == 0
        if not ok:
            print("       " + p.stderr.strip().splitlines()[0] if p.stderr.strip() else "")
    check(ok, f"{t['id']}: has a title, its script parses, nothing reaches the network")

WANT = {"a calculator": "calculator", "calculator app with a forest theme": "calculator", "tip calculator": "tip",
        "a stopwatch": "timer", "kitchen timer": "timer", "to-do list": "todo", "a checklist": "todo",
        "water tracker": "tracker", "habit tracker": "tracker", "budget tracker": "tracker",
        "countdown to my birthday": "countdown", "flashcards to study spanish": "flashcards", "tic tac toe": "tictactoe",
        "snake game": "snake", "a notepad": "notes", "drawing app": "sketch", "unit converter": "converter",
        "password generator": "password", "roll dice": "dice", "a calendar": "calendar"}
for words, want in WANT.items():
    t = apps.match_template(words)
    check(t and t["id"] == want, f"{words!r} -> {want}" + ("" if t and t["id"] == want else f" (got {t and t['id']})"))
check(apps.match_template("a spreadsheet for my taxes with charts") is None, "something with no ready-made app is left for the model to write")

print("made apps")
a = apps.from_template(apps.match_template("calculator"), "forest")
with open(a["file"], encoding="utf-8") as f:
    doc = f.read()
check(a["title"] == "Calculator · Forest", f"the look shows in the title ({a['title']!r})")
check("Content-Security-Policy" in doc and "connect-src 'none'" in doc.replace('"', "'") or "default-src 'none'" in doc.replace('"', "'"),
      "the app is sealed off from the network")
check("LLMOS" in doc and "<!doctype html>" in doc, "it is a whole page with the OS bridge")
plain = apps.from_template(apps.match_template("calculator"))
check(plain["id"] != a["id"] and os.path.exists(a["file"]), "a plain one sits next to the themed one")
check(apps.find("calculator") is not None and len(apps.installed()) == 2, "both are installed and found by name")
apps.save_state(plain["id"], {"memory": 42})
check(apps.load_state(plain["id"]) == {"memory": 42}, "an app's data is kept")
check(apps.save_state(plain["id"], {"x": "y" * (apps.MAX_STATE + 10)}) is False, "oversized app data is refused")
with open(a["file"], encoding="utf-8") as f:
    before_themed = f.read()
n = apps.retheme()
with open(a["file"], encoding="utf-8") as f:
    check(f.read() == before_themed and n >= 0, "an app with its own look keeps it when the system look changes")
body = apps._strip_doc('<html><head><script src="https://x.example/a.js"></script></head><body><p>hi</p>'
                       '<link rel="stylesheet" href="https://x"><script>1</script></body></html>')
check("x.example" not in body and "<link" not in body and "<p>hi</p>" in body, "a written app loses outside scripts and styles")
check(apps.remove(plain["id"]) and apps.load_state(plain["id"]) is None, "removing an app removes its data")

print("themes")
dark = themes.resolve("dark mode", ("#26110e", "#ffe8d6", "#ff7a3d"))
check(dark and dark["mode"] == "dark" and dark["background"] == themes.DEFAULT[0], "dark mode is the neutral dark look, not the old colours")
light = themes.resolve("light mode")
check(light and light["mode"] == "light" and themes.lum(light["background"]) > 0.5, "light mode is light")
oc = themes.resolve("ocean theme")
check(oc and oc["accent"] == "#2ec4f1", "a named theme is a whole palette")
retro = themes.resolve("make it look like a retro terminal")
check(retro and retro.get("font") == "mono", "a retro look brings its font")
pu = themes.resolve("make everything purple")
check(pu and pu["mode"] == "dark" and themes.lum(pu["background"]) < 0.2, "a colour makes a dark, tinted theme")
for words in ("make everything purple", "orange theme", "pink"):
    t = themes.resolve(words)
    lb, lf = themes.lum(t["background"]), themes.lum(t["color"])
    ratio = (max(lb, lf) + 0.05) / (min(lb, lf) + 0.05)
    check(ratio >= 4.5, f"{words!r}: text is readable on its background (contrast {ratio:.1f})")
d = themes.resolve("go back to the default theme")
check(d and d["background"] == "" and d.get("font") == "sans", "'default theme' resets everything")
check(themes.resolve("what's the weather") is None, "words that name no look change nothing")
for words, want in (("serif", "serif"), ("a sans-serif font", "sans"), ("monospace font", "mono"), ("pixel font", "pixel"),
                    ("a typewriter font", "mono"), ("something elegant", "serif")):
    got = themes.font_for(words)
    check(got == want, f"font {words!r} -> {want}" + ("" if got == want else f" (got {got!r})"))

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
