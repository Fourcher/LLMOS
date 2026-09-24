"""Brightness and volume. With llmos.fakehw (VMs, tests) values are kept in
/run/llmos/hw.json instead of touching hardware."""
import glob
import json
import os
import re
import subprocess

from . import config


def _fake_load():
    try:
        with open(config.rpath("hw.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"brightness": 80, "volume": 50, "mute": False}


def _fake_save(d):
    os.makedirs(config.RUN, exist_ok=True)
    with open(config.rpath("hw.json"), "w") as f:
        json.dump(d, f)


def _backlights():
    return sorted(glob.glob("/sys/class/backlight/*"))


def fake():
    return config.FAKE_HW or not _backlights() and not os.path.exists("/proc/asound/cards") or config.DEV


def get_brightness():
    if config.FAKE_HW or config.DEV or not _backlights():
        return _fake_load()["brightness"]
    b = _backlights()[0]
    cur = int(open(b + "/brightness").read())
    mx = int(open(b + "/max_brightness").read()) or 1
    return round(cur * 100 / mx)


def set_brightness(percent):
    percent = max(0, min(100, int(percent)))
    bl = _backlights()
    if config.FAKE_HW or config.DEV or not bl:
        d = _fake_load()
        d["brightness"] = percent
        _fake_save(d)
        if not bl and not (config.FAKE_HW or config.DEV):
            # No backlight (desktop monitor or VM): try DDC-less software dimming via gamma is
            # not available under cage, so report honestly.
            return "no backlight control on this display; value stored"
        return "brightness %d%%" % percent
    for b in bl:
        mx = int(open(b + "/max_brightness").read())
        # Never go fully black by accident; 0 means minimum visible.
        val = max(1 if percent == 0 else 0, round(mx * percent / 100))
        with open(b + "/brightness", "w") as f:
            f.write(str(val))
    return "brightness %d%%" % percent


def _amixer(*args):
    return subprocess.run(["amixer", "-q", "-M"] + list(args), capture_output=True, text=True, timeout=5)


def _controls():
    try:
        out = subprocess.run(["amixer", "scontrols"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return re.findall(r"'([^']+)'", out)


def get_volume():
    if config.FAKE_HW or config.DEV:
        d = _fake_load()
        return d["volume"], d.get("mute", False)
    for c in ("Master", "PCM", "Speaker"):
        try:
            out = subprocess.run(["amixer", "-M", "get", c], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            break
        m = re.search(r"\[(\d+)%\].*?\[(on|off)\]", out)
        if m:
            return int(m.group(1)), m.group(2) == "off"
    return _fake_load()["volume"], False


def set_volume(percent=None, mute=None):
    if config.FAKE_HW or config.DEV:
        d = _fake_load()
        if percent is not None:
            d["volume"] = max(0, min(100, int(percent)))
        if mute is not None:
            d["mute"] = bool(mute)
        _fake_save(d)
        return "volume %d%%%s" % (d["volume"], " (muted)" if d.get("mute") else "")
    ctrls = [c for c in ("Master", "PCM", "Speaker", "Headphone") if c in _controls()]
    if not ctrls:
        return "no audio device found"
    for c in ctrls:
        if percent is not None:
            _amixer("set", c, "%d%%" % max(0, min(100, int(percent))))
        if mute is not None:
            _amixer("set", c, "mute" if mute else "unmute")
        elif percent is not None and int(percent) > 0:
            _amixer("set", c, "unmute")
    v, m = get_volume()
    return "volume %d%%%s" % (v, " (muted)" if m else "")
