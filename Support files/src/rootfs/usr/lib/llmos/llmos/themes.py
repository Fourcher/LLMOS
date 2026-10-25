"""Whole looks from a few words: "dark mode", "ocean theme", "make everything purple", "retro terminal", "high contrast".

A theme is a coherent set -- background, text, accent, font and the kind of background behind the desk -- so a
request never leaves half the screen in the old look (orange text on a dark background, a bright wallpaper in dark
mode). Colours are checked for contrast before they are kept.

The same tokens are written out for GTK, labwc and Firefox, from Desk.theme_payload, so a restyle does not stop
at the desk page. Nothing is fetched.
"""
import colorsys
import os
import re

from . import config, ui

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
    (("dark", "night", "black", "midnight", "dim"), "#0b0d14", "#e8e9ef", "#7a52ff", ""),
]
DEFAULT = ("#0b0d14", "#e8e9ef", "#7a52ff")
# System faces only. Named fonts are used when the machine has them; nothing is fetched.
FONTS = {
    "sans": 'system-ui, "Noto Sans", sans-serif',
    "serif": 'ui-serif, Georgia, "Noto Serif", serif',
    "mono": 'ui-monospace, "Noto Sans Mono", monospace',
    "pixel": 'Terminus, ui-monospace, monospace',
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


# Pango names for GTK. system-ui matches the desk page. Inter and JetBrains Mono are not bundled.
FAMILY = {"sans": "system-ui", "serif": "serif", "mono": "monospace", "pixel": "Terminus"}


def apply_programs(home, mode, font="sans", bg="", fg="", acc="", scale=100):
    """The other programs follow the look too: GTK programs (Files, the editor, Firefox's own dark mode) through
    their settings files, the terminal through its colours. Programs read these when they start."""
    import os
    fam = FAMILY.get(font or "sans", "system-ui")
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
    a = (acc or "#7a52ff").lstrip("#")
    try:
        d = os.path.join(home, ".config", "foot")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "foot.ini"), "w") as f:
            f.write(f"font={'monospace' if font in ('sans', 'serif', '') else fam}:size={round(11 * max(80, min(int(scale or 100), 250)) / 100)}\npad=10x10\n\n[colors-dark]\n"
                    f"background={b}\nforeground={t}\nselection-background={a}\nselection-foreground={b}\n")
        out.append("foot")
    except OSError:
        pass
    out.extend(publish(home))
    return out


# The page's own defaults (desk.css :root) for a token theme_payload leaves unset, so GTK and Firefox still
# match the desk when the owner has not picked a colour.
_PAGE_DEFAULTS = {"--bg": "#14161c", "--fg": "#eceae4", "--accent": "#7a52ff", "--on-accent": "#ffffff", "--radius": "12px"}


def desk_tokens():
    """The CSS variables the desk is showing, from Desk.theme_payload, so a generated file cannot drift from the page."""
    from . import desk
    css = dict((desk.Desk.theme_payload(None).get("css") or {}))
    for key, val in _PAGE_DEFAULTS.items():
        css.setdefault(key, val)
    return css


def _parts(css):
    bg = str(css.get("--bg") or _PAGE_DEFAULTS["--bg"])
    fg = str(css.get("--fg") or _PAGE_DEFAULTS["--fg"])
    acc = str(css.get("--accent") or _PAGE_DEFAULTS["--accent"])
    on = str(css.get("--on-accent") or _PAGE_DEFAULTS["--on-accent"])
    radius = str(css.get("--radius") or _PAGE_DEFAULTS["--radius"]).strip()
    br = "0" if radius in ("0", "0px") else radius
    m = re.match(r"(\d+)", br)
    px = int(m.group(1)) if m else 14
    return bg, fg, acc, on, radius, br, px


def window_radius():
    """The desk's corner radius in pixels, for labwc's <cornerRadius>. None when the tokens cannot be read."""
    if not hasattr(config.settings, "all"):
        return None
    try:
        return _parts(desk_tokens())[6]
    except Exception:
        return None


def appearance_paths(home):
    """Where a restyle is written. Firefox also receives a copy in every profile that already exists."""
    return {
        "gtk": os.path.join(home, ".config", "gtk-3.0", "gtk.css"),
        "gtk4": os.path.join(home, ".config", "gtk-4.0", "gtk.css"),
        "chrome": os.path.join(home, ".mozilla", "firefox", "llmos", "chrome", "userChrome.css"),
        "content": os.path.join(home, ".mozilla", "firefox", "llmos", "chrome", "userContent.css"),
        "labwc": os.path.join(home, ".local", "share", "themes", "llmos", "labwc", "themerc"),
    }


def _note(bg, fg, acc, radius):
    # The exact theme_payload strings, so a file can be checked against the desk without reformatting.
    return f"/* LLM OS desk tokens --bg: {bg}; --fg: {fg}; --accent: {acc}; --radius: {radius}. Nothing is fetched. */\n"


def _gtk_css(bg, fg, acc, on, radius, br):
    # @define-color is what Adwaita and GTK 4 actually paint with. The border-radius line is the desk's radius
    # (0, not 0px, when the corners are square) so a check can see the same token.
    return (
        _note(bg, fg, acc, radius)
        + f"@define-color theme_bg_color {bg};\n"
        f"@define-color theme_fg_color {fg};\n"
        f"@define-color theme_selected_bg_color {acc};\n"
        f"@define-color theme_selected_fg_color {on};\n"
        f"@define-color theme_base_color {bg};\n"
        f"@define-color theme_text_color {fg};\n"
        f"@define-color accent_bg_color {acc};\n"
        f"@define-color accent_fg_color {on};\n"
        f"@define-color accent_color {acc};\n"
        f"@define-color window_bg_color {bg};\n"
        f"@define-color window_fg_color {fg};\n"
        f"@define-color headerbar_bg_color {bg};\n"
        f"@define-color headerbar_fg_color {fg};\n"
        f"@define-color popover_bg_color {bg};\n"
        f"@define-color popover_fg_color {fg};\n"
        "window, .background, headerbar, button, entry, text, textview, treeview, list, row, popover, menu,\n"
        "notebook, frame, .view, scrollbar, tab, menuitem {\n"
        f"  background-color: {bg};\n"
        f"  color: {fg};\n"
        f"  border-radius: {br};\n"
        "}\n"
        "button.suggested-action, button.destructive-action, selection, :selected {\n"
        f"  background-color: {acc};\n"
        f"  color: {on};\n"
        "}\n"
    )


def _chrome_css(bg, fg, acc, on, radius, br):
    return (
        _note(bg, fg, acc, radius)
        + ":root {\n"
        f"  --bg: {bg} !important;\n"
        f"  --fg: {fg} !important;\n"
        f"  --accent: {acc} !important;\n"
        f"  --radius: {br} !important;\n"
        f"  background-color: {bg} !important;\n"
        f"  color: {fg} !important;\n"
        "}\n"
        "#navigator-toolbox, #nav-bar, #TabsToolbar, #PersonalToolbar, #sidebar-box, #urlbar,\n"
        "#searchbar, .tabbrowser-tab, panel, menupopup, #appMenu-popup, window, dialog {\n"
        f"  background-color: {bg} !important;\n"
        f"  color: {fg} !important;\n"
        f"  border-radius: {br} !important;\n"
        "}\n"
        ".tabbrowser-tab[selected], #urlbar[focused], button.primary {\n"
        f"  background-color: {acc} !important;\n"
        f"  color: {on} !important;\n"
        "}\n"
    )


def _content_css(bg, fg, acc, radius, br):
    # Web pages stay as they are. Only the browser's own empty pages take the desk colours.
    return (
        _note(bg, fg, acc, radius)
        + "/* new-tab and blank pages follow the desk */\n"
        '@-moz-document url("about:home"), url("about:newtab"), url("about:blank"), url("about:privatebrowsing") {\n'
        "  body, html {\n"
        f"    background-color: {bg} !important;\n"
        f"    color: {fg} !important;\n"
        "  }\n"
        "  input, textarea, button, select {\n"
        f"    border-radius: {br} !important;\n"
        f"    background-color: {bg} !important;\n"
        f"    color: {fg} !important;\n"
        "  }\n"
        "  a { color: " + acc + " !important; }\n"
        "}\n"
    )


def _themerc(bg, fg, acc, on, px):
    return (
        "# LLM OS window frames, written from the desk tokens. Nothing is fetched.\n"
        "border.width: 1\n"
        f"window.active.border.color: {acc}\n"
        f"window.inactive.border.color: {bg}\n"
        "window.active.title.bg: Solid\n"
        f"window.active.title.bg.color: {bg}\n"
        "window.inactive.title.bg: Solid\n"
        f"window.inactive.title.bg.color: {bg}\n"
        f"window.active.label.text.color: {fg}\n"
        f"window.inactive.label.text.color: {fg}\n"
        f"window.active.button.unpressed.image.color: {fg}\n"
        f"window.inactive.button.unpressed.image.color: {fg}\n"
        f"window.active.button.close.unpressed.image.color: {acc}\n"
        f"window.button.hover.bg.corner-radius: {px}\n"
        "window.titlebar.padding.width: 6\n"
        "window.titlebar.padding.height: 4\n"
        f"osd.bg.color: {bg}\n"
        f"osd.border.color: {acc}\n"
        f"osd.label.text.color: {fg}\n"
        f"menu.items.bg.color: {bg}\n"
        f"menu.items.text.color: {fg}\n"
        f"menu.items.active.bg.color: {acc}\n"
        f"menu.items.active.text.color: {on}\n"
        f"menu.border.color: {acc}\n"
    )


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


_FIREFOX_PREFS = (
    "toolkit.legacyUserProfileCustomizations.stylesheets",
    "browser.display.background_color",
    "browser.display.foreground_color",
    "browser.anchor_color",
)


def _write_user_js(profile, bg, fg, acc):
    path = os.path.join(profile, "user.js")
    try:
        old = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        old = []
    kept = [ln for ln in old if not any(k in ln for k in _FIREFOX_PREFS)]
    kept += [
        'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);',
        f'user_pref("browser.display.background_color", "{bg}");',
        f'user_pref("browser.display.foreground_color", "{fg}");',
        f'user_pref("browser.anchor_color", "{acc}");',
    ]
    _write(path, "\n".join(kept) + "\n")


def _firefox_profiles(home):
    """Every Firefox profile under this home, plus the llmos profile a first launch will use."""
    base = os.path.join(home, ".mozilla", "firefox")
    found = []
    ini = os.path.join(base, "profiles.ini")
    path, rel = None, True

    def remember():
        if path:
            found.append(path if not rel else os.path.join(base, path))

    if os.path.isfile(ini):
        try:
            lines = open(ini, encoding="utf-8").read().splitlines()
        except OSError:
            lines = []
        for line in lines + ["[end]"]:
            s = line.strip()
            if s.startswith("["):
                remember()
                path, rel = None, True
            elif s.startswith("Path="):
                path = s.split("=", 1)[1].strip()
            elif s.startswith("IsRelative="):
                rel = s.split("=", 1)[1].strip() != "0"
    owned = os.path.join(base, "llmos")
    if not any(os.path.abspath(p) == os.path.abspath(owned) for p in found):
        found.append(owned)
    if not os.path.isfile(ini):
        try:
            _write(ini, "[General]\nStartWithLastProfile=1\n\n[Profile0]\nName=llmos\nIsRelative=1\nPath=llmos\nDefault=1\n")
        except OSError:
            pass
    return found


def _patch_corner_radius(px, home):
    paths = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        paths.append(os.path.join(xdg, "labwc", "rc.xml"))
    paths.append(os.path.join(home, ".config", "labwc", "rc.xml"))
    seen = set()
    for path in paths:
        ap = os.path.abspath(path)
        if ap in seen or not os.path.isfile(path):
            continue
        seen.add(ap)
        try:
            with open(path, encoding="utf-8") as f:
                xml = f.read()
            new = re.sub(r"(<cornerRadius>)\d+(</cornerRadius>)", rf"\g<1>{px}\2", xml, count=1)
            if new != xml:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new)
        except OSError:
            pass


def publish(home=None):
    """Write the desk's tokens into GTK, labwc and Firefox. Returns the paths written. A settings stand-in
    with no all() (a unit test) is left alone. Nothing is downloaded."""
    if not hasattr(config.settings, "all"):
        return []
    home = home or config.home()
    try:
        bg, fg, acc, on, _radius, br, px = _parts(desk_tokens())
    except Exception as e:
        sys_write(f"themes: desk tokens unavailable ({e})")
        return []
    gtk = _gtk_css(bg, fg, acc, on, _radius, br)
    chrome = _chrome_css(bg, fg, acc, on, _radius, br)
    content = _content_css(bg, fg, acc, _radius, br)
    theme = _themerc(bg, fg, acc, on, px)
    paths = appearance_paths(home)
    written = []
    try:
        for key in ("gtk", "gtk4"):
            written.append(_write(paths[key], gtk))
        for profile in _firefox_profiles(home):
            cdir = os.path.join(profile, "chrome")
            written.append(_write(os.path.join(cdir, "userChrome.css"), chrome))
            written.append(_write(os.path.join(cdir, "userContent.css"), content))
            _write_user_js(profile, bg, fg, acc)
        written.append(_write(paths["labwc"], theme))
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            alt = os.path.join(xdg_data, "themes", "llmos", "labwc", "themerc")
            if os.path.abspath(alt) != os.path.abspath(paths["labwc"]):
                written.append(_write(alt, theme))
        _patch_corner_radius(px, home)
    except OSError as e:
        sys_write(f"themes: look not written ({e})")
    return written


def sys_write(msg):
    import sys
    sys.stderr.write(msg.rstrip() + "\n")
