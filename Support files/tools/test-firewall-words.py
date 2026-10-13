#!/usr/bin/env python3
"""Host-side test of the firewall words.
- intent.match: "turn off the firewall", "disable the firewall", "firewall off", "switch the firewall off" -> change_setting
  firewall off; "turn on the firewall", "enable the firewall", "firewall on" -> change_setting firewall on.
  The internet on/off routes are unchanged.
- desk._HOWTO (read with ast; desk.py needs GTK): the status questions ("is the firewall on", "check the firewall",
  "do i have a firewall") answer from the setting: firewall off -> the off text, otherwise the on text.
  "turn on"/"enable" are no longer status questions; they go to the setting route.
- negatives: "turn off the fire alarm", "firewall rules explained", "is my firewall software good" are not firewall
  settings and get no fixed firewall answer.
Run: python3 tools/test-firewall-words.py (no VM, no nft). Exit status 0 = pass."""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(HERE, "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True

DESK = os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py")
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


# ---- intent routes
for phrase in ("turn off the firewall", "disable the firewall", "firewall off", "switch the firewall off",
               "turn the firewall off"):
    got = intent.match(phrase)
    check(got == ("change_setting", {"setting": "firewall", "value": "off"}), f"{phrase!r} -> firewall off: {got}")
for phrase in ("turn on the firewall", "enable the firewall", "firewall on", "switch the firewall on", "turn the firewall on"):
    got = intent.match(phrase)
    check(got == ("change_setting", {"setting": "firewall", "value": "on"}), f"{phrase!r} -> firewall on: {got}")
for phrase, value in (("turn the internet off", "no"), ("turn the internet on", "yes")):
    got = intent.match(phrase)
    check(got == ("change_setting", {"setting": "internet", "value": value}), f"{phrase!r} unchanged -> internet {value}: {got}")
for phrase in ("turn off the fire alarm", "firewall rules explained", "is my firewall software good"):
    got = intent.match(phrase)
    check(not (got and got[0] == "change_setting" and got[1].get("setting") == "firewall"),
          f"{phrase!r} is not a firewall setting: {got}")

# ---- desk table, read from source
src = open(DESK, encoding="utf-8").read()
tree = ast.parse(src)
table, howto_src = None, None
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "Desk":
        for item in node.body:
            if isinstance(item, ast.Assign) and any(getattr(t, "id", "") == "_HOWTO" for t in item.targets):
                table = ast.literal_eval(item.value)
            if isinstance(item, ast.FunctionDef) and item.name == "_howto":
                howto_src = ast.get_source_segment(src, item)
assert table is not None and howto_src is not None, "desk _HOWTO / _howto not found"


class Settings:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class Config:
    settings = Settings({})


ns = {"re": re, "config": Config}
import textwrap
exec(textwrap.dedent(howto_src), ns)   # defines _howto(self, l2) in ns
H = type("H", (), {"_HOWTO": table, "_howto": ns["_howto"]})
h = H()

OFF_TEXT = ("The firewall is off: other computers can connect to this one. "
            "Say \u201cturn the firewall on\u201d to put it back.")
ON_START = "The firewall is always on:"

for setting, label in (("off", "off"), (None, "on (default)"), ("on", "on")):
    Config.settings = Settings({} if setting is None else {"firewall": setting})
    for phrase in ("is the firewall on", "check the firewall", "do i have a firewall"):
        reply = h._howto(phrase.rstrip("?.!"))
        if label == "off":
            check(reply == OFF_TEXT, f"[{label}] {phrase!r} -> off text")
        else:
            check(reply is not None and reply.startswith(ON_START), f"[{label}] {phrase!r} -> on text")

Config.settings = Settings({"firewall": "off"})
for phrase in ("turn on the firewall", "enable the firewall", "turn off the firewall", "firewall rules explained",
               "is my firewall software good", "turn off the fire alarm"):
    check(h._howto(phrase) is None, f"[off] {phrase!r} -> not a fixed firewall answer")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
