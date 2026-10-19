#!/usr/bin/env python3
"""Measure the desk's UI as it is drawn now, on the test VM or the real laptop (development).

    tools/uiaudit.py vm NAME        audit the VM's desk  (uses tools/vmuser.py)
    tools/uiaudit.py laptop NAME    audit the laptop's desk (uses tools/devlink.py)

Runs src/rootfs/usr/share/llmos/desk/uiaudit.js inside the desk's own page (WebKit, real size and scale) through
`llmos ui-audit`, takes a screenshot beside it, saves both under run/uiaudit/, and prints a summary: text below the
WCAG 2.2 contrast minimum, text cut off, controls smaller than 24 px (fail) / 32 px (tight), controls off the screen,
text over text, and the type / colour / spacing inventory. Numbers, not impressions: compare runs before and after.
"""
import json
import os
import subprocess
import sys

try:
    import PIL  # noqa: F401
except ImportError:                     # the project's own environment has Pillow (run/venv-ui)
    _py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "run", "venv-ui", "bin", "python")
    if os.path.exists(_py) and sys.executable != os.path.abspath(_py):
        os.execv(_py, [_py] + sys.argv)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "run", "uiaudit")


def _env(where):
    return dict(os.environ, DEVLINK_TARGET="vm") if where == "vm" else dict(os.environ)


def run(where, cmd, timeout=200):
    """A shell command on the VM or the laptop, through remote testing (tools/devlink.py; the VM's own queue)."""
    p = subprocess.run([sys.executable, os.path.join(HERE, "devlink.py"), "sh", cmd], capture_output=True, text=True,
                       timeout=timeout, env=_env(where))
    return p.stdout


def shot(where, name):
    p = subprocess.run([sys.executable, os.path.join(HERE, "devlink.py"), "shot", f"audit-{where}-{name}"], capture_output=True,
                       text=True, timeout=200, env=_env(where))
    return p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""


def _lum(c):
    f = lambda v: (v / 255) / 12.92 if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def glass_contrast(rep, png):
    """Text over the wallpaper or a see-through panel: contrast measured on the screenshot, against the worst tenth
    of what is behind it (the pixels that are not the text's own colour)."""
    from PIL import Image
    img = Image.open(png).convert("RGB")
    sc = img.width / float(rep["viewport"][0])
    fails = []
    for g in rep.get("glass", []):
        x, y, w, h = g["box"]
        box = (max(0, int(x * sc)), max(0, int(y * sc)), min(img.width, int((x + w) * sc)), min(img.height, int((y + h) * sc)))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        px = list(img.crop(box).get_flattened_data()) if hasattr(img, 'get_flattened_data') else list(img.crop(box).getdata())
        fg = g["fg"]
        # background = what is left once the 30% of pixels most like the text colour (the letters and their edges)
        # are set aside; white text on white snow then still counts as white on white
        px = sorted(px[::max(1, len(px) // 2000)], key=lambda p: sum((a - b) ** 2 for a, b in zip(p, fg)))
        bg = px[int(len(px) * 0.3):] or px
        lt = _lum(fg)
        cr = sorted((max(lt, _lum(p)) + 0.05) / (min(lt, _lum(p)) + 0.05) for p in bg[::max(1, len(bg) // 400)])
        worst, mid = cr[len(cr) // 4], cr[len(cr) // 2]          # the worst quarter of what is behind it
        g["measured"] = [round(worst, 2), round(mid, 2)]
        if worst < g["need"]:
            fails.append(g)
    return fails


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("vm", "laptop"):
        print(__doc__)
        sys.exit(2)
    where, name = sys.argv[1], sys.argv[2]
    os.makedirs(OUT, exist_ok=True)
    raw = run(where, "llmos ui-audit")
    start = raw.find("{")
    try:
        outer = json.loads(raw[start:raw.rfind("}") + 1])
        rep = json.loads(outer["result"]) if isinstance(outer.get("result"), str) else outer
    except (ValueError, KeyError, TypeError):
        print("no report:", raw[-800:])
        sys.exit(1)
    path = os.path.join(OUT, f"{where}-{name}.json")
    with open(path, "w") as f:
        json.dump(rep, f, indent=1)
    png = shot(where, name)
    gf = []
    try:
        gf = glass_contrast(rep, png)
    except Exception as e:
        print("  (screenshot contrast not measured:", e, ")")
    rep["glassFails"] = gf
    with open(path, "w") as f:
        json.dump(rep, f, indent=1)
    c = rep.get("counts", {})
    c["glassFails"] = len(gf)
    c["glassTexts"] = len(rep.get("glass", []))
    print(f"{where} {name}: viewport {rep.get('viewport')}  report {os.path.relpath(path)}  screenshot {png}")
    print(f"  texts {c.get('texts')}  contrast fails {c.get('contrastFails')}  clipped {c.get('clipped')}  ellipsis {c.get('ellipsis')}  "
          f"over-wallpaper {c.get('glassFails')}/{c.get('glassTexts')} fail  targets <32px {c.get('smallTargets')} (<24px {c.get('smallFails')})  offscreen {c.get('offscreen')}  overlaps {c.get('overlaps')}")
    inv = rep.get("inventory", {})
    print(f"  font sizes {c.get('fontSizes')}: {', '.join(f'{s}px×{n}' for s, n in inv.get('fontSizes', []))}")
    print(f"  families {inv.get('families')}  weights {inv.get('weights')}  text colours {inv.get('textColors')}")
    print(f"  radii {inv.get('radii')}  spacing values {inv.get('spacingDistinct')} (on 4px grid {inv.get('spacingOn4pxGrid')})")
    for k, title in (("glassFails", "LOW CONTRAST ON THE SCREEN (worst quarter, median)"), ("contrast", "LOW CONTRAST"), ("clipped", "CUT OFF"), ("small", "SMALL TARGETS"), ("offscreen", "OFF SCREEN"), ("overlap", "TEXT OVER TEXT")):
        rows = rep.get(k) or []
        if rows:
            print(f"  {title}:")
            for r in rows[:14]:
                print("    " + json.dumps({k: v for k, v in r.items() if k not in ("fg",)}, ensure_ascii=False)[:220])


if __name__ == "__main__":
    main()
