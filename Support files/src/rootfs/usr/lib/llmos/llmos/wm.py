"""Programs' windows on the screen (not the desk's own): switch to one, maximize, minimize, close or stop a frozen one,
and drive the browser with its own keys (back, forward, reload, new tab, close tab). Uses wlrctl (the compositor's
window list) and wtype (keys go to the window in front)."""
import os
import re
import shutil
import subprocess
import time

APP_IDS = {"browser": "firefox", "firefox": "firefox", "web": "firefox", "internet": "firefox", "files": "thunar", "file manager": "thunar",
           "thunar": "thunar", "terminal": "foot", "foot": "foot", "editor": "org.xfce.mousepad", "text editor": "org.xfce.mousepad",
           "mousepad": "org.xfce.mousepad", "abiword": "abiword", "word processor": "abiword", "gnumeric": "gnumeric",
           "spreadsheet": "gnumeric", "photos": "org.xfce.ristretto", "ristretto": "org.xfce.ristretto", "image viewer": "org.xfce.ristretto",
           "video": "mpv", "document": "abiword", "word": "abiword", "player": "mpv", "music": "mpv", "mpv": "mpv"}
PROCS = {"firefox": "firefox", "thunar": "thunar", "foot": "foot", "org.xfce.mousepad": "mousepad", "abiword": "abiword",
         "gnumeric": "gnumeric", "org.xfce.ristretto": "ristretto", "mpv": "mpv"}
NAMES = {"firefox": "the browser", "thunar": "Files", "foot": "the terminal", "org.xfce.mousepad": "the text editor",
         "abiword": "the word processor", "gnumeric": "the spreadsheet", "org.xfce.ristretto": "the image viewer", "mpv": "the player"}
KEYS = {"back": ["-M", "alt", "-k", "Left", "-m", "alt"], "forward": ["-M", "alt", "-k", "Right", "-m", "alt"],
        "reload": ["-k", "F5"], "new tab": ["-M", "ctrl", "-k", "t", "-m", "ctrl"], "close tab": ["-M", "ctrl", "-k", "w", "-m", "ctrl"],
        "home": ["-M", "alt", "-k", "Home", "-m", "alt"], "print": ["-M", "ctrl", "-k", "p", "-m", "ctrl"],
        "save": ["-M", "ctrl", "-k", "s", "-m", "ctrl"],
        "zoom in": ["-M", "ctrl", "-k", "plus", "-m", "ctrl"], "zoom out": ["-M", "ctrl", "-k", "minus", "-m", "ctrl"],
        "zoom reset": ["-M", "ctrl", "-k", "0", "-m", "ctrl"], "bookmark": ["-M", "ctrl", "-k", "d", "-m", "ctrl"],
        "clear history": ["-M", "ctrl", "-M", "shift", "-k", "Delete", "-m", "shift", "-m", "ctrl"], "find": ["-M", "ctrl", "-k", "f", "-m", "ctrl"],
        "bookmarks": ["-M", "ctrl", "-M", "shift", "-k", "o", "-m", "shift", "-m", "ctrl"]}


def _env():
    env = dict(os.environ)
    try:
        with open("/run/llmos/display.env") as f:
            for ln in f:
                k, _, v = ln.strip().partition("=")
                if k:
                    env[k] = v
    except OSError:
        pass
    return env


def _run(argv, timeout=10):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=_env())
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def app_id(words):
    w = re.sub(r"\b(the|my|this|that|app|window|program)\b", " ", str(words).lower())
    w = " ".join(w.split())
    return APP_IDS.get(w) or (w if w in PROCS else None)


def windows():
    """[app_id] of the program windows open now."""
    if not shutil.which("lswt"):
        return []
    rc, out = _run(["lswt", "-j"])
    # (its "identifier" is printed unquoted, so this is not strict JSON: read the app ids directly)
    return [a for a in re.findall(r'"app-id":\s*"([^"]*)"', out) if a and a != "org.llmos.desk"]


def act(what, target):
    """what: focus | maximize | minimize | fullscreen | close. target: an app id."""
    if not shutil.which("wlrctl"):
        return False, "window control is not available on this system"
    if not target:
        return False, "that program is not open"
    if target not in windows():
        return False, f"{NAMES.get(target, target)} is not open"
    verb = {"focus": "focus", "maximize": "maximize", "minimize": "minimize", "fullscreen": "fullscreen", "close": "close"}[what]
    if verb in ("focus", "maximize", "fullscreen"):
        _run(["wlrctl", "toplevel", "unminimize", f"app_id:{target}"])   # a minimized window is never "focused" out of sight
    rc, out = _run(["wlrctl", "toplevel", verb, f"app_id:{target}"])
    return rc == 0, out.strip()


def force_quit(target):
    proc = PROCS.get(target, target)
    rc, _ = _run(["pkill", "-x", proc])
    time.sleep(1.5)
    if _run(["pgrep", "-x", proc])[0] == 0:
        _run(["pkill", "-9", "-x", proc])
    return True, f"stopped {NAMES.get(target, proc)}"


def browser_key(action):
    if "firefox" not in windows():
        return False, "the browser is not open"
    act("focus", "firefox")
    time.sleep(0.3)
    rc, out = _run(["wtype"] + KEYS[action])
    return rc == 0, out.strip()


def last_program():
    ws = windows()
    return ws[-1] if ws else None


def focus_program(argv):
    """Bring a program the desk started to the front (its dock chip was clicked)."""
    name = os.path.basename(str(argv[0])) if argv else ""
    ids = windows()
    for aid in [a for a, p in PROCS.items() if p == name] + [name, name.lower()]:
        if aid in ids:
            return act("focus", aid)
    # a window id that names the program ("telegram-desktop" shows as "org.telegram.desktop")
    core = re.sub(r"[-_](?:desktop|bin|app|gtk|qt)$", "", name.lower())
    for aid in ids:
        if core and (core in aid.lower().split(".") or aid.lower().endswith("." + core) or core in aid.lower()):
            return act("focus", aid)
    return False, "its window is not open"


def minimize_all():
    """Show the desktop: every program window out of the way."""
    n = 0
    for aid in set(windows()):
        if act("minimize", aid)[0]:
            n += 1
    return n > 0, ("Everything is out of the way." if n else "No program windows are open.")


def tile(target, side):
    """Put a program on the left or right half (focus it, then the compositor's own snap keys)."""
    ok, note = act("focus", target)
    if not ok:
        return ok, note
    time.sleep(0.2)
    rc, out = _run(["wtype", "-M", "logo", "-k", "Left" if side == "left" else "Right", "-m", "logo"])
    return rc == 0, f"Put {NAMES.get(target, target)} on the {side}."


def key_to_front(action):
    """Send a program's own key (print, save) to the program window in front. (ok, which program)."""
    t = last_program()
    if not t or t in ("mpv",):
        return False, None
    act("focus", t)
    time.sleep(0.3)
    rc, _ = _run(["wtype"] + KEYS[action])
    return rc == 0, NAMES.get(t, t)


def side_by_side():
    """The two most recent program windows, one on each half of the screen."""
    ws = [w for w in dict.fromkeys(windows())]
    if len(ws) < 2:
        return False, "only one program window is open" if ws else "no program windows are open"
    a, b = ws[-2], ws[-1]
    tile(a, "left")
    time.sleep(0.3)
    tile(b, "right")
    return True, f"{NAMES.get(a, a)} on the left, {NAMES.get(b, b)} on the right"
