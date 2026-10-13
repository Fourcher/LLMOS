#!/usr/bin/env python3
"""Host-side test of keyboard reach in the desk renderer (desk.js, desk.css): the clock is a keyboard button, Enter
confirms a plain question but never a danger one, the .seg radio groups answer the arrow keys with wrap-around, and
the textarea focus keeps a visible outline. The seg arrow rule is run on its own under node.
Run: python3 tools/test-desk-keyboard.py"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(HERE, "..", "src/rootfs/usr/share/llmos/desk")
JS = os.path.join(DESK, "desk.js")
CSS = os.path.join(DESK, "desk.css")
src = open(JS, encoding="utf-8").read()
css = open(CSS, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


# 1. node parses desk.js
r = subprocess.run(["node", "--check", JS], capture_output=True, text=True)
check(r.returncode == 0, "node --check desk.js" + ("" if r.returncode == 0 else " : " + r.stderr.strip()))

# 2. clock is keyboard reachable and acts like a click
clock_line = next((ln for ln in src.splitlines() if 'const openClock' in ln), "")
check(bool(clock_line), "clock action is a named function (openClock)")
check('$("clock").tabIndex = 0' in src, "clock gets tabIndex 0")
check('setAttribute("role", "button")' in src and '$("clock").setAttribute("role"' in src, "clock gets role=button")
check('$("clock").setAttribute("aria-label", t("d_clock_title"' in src, "clock aria-label reuses d_clock_title")
m = re.search(r'\$\("clock"\)\.addEventListener\("keydown", \(e\) => \{ if \(e\.key === "Enter" \|\| e\.key === " "\) \{ e\.preventDefault\(\); openClock\(\); \} \}\);', src)
check(m is not None, "clock keydown: Enter or Space -> openClock, preventDefault")
check('$("clock").addEventListener("click", openClock)' in src, "clock click still calls openClock")

# 3. dialogs: Enter confirms only plain dialogs, and never while typing or on a button
dlg_block = src[src.index('document.addEventListener("keydown", (e) => {\n    const ov = $("overlay");'):]
dlg_block = dlg_block[:dlg_block.index("if (wizard.active")]
check('e.key === "Escape") { dialogDone(ov)' in dlg_block, "Escape still declines the dialog")
check('e.key === "Enter"' in dlg_block, "overlay keydown has an Enter branch")
check('.dlg:not(.danger) .btn.primary' in dlg_block, "Enter branch clicks the primary button of a non-danger dialog only")
check('tag !== "TEXTAREA" && tag !== "INPUT" && tag !== "BUTTON"' in dlg_block, "Enter branch skips textarea, input and focused buttons")
check('m.danger ? d.querySelector(\'[data-value="no"]\') : d.querySelector(".btn.primary")' in src,
      "initial focus: danger -> no, plain -> primary")

# 4. seg radio groups: the four arrow keys are handled on role=radio inside role=radiogroup
seg_block = src[src.index("document.addEventListener(\"keydown\", (e) => {\n    const r = e.target;"):]
seg_block = seg_block[:seg_block.index("document.addEventListener(\"keydown\", (e) => {\n    const ov")]
check('role") === "radio"' in seg_block and 'parentElement.getAttribute("role") === "radiogroup"' in seg_block,
      "seg handler only acts on radio buttons inside a radiogroup")
for key in ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]:
    check(f'"{key}"' in src[src.index("function nextIndex"):src.index("function nextIndex") + 400],
          f"nextIndex handles {key}")
check("opts[j].focus(); opts[j].click();" in seg_block, "seg handler focuses and clicks the next option")

# 5. nextIndex as a pure function, run under node
fn = re.search(r"  function nextIndex\(i, n, key\) \{\n.*?\n  \}\n", src, re.S)
check(fn is not None, "nextIndex extracted from desk.js")
if fn:
    code = fn.group(0) + """
const cases = [
  [0, 3, "ArrowRight", 1], [1, 3, "ArrowRight", 2], [2, 3, "ArrowRight", 0],
  [0, 3, "ArrowLeft", 2], [2, 3, "ArrowLeft", 1], [0, 3, "ArrowDown", 1], [2, 3, "ArrowDown", 0],
  [0, 3, "ArrowUp", 2], [1, 3, "ArrowUp", 0], [0, 1, "ArrowRight", 0], [0, 3, "Enter", -1],
  [0, 3, "a", -1], [-1, 3, "ArrowRight", -1], [0, 0, "ArrowRight", -1]
];
const bad = cases.filter(([i, n, k, want]) => nextIndex(i, n, k) !== want);
console.log(JSON.stringify({ n: cases.length, bad }));
"""
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    out = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {"n": 0, "bad": ["node failed: " + r.stderr]}
    check(not out["bad"], f"nextIndex wraps and ignores other keys ({out['n']} cases)" + ("" if not out["bad"] else " : " + json.dumps(out["bad"])))

# 6. desk.css: a rule that removes the outline on a :focus selector must put one back in the same rule
rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
bad_rules = []
for sel, body in rules:
    if ":focus" in sel and re.search(r"outline\s*:\s*none", body):
        if not re.search(r"outline\s*:\s*(?!none)", body):
            bad_rules.append(sel.strip())
check(not bad_rules, "no :focus rule removes the outline without a replacement" + ("" if not bad_rules else " : " + repr(bad_rules)))
check("outline: 2px solid var(--accent); outline-offset: 2px; border-color: var(--accent);" in css,
      "textarea:focus keeps the border colour and gets a 2px accent outline")

print("all good" if fails == 0 else f"{fails} FAIL(S)")
sys.exit(1 if fails else 0)
