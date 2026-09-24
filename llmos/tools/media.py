import glob
import json
import os
import re
import subprocess

from .. import config
from . import tool, ToolError, s, b, R, N
from .system import run_cmd

MAX_HEIGHT = 720  # old laptops; the user can raise it with remember(video_quality, 1080)


def _display_env():
    env = {}
    socks = glob.glob(os.path.join(config.rpath("xdg"), "wayland-*"))
    socks = [p for p in socks if not p.endswith(".lock")]
    if socks:
        env["WAYLAND_DISPLAY"] = os.path.basename(socks[0])
        env["XDG_RUNTIME_DIR"] = config.rpath("xdg")
        return env, []
    if glob.glob("/dev/dri/card*") and not config.DEV:
        return env, ["--vo=drm"]
    return None, []


def _ytdlp(ctx, *args, timeout=60):
    cmd = ["yt-dlp", "--no-warnings", "--no-playlist"]
    if ctx.net.mode == "tor":
        cmd += ["--proxy", "socks5://127.0.0.1:9050"]
    cmd += list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise ToolError("yt-dlp: " + (p.stderr.strip().splitlines() or ["failed"])[-1][:300])
    return p.stdout.strip()


def resolve(ctx, query, latest_from_channel=False):
    """Find exactly one video. Returns (url, title, channel)."""
    if re.match(r"https?://", query) and not latest_from_channel:
        out = _ytdlp(ctx, "--print", "%(webpage_url)s\t%(title)s\t%(channel)s", query)
        return out.split("\t", 2) + [""] * (3 - len(out.split("\t", 2)))
    if latest_from_channel:
        if re.match(r"https?://", query) or query.startswith("@"):
            chan = query if query.startswith("http") else "https://www.youtube.com/" + query
        else:
            chan = _ytdlp(ctx, "--print", "channel_url", "ytsearch1:" + query + " channel")
        out = _ytdlp(ctx, "--flat-playlist", "--playlist-items", "1", "--yes-playlist",
                     "--print", "%(url)s\t%(title)s\t%(channel)s", chan.rstrip("/") + "/videos")
    else:
        out = _ytdlp(ctx, "--print", "%(webpage_url)s\t%(title)s\t%(channel)s", "ytsearch1:" + query)
    parts = out.splitlines()[0].split("\t")
    while len(parts) < 3:
        parts.append("")
    return parts


def _mpv(ctx, target, video=True):
    env, extra = _display_env()
    if video and env is None:
        raise ToolError("no screen available to play video on (text console)")
    ctx.stop_media()
    q = int(ctx.memory.pref("video_quality", MAX_HEIGHT) or MAX_HEIGHT) if hasattr(ctx.memory, "pref") else MAX_HEIGHT
    cmd = ["mpv", "--really-quiet", "--no-terminal", "--keep-open=no", "--loop-file=no", "--loop-playlist=no",
           "--ytdl-raw-options=no-playlist=", "--ytdl-format=bestvideo[height<=%d]+bestaudio/best[height<=%d]/best" % (q, q)]
    if ctx.net.mode == "tor":
        cmd.append("--ytdl-raw-options-append=proxy=socks5://127.0.0.1:9050")
    if video:
        cmd += ["--fs", "--osc=yes"] + extra
    else:
        cmd += ["--no-video"]
    cmd.append(target)
    e = dict(os.environ)
    e.update(env or {})
    e.update(ctx.net_env())
    ctx.media = subprocess.Popen(cmd, env=e, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)


@tool("play_video", "Play one video fullscreen (YouTube or any site yt-dlp supports). Give a URL or a search query. "
      "latest_from_channel=true plays the newest upload of the named channel. Plays only that video, no recommendations.",
      {"query_or_url": s(), "latest_from_channel": b()}, ["query_or_url"], klass=N)
def play_video(ctx, query_or_url, latest_from_channel=False):
    ctx.require_network()
    url, title, channel = resolve(ctx, query_or_url, latest_from_channel)
    if "youtube.com" in url or "youtu.be" in url:
        url = re.sub(r"[?&](list|index|pp)=[^&]*", "", url)
    _mpv(ctx, url, True)
    return "playing: %s%s\n%s" % (title, (" (" + channel + ")") if channel else "", url)


@tool("play_audio", "Play audio only (a URL, a search query for music/podcasts, or a local file path).",
      {"query_or_url": s()}, klass=N)
def play_audio(ctx, query_or_url):
    if os.path.exists(query_or_url):
        _mpv(ctx, query_or_url, False)
        return "playing " + query_or_url
    ctx.require_network()
    url, title, channel = resolve(ctx, query_or_url)
    _mpv(ctx, url, False)
    return "playing audio: %s\n%s" % (title, url)


@tool("stop_media", "Stop any video or audio that is playing.", {}, klass=R)
def stop_media(ctx):
    return "stopped" if ctx.stop_media() else "nothing was playing"
