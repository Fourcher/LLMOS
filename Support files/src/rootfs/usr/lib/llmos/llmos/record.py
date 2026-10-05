"""Recording what is on the screen (wf-recorder, into Videos) and the microphone (pw-record, into Music), started and
stopped in words: "record my screen", "record my voice", "stop recording"."""
import os
import shutil
import signal
import subprocess
import time

from . import config, media

_CUR = {}          # kind -> (Popen, path)


def _env():
    return dict(os.environ, **(media.desk_env() or {}))


def _dest(folder, ext):
    d = os.path.join(config.home(), folder)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, time.strftime(f"{'screen' if folder == 'Videos' else 'recording'}-%Y%m%d-%H%M%S.{ext}"))


def recording():
    """The kinds being recorded now ('screen', 'voice')."""
    return [k for k, (p, _) in _CUR.items() if p.poll() is None]


def start(kind):
    """(ok, words)."""
    if kind in recording():
        return False, f"already recording the {'screen' if kind == 'screen' else 'microphone'}; say “stop recording” to finish"
    if kind == "screen":
        if not shutil.which("wf-recorder"):
            return False, "the screen recorder is not installed (say “install wf-recorder”)"
        path = _dest("Videos", "mp4")
        argv = ["wf-recorder", "-f", path]
    else:
        rec = shutil.which("pw-record") or shutil.which("arecord")
        if not rec:
            return False, "there is no recording program on this system"
        path = _dest("Music", "wav")
        argv = [rec, path] if rec.endswith("pw-record") else [rec, "-q", "-f", "cd", path]
    try:
        p = subprocess.Popen(argv, env=_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except OSError as e:
        return False, f"could not start recording: {e}"
    time.sleep(1.0)
    if p.poll() is not None:
        return False, "recording stopped at once (no screen to record, or no microphone)"
    _CUR[kind] = (p, path)
    return True, path


def stop():
    """[(kind, path)] of what was being recorded, now saved."""
    out = []
    for kind, (p, path) in list(_CUR.items()):
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGINT)        # both programs finish the file cleanly on Ctrl+C
                p.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()
        _CUR.pop(kind, None)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            out.append((kind, path))
    return out
