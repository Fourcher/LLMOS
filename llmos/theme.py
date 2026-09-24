"""The look of the whole system lives in one small JSON document. The model
edits it with set_theme(patch); the client renders from it."""
import copy
import json
import os
import re

from . import config

DEFAULT = {
    "palette": {
        "bg": "#111111", "fg": "#e4e4e4", "accent": "#7aa2f7",
        "muted": "#8a8a8a", "error": "#f7768e", "ok": "#9ece6a",
    },
    "corners": "rounded",   # rounded | square | none
    "font": "JetBrains Mono",
    "font_size": 13,
    "padding": 16,
    "density": "normal",    # compact | normal | roomy
    "lang": {
        "default": "en",
        "sections": {},     # settings, system, answers, errors, prompts -> lang code
    },
}

SECTIONS = ("settings", "system", "answers", "errors", "prompts")
CORNERS = ("rounded", "square", "none")
DENSITY = ("compact", "normal", "roomy")
FONTS = ("JetBrains Mono", "DejaVu Sans Mono", "Noto Sans Mono", "Noto Sans Mono CJK SC")

NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#e05555", "green": "#5fbf6f",
    "blue": "#5b8def", "yellow": "#e5c07b", "orange": "#f0883e", "purple": "#a36ee8",
    "violet": "#9b72e8", "magenta": "#d65fd6", "pink": "#f28fbf", "cyan": "#56c2d6",
    "teal": "#3fb6a8", "gray": "#8a8a8a", "grey": "#8a8a8a", "brown": "#a0714f",
    "gold": "#d4a72c", "navy": "#1f2d5c", "lime": "#9be15d", "indigo": "#6a5acd",
    "lavender": "#b8a9f0", "beige": "#e8dcc2", "cream": "#f5efe0",
}
HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def color(value):
    """Accept #rrggbb, rrggbb, #rgb or a colour name."""
    if not isinstance(value, str):
        raise ValueError("colour must be a string")
    v = value.strip().lower()
    if v in NAMED:
        return NAMED[v]
    if re.fullmatch(r"#?[0-9a-f]{3}", v):
        v = v.lstrip("#")
        return "#" + "".join(c * 2 for c in v)
    if HEX.match(v):
        return "#" + v.lstrip("#")
    raise ValueError("unknown colour %r" % value)


def rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(a, b, t):
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def luminance(hexcolor):
    r, g, b = rgb(hexcolor)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def path():
    return config.dpath("theme.json")


def load():
    t = copy.deepcopy(DEFAULT)
    try:
        with open(path()) as f:
            _merge(t, json.load(f))
    except (OSError, ValueError):
        pass
    return t


def save(t):
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(t, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path())


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


ALIASES = {
    "background": ("palette", "bg"), "bg": ("palette", "bg"),
    "foreground": ("palette", "fg"), "fg": ("palette", "fg"), "text": ("palette", "fg"),
    "text_color": ("palette", "fg"), "accent": ("palette", "accent"),
    "accent_color": ("palette", "accent"), "color": ("palette", "accent"),
    "muted": ("palette", "muted"), "error": ("palette", "error"), "ok": ("palette", "ok"),
    "border": ("corners",), "borders": ("corners",), "corner": ("corners",),
    "corner_style": ("corners",), "size": ("font_size",), "fontsize": ("font_size",),
    "font_family": ("font",), "language": ("lang", "default"),
}


def normalize_patch(patch):
    """Small models write patches in many shapes. Map the common ones onto the
    real structure instead of failing."""
    out = {}
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")
    for k, v in patch.items():
        key = str(k).strip().lower().replace(" ", "_").replace("-", "_")
        if key in ("palette", "lang") and isinstance(v, dict):
            sub = out.setdefault(key, {})
            _merge(sub, v)
            continue
        if key in ("corners", "font", "font_size", "padding", "density"):
            out[key] = v
            continue
        if key in ALIASES:
            tgt = ALIASES[key]
            d = out
            for part in tgt[:-1]:
                d = d.setdefault(part, {})
            d[tgt[-1]] = v
            continue
        if key in ("theme", "mode", "scheme") and isinstance(v, str):
            out.update(preset(v))
            continue
        raise ValueError("unknown theme key %r" % k)
    return out


def preset(name):
    n = name.lower()
    if n in ("light", "day", "white"):
        return {"palette": {"bg": "#f7f7f5", "fg": "#1d1d1d", "muted": "#6b6b6b", "accent": "#2f6fdd"}}
    if n in ("dark", "night", "black"):
        return {"palette": {"bg": "#111111", "fg": "#e4e4e4", "muted": "#8a8a8a"}}
    if n in ("default", "reset"):
        return copy.deepcopy(DEFAULT)
    return {"palette": {"accent": color(n)}}


def apply_patch(current, patch):
    """Validate and merge. Returns (new_theme, needs_restart)."""
    patch = normalize_patch(patch)
    t = copy.deepcopy(current)
    if patch.get("palette") == {} and "palette" in patch:
        patch.pop("palette")
    # A single colour for "make everything X" tints the whole palette.
    pal = patch.get("palette", {})
    for k in list(pal):
        if k == "all":
            base = color(pal.pop("all"))
            pal.update(tint(base))
            continue
        if k not in DEFAULT["palette"]:
            raise ValueError("unknown palette key %r" % k)
        pal[k] = color(pal[k])
    restart = False
    if "corners" in patch:
        c = str(patch["corners"]).lower()
        c = {"round": "rounded", "sharp": "square", "squared": "square", "no": "none",
             "off": "none", "false": "none", "true": "rounded", "flat": "none"}.get(c, c)
        if c not in CORNERS:
            raise ValueError("corners must be rounded, square or none")
        patch["corners"] = c
    if "density" in patch and patch["density"] not in DENSITY:
        raise ValueError("density must be compact, normal or roomy")
    if "font_size" in patch:
        fs = int(patch["font_size"])
        if not 7 <= fs <= 40:
            raise ValueError("font_size must be between 7 and 40")
        patch["font_size"] = fs
        restart = restart or fs != t["font_size"]
    if "padding" in patch:
        p = int(patch["padding"])
        if not 0 <= p <= 200:
            raise ValueError("padding must be between 0 and 200")
        patch["padding"] = p
        restart = restart or p != t["padding"]
    if "font" in patch:
        f = str(patch["font"])
        restart = restart or f != t["font"]
    if "lang" in patch:
        lang = patch["lang"]
        secs = lang.get("sections", {})
        for s in list(lang):
            if s in SECTIONS:
                secs[s] = lang.pop(s)
        for s in secs:
            if s not in SECTIONS:
                raise ValueError("unknown section %r (use %s)" % (s, ", ".join(SECTIONS)))
        if secs:
            lang["sections"] = secs
    if patch.get("palette") and "bg" in patch["palette"] and "fg" not in patch["palette"]:
        # Keep text readable when only the background changes.
        bg = patch["palette"]["bg"]
        fg = t["palette"]["fg"]
        if abs(luminance(bg) - luminance(fg)) < 90:
            patch["palette"]["fg"] = "#111111" if luminance(bg) > 128 else "#eeeeee"
            patch["palette"]["muted"] = _mix(patch["palette"]["fg"], bg, 0.45)
    _merge(t, patch)
    return t, restart


def tint(base):
    """A full palette in one hue, readable either way."""
    return {
        "accent": base,
        "bg": _mix(base, "#000000", 0.86),
        "fg": _mix(base, "#ffffff", 0.82),
        "muted": _mix(base, "#9a9a9a", 0.55),
    }


def lang_for(t, section):
    return t["lang"].get("sections", {}).get(section) or t["lang"].get("default", "en")


def foot_ini(t):
    p = t["palette"]
    fonts = "%s:size=%d, Noto Sans Mono CJK SC:size=%d, Noto Color Emoji:size=%d" % (
        t["font"], t["font_size"], t["font_size"], t["font_size"])
    pad = int(t["padding"])
    return "\n".join([
        "[main]",
        "font=%s" % fonts,
        "pad=%dx%d center" % (pad, pad),
        "dpi-aware=no",
        "[scrollback]",
        "lines=4000",
        "[cursor]",
        "style=beam",
        "blink=no",
        "[mouse]",
        "hide-when-typing=yes",
        "[colors]",
        "foreground=%s" % p["fg"].lstrip("#"),
        "background=%s" % p["bg"].lstrip("#"),
        "regular1=%s" % p["error"].lstrip("#"),
        "regular2=%s" % p["ok"].lstrip("#"),
        "regular4=%s" % p["accent"].lstrip("#"),
        "",
    ])


def osc(t):
    """Escape sequences that recolour a running terminal without restart."""
    p = t["palette"]
    return "\033]10;%s\033\\\033]11;%s\033\\\033]12;%s\033\\" % (p["fg"], p["bg"], p["accent"])


def write_foot_ini(t):
    os.makedirs(config.RUN, exist_ok=True)
    tmp = config.rpath("foot.ini.tmp")
    with open(tmp, "w") as f:
        f.write(foot_ini(t))
    os.replace(tmp, config.rpath("foot.ini"))


def summary(t):
    p = t["palette"]
    secs = t["lang"].get("sections", {})
    langs = t["lang"].get("default", "en") + ("".join(" %s=%s" % kv for kv in sorted(secs.items())))
    return "bg %s fg %s accent %s, corners %s, font %s %d, padding %d, density %s, lang %s" % (
        p["bg"], p["fg"], p["accent"], t["corners"], t["font"], t["font_size"], t["padding"],
        t["density"], langs)
