"""The clipboard and the camera and microphone check.

Clipboard: what was copied in any program (the browser, a terminal, the file manager, an app) is noted as it is copied
(wl-paste --watch), the last few kept in memory only (/run, never on disk), so "what did I copy" and "clipboard
history" work, and an old item can be copied again. Camera and microphone: "is my webcam working" shows the camera's
picture; "test my mic" records a few seconds, says how loud it was and plays it back.
"""
import array
import glob
import os
import shutil
import subprocess

from . import config, media

DIR = os.path.join(config.RUN, "clip")
KEEP = 20
MAX = 4000


def _env():
    return dict(os.environ, **(media.desk_env() or {}))


def start_watch():
    """Note every copy from now on (one small helper process; returns it, or None without wl-clipboard)."""
    if not shutil.which("wl-paste"):
        return None
    os.makedirs(DIR, mode=0o700, exist_ok=True)
    keep = f"ls -1t {DIR}/*.txt 2>/dev/null | tail -n +{KEEP + 1} | xargs -r rm -f"
    cmd = f'f={DIR}/$(date +%s%N).txt; head -c {MAX} > "$f"; [ -s "$f" ] || rm -f "$f"; {keep}'
    try:
        return subprocess.Popen(["wl-paste", "--type", "text", "--watch", "sh", "-c", cmd], env=_env(),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def history():
    """[(id, text)] newest first, repeats folded."""
    out, seen = [], set()
    for p in sorted(glob.glob(os.path.join(DIR, "*.txt")), reverse=True):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                t = f.read()
        except OSError:
            continue
        if t.strip() and t not in seen:
            seen.add(t)
            out.append((os.path.basename(p)[:-4], t))
    return out


def current():
    if not shutil.which("wl-paste"):
        return ""
    try:
        p = subprocess.run(["wl-paste", "--no-newline", "--type", "text"], capture_output=True, text=True, timeout=5, env=_env())
        return p.stdout[:MAX] if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def copy(text=None, path=None, mime=None):
    """Put text (or a file's bytes, e.g. a screenshot) on the clipboard."""
    if not shutil.which("wl-copy"):
        return False
    try:
        if path:
            with open(path, "rb") as f:
                data = f.read()
            argv = ["wl-copy"] + (["--type", mime] if mime else [])
            subprocess.run(argv, input=data, timeout=5, env=_env())
        else:
            subprocess.run(["wl-copy"], input=str(text).encode(), timeout=5, env=_env())
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def copy_again(item_id):
    for i, t in history():
        if i == item_id:
            return copy(t)
    return False


def clear():
    for p in glob.glob(os.path.join(DIR, "*.txt")):
        try:
            os.remove(p)
        except OSError:
            pass
    if shutil.which("wl-copy"):
        try:
            subprocess.run(["wl-copy", "--clear"], timeout=5, env=_env())
        except (OSError, subprocess.SubprocessError):
            pass


def panel():
    items = history()
    rows = [{"title": t.strip().replace("\n", " ")[:90] + ("…" if len(t.strip()) > 90 else ""),
             "subtitle": f"{len(t)} characters" if len(t) > 90 else "",
             "actions": [{"label": "Copy", "say": f"copy clip {i}", "primary": True}]} for i, t in items[:KEEP]]
    blocks = [{"type": "list", "items": rows}] if rows else \
        [{"type": "text", "text": "Nothing copied yet. Whatever you copy in any program shows up here (kept until the computer restarts).", "dim": True}]
    if rows:
        blocks.append({"type": "buttons", "items": [{"label": "Clear the clipboard", "say": "clear the clipboard"}]})
    return {"id": "clipboard", "replace": True, "title": "Clipboard", "size": "m", "blocks": blocks}


# ---- camera and microphone

def cameras():
    return sorted(glob.glob("/dev/video*"))


def camera_test():
    """(ok, words). Shows the first camera's picture in a window (mpv)."""
    cams = cameras()
    if not cams:
        return False, "No camera found. If it is a USB camera, plug it in and ask again; a laptop's may be switched off with a key or a switch."
    if not shutil.which("mpv"):
        return False, "The camera is there, but the player that shows it is missing."
    try:
        subprocess.Popen(["mpv", "--title=Camera check", "--profile=low-latency", "--untimed", "--no-osc",
                          f"av://v4l2:{cams[0]}"], env=_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        return False, f"Could not open the camera: {e}"
    return True, "Here's your camera. If the picture is black, check for a privacy shutter or switch. Close the window when you're done."


def _level(path):
    """Peak of a 16-bit little-endian mono recording, 0..1."""
    try:
        with open(path, "rb") as f:
            raw = f.read()[44:]
    except OSError:
        return 0.0
    a = array.array("h")
    a.frombytes(raw[:len(raw) // 2 * 2])
    return (max((abs(x) for x in a), default=0)) / 32768


def mic_test(seconds=4):
    """(ok, words). Records a few seconds, measures how loud, plays it back."""
    rec = shutil.which("pw-record") or shutil.which("arecord")
    if not rec:
        return False, "There is no recording program on this system."
    path = os.path.join(config.RUN, "mic-test.wav")
    if rec.endswith("pw-record"):
        argv = [rec, "--channels", "1", "--format", "s16", "--rate", "16000", path]
    else:
        argv = [rec, "-q", "-f", "S16_LE", "-c", "1", "-r", "16000", "-d", str(seconds), path]
    try:
        p = subprocess.Popen(argv, env=_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            p.terminate()
            p.wait(timeout=3)
    except OSError as e:
        return False, f"Could not record: {e}"
    peak = _level(path)
    play = shutil.which("pw-play") or shutil.which("aplay")
    if play and peak > 0.02:
        subprocess.Popen([play, path], env=_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if peak < 0.02:
        return False, ("I heard nothing. Check the microphone isn't muted (some have a button or a key), that it's "
                       "plugged in, and in the sound settings that the right one is chosen.")
    if peak < 0.08:
        return True, "The microphone works, but it's quiet. Speak closer, or turn the input level up in the sound settings."
    return True, "The microphone works. Playing back what I heard."

