#!/usr/bin/env python3
"""Host-side source checks for the guard_untrusted toggle in the desk's settings panel.
- desk.js renders a "toggle" block with a hint line and sends its say_on/say_off text as an "act" message.
- desk.py puts the guard_untrusted toggle in the settings panel, reads its current value (default on),
  and the "act" message handler carries the text to the agent.
- the say_on/say_off phrases are matched by intent._GUARD and resolve to change_setting guard_untrusted on/off,
  and tools.py writes config.settings "guard_untrusted" from that.
- the two label keys exist in all six language tables.
Run: python3 tools/test-guard-toggle.py  (no VM needed). Exit status 0 = pass."""
import ast
import os
import py_compile
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(TOOLS), "src", "rootfs")
DESK_PY = os.path.join(ROOT, "usr", "lib", "llmos", "llmos", "desk.py")
DESK_JS = os.path.join(ROOT, "usr", "share", "llmos", "desk", "desk.js")
INTENT = os.path.join(ROOT, "usr", "lib", "llmos", "llmos", "intent.py")
TOOLS_PY = os.path.join(ROOT, "usr", "lib", "llmos", "llmos", "tools.py")
I18N = os.path.join(ROOT, "usr", "lib", "llmos", "llmos", "i18n.py")

failures = []


def check(label, ok):
    if ok:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}")
        failures.append(label)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


desk_py = read(DESK_PY)
desk_js = read(DESK_JS)
tools_py = read(TOOLS_PY)

# desk.js: toggle renders a hint line and sends the say text via act
toggle_start = desk_js.find('case "toggle"')
toggle_block = desk_js[toggle_start:toggle_start + 700] if toggle_start >= 0 else ""
check("desk.js has a toggle case", toggle_start >= 0)
check("desk.js toggle renders b.hint", "b.hint" in toggle_block)
check("desk.js toggle sends say_on/say_off via act", "act(on ? b.say_on : b.say_off)" in toggle_block)

# desk.py: the toggle block for guard_untrusted in the settings panel
check("desk.py settings toggle label uses s_guard_untrusted",
      'L("s_guard_untrusted")' in desk_py)
check("desk.py settings toggle hint uses s_guard_untrusted_hint",
      'L("s_guard_untrusted_hint")' in desk_py)
check("desk.py toggle reads guard_untrusted with default on",
      'bool(s.get("guard_untrusted", True))' in desk_py)
check("desk.py settings toggle is type toggle",
      re.search(r'"type": "toggle", "label": L\("s_guard_untrusted"\)', desk_py) is not None)
check("desk.py has the act message handler", 'elif t == "act":' in desk_py)

# Extract say phrases from the desk.py toggle block
m = re.search(r'"say_on": "([^"]+)",\s*"say_off": "([^"]+)"', desk_py[desk_py.find("s_guard_untrusted"):])
say_on, say_off = (m.group(1), m.group(2)) if m else (None, None)
check("desk.py guard toggle has say_on and say_off", bool(m))

# intent._GUARD (read from source, intent.py needs its package to import)
intent_tree = ast.parse(read(INTENT))
guard_src = None
for node in intent_tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_GUARD" for t in node.targets):
        guard_src = ast.literal_eval(node.value.args[0])
check("intent.py defines _GUARD", guard_src is not None)
GUARD = re.compile(guard_src, re.I) if guard_src else None


def guard_value(text):
    mm = GUARD.match(text.strip()) if GUARD else None
    if not mm:
        return None
    off = bool(mm.group("off") or mm.group("off2") or (mm.group("onoff") or "").lower() == "off")
    return "off" if off else "on"


if say_on and say_off:
    check(f"say_on {say_on!r} -> guard_untrusted on", guard_value(say_on) == "on")
    check(f"say_off {say_off!r} -> guard_untrusted off", guard_value(say_off) == "off")

# tools.py: the write to config.settings for guard_untrusted
check("tools.py writes config.settings guard_untrusted",
      'config.settings.set("guard_untrusted", on)' in tools_py)

# i18n: both keys in all six language tables
i18n_tree = ast.parse(read(I18N))
tables = {}
for node in i18n_tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in ("EN", "ZH", "ES", "FR", "DE", "JA"):
                tables[t.id] = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
for lang in ("EN", "ZH", "ES", "FR", "DE", "JA"):
    have = tables.get(lang, set())
    check(f"i18n {lang} has s_guard_untrusted and s_guard_untrusted_hint",
          {"s_guard_untrusted", "s_guard_untrusted_hint"} <= have)

try:
    py_compile.compile(DESK_PY, doraise=True)
    check("py_compile desk.py", True)
except py_compile.PyCompileError as e:
    check(f"py_compile desk.py ({e})", False)

if failures:
    print(f"{len(failures)} FAIL")
    sys.exit(1)
print("all good")
