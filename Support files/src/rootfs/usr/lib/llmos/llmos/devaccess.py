"""Direct access to a TEST computer from the owner's own computer (development only).

With remote testing on (setting "devlink") and the owner's development key received in a signed remote-testing
command (setting "devssh_key"), an SSH server runs (dropbear, key only: no password works) and the firewall lets
the local network reach it (system.py). The owner's computer can then log in whenever this one is on, wherever its
own address moved. Remote testing off: the server stops and the key is removed.
"""
import os
import shutil
import subprocess

from . import config

KEYS = "/root/.ssh/authorized_keys"
MARK = "llmos-dev"


def _rc(*a):
    try:
        return subprocess.run(["rc-service", *a], capture_output=True, text=True, timeout=60).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def _write_key(key):
    os.makedirs("/root/.ssh", mode=0o700, exist_ok=True)
    lines = []
    if os.path.exists(KEYS):
        lines = [ln for ln in open(KEYS).read().splitlines() if not ln.rstrip().endswith(MARK)]
    if key:
        lines.append(f"{key.strip().split(' ')[0]} {key.strip().split(' ')[1]} {MARK}")
    with open(KEYS, "w") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    os.chmod(KEYS, 0o600)


def ensure(log=print):
    """Bring the SSH server in line with the settings (cheap when nothing changed: the watchdog calls it)."""
    key = config.settings.get("devssh_key") if config.settings.get("devlink") else None
    try:
        if not key:
            if os.path.exists(KEYS) and MARK in open(KEYS).read():
                _write_key(None)
                _rc("dropbear", "stop")
                subprocess.run(["rc-update", "del", "dropbear", "default"], capture_output=True, timeout=30)
                log("devaccess: remote testing is off: direct access closed")
            return False
        if not shutil.which("dropbear"):
            subprocess.run(["apk", "add", "--no-cache", "dropbear"], capture_output=True, timeout=300)
        if not shutil.which("dropbear"):
            log("devaccess: dropbear could not be installed")
            return False
        want = 'DROPBEAR_OPTS="-s -g -p 22"\n'          # keys only: no password logins at all
        conf = "/etc/conf.d/dropbear"
        if not os.path.exists(conf) or open(conf).read() != want:
            with open(conf, "w") as f:
                f.write(want)
            _rc("dropbear", "restart")
        cur = open(KEYS).read() if os.path.exists(KEYS) else ""
        if key.strip().split(" ")[1] not in cur:
            _write_key(key)
            from . import system
            system.apply_firewall()
            log("devaccess: the owner's computer may log in now")
        subprocess.run(["rc-update", "add", "dropbear", "default"], capture_output=True, timeout=30)
        if _rc("dropbear", "status") != 0:
            _rc("dropbear", "start")
        return True
    except OSError as e:
        log(f"devaccess: {e}")
        return False
