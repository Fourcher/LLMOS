#!/usr/bin/env python3
"""Host-side test of the plain English wording in i18n.py (the six strings reworded so the interface
does not say "on-device model" to people who only want the assistant). Checks: the six English values are
exact, every language block keeps the same key set as the reference commit (llmos-1.5.0), non-English
blocks are unchanged, and placeholders such as {model} match across languages.
Run: python3 tools/test-i18n-plain.py"""
import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LLMOS_DIR = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos", "llmos")
ROOTFS = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos")
REF = "llmos-1.5.0"
BLOCKS = ["EN", "ZH", "ES", "FR", "DE", "JA"]
NEW = {
    "loading_model": "Getting ready…",
    "model_down": "The assistant isn't answering right now. Try again in a moment, or say \"the assistant isn't answering\".",
    "w_model_none": "This computer's memory is too small to run the assistant here.",
    "d_online_failed": "This computer couldn't finish it on its own.",
    "w_text": "This computer does what you tell it — in plain words, typed or spoken. The assistant runs on this computer itself; nothing you do leaves it unless you ask for something from the internet. A few quick questions, then it's yours.",
    "w_net_no_d": "The firewall blocks all outgoing traffic. Everything else still works.",
}
PLACEHOLDER = re.compile(r"\{(\w+)\}")

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def blocks_from_source(src):
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in BLOCKS:
                    out[t.id] = ast.literal_eval(node.value)
    return out


src = open(os.path.join(LLMOS_DIR, "i18n.py"), encoding="utf-8").read()
new = blocks_from_source(src)
old_src = subprocess.run(["git", "show", REF + ":./i18n.py"], cwd=LLMOS_DIR,
                         capture_output=True, text=True, check=False)
check(old_src.returncode == 0, f"reference {REF}:i18n.py readable")
old = blocks_from_source(old_src.stdout) if old_src.returncode == 0 else {}

check(sorted(new) == sorted(BLOCKS), "all six language blocks present")
NEW_KEYS = {"no_model"}  # the one key added to every block (no assistant set up yet)
for b in BLOCKS:
    if b in old:
        check(set(new[b]) == set(old[b]) | NEW_KEYS, f"{b}: key set = {REF} + no_model ({len(new[b])} keys)")
        check(all(isinstance(new[b].get(k), str) and "{" not in new[b][k] for k in NEW_KEYS),
              f"{b}: no_model present and has no placeholder braces")
        if b != "EN":
            check({k: v for k, v in new[b].items() if k not in NEW_KEYS} == old[b],
                  f"{b}: values unchanged apart from no_model (non-English not edited)")

en = new.get("EN", {})
check(en.get("no_model") == "No assistant is set up yet.", "EN no_model == 'No assistant is set up yet.'")
for key, text in NEW.items():
    check(en.get(key) == text, f"EN {key} == new text")
    if key in old.get("EN", {}):
        old_ph = sorted(PLACEHOLDER.findall(old["EN"][key]))
        check(sorted(PLACEHOLDER.findall(en.get(key, ""))) == old_ph, f"EN {key}: placeholders {old_ph} kept")
    for b in BLOCKS:
        if b != "EN" and key in new.get(b, {}):
            ph_en = sorted(PLACEHOLDER.findall(en.get(key, "")))
            ph_b = sorted(PLACEHOLDER.findall(new[b][key]))
            check(ph_en == ph_b, f"{b} {key}: placeholders match English {ph_en}")

# the importable module still loads and gives the new text
sys.path.insert(0, ROOTFS)
import llmos.i18n as i18n  # noqa: E402

check(i18n.EN.get("loading_model") == NEW["loading_model"], "i18n.EN imports with new loading_model")
check(i18n.EN.get("w_text") == NEW["w_text"], "i18n.EN imports with new w_text")

print("all good" if fails == 0 else f"{fails} FAIL(S)")
sys.exit(1 if fails else 0)
