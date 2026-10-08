"""Using any program on the screen the way a person does: read what is on the screen (the text of every window, with
where it is), click on a word or a place, type, press keys, scroll, bring a window to the front.

The screen is read with grim (a screenshot) and tesseract (the words and their boxes), the pointer and windows are
driven with wlrctl and the keyboard with wtype -- all already part of the system. Nothing here needs a model that
can see pictures: the screen comes back as lines of text with their positions, which any model can act on.
"""
import difflib
import os
import re
import shutil
import subprocess
import time

from . import media

SHOT = "/tmp/llmos-screen.png"
_LAST = {"lines": [], "at": 0.0, "size": (0, 0)}


def available():
    return all(shutil.which(b) for b in ("grim", "tesseract", "wlrctl", "wtype")) and media.desk_env() is not None


def _env():
    return dict(os.environ, **(media.desk_env() or {}))


def _run(argv, timeout=20, text=True):
    try:
        return subprocess.run(argv, capture_output=True, text=text, timeout=timeout, env=_env())
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(argv, 1, "", str(e))


def _size(path):
    """(width, height) of a PNG, from its header."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except OSError:
        return 0, 0


def _ocr(psm):
    """The lines tesseract reads in the screenshot with one page-segmentation mode, in screen pixels."""
    t = _run(["tesseract", SHOT, "-", "--psm", psm, "tsv"], timeout=90)
    if t.returncode != 0:
        raise RuntimeError("the text on the screen could not be read: " + (t.stderr or "").strip()[:200])
    groups = {}
    for row in t.stdout.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        try:
            conf = float(c[10])
            left, top, w, h = (int(v) for v in c[6:10])
        except ValueError:
            continue
        word = c[11].strip()
        if conf < (35 if len(word) > 2 else 5):           # a button's single digit or sign is read with low confidence
            continue
        left, top, w, h = left // 2, top // 2, max(1, w // 2), max(1, h // 2)   # back to screen pixels
        groups.setdefault((c[2], c[3], c[4]), []).append((left, top, w, h, word))   # block, paragraph, line
    lines = []
    for words in groups.values():
        words.sort()
        x0 = min(q[0] for q in words); y0 = min(q[1] for q in words)
        x1 = max(q[0] + q[2] for q in words); y1 = max(q[1] + q[3] for q in words)
        lines.append({"text": " ".join(q[4] for q in words), "x": (x0 + x1) // 2, "y": (y0 + y1) // 2,
                      "w": x1 - x0, "h": y1 - y0, "words": words})
    return lines


def read_screen():
    """Every line of text on the screen with its centre: [{"text", "x", "y", "w", "h"}], top to bottom."""
    r = _run(["grim", "-s", "2", SHOT], timeout=30)       # twice the size: tesseract reads small text and single keys far better
    if r.returncode != 0:
        raise RuntimeError("the screen could not be captured: " + (r.stderr or "").strip()[:200])
    # two readings merged: as one block (reads every button's single digit or sign) and as scattered text (finds
    # labels the block reading skips); a scattered line is kept only where the block reading found nothing
    lines = _ocr("6")
    for d in _ocr("11"):
        if not any(abs(d["x"] - e["x"]) <= e["w"] // 2 + 6 and abs(d["y"] - e["y"]) <= e["h"] // 2 + 6 for e in lines):
            lines.append(d)
    lines.sort(key=lambda d: (d["y"] // 12, d["x"]))
    sw, sh = _size(SHOT)
    _LAST.update(lines=lines, at=time.time(), size=(sw // 2, sh // 2))
    return lines


def describe(lines=None, limit=120):
    """The screen in words for the model: the open windows, then each line of text as [x,y] text."""
    from . import wm
    lines = read_screen() if lines is None else lines
    try:
        wins = wm.windows()
    except Exception:
        wins = []
    w, h = _LAST["size"]
    out = [f"screen {w}x{h}" + (f"; windows open: {', '.join(wins)}" if wins else "")]
    for d in lines[:limit]:
        out.append(f"[{d['x']},{d['y']}] {d['text']}")
    if len(lines) > limit:
        out.append(f"(+{len(lines) - limit} more lines)")
    return "\n".join(out)


_SAME = {"×": "x", "*": "x", "−": "-", "–": "-", "—": "-", "÷": "/", "o": "0", "O": "0"}


def _norm_char(c):
    c = (c or "").strip()
    return _SAME.get(c, c).lower()


def _read_box(x, y, w, h):
    """One small piece of the last screenshot read as a single character or two (a button's label)."""
    if not shutil.which("magick"):
        return ""
    pad = 6
    crop = "/tmp/llmos-key.png"
    geo = f"{(w + 2 * pad) * 2}x{(h + 2 * pad) * 2}+{max(0, (x - pad) * 2)}+{max(0, (y - pad) * 2)}"
    if _run(["magick", SHOT, "-crop", geo, "+repage", "-colorspace", "Gray", "-resize", "300%", crop], timeout=20).returncode:
        return ""
    return (_run(["tesseract", crop, "-", "--psm", "10"], timeout=20).stdout or "").strip()


def _find_key(want, lines):
    """A short label ("7", "+", "=", "OK"): every short word on the screen is read again on its own, so a misread
    sign (÷ taken for +) is never clicked by mistake; the matching one is returned."""
    goal = _norm_char(want)
    for d in lines:
        for (x, y, w, h, word) in d["words"]:
            if len(word) > 3:
                continue
            if _norm_char(_read_box(x, y, w, h)) == goal:
                return dict(d, text=word, x=x + w // 2, y=y + h // 2)
    return None


def find(target, lines=None):
    """The place on the screen that best matches the words: a whole line, or a word inside a line."""
    lines = read_screen() if lines is None else lines
    want = re.sub(r"\s+", " ", str(target or "")).strip().lower()
    if not want:
        return None
    if len(want) <= 2:
        return _find_key(want, lines)
    best, score = None, 0.0
    for d in lines:
        text = d["text"].lower()
        if text == want:
            return d
        if want in text:
            # the matching words themselves, not the middle of a long line
            ws = [x for x in d["words"] if x[4].lower().strip(".,:;!?()[]") in want.split()]
            if ws:
                x0 = min(a[0] for a in ws); y0 = min(a[1] for a in ws)
                x1 = max(a[0] + a[2] for a in ws); y1 = max(a[1] + a[3] for a in ws)
                cand = dict(d, x=(x0 + x1) // 2, y=(y0 + y1) // 2)
            else:
                cand = d
            s = 0.9 + len(want) / (len(text) + 1) / 10
        else:
            s = difflib.SequenceMatcher(None, want, text).ratio()
            cand = d
        if s > score:
            best, score = cand, s
    return best if score >= 0.72 else None


def _scale():
    """Screen pixels per pointer unit (2 on a HiDPI output scaled 2x), from wlr-randr when it is there."""
    if shutil.which("wlr-randr"):
        m = re.search(r"Scale:\s*([\d.]+)", _run(["wlr-randr"], timeout=5).stdout or "")
        if m:
            try:
                return float(m.group(1)) or 1.0
            except ValueError:
                pass
    return 1.0


def move_to(x, y):
    """The pointer to a place on the screen (in screenshot pixels): to the top-left corner, then across."""
    s = _scale()
    _run(["wlrctl", "pointer", "move", "-20000", "-20000"], timeout=5)
    r = _run(["wlrctl", "pointer", "move", str(int(x / s)), str(int(y / s))], timeout=5)
    return r.returncode == 0


def click(x, y, button="left", double=False):
    if not move_to(x, y):
        return False
    time.sleep(0.1)
    for _ in range(2 if double else 1):
        r = _run(["wlrctl", "pointer", "click", button], timeout=5)
        if r.returncode != 0:
            return False
        time.sleep(0.08)
    return True


def type_text(text):
    r = _run(["wtype", "--", str(text)], timeout=60)
    return r.returncode == 0, (r.stderr or "").strip()


_KEYNAMES = {"enter": "Return", "return": "Return", "tab": "Tab", "esc": "Escape", "escape": "Escape",
             "backspace": "BackSpace", "delete": "Delete", "del": "Delete", "space": "space", "up": "Up",
             "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End", "pageup": "Prior",
             "pagedown": "Next", "page up": "Prior", "page down": "Next", "f5": "F5", "f11": "F11", "f12": "F12"}
_MODS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift", "super": "logo", "win": "logo",
         "windows": "logo", "cmd": "ctrl", "command": "ctrl", "logo": "logo"}


def press(keys):
    """A key or a combination: "enter", "ctrl+s", "ctrl+shift+t", "alt+f4". Several in a row: "tab tab enter"."""
    for combo in str(keys).strip().split():
        parts = [p for p in re.split(r"\+", combo.lower()) if p]
        if not parts:
            continue
        mods = [_MODS[p] for p in parts[:-1] if p in _MODS]
        key = parts[-1]
        key = _KEYNAMES.get(key, key if len(key) == 1 else key.capitalize())
        argv = ["wtype"]
        for m in mods:
            argv += ["-M", m]
        argv += ["-k", key]
        for m in reversed(mods):
            argv += ["-m", m]
        r = _run(argv, timeout=10)
        if r.returncode != 0:
            return False, (r.stderr or "").strip()
        time.sleep(0.12)
    return True, ""


def scroll(direction="down", amount=3):
    dy = 15 * int(amount or 3) * (-1 if str(direction).lower().startswith("u") else 1)
    r = _run(["wlrctl", "pointer", "scroll", str(dy), "0"], timeout=5)
    return r.returncode == 0
