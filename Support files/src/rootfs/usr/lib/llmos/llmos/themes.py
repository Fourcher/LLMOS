"""Whole looks from a few words: "dark mode", "ocean theme", "make everything purple", "retro terminal", "high contrast".

A theme is a coherent set -- background, text, accent, font and the kind of background behind the desk -- so a
request never leaves half the screen in the old look (orange text on a dark background, a bright wallpaper in dark
mode). Colours are checked for contrast before they are kept.
"""
import colorsys
import re

from . import ui

# (names, background, text, accent, font)
PALETTES = [
    (("patriotic", "patriot", "americana", "stars and stripes", "red white and blue", "red, white and blue", "red white & blue", "flag", "usa", "america"), "#0b1f4b", "#ffffff", "#c8102e", ""),
    (("retro", "terminal", "hacker", "matrix", "green screen", "crt", "8-bit", "8 bit"), "#031a07", "#3cff6e", "#3cff6e", "mono"),
    (("neon", "cyberpunk", "synthwave", "vaporwave", "futuristic", "sci-fi", "scifi"), "#0d0221", "#f6e7ff", "#ff2bd6", ""),
    (("pastel", "cute", "soft", "kawaii"), "#fff4fa", "#4a3b4f", "#e0729f", ""),
    (("ocean", "sea", "aqua", "underwater", "beach"), "#061a2b", "#dff3ff", "#2ec4f1", ""),
    (("sunset", "warm", "autumn", "fall", "cozy", "cosy"), "#26110e", "#ffe8d6", "#ff7a3d", ""),
    (("forest", "nature", "earthy", "woods", "jungle"), "#0f1f14", "#e3f2e1", "#5cbf73", ""),
    (("minimal", "clean", "paper", "white"), "#ffffff", "#111111", "#2b2b2b", ""),
    (("gold", "luxury", "elegant", "classy", "royal"), "#121008", "#f5ecd0", "#d4af37", "serif"),
    (("high contrast", "contrast", "accessible", "easy to see", "low vision"), "#000000", "#ffffff", "#ffd400", ""),
    (("space", "galaxy", "cosmic", "stars", "night sky"), "#05060f", "#e6e8ff", "#8f7cff", ""),
    (("coffee", "mocha", "latte", "brown"), "#1c1410", "#f1e4d8", "#c48a5a", "serif"),
    (("light", "bright", "day", "daytime"), "#f6f6f8", "#16171d", "#5b5bd6", ""),
    (("dark", "night", "black", "midnight", "dim"), "#0b0d14", "#e8e9ef", "#7c5cff", ""),
]
DEFAULT = ("#0b0d14", "#e8e9ef", "#7c5cff")
FONTS = {
    "sans": 'Inter, "Noto Sans", system-ui, sans-serif',
    "serif": '"Noto Serif", Georgia, serif',
    "mono": '"JetBrains Mono", "Noto Sans Mono", monospace',
    "pixel": 'Terminus, "JetBrains Mono", monospace',
}
FONT_WORDS = {
    "mono": ("mono", "monospace", "monospaced", "code", "coding", "programmer", "typewriter", "jetbrains", "courier", "console"),
    "serif": ("serif", "times", "georgia", "book", "classic", "elegant", "fancy", "old fashioned", "old-fashioned", "newspaper", "noto serif"),
    "pixel": ("pixel", "bitmap", "terminus", "retro font", "8-bit font"),
    "sans": ("sans", "sans-serif", "inter", "default font", "normal font", "modern", "clean font", "helvetica", "arial"),
}
BACKGROUNDS = ("living", "still", "photo", "plain")


def hx(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x)))) for x in c)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(h):
    return ui._lum(rgb(h))


def from_color(c, dark=True):
    """'make everything purple': the colour leads, the background takes a hint of it, the text stays readable."""
    r, g, b = [x / 255 for x in rgb(c)]
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if dark:
        bg = colorsys.hls_to_rgb(hue, 0.075, min(0.55, sat * 0.6 + 0.1))
        fg = colorsys.hls_to_rgb(hue, 0.93, min(0.25, sat * 0.3))
        acc = colorsys.hls_to_rgb(hue, max(0.55, min(0.68, light)), max(0.6, sat))
    else:
        bg = colorsys.hls_to_rgb(hue, 0.965, min(0.6, sat * 0.6 + 0.1))
        fg = colorsys.hls_to_rgb(hue, 0.12, min(0.3, sat * 0.3))
        acc = colorsys.hls_to_rgb(hue, max(0.36, min(0.48, light)), max(0.6, sat))
    if sat < 0.08:                               # grey / white / black named: keep it neutral
        acc = colorsys.hls_to_rgb(hue, 0.62 if dark else 0.35, 0)
    t = lambda x: hx([v * 255 for v in x])
    return t(bg), t(fg), t(acc)


def font_for(words):
    w = " " + str(words or "").lower() + " "
    if re.search(r"sans[- ]?serif", w):
        return "sans"
    for name, keys in FONT_WORDS.items():
        if any(k in w for k in keys):
            return name
    return ""


def resolve(words, current=None):
    """The look the words ask for: {"background", "color", "accent", "font"?, "mode"} or None if no theme is named.
    current: (background, text, accent) now, so 'dark mode' keeps the accent the owner chose."""
    w = " " + re.sub(r"[_]+", " ", str(words or "").lower()) + " "
    cur_bg, cur_fg, cur_acc = current or DEFAULT
    for names, b, f, a, fo in PALETTES:
        if any(f" {n} " in w or f" {n}-" in w or f"{n} mode" in w or f"{n} theme" in w for n in names):
            if names[0] in ("dark", "light"):
                # dark / light mode: the classic neutral look, whatever colour theme came before
                return {"background": b, "color": f, "accent": a, "mode": names[0]}
            out = {"background": b, "color": f, "accent": a, "mode": "light" if lum(b) > 0.5 else "dark"}
            if fo:
                out["font"] = fo
            return out
    if re.search(r"\b(default|original|normal|standard|stock|reset)\b", w) and (
            re.search(r"\b(theme|look|colou?rs?|everything|appearance)\b", w) or len(w.split()) <= 2):
        return {"background": "", "color": "", "accent": "", "font": "sans", "mode": "dark"}
    for word in re.findall(r"#[0-9a-f]{6}|[a-z]+(?: [a-z]+)?", w):
        for cand in (word, word.split(" ")[-1]):
            c = ui.parse_color(cand)
            if c:
                light = bool(re.search(r"\b(light|bright|pale|white background)\b", w))
                bg, fg, acc = from_color(hx(c), dark=not light)
                return {"background": bg, "color": fg, "accent": acc, "mode": "light" if light else "dark"}
    return None


FAMILY = {"sans": "Inter", "serif": "Noto Serif", "mono": "JetBrains Mono", "pixel": "Terminus"}


def apply_programs(home, mode, font="sans", bg="", fg="", acc="", scale=100):
    """The other programs follow the look too: GTK programs (Files, the editor, Firefox's own dark mode) through
    their settings files, the terminal through its colours. Programs read these when they start."""
    import os
    fam = FAMILY.get(font or "sans", "Inter")
    dark = mode != "light"
    ini = ("[Settings]\n"
           f"gtk-application-prefer-dark-theme={'1' if dark else '0'}\n"
           f"gtk-theme-name={'Adwaita-dark' if dark else 'Adwaita'}\n"
           "gtk-icon-theme-name=Adwaita\n"
           f"gtk-font-name={fam} {round(11 * max(80, min(int(scale or 100), 250)) / 100)}\n")
    out = []
    for v in ("gtk-3.0", "gtk-4.0"):
        d = os.path.join(home, ".config", v)
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "settings.ini"), "w") as f:
                f.write(ini if v == "gtk-3.0" else ini.replace("gtk-theme-name=Adwaita-dark\n", "").replace("gtk-theme-name=Adwaita\n", ""))
            out.append(v)
        except OSError:
            pass
    b = (bg or ("#0b0d14" if dark else "#f6f6f8")).lstrip("#")
    t = (fg or ("#e8e9ef" if dark else "#16171d")).lstrip("#")
    a = (acc or "#7c5cff").lstrip("#")
    try:
        d = os.path.join(home, ".config", "foot")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "foot.ini"), "w") as f:
            f.write(f"font={'JetBrains Mono' if font in ('sans', 'serif', '') else fam}:size={round(11 * max(80, min(int(scale or 100), 250)) / 100)}\npad=10x10\n\n[colors-dark]\n"
                    f"background={b}\nforeground={t}\nselection-background={a}\nselection-foreground={b}\n")
        out.append("foot")
    except OSError:
        pass
    return out
