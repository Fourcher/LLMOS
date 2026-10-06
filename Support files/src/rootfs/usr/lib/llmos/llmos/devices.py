"""Hardware controls. They act on real devices and say so plainly when a
device does not exist (a virtual machine has no backlight)."""
import os
import re
import shutil
import subprocess


def brightness(percent=None, delta=None):
    base = "/sys/class/backlight"
    try:
        devs = sorted(os.listdir(base))
    except OSError:
        devs = []
    if not devs:
        return ("This machine has no adjustable backlight, so brightness can't be changed "
                "here (under a virtual machine the host controls the screen).")
    dev = os.path.join(base, devs[0])
    with open(os.path.join(dev, "max_brightness")) as f:
        mx = int(f.read())
    with open(os.path.join(dev, "brightness")) as f:
        raw = int(f.read())
    if delta is not None and percent is None:
        # a step is at least one raw level: panels with a handful of levels still move
        step = max(1, round(mx * abs(int(delta)) / 100))
        new = raw + step if int(delta) > 0 else raw - step
    elif percent is None:
        return f"Brightness is {raw * 100 // mx}%."
    else:
        new = round(mx * max(1, min(100, int(percent))) / 100)
    new = max(1, min(mx, int(new)))          # never 0: that is "off" on most backlights
    with open(os.path.join(dev, "brightness"), "w") as f:
        f.write(str(new))
    return f"Brightness set to {new * 100 // mx}%."


def _amixer(*args):
    return subprocess.run(["amixer", *args], capture_output=True, text=True)


def _control():
    """The playback control to drive: 'Master' where it exists, otherwise the
    first playback control the card offers (a virtio or HDA card names them
    differently)."""
    r = _amixer("scontrols")
    names = re.findall(r"Simple mixer control '([^']+)'", r.stdout)
    for pref in ("Master", "PCM", "Speaker", "Headphone", "Playback", "Front"):
        if pref in names:
            return pref
    for n in names:
        if "Playback" in _amixer("get", n).stdout:
            return n
    return names[0] if names else None


def chime():
    """A short sound for timers and finished background work; silent without a sound card."""
    from . import config, media
    wav = os.path.join(config.SHARE, "chime.wav")
    if not config.settings.get("chime", True) or not os.path.exists(wav) or not media.has_audio():
        return False
    for cmd in (["aplay", "-q", wav], ["mpv", "--no-video", "--really-quiet", wav]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True
    return False


def volume(percent=None, mute=None, delta=None):
    if not shutil.which("amixer"):
        return "No audio mixer is installed."
    try:
        with open("/proc/asound/cards") as f:
            if "no soundcards" in f.read():
                return "This machine has no sound card, so there is no volume to set."
    except OSError:
        return "This machine has no sound card, so there is no volume to set."
    ctl = _control()
    if not ctl:
        return "The sound card offers no volume control (it plays at a fixed level)."
    if mute == "toggle":
        mute = "[off]" not in _amixer("get", ctl).stdout
    if mute is not None:
        r = _amixer("set", ctl, "mute" if mute else "unmute")
        return ("Muted." if mute else "Unmuted.") if r.returncode == 0 else r.stderr.strip()
    if percent is None:
        r = _amixer("get", ctl)
        m = re.search(r"\[(\d+)%\]", r.stdout)
        if delta is not None and m:
            percent = int(m.group(1)) + int(delta)
        else:
            return f"Volume is {m.group(1)}%." if m else "The volume level can't be read."
    pct = max(0, min(100, int(percent)))
    r = _amixer("set", ctl, f"{pct}%")
    if r.returncode != 0:
        return "Couldn't set the volume: " + (r.stderr.strip() or r.stdout.strip())[:200]
    m = re.search(r"\[(\d+)%\]", r.stdout)
    return f"Volume set to {m.group(1) if m else pct}%."
