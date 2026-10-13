#!/usr/bin/env python3
"""Host-side test of the text colour on accent and danger fills (desk.py _best_text, desk.css --on-accent / --on-danger):
for every palette accent in themes.py, the layout-preset accents in intent.py and the default accent, the text colour
chosen (#111111 or #ffffff) has the higher WCAG contrast ratio; the accent selectors in desk.css no longer hard-code
white; the desk theme reset in desk.js covers the new variables; desk.js and desk.py still compile.
Run: python3 tools/test-on-accent.py"""
import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "src/rootfs")
DESK_PY = os.path.join(ROOT, "usr/lib/llmos/llmos/desk.py")
THEMES_PY = os.path.join(ROOT, "usr/lib/llmos/llmos/themes.py")
INTENT_PY = os.path.join(ROOT, "usr/lib/llmos/llmos/intent.py")
DESK_CSS = os.path.join(ROOT, "usr/share/llmos/desk/desk.css")
DESK_JS = os.path.join(ROOT, "usr/share/llmos/desk/desk.js")
DANGER = "#ef5a6f"  # desk.css :root --danger; desk.py does not set it
fails = []


def check(cond, what):
    what = what[3:] if what.startswith("ok ") else what
    print(("ok " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def literal_assign(path, name):
    for node in ast.parse(read(path)).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


# the helper, lifted out of desk.py without importing the whole desk module
def load_best_text():
    for node in ast.parse(read(DESK_PY)).body:
        if isinstance(node, ast.FunctionDef) and node.name == "_best_text":
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(mod, DESK_PY, "exec"), ns)
            return ns["_best_text"]
    raise KeyError("_best_text")


def lum(hexcol):
    h = hexcol.lstrip("#")
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(int(h[0:2], 16)) + 0.7152 * ch(int(h[2:4], 16)) + 0.0722 * ch(int(h[4:6], 16))


def ratio(a, b):
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


best_text = load_best_text()

# ---- accents to cover: every palette accent, the layout presets, the default accent, the danger colour
accents = []
for names, bg, fg, acc, font in literal_assign(THEMES_PY, "PALETTES"):
    accents.append(("palette " + names[0], acc))
accents.append(("default", literal_assign(THEMES_PY, "DEFAULT")[2]))
for name, preset in literal_assign(INTENT_PY, "_LAYOUT_PRESETS").items():
    if str(preset.get("accent", "")).startswith("#"):
        accents.append(("layout " + name, preset["accent"]))
accents.append(("danger", DANGER))

print("%-22s %-9s %-8s %-8s %-8s %s" % ("fill", "colour", "white", "#111111", "chosen", "ok"))
below = []
for label, acc in accents:
    chosen = best_text(acc)
    r_white, r_dark = ratio(acc, "#ffffff"), ratio(acc, "#111111")
    r_chosen = ratio(acc, chosen)
    print("%-22s %-9s %-8.2f %-8.2f %-8.2f %s" % (label, acc, r_white, r_dark, r_chosen, chosen))
    check(chosen in ("#111111", "#ffffff"), "ok %s: text is #111111 or #ffffff" % label)
    check(r_chosen >= max(r_white, r_dark) - 1e-9, "ok %s: chosen %s %.2f is the higher ratio" % (label, chosen, r_chosen))
    if r_chosen < 4.5:
        below.append("%s %s %.2f" % (label, acc, r_chosen))
if below:
    print("accents where neither text colour reaches 4.5:1: " + "; ".join(below))
else:
    print("every accent reaches 4.5:1 with the chosen text colour")

check(best_text("#7a52ff") == "#ffffff" and ratio("#7a52ff", "#ffffff") >= 4.5, "ok default accent #7a52ff keeps white at %.2f:1 (needs 4.5)" % ratio("#7a52ff", "#ffffff"))

# ---- the named "dark" palette (themes.py) is strict: its accent reaches 4.5:1 with the chosen text colour
dark_accents = [acc for names, bg, fg, acc, font in literal_assign(THEMES_PY, "PALETTES") if names[0] == "dark"]
check(len(dark_accents) == 1, "ok themes.py has one 'dark' palette")
dark_acc = dark_accents[0] if dark_accents else "#000000"
dark_chosen = best_text(dark_acc)
check(dark_chosen == "#ffffff" and ratio(dark_acc, dark_chosen) >= 4.5,
      "ok dark palette accent %s picks %s at %.2f:1 (needs 4.5)" % (dark_acc, dark_chosen, ratio(dark_acc, dark_chosen)))

# ---- labwc window menu highlight (themerc): active text on active bg reaches 4.5:1 with ui.contrast
def load_ui_contrast():
    ui_py = os.path.join(ROOT, "usr/lib/llmos/llmos/ui.py")
    wanted = {"_lum", "contrast"}
    body = [n for n in ast.parse(read(ui_py)).body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    ns = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), ui_py, "exec"), ns)
    return ns["contrast"]

ui_contrast = load_ui_contrast()
themerc = read(os.path.join(ROOT, "usr/share/themes/llmos/labwc/themerc"))
def rc(key):
    m = re.search(r"^" + re.escape(key) + r":\s*(#[0-9a-fA-F]{6})\b", themerc, re.M)
    return m.group(1) if m else None
mb, mt = rc("menu.items.active.bg.color"), rc("menu.items.active.text.color")
check(mb is not None and mt is not None, "ok themerc has menu.items.active bg and text colours (%s, %s)" % (mb, mt))
if mb and mt:
    cr = ui_contrast(tuple(int(mb[i:i + 2], 16) for i in (1, 3, 5)), tuple(int(mt[i:i + 2], 16) for i in (1, 3, 5)))
    check(cr >= 4.5, "ok themerc window menu highlight %s on %s is %.2f:1 (needs 4.5)" % (mt, mb, cr))

# ---- desk.css: no white left on the accent or danger fills; the variables exist with their white fallback
css = read(DESK_CSS)
root = re.search(r":root\s*\{([^}]*)\}", css).group(1)
check("--on-accent: #fff" in root and "--on-danger: #fff" in root, "ok desk.css :root defaults --on-accent and --on-danger")
rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
accent_rules = [(sel.strip(), body) for sel, body in rules if re.search(r"var\(--(accent|danger)\)", body)]
bad = [sel for sel, body in accent_rules if re.search(r"(?<![-\w])color:\s*#fff\b", body)]
check(not bad, "ok no `color: #fff` left on accent/danger fills (%d rules checked): %s" % (len(accent_rules), bad))
for needle in ("color: var(--on-accent, #fff)", "color: var(--on-danger, #fff)"):
    check(needle in css, "ok desk.css contains %s" % needle)

# ---- desk.js: theme changes reset the new variables
js = read(DESK_JS)
check('"--on-accent", "--on-danger"' in js, "ok desk.js applyTheme resets --on-accent and --on-danger")

# ---- compile checks
r = subprocess.run(["node", "--check", DESK_JS], capture_output=True, text=True)
check(r.returncode == 0, "ok node --check desk.js %s" % (r.stderr.strip()[:200] or ""))
r = subprocess.run([sys.executable, "-m", "py_compile", DESK_PY], capture_output=True, text=True)
check(r.returncode == 0, "ok py_compile desk.py %s" % (r.stderr.strip()[:200] or ""))

if fails:
    print("FAILED: %d" % len(fails))
    sys.exit(1)
print("all good")
