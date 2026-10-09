"""Using any program on the screen the way a person does: read what is on the screen (the text of every window, with
where it is), click on a word or a place, type, press keys, scroll, bring a window to the front.

The screen is read with grim (a screenshot) and tesseract (the words and their boxes), the pointer and windows are
driven with wlrctl and the keyboard with wtype -- all already part of the system. Nothing here needs a model that
can see pictures: the screen comes back as lines of text with their positions, which any model can act on.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import media

SHOT = "/tmp/llmos-screen.png"
_LAST = {"lines": [], "at": 0.0, "size": (0, 0)}
# AT-SPI (the accessibility bus) first for native windows; OCR is the fallback. The bus address is written by the
# desk's session (llmos-desk) to this file. Each AT-SPI request runs in a child process that is killed after the
# timeout, so a stuck D-Bus call can never hang the agent.
ATSPI_ENV = os.environ.get("LLMOS_A11Y_ENV", "/run/llmos/a11y.env")
_ATSPI_TIMEOUT = 2.5
_CLICK_ROLES = ("push button", "toggle button", "check box", "radio button", "menu item", "check menu item",
                "radio menu item", "menu", "link", "button")
_FIELD_ROLES = ("entry", "text", "password text")
_DESK_APPS = ("llmos", "llmos-desk", "python3", "python")       # the desk's own webview: the OS's apps have their own bridge
_HIT = {}                                                       # the AT-SPI element the last find() returned


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


STRIP = "/tmp/llmos-strip.png"


def _ocr(psm, path=SHOT, dy=0):
    """The lines tesseract reads in an image (the screenshot, or a strip of it starting dy pixels down, at twice the
    screen's size) with one page-segmentation mode, in screen pixels."""
    t = _run(["tesseract", path, "-", "--psm", psm, "tsv"], timeout=90)
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
        left, top, w, h = left // 2, (top + dy) // 2, max(1, w // 2), max(1, h // 2)   # back to screen pixels
        groups.setdefault((c[2], c[3], c[4]), []).append((left, top, w, h, word))   # block, paragraph, line
    lines = []
    for words in groups.values():
        words.sort()
        x0 = min(q[0] for q in words); y0 = min(q[1] for q in words)
        x1 = max(q[0] + q[2] for q in words); y1 = max(q[1] + q[3] for q in words)
        lines.append({"text": " ".join(q[4] for q in words), "x": (x0 + x1) // 2, "y": (y0 + y1) // 2,
                      "w": x1 - x0, "h": y1 - y0, "words": words})
    return lines


BOX = "/tmp/llmos-box.png"


def _buttons():
    """Buttons and other solid boxes, each read on its own: a dark button with light words (or the other way round)
    reads cleanly by itself even where a whole-screen reading turns it into noise."""
    if not shutil.which("magick"):
        return []
    sw, sh = _size(SHOT)
    r = _run(["magick", SHOT, "-colorspace", "Gray", "-threshold", "70%", "-define", "connected-components:verbose=true",
              "-define", "connected-components:area-threshold=1500", "-connected-components", "4", "null:"], timeout=60)
    boxes = []
    for row in (r.stdout or "").splitlines()[1:]:
        m = re.match(r"\s*\d+:\s+(\d+)x(\d+)\+(\d+)\+(\d+)", row)
        if not m:
            continue
        w, h, x, y = (int(v) for v in m.groups())
        if 100 <= w <= min(1400, sw // 2) and 40 <= h <= 220:        # the size of a button, a tab or a field (at 2x)
            boxes.append((x, y, w, h))
    lines = []
    for (x, y, w, h) in boxes[:40]:
        if _run(["magick", SHOT, "-crop", f"{w}x{h}+{x}+{y}", "+repage", "PNG24:" + BOX], timeout=20).returncode:
            continue
        text = " ".join((_run(["tesseract", BOX, "-", "--psm", "7"], timeout=20).stdout or "").split())
        if not text.strip() and w < 2.5 * h:            # a key with one sign on it ("7", "=", "+"): read as one character
            text = " ".join((_run(["tesseract", BOX, "-", "--psm", "10"], timeout=20).stdout or "").split())
        text = re.sub(r"^[^\w(]+|[^\w).!?]+$", "", text)        # the box's own edge read as ':' or '|' 
        cx, cy, sx, sy = (x + w // 2) // 2, (y + h // 2) // 2, w // 2, h // 2
        if not re.search(r"[A-Za-z0-9=+×÷−%.()-]", text) or len(text) > 60:
            if w > 3 * h:                                  # an empty, wide box: a place to write (a text field)
                lines.append({"text": "", "x": cx, "y": cy, "w": sx, "h": sy, "words": [], "field": True})
            continue
        lines.append({"text": text, "x": cx, "y": cy, "w": sx, "h": sy,
                      "words": [(x // 2, y // 2, sx, sy, text)], "button": True, "field": w > 4 * h})
    return lines


def read_screen():
    """Every line of text on the screen with its centre: [{"text", "x", "y", "w", "h"}], top to bottom."""
    r = _run(["grim", "-s", "2", SHOT], timeout=30)       # twice the size: tesseract reads small text and single keys far better
    if r.returncode != 0:
        raise RuntimeError("the screen could not be captured: " + (r.stderr or "").strip()[:200])
    # the screen is read in overlapping strips (a whole-screen reading drops buttons drawn as dark boxes, like a
    # "Download" button), then once whole as scattered text for anything the strips missed; a line already found is
    # not added twice
    lines = []

    def add(found):
        for d in found:
            if not any(abs(d["x"] - e["x"]) <= max(e["w"], d["w"]) // 2 + 6 and abs(d["y"] - e["y"]) <= max(e["h"], d["h"]) // 2 + 6
                       for e in lines):
                lines.append(d)
    sw, sh = _size(SHOT)
    add(_buttons())                                    # buttons first: the most reliable reading of what can be clicked
    step, height = 150, 200
    if shutil.which("magick") and sh:
        for y in range(0, sh, step):
            if _run(["magick", SHOT, "-crop", f"{sw}x{height}+0+{y}", "+repage", "PNG24:" + STRIP], timeout=20).returncode == 0:
                add(_ocr("6", STRIP, y))
    else:
        add(_ocr("6"))
    add(_ocr("11"))
    lines.sort(key=lambda d: (d["y"] // 12, d["x"]))
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
        out.append(f"[{d['x']},{d['y']}] {d['text']}" if d["text"] else f"[{d['x']},{d['y']}] (empty box to write in)")
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


def field_for(target, lines=None, atspi=True):
    """The box to write in for these words: the box whose own words (a grey hint inside it) match, else the empty box
    nearest to the matching words (a label beside or above it), else the only box on the screen."""
    want = str(target or "").lower()
    if want and atspi:
        d = _atspi_find(want, _FIELD_ROLES)
        if d:
            return dict(d, field=True)
    lines = read_screen() if lines is None else lines
    fields = [d for d in lines if d.get("field")]
    if not fields:
        return None
    for d in fields:
        if d["text"] and want and want in d["text"].lower():
            return d
    near = find(want, [d for d in lines if d["text"]], atspi=False) if want else None
    if near:
        return min(fields, key=lambda f: abs(f["x"] - near["x"]) / 3 + abs(f["y"] - near["y"]) + (0 if f["y"] >= near["y"] - 4 else 200))
    return fields[0] if len(fields) == 1 else max(fields, key=lambda f: f["w"])


def find(target, lines=None, atspi=True):
    """The place on the screen that best matches the words: a whole line, or a word inside a line."""
    want = re.sub(r"\s+", " ", str(target or "")).strip().lower()
    if not want:
        return None
    if atspi:
        d = _atspi_find(want, _CLICK_ROLES + _FIELD_ROLES)
        if d is not None:
            return d
    _log(f"ocr find {want!r} (no accessible match)")
    lines = read_screen() if lines is None else lines
    if len(want) <= 2:
        return _find_key(want, lines)
    best, score = None, 0.0
    for d in lines:
        if not d["text"]:
            continue
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
            s = 0.75 + 0.25 * len(want) / max(len(text), 1)
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
    hit = dict(_HIT)
    _HIT.clear()                                   # one-shot: the element found for this click
    if (hit and hit.get("x") == x and hit.get("y") == y and button == "left" and not double
            and time.time() - hit.get("at", 0) < 15):
        field = hit.get("role") in _FIELD_ROLES
        r = _atspi_req({"op": "focus" if field else "click", "target": hit["name"], "roles": [hit["role"]],
                        "window": hit.get("window", "")})
        if r.get("ok"):
            _log(f"atspi {'focus' if field else 'click'} {hit['name']!r} ({hit['role']})")
            return True
        if r.get("timeout"):
            _log(f"atspi timed out on {hit['name']!r}; not clicking")
            return False
        # the action did not go through: the pointer goes to the place the element was found at, below
    if x is None or y is None:
        return False
    _log(f"ocr click at {x},{y}")
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


# ------------------------------------------------------------ AT-SPI: the accessible buttons and fields of native windows
# A native program (GTK, Qt, Firefox with a11y) publishes its windows on the accessibility bus. A button is found by its
# name and role and pressed through its Action; a field is focused and then typed in. Anything that does not publish
# (the foot terminal, a game, a picture) has no tree here and falls back to the OCR above.

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log(msg):
    print("control: " + msg, file=sys.stderr, flush=True)


def _norm(s):
    return " ".join(str(s or "").split()).casefold()


def _iface(node, name):
    try:
        return getattr(node, name)()
    except Exception:
        return None


def _iface_name(node):
    try:
        return node.get_name() or ""
    except Exception:
        return ""


def _children(node):
    out = []
    try:
        for i in range(min(int(node.get_child_count() or 0), 200)):
            c = node.get_child_at_index(i)
            if c is not None:
                out.append(c)
    except Exception:
        pass
    return out


def find_element(frames, target, roles, children=_children, max_nodes=1500):
    """The first element (breadth first) whose role is in roles and whose name matches target: exact (case- and
    whitespace-insensitive) before partial. Returns (node, name, role) or None. Pure: takes any Atspi-like objects."""
    want = _norm(target)
    roles = set(roles)
    if not want:
        return None
    queue = list(frames)
    exact = partial = None
    seen = 0
    while queue and seen < max_nodes:
        node = queue.pop(0)
        seen += 1
        try:
            raw = node.get_name() or ""
            role = (node.get_role_name() or "").lower()
        except Exception:
            raw, role = "", ""
        name = _norm(raw.replace("_", ""))
        if name and role in roles:
            if name == want:
                exact = (node, raw, role)
                break
            if partial is None and re.search(r"(?<!\w)" + re.escape(want) + r"(?!\w)", name):
                partial = (node, raw, role)
        queue.extend(children(node))
    return exact or partial


def _active(Atspi, node):
    try:
        return bool(node.get_state_set().contains(Atspi.StateType.ACTIVE))
    except Exception:
        return False


def _scope(Atspi, window=""):
    """The top-level windows to search: the named window, else the focused one. The desk's own windows are left out."""
    want = _norm(window)
    out = []
    for app in _children(Atspi.get_desktop(0)):
        if _norm(_iface_name(app)) in _DESK_APPS:
            continue
        for top in _children(app):
            name = _norm(_iface_name(top))
            if "llm os" in name:
                continue
            if want:
                if want in name:
                    out.append(top)
            elif _active(Atspi, top):
                out.append(top)
    return out


def _do_action(node):
    """Press it: the Action named click, press or activate (else the first action). True if the toolkit acted."""
    act = _iface(node, "get_action")
    if act is None:
        return False
    try:
        n = act.get_n_actions()
        names = [(act.get_action_name(i) or "").lower() for i in range(n)]
        for want in ("click", "press", "activate", "toggle"):
            if want in names:
                return bool(act.do_action(names.index(want)))
        return bool(n) and bool(act.do_action(0))
    except Exception:
        return False


def _grab_focus(node):
    comp = _iface(node, "get_component")
    try:
        return bool(comp.grab_focus()) if comp is not None else False
    except Exception:
        return False


def _set_text(node, text):
    et = _iface(node, "get_editable_text")
    try:
        return bool(et.set_text_contents(text)) if et is not None else False
    except Exception:
        return False


def _center(Atspi, node):
    """The middle of the element on the screen, in logical (toolkit) pixels; (None, None) when it has no place."""
    comp = _iface(node, "get_component")
    if comp is None:
        return None, None
    try:
        r = comp.get_extents(Atspi.CoordType.SCREEN)
    except Exception:
        return None, None
    if not r or r.width <= 0 or r.height <= 0:
        return None, None
    return r.x + r.width / 2, r.y + r.height / 2


def _atspi_module():
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except Exception:
        return None
    try:
        Atspi.init()
    except Exception:
        pass
    return Atspi


def _child(req, Atspi=None):
    """One request answered from the accessibility tree. Runs in the child process (or directly in a test with a fake
    Atspi). op: find | click | focus | text."""
    if Atspi is None:
        Atspi = _atspi_module()
        if Atspi is None:
            return {"ok": False, "why": "no gi/Atspi"}
    hit = find_element(_scope(Atspi, req.get("window") or ""), req.get("target"), req.get("roles") or [])
    if hit is None:
        return {"ok": False, "why": "no match"}
    node, name, role = hit
    cx, cy = _center(Atspi, node)
    out = {"ok": False, "name": name, "role": role, "x": cx, "y": cy}
    op = req.get("op")
    if op == "find":
        out["ok"] = True
    elif op == "click":
        out["ok"] = _do_action(node)
    elif op == "focus":
        out["ok"] = _grab_focus(node)
    elif op == "text":
        out["ok"] = _set_text(node, str(req.get("text", "")))
    return out


def _child_main():
    try:
        req = json.loads(sys.stdin.read() or "{}")
        out = _child(req)
    except Exception as e:
        out = {"ok": False, "why": str(e)[:200]}
    sys.stdout.write("\n" + json.dumps(out) + "\n")
    sys.stdout.flush()


def _bus_env():
    env = {}
    try:
        with open(ATSPI_ENV) as f:
            for ln in f:
                k, _, v = ln.strip().partition("=")
                if k == "DBUS_SESSION_BUS_ADDRESS" and v:
                    env[k] = v
    except OSError:
        pass
    return env


def _atspi_req(req):
    """Ask the accessibility tree in a child process, killed after _ATSPI_TIMEOUT seconds. Returns a dict with ok."""
    env = dict(os.environ, **_bus_env())
    if not env.get("DBUS_SESSION_BUS_ADDRESS"):
        return {"ok": False, "why": "no accessibility bus"}
    code = "import sys; sys.path.insert(0, %r); from llmos import control; control._child_main()" % _PKG
    try:
        p = subprocess.run([sys.executable, "-I", "-c", code], input=json.dumps(req), capture_output=True, text=True,
                           timeout=_ATSPI_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "timeout": True}
    except Exception as e:
        return {"ok": False, "why": str(e)[:200]}
    lines = (p.stdout or "").strip().splitlines()
    try:
        return json.loads(lines[-1]) if lines else {"ok": False, "why": (p.stderr or "")[-200:]}
    except ValueError:
        return {"ok": False, "why": "bad reply"}


def _atspi_find(target, roles, window=""):
    """The accessible element for these words as a find() result ({"text","x","y",...}), or None (use OCR). Its place
    is remembered so that click() on the same place presses the element through its Action."""
    if not _norm(target):
        return None
    r = _atspi_req({"op": "find", "target": target, "roles": list(roles), "window": window})
    if r.get("timeout"):
        _log(f"atspi timed out for {target!r}; using ocr")
        return None
    if not r.get("ok"):
        return None
    x = y = None
    if r.get("x") is not None:
        s = _scale()
        x, y = int(r["x"] * s), int(r["y"] * s)              # logical -> the screenshot's pixels, as the OCR reads
    _HIT.clear()
    _HIT.update(name=r["name"], role=r["role"], window=window, x=x, y=y, at=time.time())
    return {"text": r["name"], "x": x, "y": y, "w": 0, "h": 0, "words": [], "atspi": True,
            "field": r["role"] in _FIELD_ROLES}


def _atspi_act(target, op, roles, window="", text=None):
    """Find the element and act on it in one request (for a caller that does not go through find())."""
    req = {"op": op, "target": target, "roles": list(roles), "window": window}
    if text is not None:
        req["text"] = text
    r = _atspi_req(req)
    if r.get("timeout"):
        _log(f"atspi timed out on {target!r}; not acting")
        return False
    if r.get("ok"):
        _log(f"atspi {op} {r.get('name')!r} ({r.get('role')})")
    return bool(r.get("ok"))


def atspi_click(target, window=None):
    """Press the button, toggle, menu item or link named target in the focused (or the named) window."""
    return _atspi_act(str(target or ""), "click", _CLICK_ROLES, window or "")


def atspi_set_text(target, text, window=None):
    """Put text into the field named target (its EditableText), in the focused (or the named) window."""
    return _atspi_act(str(target or ""), "text", _FIELD_ROLES, window or "", text=str(text))
