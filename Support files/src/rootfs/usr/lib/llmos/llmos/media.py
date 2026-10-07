"""Video and music: find it with yt-dlp, play it with mpv on this machine's
screen and speakers (under QEMU: the VM window and the host's speakers).

With the graphical desk running, mpv opens as a window in its compositor and
is controlled over its IPC socket (pause, volume, stop). Without a desk (the
text console on a machine with a screen) it runs inside a one-window kiosk;
without any screen it plays audio only."""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time

from . import config

PIDFILE = os.path.join(config.RUN, "mpv.pid")
LOG = os.path.join(config.RUN, "mpv.log")
IPC = os.path.join(config.RUN, "mpv.sock")
DISPLAY_ENV = os.path.join(config.RUN, "display.env")


class MediaError(Exception):
    pass


def has_display():
    return any(os.path.exists(f"/dev/dri/card{i}") for i in range(4))


def has_audio():
    try:
        with open("/proc/asound/cards") as f:
            return "no soundcards" not in f.read()
    except OSError:
        return False


def desk_env():
    """Environment of the running graphical desk (its compositor), or None."""
    env = {}
    try:
        with open(DISPLAY_ENV) as f:
            for ln in f:
                k, _, v = ln.strip().partition("=")
                if k and v:
                    env[k] = v
    except OSError:
        return None
    if not env.get("WAYLAND_DISPLAY"):
        return None
    sock = os.path.join(env.get("XDG_RUNTIME_DIR", config.RUN), env["WAYLAND_DISPLAY"])
    if not os.path.exists(sock):
        return None
    return env


def _proxy_args():
    return ["--proxy", "socks5h://127.0.0.1:9050"] if config.settings.get("tor") else []   # h: names resolved by Tor, no DNS leak


def find(query, pick=1):
    """Return a dict (url, title, channel, duration, thumbnail, live) for a
    URL or a search phrase. pick: which result of a search (1 = the first; "skip" asks for the next)."""
    from . import system
    if re.match(r"^https?://", query) and system.is_blocked(query):
        raise MediaError("that site is blocked while focus mode is on; turn focus off to play from it")
    target = query if re.match(r"^https?://", query) else f"ytsearch{max(1, int(pick))}:{query}"
    cmd = ["yt-dlp", "--no-warnings", "--no-playlist", "--js-runtimes", "quickjs",
           *_proxy_args(), "--skip-download",
           "--print", "%(webpage_url)s\t%(title)s\t%(channel,uploader)s\t%(duration_string)s\t%(thumbnail)s\t%(is_live)s", target]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise MediaError("yt-dlp is not installed")
    except subprocess.TimeoutExpired:
        raise MediaError("the video site took too long to answer")
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("http")]
    line = lines[-1] if lines else ""
    if not line:
        err = (p.stderr.strip().splitlines() or ["nothing found"])[-1]
        raise MediaError(err[:300])
    parts = (line.split("\t") + ["", "", "", "", ""])[:6]
    thumb = parts[4] if parts[4].startswith("http") else ""
    return {"url": parts[0], "title": parts[1], "channel": parts[2], "duration": parts[3],
            "thumbnail": thumb, "live": parts[5].lower() == "true"}


def _common_args():
    common = ["--no-terminal", "--really-quiet", "--keep-open=no",
              "--ytdl-format=bv*[height<=720]+ba/b[height<=720]/b",
              "--script-opts=ytdl_hook-ytdl_path=yt-dlp",
              "--ytdl-raw-options=js-runtimes=quickjs" + (",proxy=socks5h://127.0.0.1:9050" if config.settings.get("tor") else "")]
    if not has_audio():
        common.append("--ao=null")
    return common


def kiosk_launch(argv, log_path):
    """Run a graphical program on the screen. With the desk running it becomes
    a window in the desk's compositor; otherwise it gets the one-window
    Wayland kiosk (cage, software rendered, seat from seatd-launch)."""
    os.makedirs(config.RUN, exist_ok=True)
    log = open(log_path, "a")
    denv = desk_env()
    if denv:
        env = dict(os.environ, **denv, HOME=config.home(), MOZ_ENABLE_WAYLAND="1", GDK_BACKEND="wayland",
                   QT_QPA_PLATFORM="wayland", SDL_VIDEODRIVER="wayland")
        return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                start_new_session=True, env=env, cwd="/")   # not inside the vault: it must stay lockable
    subprocess.run(["pkill", "-x", "cage"], capture_output=True)
    subprocess.run(["pkill", "-x", "seatd"], capture_output=True)
    # the display is only free once the old kiosk has really exited
    for _ in range(40):
        gone = subprocess.run(["pgrep", "-x", "cage"], capture_output=True).returncode != 0 and \
               subprocess.run(["pgrep", "-x", "seatd"], capture_output=True).returncode != 0
        if gone:
            break
        time.sleep(0.1)
    else:
        subprocess.run(["pkill", "-9", "-x", "cage"], capture_output=True)
        subprocess.run(["pkill", "-9", "-x", "seatd"], capture_output=True)
        time.sleep(0.5)
    time.sleep(0.6)
    try:
        os.unlink("/run/seatd.sock")
    except OSError:
        pass
    env = dict(os.environ, WLR_RENDERER=os.environ.get("WLR_RENDERER", "pixman"), XDG_RUNTIME_DIR=config.RUN,
               MOZ_ENABLE_WAYLAND="1")
    env.update(config.personal_env())
    return subprocess.Popen(["seatd-launch", "--", "cage", "--", *argv], stdin=subprocess.DEVNULL,
                            stdout=log, stderr=log, start_new_session=True, env=env)


def playing():
    try:
        with open(PIDFILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def ipc(command):
    """Send one command to the running mpv (desk mode). True if it answered."""
    if not os.path.exists(IPC):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(IPC)
        s.sendall((json.dumps(command) + "\n").encode())
        data = s.recv(4096)
        s.close()
        return b'"success"' in data or b"error" in data
    except OSError:
        return False


def stop():
    pid = playing()
    if pid:
        ipc({"command": ["quit"]})
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    for p in (PIDFILE, IPC):
        try:
            os.unlink(p)
        except OSError:
            pass
    return bool(pid)


def pause(resume=False):
    pid = playing()
    if not pid:
        return False
    if os.path.exists(IPC):
        return ipc({"command": ["set_property", "pause", not resume]})
    os.killpg(pid, signal.SIGCONT if resume else signal.SIGSTOP)
    return True


def play_windowed(info, audio_only, env):
    """mpv as a window of the desk's compositor, with an IPC socket."""
    os.makedirs(config.RUN, exist_ok=True)
    try:
        os.unlink(IPC)
    except OSError:
        pass
    # gpu output only through a Wayland GL context (never X11); without one
    # (a VM) mpv falls back to plain shared-memory frames
    args = ["mpv", f"--input-ipc-server={IPC}", "--wayland-app-id=llmos-media", f"--title={info.get('title', 'LLM OS')[:80]}",
            "--osc=yes", "--vo=gpu,wlshm", "--gpu-context=wayland", "--geometry=62%x62%", "--autofit-larger=90%x85%",
            *_common_args()]
    if os.environ.get("LIBGL_ALWAYS_SOFTWARE") == "1" or env.get("LIBGL_ALWAYS_SOFTWARE") == "1":
        args[args.index("--vo=gpu,wlshm")] = "--vo=wlshm"
    if audio_only:
        args += ["--no-video", "--force-window=no"]
    args.append(info["url"])
    log = open(LOG, "w")
    p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                         env=dict(env, HOME=config.home()))
    with open(PIDFILE, "w") as f:
        f.write(str(p.pid))
    return p


def play_local(path, title, audio_only=False):
    """Play a file from the disk: a window on the desk, the kiosk without one, audio only when asked.
    Writes the pid file like play() so stop/pause work the same way."""
    stop()
    denv = desk_env()
    info = {"url": path, "title": title}
    os.makedirs(config.RUN, exist_ok=True)
    if denv is not None:
        p = play_windowed(info, audio_only or not has_display(), dict(os.environ, **denv))
    elif has_display() and not audio_only and shutil.which("cage"):
        p = kiosk_launch(["mpv", "--vo=wlshm", "--fs", *_common_args(), path], LOG)
    else:
        log = open(LOG, "w")
        p = subprocess.Popen(["mpv", *_common_args(), "--no-video", path], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    with open(PIDFILE, "w") as f:
        f.write(str(p.pid))
    return p


def play(query, audio_only=False):
    info = find(query)
    stop()
    denv = desk_env()
    common = _common_args()
    os.makedirs(config.RUN, exist_ok=True)
    video = has_display() and not audio_only and (denv is not None or shutil.which("cage") is not None)
    if denv is not None:
        p = play_windowed(info, audio_only or not has_display(), dict(os.environ, **denv))
    elif video:
        # no desk: the one-window kiosk (cage) with mpv's software output
        p = kiosk_launch(["mpv", "--vo=wlshm", "--fs", *common, info["url"]], LOG)
    else:
        log = open(LOG, "w")
        p = subprocess.Popen(["mpv", *common, "--no-video", info["url"]], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    with open(PIDFILE, "w") as f:
        f.write(str(p.pid))
    info["video"] = video
    info["audio"] = has_audio()
    return info
