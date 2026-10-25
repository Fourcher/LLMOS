"""Remote access through Tailscale.

The owner connects this computer to a tailnet once. Someone invited on that tailnet can open a terminal
here (Tailscale SSH). The login and the node key stay in /var/lib/tailscale; an update never replaces them.

Commands are argv lists. `tailscale up` blocks until the owner finishes signing in, so Connect reads the
login link for a few seconds and leaves that process running. The first three arguments of UP stay
`tailscale up --ssh` so a host test can see the command the button runs.
"""
import json
import os
import re
import select
import shutil
import subprocess
import threading
import time

# Connect runs exactly this. The first three arguments are the command the desk promises.
UP = ["tailscale", "up", "--ssh", "--qr"]
_LOGIN = re.compile(r"https://login\.tailscale\.com/\S+")
_IPV4 = re.compile(r"\d+\.\d+\.\d+\.\d+")
LOGIN_TTL = 600
_ACTIONS = ("status", "up", "ssh-on", "ssh-off")

_lock = threading.Lock()
_pending = False
_login_url = ""
_login_qr = ""
_login_at = 0.0
_up_proc = None


def note_pending():
    """The panel is about to open while Connect is still waiting for the login link."""
    global _pending
    with _lock:
        _pending = True


def login_view():
    """(url, qr, pending) for the panel. A login link older than LOGIN_TTL is dropped."""
    with _lock:
        fresh = bool(_login_url) and (time.time() - _login_at) < LOGIN_TTL
        return (_login_url if fresh else ""), (_login_qr if fresh else ""), _pending


def _remember(d):
    """Keep a login link in this process so a panel refresh still shows it."""
    global _pending, _login_url, _login_qr, _login_at
    if not isinstance(d, dict):
        return
    with _lock:
        if d.get("url"):
            _login_url = d["url"]
            _login_qr = d.get("qr") or ""
            _login_at = time.time()
            _pending = False
        elif d.get("pending"):
            _pending = True
        elif d.get("ok") and not d.get("running"):
            _login_url = ""
            _login_qr = ""
            _pending = False
        else:
            _pending = bool(d.get("pending"))


def ssh_enabled(prefs):
    """True when `tailscale debug prefs` says RunSSH is on."""
    text = prefs or ""
    return '"RunSSH": true' in text or '"RunSSH":true' in text


def owner_wants_ssh(value=None):
    """True unless the owner has turned remote SSH off.

    The settings key is `remote_ssh`. Absent, or any value other than false, means yes: the 15-minute
    check puts RunSSH back after a crash, an update, or a prefs reset. False stays off."""
    if value is None:
        from . import config
        value = config.settings.get("remote_ssh", True)
    return value is not False


def _remember_choice(on):
    """Record the owner's SSH choice. The periodic check reads this and does not override it."""
    from . import config
    config.settings.set("remote_ssh", bool(on))


def facts_from(status, prefs, installed=True):
    """Panel facts from `tailscale status --json` and `tailscale debug prefs`. No commands run here."""
    if not installed:
        return {"installed": False, "status": "Not installed", "ip": "—", "ssh": False, "state": ""}
    state, ip = "", "—"
    if isinstance(status, dict):
        state = str(status.get("BackendState") or "")
        ips = ((status.get("Self") or {}).get("TailscaleIPs") or [])
        ips = [x for x in ips if isinstance(x, str)]
        v4 = [x for x in ips if _IPV4.fullmatch(x)]
        ip = v4[0] if v4 else (ips[0] if ips else "—")
    labels = {"Running": "Connected", "NeedsLogin": "Not signed in", "NeedsMachineAuth": "Waiting for approval",
              "Stopped": "Off", "Starting": "Starting"}
    return {"installed": True, "status": labels.get(state, "Not running"), "ip": ip,
            "ssh": ssh_enabled(prefs), "state": state}


def parse_login(text):
    """(url, qr) from `tailscale up --qr` output. QR lines are the block-character rows."""
    raw = text or ""
    m = _LOGIN.search(raw)
    url = m.group(0).rstrip(").,]>\"'") if m else ""
    qr = "\n".join(ln for ln in raw.splitlines() if "█" in ln)
    return url, qr


def _run(argv, timeout):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _gather():
    """Read status and prefs. Does not run `tailscale up`."""
    if not shutil.which("tailscale"):
        return facts_from(None, "", installed=False)
    st = _run(["tailscale", "status", "--json"], 8)
    prefs = _run(["tailscale", "debug", "prefs"], 8)
    data = None
    if st and st.stdout:
        try:
            data = json.loads(st.stdout)
        except ValueError:
            data = None
    return facts_from(data, prefs.stdout if prefs else "", installed=True)


def _capture_up():
    """Run UP, read the login link for about 12 seconds, and leave the process running if it is still waiting."""
    global _up_proc
    if not shutil.which("tailscale"):
        return {"ok": False, "installed": False, "note": "Tailscale is not on this computer yet."}
    with _lock:
        proc = _up_proc
        if proc is not None and proc.poll() is None:
            return {"ok": True, "pending": True, "url": _login_url, "qr": _login_qr, "running": True, "installed": True}
    try:
        proc = subprocess.Popen(UP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        return {"ok": False, "installed": True, "note": str(e)}
    fd = proc.stdout.fileno()
    os.set_blocking(fd, False)
    buf = b""
    url, qr = "", ""
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        ready, _, _ = select.select([fd], [], [], 0.25)
        if not ready:
            if url and qr:
                break
            continue
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            continue
        if not chunk:
            break
        buf += chunk
        url, qr = parse_login(buf.decode("utf-8", "replace"))
        if url and qr:
            # one quiet moment so the last QR rows are in
            more, _, _ = select.select([fd], [], [], 0.4)
            if not more:
                break
    if proc.poll() is not None:
        try:
            rest = os.read(fd, 1 << 20)
        except OSError:
            rest = b""
        if rest:
            buf += rest
            url, qr = parse_login(buf.decode("utf-8", "replace"))
    running = proc.poll() is None
    with _lock:
        _up_proc = proc if running else None
    return {"ok": True, "installed": True, "url": url, "qr": qr, "running": running,
            "pending": running and not url}


def _set_ssh(on):
    if not shutil.which("tailscale"):
        return False, "Tailscale is not on this computer yet."
    argv = ["tailscale", "set", "--ssh" if on else "--ssh=false"]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if r.returncode:
        return False, (r.stderr or r.stdout or "could not change SSH").strip()[:200]
    try:
        _remember_choice(on)
    except Exception as e:
        return False, f"SSH changed, but the choice was not saved ({e})"
    if on:
        return True, "SSH is on."
    return True, "Remote maintenance access is off until you turn it back on."


def dispatch(action):
    """One remote-access action. Returns a JSON string. Never calls rootd (rootd calls this)."""
    if action == "status":
        return json.dumps(_gather())
    if action == "up":
        d = _capture_up()
        _remember(d)
        return json.dumps(d)
    if action == "ssh-on":
        ok, note = _set_ssh(True)
        return json.dumps({"ok": ok, "note": note})
    if action == "ssh-off":
        ok, note = _set_ssh(False)
        return json.dumps({"ok": ok, "note": note})
    raise ValueError("bad args: action")


def call(action):
    """Run dispatch here when this process is root. Otherwise ask rootd. If rootd is down and the
    tailscale binary is on the machine, try dispatch here. If the binary is missing, report that."""
    if action not in _ACTIONS:
        raise ValueError("bad args: action")
    if os.geteuid() == 0:
        return dispatch(action)
    try:
        from . import rootd_client
        return rootd_client.call("tailscale", action=action)
    except Exception:
        if shutil.which("tailscale"):
            return dispatch(action)
        return json.dumps(facts_from(None, "", installed=False))


def snapshot():
    """Facts for the panel. As root this reads the commands here; otherwise rootd does."""
    if os.geteuid() == 0:
        return _gather()
    try:
        data = json.loads(call("status"))
        if isinstance(data, dict) and "installed" in data:
            return data
    except Exception:
        pass
    if not shutil.which("tailscale"):
        return facts_from(None, "", installed=False)
    return _gather()


def connect():
    """`tailscale up --ssh`, then remember the login link in this process (the panel reads it here)."""
    if os.geteuid() != 0:
        try:
            d = json.loads(call("up"))
        except Exception as e:
            d = {"ok": False, "note": str(e)}
        if not isinstance(d, dict):
            d = {"ok": False, "note": "no answer"}
        _remember(d)
        return d
    d = _capture_up()
    _remember(d)
    return d


def set_ssh(on):
    """Turn Tailscale SSH on or off. Returns (ok, note)."""
    if os.geteuid() != 0:
        try:
            d = json.loads(call("ssh-on" if on else "ssh-off"))
        except Exception as e:
            return False, str(e)
        if not isinstance(d, dict):
            return False, "no answer"
        return bool(d.get("ok")), str(d.get("note") or "")
    return _set_ssh(bool(on))
