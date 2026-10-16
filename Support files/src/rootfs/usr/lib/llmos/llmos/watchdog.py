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


def _wifi_awake():
    """Wi-Fi power saving off (it naps between beacons and answers late)."""
    try:
        for n in os.listdir("/sys/class/net"):
            if os.path.isdir(f"/sys/class/net/{n}/wireless"):
                out = subprocess.run(["iw", "dev", n, "get", "power_save"], capture_output=True, text=True, timeout=5).stdout
                if "on" in out:
                    subprocess.run(["iw", "dev", n, "set", "power_save", "off"], capture_output=True, timeout=5)
                    _log(f"Wi-Fi power saving off on {n}")
    except (OSError, subprocess.SubprocessError):
        pass


def _repair_iwd():
    """Wi-Fi won't start: the usual cause is its DNS helper (resolvconf) missing or not runnable. Make it runnable,
    or else let Wi-Fi manage without it, and start Wi-Fi again."""
    conf = "/etc/iwd/main.conf"
    try:
        for p in ("/usr/libexec/llmos-resolvconf",):
            if os.path.exists(p) and not os.access(p, os.X_OK):
                os.chmod(p, 0o755)
                _log(f"made {p} runnable")
        txt = open(conf).read() if os.path.exists(conf) else ""
        if "NameResolvingService=resolvconf" in txt and not os.access("/sbin/resolvconf", os.X_OK):
            with open(conf, "w") as f:
                f.write(txt.replace("NameResolvingService=resolvconf", "NameResolvingService=none"))
            _log("Wi-Fi set back to manage without resolvconf")
    except OSError as e:
        _log(f"Wi-Fi repair failed: {e}")
    _rc("iwd", "start")


def _log(msg):
    print(time.strftime("%H:%M:%S ") + "watchdog: " + msg, flush=True)


def _reboot(why):
    """Restart the computer, keeping why on disk (the watchdog's own log is in /run and goes with the restart)."""
    _log(why)
    try:
        os.makedirs("/var/lib/llmos", exist_ok=True)
        with open("/var/lib/llmos/watchdog-restarts.log", "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + why + f" (memory free {_mem_avail_pct():.1f}%)\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    subprocess.run(["reboot"], timeout=30)


def _sound_firmware():
    """Intel laptops (SOF audio) find no sound card when their firmware arrived after the driver looked for it (an
    update that installed sof-firmware): load the driver again once the firmware is there."""
    try:
        if "no soundcards" not in _read_text("/proc/asound/cards") or not os.path.isdir("/lib/firmware/intel/sof"):
            return
        mods = _read_text("/proc/modules")
        for m in ("snd_sof_pci_intel_tgl", "snd_sof_pci_intel_mtl", "snd_sof_pci_intel_cnl", "snd_sof_pci_intel_icl",
                  "snd_sof_pci_intel_apl"):
            if m + " " in mods:
                subprocess.run(["modprobe", "-r", m], capture_output=True, timeout=30)
                subprocess.run(["modprobe", m], capture_output=True, timeout=30)
                _log(f"sound: loaded {m} again with its firmware")
    except (OSError, subprocess.SubprocessError) as e:
        _log(f"sound check failed: {e}")


def _read_text(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def _mem_avail_pct():
    try:
        mi = dict(re.findall(r"^(\w+):\s+(\d+)", _read_text("/proc/meminfo"), re.M))
        return 100.0 * int(mi["MemAvailable"]) / max(1, int(mi["MemTotal"]))
    except (KeyError, ValueError):
        return 100.0


def run():
    down_since = None
    wifi_kicked = False
    low_since, model_kicked = None, False
    desk_gone = None
    _sound_firmware()
    while True:
        try:
            if _has_service("iwd") and _wifi_present() and not _running("iwd"):
                _log("Wi-Fi was stopped: starting it")
                _rc("iwd", "start")
                if not _running("iwd"):
                    _repair_iwd()
            if config.settings.get("devlink") or config.settings.get("stay_awake"):
                _wifi_awake()            # a test computer answers at once, also when idle
            # memory nearly gone (a model too big for this machine, a crash that left graphics memory behind): the
            # computer swaps until nothing answers. The model server is started again first; on a test computer that
            # cannot be reached otherwise, a restart follows if that did not help.
            if _mem_avail_pct() < 3:
                low_since = low_since or time.time()
                if time.time() - low_since > 90 and not model_kicked:
                    _log(f"memory nearly gone ({_mem_avail_pct():.1f}% free): starting the model server again")
                    _rc("llmos-model", "restart", timeout=120)
                    model_kicked = True
                elif time.time() - low_since > 300 and model_kicked and config.settings.get("devlink"):
                    _reboot("memory still nearly gone after 5 minutes on a test computer: restarting it")
            else:
                low_since, model_kicked = None, False
            # the screen session is up but the desk program died (out of memory, a crash): start it again
            from . import ota
            if ota.desk_missing():
                desk_gone = desk_gone or time.time()
                if time.time() - desk_gone > 60:
                    _log("the desk was gone for a minute: starting it again")
                    ota.restart_desk()
                    desk_gone = None
            else:
                desk_gone = None
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
                    _reboot("still no network after 25 minutes on a test computer: restarting it")
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
