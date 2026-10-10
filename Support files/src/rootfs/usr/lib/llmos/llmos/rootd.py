"""rootd: a small root service that will later perform the privileged actions for an unprivileged desk.

Stdlib only. One JSON request per connection: {"verb": "...", "args": {...}}. One JSON reply:
{"ok": true, "out": "..."} or {"ok": false, "error": "..."}. Never a traceback.
Not wired into anything yet: no init script, no callers.
"""
import grp
import ipaddress
import json
import os
import re
import socket
import tempfile
import threading
from datetime import datetime

ZONEINFO = "/usr/share/zoneinfo"
ETC_ROOT = "/"
LOG_PATH = "/run/llmos/rootd.log"
MAX_REQUEST = 2 * 1024 * 1024
MAX_SETTING = 256 * 1024
MAX_HOSTS = 1024 * 1024
CONN_TIMEOUT = 5.0
MAX_CONN = 16

# fullmatch, not match with $: "$" accepts a trailing newline.
ZONE_RE = re.compile(r"[A-Za-z_]+(?:/[A-Za-z0-9_+-]+){0,2}")
HOST_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
SETTING_NAMES = {"settings.json", "conduct.txt"}
# A hostname label or dotted name: letters, digits, inner dashes.
HOSTS_NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*")


def _etc(*parts):
    return os.path.join(ETC_ROOT, "etc", *parts)


def _plain_etc(what="settings folder"):
    """Return ETC_ROOT/etc, refusing it if it is a symlink or leads outside ETC_ROOT."""
    etc = _etc()
    if os.path.islink(etc):
        raise ValueError(f"bad args: {what} is not a plain folder")
    if os.path.realpath(etc) != os.path.join(os.path.realpath(ETC_ROOT), "etc"):
        raise ValueError(f"bad args: {what} is not a plain folder")
    return etc


def _llmos_dir():
    """Return ETC_ROOT/etc/llmos, refusing it if any part from etc down is a symlink or it leads outside ETC_ROOT."""
    _plain_etc()
    llmos = _etc("llmos")
    if os.path.islink(llmos):
        raise ValueError("bad args: settings folder is not a plain folder")
    if os.path.realpath(llmos) != os.path.join(os.path.realpath(ETC_ROOT), "etc", "llmos"):
        raise ValueError("bad args: settings folder is not a plain folder")
    return llmos


def _write_atomic(path, text, mode=None):
    """Write text to path through a temp file in the same directory, then os.replace."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _args_dict(args):
    if not isinstance(args, dict):
        raise ValueError("bad args: args must be an object")
    return args


def set_timezone(args):
    args = _args_dict(args)
    zone = args.get("zone")
    chosen = args.get("chosen", True)
    if not isinstance(zone, str) or not ZONE_RE.fullmatch(zone):
        raise ValueError("bad args: zone")
    if not isinstance(chosen, bool):
        raise ValueError("bad args: chosen")
    # Check the settings folder before anything is written.
    llmos = _llmos_dir()
    # Resolve symlinks first: the target must be a regular file inside ZONEINFO.
    real_zoneinfo = os.path.realpath(ZONEINFO)
    src = os.path.realpath(os.path.join(ZONEINFO, zone))
    try:
        inside = os.path.commonpath([real_zoneinfo, src]) == real_zoneinfo
    except ValueError:
        inside = False
    if not inside or not os.path.isfile(src):
        raise ValueError("bad args: unknown zone")
    # Same steps as system.set_timezone: symlink /etc/localtime, /etc/timezone, and /etc/llmos/timezone when the owner chose it.
    localtime = _etc("localtime")
    tmp = _etc("localtime.tmp")
    os.makedirs(os.path.dirname(localtime), exist_ok=True)
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(src, tmp)
    os.replace(tmp, localtime)
    with open(_etc("timezone"), "w") as f:
        f.write(zone + "\n")
    if chosen:
        os.makedirs(llmos, exist_ok=True)
        with open(os.path.join(llmos, "timezone"), "w") as f:
            f.write(zone + "\n")
    return "ok"


def set_hostname(args):
    args = _args_dict(args)
    name = args.get("name")
    if not isinstance(name, str) or not HOST_RE.fullmatch(name):
        raise ValueError("bad args: name")
    os.makedirs(_etc(), exist_ok=True)
    with open(_etc("hostname"), "w") as f:
        f.write(name + "\n")
    return "ok"


def write_setting_file(args):
    args = _args_dict(args)
    name = args.get("name")
    text = args.get("text")
    if not isinstance(name, str) or name not in SETTING_NAMES:
        raise ValueError("bad args: name")
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_SETTING:
        raise ValueError("bad args: text")
    _write_atomic(os.path.join(_llmos_dir(), name), text)
    return "ok"


def _check_hosts(text):
    """Raise ValueError unless text is a hosts file this service will write."""
    if not isinstance(text, str):
        raise ValueError("bad args: hosts must be text")
    if len(text.encode("utf-8")) > MAX_HOSTS:
        raise ValueError("bad args: hosts too large")
    keeps_localhost = False
    for n, line in enumerate(text.split("\n"), 1):
        bad = ValueError(f"bad args: hosts line {n}")
        if "\0" in line or "\r" in line:
            raise bad
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Trailing comments are allowed, e.g. "0.0.0.0 example.com # llmos focus mode".
        fields = line.split("#", 1)[0].split()
        if len(fields) < 2:
            raise bad
        ip, names = fields[0], fields[1:]
        if "%" in ip:
            raise bad
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            raise bad from None
        for name in names:
            if len(name) > 253 or not HOSTS_NAME_RE.fullmatch(name):
                raise bad
        if str(addr) == "127.0.0.1" and "localhost" in names:
            keeps_localhost = True
    if not keeps_localhost:
        raise ValueError("bad args: hosts must keep localhost")


def write_hosts(args):
    args = _args_dict(args)
    text = args.get("text")
    _check_hosts(text)
    etc = _plain_etc("etc folder")
    _write_atomic(os.path.join(etc, "hosts"), text, mode=0o644)
    return "ok"


def remove_setting_file(args):
    args = _args_dict(args)
    name = args.get("name")
    if not isinstance(name, str) or name not in SETTING_NAMES:
        raise ValueError("bad args: name")
    try:
        os.unlink(os.path.join(_llmos_dir(), name))
    except FileNotFoundError:
        pass
    return "ok"


def firewall_apply(args):
    args = _args_dict(args)
    internet = args.get("internet")
    if internet is not None and internet not in ("yes", "ask", "no"):
        raise ValueError("bad args: internet")
    from . import system
    ok, err = system._apply_firewall_root(internet)
    return json.dumps([ok, err])


def set_tor(args):
    args = _args_dict(args)
    on = args.get("on")
    if not isinstance(on, bool):
        raise ValueError("bad args: on")
    from . import system
    ok, note = system._set_tor_root(on)
    return json.dumps([ok, note])


APK_NAME_RE = re.compile(r"[a-z0-9][a-z0-9+._-]{0,99}")


def _apk_name(name):
    if not isinstance(name, str) or not APK_NAME_RE.fullmatch(name):
        raise ValueError("bad args: name")
    return name


def apk_add(args):
    args = _args_dict(args)
    names = args.get("names")
    quiet = args.get("quiet", False)
    if not isinstance(names, list) or not 1 <= len(names) <= 20:
        raise ValueError("bad args: names")
    names = [_apk_name(n) for n in names]
    if not isinstance(quiet, bool):
        raise ValueError("bad args: quiet")
    from . import system
    rc, out, err = system._apk_add_root(names, quiet=quiet)
    return json.dumps([rc, out[-20000:], err[-20000:]])


def apk_del(args):
    args = _args_dict(args)
    name = _apk_name(args.get("name"))
    force = args.get("force", False)
    if not isinstance(force, bool):
        raise ValueError("bad args: force")
    from . import system
    rc, out, err = system._apk_del_root(name, force=force)
    return json.dumps([rc, out[-20000:], err[-20000:]])


VERBS = {
    "apk_add": apk_add,
    "apk_del": apk_del,
    "set_timezone": set_timezone,
    "set_hostname": set_hostname,
    "write_setting_file": write_setting_file,
    "remove_setting_file": remove_setting_file,
    "write_hosts": write_hosts,
    "firewall_apply": firewall_apply,
    "set_tor": set_tor,
}


def _run(request_bytes):
    """Return (verb, reply dict). verb is the requested name as text, or '?' when unreadable."""
    verb = "?"
    try:
        if not isinstance(request_bytes, (bytes, bytearray)):
            return verb, {"ok": False, "error": "bad args: request must be bytes"}
        if len(request_bytes) > MAX_REQUEST:
            return verb, {"ok": False, "error": "bad args: request too large"}
        try:
            req = json.loads(bytes(request_bytes).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return verb, {"ok": False, "error": "bad args: request is not JSON"}
        if not isinstance(req, dict):
            return verb, {"ok": False, "error": "bad args: request must be an object"}
        name = req.get("verb")
        if isinstance(name, str):
            verb = name
        fn = VERBS.get(name) if isinstance(name, str) else None
        if fn is None:
            return verb, {"ok": False, "error": "unknown verb"}
        args = req.get("args", {})
        out = fn(args)
        return verb, {"ok": True, "out": out}
    except ValueError as e:
        return verb, {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - never leak a traceback to the caller
        return verb, {"ok": False, "error": f"failed: {type(e).__name__}"}


def handle(request_bytes):
    _, reply = _run(request_bytes)
    return json.dumps(reply).encode("utf-8")


_LOG_LOCK = threading.Lock()


def _log(verb, ok):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        line = f"{datetime.now().isoformat(timespec='seconds')} {verb} {'ok' if ok else 'error'}\n"
        with _LOG_LOCK:
            with open(LOG_PATH, "a") as f:
                f.write(line)
    except OSError:
        pass


def _read_request(conn):
    data = b""
    while len(data) <= MAX_REQUEST:
        chunk = conn.recv(65536)
        if not chunk:
            break
        data += chunk
    return data


def _reply(conn, reply):
    try:
        conn.sendall(json.dumps(reply).encode("utf-8"))
    except OSError:
        pass


def _handle_conn(conn, slots):
    """Serve one connection in its own thread. Releases its slot when done."""
    try:
        with conn:
            try:
                req = _read_request(conn)
                verb, reply = _run(req)
            except socket.timeout:
                _log("?", False)
                _reply(conn, {"ok": False, "error": "timeout"})
                return
            except OSError:
                return
            _reply(conn, reply)
            _log(verb, reply["ok"])
    finally:
        slots.release()


def serve(path="/run/llmos/root.sock", group="owner"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.lexists(path):
        os.unlink(path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    os.chmod(path, 0o660)
    try:
        gid = grp.getgrnam(group).gr_gid
        os.chown(path, -1, gid)
    except (KeyError, OSError):
        pass
    srv.listen(MAX_CONN)
    slots = threading.BoundedSemaphore(MAX_CONN)
    while True:
        conn, _ = srv.accept()
        conn.settimeout(CONN_TIMEOUT)
        if not slots.acquire(blocking=False):
            _reply(conn, {"ok": False, "error": "busy"})
            conn.close()
            continue
        try:
            threading.Thread(target=_handle_conn, args=(conn, slots), daemon=True).start()
        except RuntimeError:
            slots.release()
            conn.close()


if __name__ == "__main__":
    serve()
