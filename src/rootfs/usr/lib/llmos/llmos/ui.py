"""Terminal rendering: the whole interface is text, generated on the fly from
the user's appearance settings (colors, corners, language)."""
import colorsys
import os
import re
import select
import shutil
import sys
import termios
import textwrap
import time
import tty
import unicodedata

from . import config

# CSS/X11 color names (plus a few common words) -> RGB
NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (192, 192, 192), "red": (220, 38, 38),
    "crimson": (220, 20, 60), "maroon": (128, 0, 0), "orange": (249, 115, 22),
    "amber": (255, 191, 0), "gold": (255, 215, 0), "yellow": (250, 204, 21),
    "lime": (132, 204, 22), "green": (34, 197, 94), "mint": (152, 255, 152),
    "olive": (128, 128, 0), "teal": (20, 184, 166), "cyan": (6, 182, 212),
    "turquoise": (64, 224, 208), "aqua": (0, 255, 255), "sky": (56, 189, 248),
    "blue": (59, 130, 246), "navy": (0, 0, 128), "indigo": (99, 102, 241),
    "violet": (139, 92, 246), "purple": (147, 51, 234), "lavender": (200, 162, 255),
    "magenta": (217, 70, 239), "fuchsia": (217, 70, 239), "pink": (236, 72, 153),
    "rose": (244, 63, 94), "brown": (146, 64, 14), "beige": (245, 245, 220),
    "cream": (255, 253, 208), "ivory": (255, 255, 240), "tan": (210, 180, 140),
    "coral": (255, 127, 80), "salmon": (250, 128, 114), "plum": (221, 160, 221),
    "orchid": (218, 112, 214), "mauve": (224, 176, 255), "lilac": (200, 162, 200),
    "emerald": (16, 185, 129), "forest": (34, 139, 34), "charcoal": (54, 69, 79),
    "slate": (100, 116, 139), "sand": (194, 178, 128), "peach": (255, 218, 185),
    "burgundy": (128, 0, 32), "wine": (114, 47, 55), "ruby": (224, 17, 95),
    "sapphire": (15, 82, 186), "jade": (0, 168, 107), "khaki": (240, 230, 140),
}
_FILLER = {"dark", "light", "deep", "pale", "bright", "soft", "pastel", "neon",
           "a", "an", "the", "color", "colour", "ish"}


def parse_color(spec):
    """'purple', 'dark green', '#a0f', '#aa00ff', 'rgb(1,2,3)' -> (r,g,b) or None."""
    if not spec:
        return None
    s = str(spec).strip().lower()
    m = re.fullmatch(r"#?([0-9a-f]{6})", s)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"#?([0-9a-f]{3})", s)
    if m and s.startswith("#"):
        return tuple(int(c * 2, 16) for c in m.group(1))
    m = re.fullmatch(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", s)
    if m:
        return tuple(min(255, int(x)) for x in m.groups())
    words = re.findall(r"[a-z]+", s)
    base = next((NAMED[w] for w in words if w in NAMED), None)
    if base is None:
        joined = "".join(w for w in words if w not in _FILLER)
        base = NAMED.get(joined)
    if base is None:
        return None
    h, l, sat = colorsys.rgb_to_hls(*(c / 255 for c in base))
    if "dark" in words or "deep" in words:
        l = max(0.12, l * 0.55)
    if "light" in words or "pale" in words or "pastel" in words:
        l = min(0.88, l + (1 - l) * 0.5)
    if "neon" in words or "bright" in words:
        sat = 1.0
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, sat))


def _lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _with_lightness(rgb, l):
    h, _, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))


def harmonize(fg, bg):
    """Keep text readable whatever the user asked for. 'Everything purple'
    becomes light-lavender text on deep purple, not purple on purple."""
    if bg is None:
        return fg, bg
    if fg is None:
        fg = bg
    if contrast(fg, bg) >= 4.5:
        return fg, bg
    dark_bg = _lum(bg) < 0.18
    if dark_bg:
        for l in (0.8, 0.88, 0.95, 1.0):
            cand = _with_lightness(fg, l)
            if contrast(cand, bg) >= 4.5:
                return cand, bg
        bg = _with_lightness(bg, 0.1)
        return _with_lightness(fg, 0.9), bg
    for l in (0.25, 0.15, 0.08, 0.0):
        cand = _with_lightness(fg, l)
        if contrast(cand, bg) >= 4.5:
            return cand, bg
    # a mid-tone background: darken it and use a light tint of the text hue
    bg = _with_lightness(bg, 0.14)
    return _with_lightness(fg, 0.88), bg


def to256(rgb):
    """Nearest xterm-256 color (works on every terminal, incl. macOS Terminal)."""
    r, g, b = rgb

    def cube(v):
        return 0 if v < 48 else 1 if v < 115 else (v - 35) // 40

    cr, cg, cb = cube(r), cube(g), cube(b)
    lv = [0, 95, 135, 175, 215, 255]
    cube_rgb = (lv[cr], lv[cg], lv[cb])
    gray_i = max(0, min(23, round((sum(rgb) / 3 - 8) / 10)))
    gray_v = 8 + gray_i * 10
    d_cube = sum((a - b_) ** 2 for a, b_ in zip(rgb, cube_rgb))
    d_gray = sum((a - gray_v) ** 2 for a in rgb)
    return 232 + gray_i if d_gray < d_cube else 16 + 36 * cr + 6 * cg + cb


CORNERS = {
    "rounded": "╭╮╰╯─│",
    "square": "┌┐└┘─│",
    "double": "╔╗╚╝═║",
    "heavy": "┏┓┗┛━┃",
    "ascii": "++++-|",
}


class Theme:
    def __init__(self, appearance=None):
        a = appearance if appearance is not None else config.settings.get("appearance", {})
        fg, bg = parse_color(a.get("color")), parse_color(a.get("background"))
        fg, bg = harmonize(fg, bg)
        acc = parse_color(a.get("accent")) or (fg if (fg or bg) else None)
        if acc and bg and contrast(acc, bg) < 3:
            acc, _ = harmonize(acc, bg)
        self.fg, self.bg, self.acc = fg, bg, acc
        self.corners = a.get("corners") or "rounded"
        self.prompt_symbol = a.get("prompt") or "›"
        try:
            self.scale = max(70, min(200, int(a.get("scale") or 100)))
        except (TypeError, ValueError):
            self.scale = 100
        self.motion = a.get("motion") if a.get("motion") in ("full", "reduced", "off") else "full"

    def base(self):
        """Escape sequence that (re)establishes the theme's text+background."""
        s = "\033[0m"
        if self.fg:
            s += f"\033[38;5;{to256(self.fg)}m"
        if self.bg:
            s += f"\033[48;5;{to256(self.bg)}m"
        return s

    def accent(self):
        if self.acc:
            return f"\033[38;5;{to256(self.acc)}m\033[1m"
        return "\033[1m"

    def dim(self):
        if self.fg and self.bg:
            mid = tuple((a * 2 + b) // 3 for a, b in zip(self.fg, self.bg))
            return f"\033[38;5;{to256(mid)}m"
        return "\033[2m"

    def err(self):
        return "\033[38;5;203m"


theme = Theme()
_size = [80, 24]


def reload_theme():
    global theme
    theme = Theme()
    paint()


def cols():
    return max(40, _size[0])


def query_size(fd=None):
    """Ask the terminal for its size (works over a serial line, where the
    kernel has no idea how big the window on the other end is)."""
    env = shutil.get_terminal_size((0, 0))
    fd = sys.stdin.fileno() if fd is None else fd
    if not os.isatty(fd):
        return
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        os.write(sys.stdout.fileno(), b"\0337\033[999;999H\033[6n\0338")
        buf = b""
        end = time.time() + 0.4
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                buf += os.read(fd, 64)
                m = re.search(rb"\033\[(\d+);(\d+)R", buf)
                if m:
                    rows, cs = int(m.group(1)), int(m.group(2))
                    if cs >= 20 and rows >= 5:
                        _size[:] = [cs, rows]
                        os.system(f"stty rows {rows} cols {cs} 2>/dev/null")
                    return
    except OSError:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if env.columns >= 20:
        _size[:] = [env.columns, env.lines]


def width(s):
    """Display width (CJK characters take two cells)."""
    s = strip(s)
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 0 if unicodedata.combining(c) else 1 for c in s)


_ANSI = re.compile(r"\033\[[0-9;?]*[A-Za-z]")


def strip(s):
    return _ANSI.sub("", s)


def wrap(text, w):
    out = []
    for para in str(text).split("\n"):
        if width(para) <= w:
            out.append(para)
            continue
        if any(unicodedata.east_asian_width(c) in "WF" for c in para):
            line, lw = "", 0
            for ch in para:
                cw = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
                if lw + cw > w:
                    out.append(line)
                    line, lw = "", 0
                line += ch
                lw += cw
            out.append(line)
        else:
            out.extend(textwrap.wrap(para, w, break_long_words=True, replace_whitespace=False) or [""])
    return out


def write(s):
    try:
        sys.stdout.write(s)
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def line(text="", style=None, indent=2):
    """Print wrapped text in the theme. ESC[K paints the rest of the row with
    the theme background, so a colored background fills the whole screen."""
    base = theme.base()
    pre = {"accent": theme.accent(), "dim": theme.dim(), "err": theme.err()}.get(style, "")
    for row in wrap(text, cols() - indent - 1):
        write(f"{base}{' ' * indent}{pre}{row}{base}\033[K\n")


def blank():
    write(f"{theme.base()}\033[K\n")


def paint():
    """Repaint the screen with the theme (clears it)."""
    write(f"{theme.base()}\033[2J\033[H")


def reset():
    write("\033[0m")


def box(title, rows, indent=2):
    """A framed panel; the frame style follows the user's corner preference."""
    style = theme.corners
    base, acc, dim = theme.base(), theme.accent(), theme.dim()
    pad = " " * indent
    if style == "none":
        write(f"{base}{pad}{acc}{title}{base}\033[K\n")
        for r in rows:
            for piece in wrap(r, cols() - indent - 3):
                write(f"{base}{pad}{piece}{base}\033[K\n")
        return
    # interior width between the two vertical bars
    inner = min(cols() - indent - 2, max([width(title) + 4] + [width(r) + 2 for r in rows] + [24]))
    wrapped = []
    for r in rows:
        wrapped.extend(wrap(r, inner - 2))
    tl, tr, bl, br, h, v = CORNERS.get(style, CORNERS["rounded"])
    fill = h * max(0, inner - width(title) - 3)
    write(f"{base}{pad}{dim}{tl}{h} {acc}{title}{base}{dim} {fill}{tr}{base}\033[K\n")
    for r in wrapped:
        write(f"{base}{pad}{dim}{v}{base} {r}{' ' * (inner - width(r) - 1)}{dim}{v}{base}\033[K\n")
    write(f"{base}{pad}{dim}{bl}{h * inner}{br}{base}\033[K\n")


def status(text):
    """One dim line describing an action the agent took (transparency without
    interruption)."""
    short = text if width(text) < cols() - 8 else text[: cols() - 10] + "…"
    write(f"{theme.base()}  {theme.dim()}· {short}{theme.base()}\033[K\n")


def prompt_str():
    # \001..\002 tell readline which bytes are invisible (correct cursor math)
    return f"\001{theme.base()}{theme.accent()}\002{theme.prompt_symbol}\001{theme.base()}\002 "


class Stream:
    """Prints a reply as it is generated, wrapping at word boundaries."""

    def __init__(self, indent=2):
        self.indent = indent
        self.col = 0
        self.started = False
        self.buf = ""

    def _start(self):
        if not self.started:
            self.started = True
            write(f"{theme.base()}" + " " * self.indent)
            self.col = self.indent

    def feed(self, text):
        self._start()
        self.buf += text
        while True:
            m = re.search(r"[ \n]", self.buf)
            if not m:
                break
            word, sep = self.buf[: m.start()], self.buf[m.start()]
            self.buf = self.buf[m.end():]
            self._word(word)
            if sep == "\n":
                self._newline()
            else:
                self._space()
        # CJK text has no spaces: flush when the buffer gets long
        if width(self.buf) > 20 and any(unicodedata.east_asian_width(c) in "WF" for c in self.buf):
            for ch in self.buf:
                self._word(ch, sep_ok=False)
            self.buf = ""

    def _space(self):
        if self.col < cols() - 2:
            write(" ")
            self.col += 1

    def _newline(self):
        write(f"{theme.base()}\033[K\n" + " " * self.indent)
        self.col = self.indent

    def _word(self, word, sep_ok=True):
        w = width(word)
        if w and self.col + w > cols() - 2 and self.col > self.indent:
            self._newline()
        write(word)
        self.col += w

    def end(self):
        if self.buf:
            self._word(self.buf)
            self.buf = ""
        if self.started:
            write(f"{theme.base()}\033[K\n")
        self.started = False
