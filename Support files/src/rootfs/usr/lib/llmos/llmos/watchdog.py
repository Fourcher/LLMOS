"""The llmos-watchdog service: keeps the network and the update link alive without anyone at the keyboard.

It depends on nothing network-related (unlike llmos-ota), so it can repair what the others need:
  - Wi-Fi (iwd) stopped -> started again; the update service stopped -> started again;
  - the paired update computer unreachable for 5 minutes while this machine has no working network -> Wi-Fi
    restarted (then the update service started again, since stopping Wi-Fi stops it);
  - on a test computer (remote testing on): still unreachable after 25 minutes -> restart the computer, which comes
    back to a normal session by itself.
"""
import os
import re
import socket
import subprocess
import time

from . import config

CHECK = 30            # seconds between checks
WIFI_AFTER = 300      # unreachable this long: restart Wi-Fi
REBOOT_AFTER = 1500   # still unreachable this long on a test computer: restart


def _rc(*args, timeout=90):
    try:
        return subprocess.run(["rc-service", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _running(svc):
    p = _rc(svc, "status", timeout=20)
    return bool(p) and p.returncode == 0 and "started" in (p.stdout + p.stderr)


def _has_service(svc):
    return os.path.exists(f"/etc/init.d/{svc}")


def _wifi_present():
    try:
        return any(os.path.isdir(f"/sys/class/net/{n}/wireless") for n in os.listdir("/sys/class/net"))
    except OSError:
        return False


def _server():
    o = config.settings.get("ota") or {}
    m = re.match(r"https?://([^/:]+)(?::(\d+))?", str(o.get("url") or ""))
    return (m.group(1), int(m.group(2) or 80)) if m else None


def _reachable(hp):
    if not hp:
        return True                   # nothing paired: nothing to judge by
    try:
        with socket.create_connection(hp, timeout=8):
            return True
    except OSError:
        return False


def _log(msg):
    print(time.strftime("%H:%M:%S ") + "watchdog: " + msg, flush=True)


def run():
    down_since = None
    wifi_kicked = False
    while True:
        try:
            if _has_service("iwd") and _wifi_present() and not _running("iwd"):
                _log("Wi-Fi was stopped: starting it")
                _rc("iwd", "start")
            if config.settings.get("ota") and _has_service("llmos-ota") and not _running("llmos-ota"):
                _log("the update service was stopped: starting it")
                _rc("llmos-ota", "start")
            # judged down only when neither the update computer nor the internet answers (the Mac asleep or
            # off is not this machine's problem: then nothing is restarted)
            if _reachable(_server()) or _reachable(("1.1.1.1", 443)) or _reachable(("9.9.9.9", 443)):
                if down_since:
                    _log(f"the update computer is reachable again after {time.time() - down_since:.0f} s")
                down_since, wifi_kicked = None, False
            else:
                down_since = down_since or time.time()
                gone = time.time() - down_since
                if gone > WIFI_AFTER and not wifi_kicked and _has_service("iwd") and _wifi_present():
                    _log("no network for 5 minutes: restarting Wi-Fi")
                    _rc("iwd", "restart")
                    time.sleep(10)
                    _rc("llmos-ota", "start")
                    wifi_kicked = True
                if gone > REBOOT_AFTER and config.settings.get("devlink"):
                    _log("still no network after 25 minutes on a test computer: restarting it")
                    subprocess.run(["reboot"], timeout=30)
        except Exception as e:
            _log(f"check failed: {e}")
        time.sleep(CHECK)


def ensure_service():
    """Called by the update service: the watchdog is part of every boot from now on (added by an update)."""
    if not _has_service("llmos-watchdog"):
        return
    if not os.path.exists("/etc/runlevels/default/llmos-watchdog"):
        subprocess.run(["rc-update", "add", "llmos-watchdog", "default"], capture_output=True, timeout=30)
    if not _running("llmos-watchdog"):
        _rc("llmos-watchdog", "start")
