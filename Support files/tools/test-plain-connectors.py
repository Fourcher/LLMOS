#!/usr/bin/env python3
"""Host-side test of the plain-words wording of the connector and online-model texts in i18n.py.
For each reworded key and each language block: no "MCP", no "/etc/" path. English has no "API account",
"external tools" or "Tools:". Placeholders such as {n} match the English value in every language.
Run: python3 tools/test-plain-connectors.py"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos", "llmos", "i18n.py")
BLOCKS = ["EN", "ZH", "ES", "FR", "DE", "JA"]
KEYS = ["d_conduct_hint", "d_connectors_intro", "d_conn_tools", "d_connector_form_intro",
        "d_connector_form_hint", "w_cloud_text"]
EN_BANNED = ["API account", "external tools", "Tools:"]
PLACEHOLDER = re.compile(r"\{(\w+)\}")
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


blocks = {}
for node in ast.parse(open(SRC, encoding="utf-8").read()).body:
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in BLOCKS:
                blocks[t.id] = ast.literal_eval(node.value)

check(sorted(blocks) == sorted(BLOCKS), "all six language blocks parse")
en = blocks.get("EN", {})
for key in KEYS:
    en_val = en.get(key)
    check(isinstance(en_val, str), f"EN {key} present")
    if not isinstance(en_val, str):
        continue
    en_ph = sorted(PLACEHOLDER.findall(en_val))
    for b in BLOCKS:
        val = blocks.get(b, {}).get(key)
        check(isinstance(val, str), f"{b} {key} present")
        if not isinstance(val, str):
            continue
        check("MCP" not in val, f"{b} {key}: no 'MCP'")
        check("/etc/" not in val, f"{b} {key}: no '/etc/' path")
        check(sorted(PLACEHOLDER.findall(val)) == en_ph, f"{b} {key}: placeholders {en_ph} match English")
    for banned in EN_BANNED:
        check(banned not in en_val, f"EN {key}: no {banned!r}")

print("all good" if fails == 0 else f"{fails} FAIL(S)")
sys.exit(1 if fails else 0)
