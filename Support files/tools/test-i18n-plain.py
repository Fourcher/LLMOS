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
# the reference is the merge-base of HEAD and REF, so a branch cut from an older commit is compared with its own
# base rather than the moving integration tip; if there is no merge-base, REF is used as before
mb = subprocess.run(["git", "merge-base", "HEAD", REF], cwd=LLMOS_DIR,
                    capture_output=True, text=True, check=False)
REF_USED = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else REF
old_src = subprocess.run(["git", "show", REF_USED + ":./i18n.py"], cwd=LLMOS_DIR,
                         capture_output=True, text=True, check=False)
check(old_src.returncode == 0, f"reference {REF_USED} ({'merge-base with ' + REF if REF_USED != REF else REF}):i18n.py readable")
old = blocks_from_source(old_src.stdout) if old_src.returncode == 0 else {}

check(sorted(new) == sorted(BLOCKS), "all six language blocks present")
NEW_KEYS = {"no_model", "d_maximize", "d_window", "d_sure", "d_slow_turn"}  # keys added to every block (no assistant set up yet; window controls; sure-press and slow-turn notices)
# the model-size words for the set-up's "More models" list (every block has them; the old values are unchanged)
ADDED_KEYS = {"w_model_slow", "w_more_models"}
# the "online for everything" description gained the sentence "Your name and saved memory go with each request." (test-privacy-disclosure.py)
ALLOWED_EDITS = {"q_brain_2",
                 # the "yes" internet choice says it also keeps the clock right (the boot timer syncs it; test-net-disclosure.py)
                 "w_net_yes_d",
                 # plain-words rewording of the connector and cloud texts (test-plain-connectors.py)
                 "d_conduct_hint", "d_connectors_intro", "d_conn_tools", "d_connector_form_intro",
                 "d_connector_form_hint", "w_cloud_text"}
for b in BLOCKS:
    if b in old:
        check(set(new[b]) == set(old[b]) | NEW_KEYS | ADDED_KEYS,
              f"{b}: key set = {REF} + new keys + model-size words ({len(new[b])} keys)")
        check(all(isinstance(new[b].get(k), str) and "{" not in new[b][k] for k in NEW_KEYS | ADDED_KEYS),
              f"{b}: new keys and model-size words present, no placeholder braces")
        if b != "EN":
            skip = NEW_KEYS | ADDED_KEYS | ALLOWED_EDITS
            check({k: v for k, v in new[b].items() if k not in skip}
                  == {k: v for k, v in old[b].items() if k not in skip},
                  f"{b}: values unchanged apart from no_model, the model-size words and q_brain_2 (non-English not edited)")

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

# every t("...") key desk.js uses must be in desk.py _PAGE_KEYS and present in the EN block, or the page shows the raw key
DESK_JS = os.path.join(HERE, "..", "src/rootfs/usr/share/llmos/desk/desk.js")
desk_js = open(DESK_JS, encoding="utf-8").read()
desk_py = ast.parse(open(os.path.join(LLMOS_DIR, "desk.py"), encoding="utf-8").read())
page_keys = set()
for node in desk_py.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_PAGE_KEYS" for t in node.targets):
        page_keys = set(ast.literal_eval(node.value))
PAGE_USED = sorted(set(re.findall(r'(?<![\w.])t\("([a-z][\w-]*)"\s*[,)]', desk_js)))
check(len(PAGE_USED) > 50, f"desk.js t() keys found ({len(PAGE_USED)})")
for k in PAGE_USED:
    check(k in page_keys, f"desk.py _PAGE_KEYS contains {k}")
    check(k in en, f"i18n EN contains {k}")

# desk.js also builds keys from template literals (the wizard quiz), which the regex above cannot see. The
# expansions are hard-coded here from the source named in each comment; each anchor must still appear verbatim in
# desk.js, and each array the expansion depends on must still read the same, so the list cannot drift silently.
QN = {"autonomy": 3, "internet": 3, "brain": 3, "guidance": 2, "motion": 3}   # desk.js line 314: const Q = [...] (k, n)
DESK_JS_ANCHORS = [
    'const Q = [{ k: "autonomy", n: 3 }, { k: "internet", n: 3 }, { k: "brain", n: 3 }, { k: "capability", n: 3 }, { k: "guidance", n: 2 }, { k: "motion", n: 3 }];',
    'const TIER = ["fast", "balanced", "capable"];',                                  # desk.js line 315
    '["hands-off", "balanced", "hands-on"]', '["yes", "ask", "no"]', '["local", "ask", "cloud"]',
    '["owner", "standard"]', '["off", "reduced", "full"]',                             # desk.js line 450-454 pick orders
    "t(`q_capability_${TIER.indexOf(x.tier)}_s`)",                                    # desk.js line 346
    "t(`q_capability_${TIER.indexOf(r.tier)}_s`)",                                    # desk.js line 350
    "t(`q_${q.k}_${i}_s`)",                                                           # desk.js line 353
    "t(`q_${q.k}_${cur}`)",                                                           # desk.js line 355
    "t(`q_motion_${rec().motion}_s`)",                                                # desk.js line 356
    "t(`q_${k}_${i}_s`)",                                                             # desk.js line 450
]
for anchor in DESK_JS_ANCHORS:
    check(anchor in desk_js, f"desk.js still contains {anchor[:60]}")
TEMPLATE_KEYS = sorted(set(
    [f"q_capability_{i}_s" for i in range(3)]                                         # line 346, 350: TIER.indexOf -> 0..2
    + [f"q_{k}_{i}_s" for k, n in QN.items() for i in range(n)]                        # line 353, 450: q_${k}_${i}_s over Q / pick orders
    + [f"q_{k}_{i}" for k, n in QN.items() for i in range(n)]                          # line 355: q_${q.k}_${cur} (no _s) over Q
    + ["q_motion_1_s", "q_motion_2_s"]                                                # line 356: desk.py _recommend motion is 2 or 1
))
# keys the expansion produces that desk.py _PAGE_KEYS or the EN block lack; they are shown as gaps, not hidden.
# A key listed here must still be missing (the check below fails when a gap is fixed, so the entry gets removed).
KNOWN_MISSING = set()
check(len(TEMPLATE_KEYS) == 31, f"desk.js template-literal keys expanded ({len(TEMPLATE_KEYS)})")
for k in TEMPLATE_KEYS:
    if k in KNOWN_MISSING:
        check(k not in page_keys or k not in en, f"KNOWN_MISSING {k} is still missing (remove it from KNOWN_MISSING)")
    else:
        check(k in page_keys, f"desk.py _PAGE_KEYS contains template key {k}")
        check(k in en, f"i18n EN contains template key {k}")

# the importable module still loads and gives the new text
sys.path.insert(0, ROOTFS)
import llmos.i18n as i18n  # noqa: E402

check(i18n.EN.get("loading_model") == NEW["loading_model"], "i18n.EN imports with new loading_model")
check(i18n.EN.get("w_text") == NEW["w_text"], "i18n.EN imports with new w_text")

print("all good" if fails == 0 else f"{fails} FAIL(S)")
sys.exit(1 if fails else 0)
