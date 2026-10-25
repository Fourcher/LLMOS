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
import stat
import sys
import tempfile
import threading
from datetime import datetime

ZONEINFO = "/usr/share/zoneinfo"
PROC_MOUNTS = "/proc/mounts"
ETC_ROOT = "/"
SOCK_PATH = "/run/llmos-rootd/root.sock"
LOG_PATH = "/run/llmos-rootd/rootd.log"
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


def _unparsed_settings(path):
    """Return the exact bytes of an existing regular settings.json that is not a JSON object, else None.
    A symlink is never read or copied here: the write replaces the link as before."""
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        raw = f.read()
    try:
        if isinstance(json.loads(raw.decode("utf-8")), dict):
            return None
    except ValueError:
        pass
    return raw


def _keep_copy(d, raw):
    """Write raw to d as settings.json.broken-<YYYYmmdd-HHMMSS>, then -1, -2 ... on collision. Mode 0600.
    Created exclusively and without following symlinks. Returns the name used."""
    base = "settings.json.broken-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 0
    while True:
        name = base if n == 0 else f"{base}-{n}"
        try:
            fd = os.open(os.path.join(d, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            n += 1
            continue
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(raw)
        return name


def write_setting_file(args):
    args = _args_dict(args)
    name = args.get("name")
    text = args.get("text")
    if not isinstance(name, str) or name not in SETTING_NAMES:
        raise ValueError("bad args: name")
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_SETTING:
        raise ValueError("bad args: text")
    llmos = _llmos_dir()
    path = os.path.join(llmos, name)
    if name == "settings.json":
        raw = _unparsed_settings(path)
        if raw is not None:
            # Keep the owner's corrupt text before it is overwritten. If the copy fails, nothing is written.
            _keep_copy(llmos, raw)
    _write_atomic(path, text)
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
    firewall = args.get("firewall")
    if firewall is not None and firewall not in ("on", "off"):
        raise ValueError("bad args: firewall")
    from . import system
    ok, err = system._apply_firewall_root(internet, firewall=None if firewall is None else firewall != "off")
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
    if ".." in name or name.lower().endswith(".apk"):
        raise ValueError("bad args: name")
    return name


def _apk_timeout(args, default):
    t = args.get("timeout", default)
    if isinstance(t, bool) or not isinstance(t, int) or not 30 <= t <= 1800:
        raise ValueError("bad args: timeout")
    return t


def apk_add(args):
    args = _args_dict(args)
    names = args.get("names")
    quiet = args.get("quiet", False)
    if not isinstance(names, list) or not 1 <= len(names) <= 20:
        raise ValueError("bad args: names")
    names = [_apk_name(n) for n in names]
    if not isinstance(quiet, bool):
        raise ValueError("bad args: quiet")
    timeout = _apk_timeout(args, 900)
    from . import system
    rc, out, err = system._apk_add_root(names, quiet=quiet, timeout=timeout)
    return json.dumps([rc, out[-20000:], err[-20000:]])


def apk_del(args):
    args = _args_dict(args)
    name = _apk_name(args.get("name"))
    force = args.get("force", False)
    if not isinstance(force, bool):
        raise ValueError("bad args: force")
    timeout = _apk_timeout(args, 600)
    from . import system
    rc, out, err = system._apk_del_root(name, force=force, timeout=timeout)
    return json.dumps([rc, out[-20000:], err[-20000:]])


POWER_ACTIONS = ("poweroff", "reboot", "suspend")
SERVICE_NAMES = ("llmos-model", "llmos-ota")
SERVICE_ACTIONS = ("start", "stop", "restart")


def power(args):
    args = _args_dict(args)
    action = args.get("action")
    if not isinstance(action, str) or action not in POWER_ACTIONS:
        raise ValueError("bad args: action")
    from . import system
    ok, msg = system._power_root(action)
    return json.dumps([ok, msg])


def radio(args):
    args = _args_dict(args)
    kind = args.get("kind")
    on = args.get("on")
    if set(args) - {"kind", "on"}:
        raise ValueError("bad args: unexpected argument")
    if not isinstance(kind, str) or kind not in ("wifi", "bluetooth", "all"):
        raise ValueError("bad args: kind")
    if not isinstance(on, bool):
        raise ValueError("bad args: on")
    from . import system
    rc, out, err = system._radio_root(kind, on)
    return json.dumps([rc, out[-20000:], err[-20000:]])


# Drives (USB sticks): device nodes only. Mount points: one or two levels under /media or /run/media (udisks uses
# /run/media/<user>/<label>; the label level may hold spaces). Never a bare /media or /run/media, never . or .. segments.
MOUNT_DEV_RE = re.compile(r"/dev/(?:sd[a-z]{1,2}[0-9]{1,3}|nvme[0-9]n[0-9]p[0-9]{1,3}|mmcblk[0-9]p[0-9]{1,3})")
MEDIA_MP_RE = re.compile(r"/(?:run/)?media/[A-Za-z0-9_.-]{1,64}(?:/[A-Za-z0-9_. -]{1,64})?")
_PROC_ESCAPE_RE = re.compile(r"\\([0-7]{3})")


def media_mp_ok(mp):
    """True when mp is a drive folder under /media or /run/media (one or two levels, no . or .. segment)."""
    if not isinstance(mp, str) or MEDIA_MP_RE.fullmatch(mp) is None:
        return False
    return all(seg not in (".", "..") for seg in mp.split("/")[1:])


def _proc_unescape(text):
    """/proc/mounts writes space, tab, newline and backslash as \\040 \\011 \\012 \\134. Undo that."""
    return _PROC_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 8)), text)


def _mounts():
    """[(source, mountpoint)] from the kernel's mount table, with the octal escapes decoded."""
    out = []
    with open(PROC_MOUNTS, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                out.append((_proc_unescape(parts[0]), _proc_unescape(parts[1])))
    return out


def _same_dev(a, b):
    return a == b or os.path.realpath(a) == os.path.realpath(b)


# The whole disk a partition node belongs to: sda2 -> sda, nvme0n1p3 -> nvme0n1, mmcblk0p2 -> mmcblk0.
_PART_TO_DISK_RES = (
    re.compile(r"(/dev/sd[a-z]{1,2})[0-9]{1,3}"),
    re.compile(r"(/dev/nvme[0-9]n[0-9]+)p[0-9]{1,3}"),
    re.compile(r"(/dev/mmcblk[0-9]+)p[0-9]{1,3}"),
)


def _whole_disk(dev):
    """The whole disk of a partition device node, or None when dev is not a partition node we know."""
    for rx in _PART_TO_DISK_RES:
        m = rx.fullmatch(dev)
        if m:
            return m.group(1)
    return None


def _on_system_disk(mounts, src):
    """True when src is on the same whole disk as the root filesystem (the "/" entry in the mount table).
    When the root source has no comparable disk (/dev/root, overlay), this is False: nothing is refused."""
    disk = _whole_disk(src)
    return disk is not None and any(m == "/" and _whole_disk(s) == disk for s, m in mounts)


def mount_dev(args):
    args = _args_dict(args)
    if set(args) - {"dev"}:
        raise ValueError("bad args: unexpected argument")
    dev = args.get("dev")
    if not isinstance(dev, str) or MOUNT_DEV_RE.fullmatch(dev) is None:
        raise ValueError("bad args: dev")
    try:
        mode = os.stat(dev).st_mode
    except OSError:
        raise ValueError("bad args: dev is not a block device")
    if not stat.S_ISBLK(mode):
        raise ValueError("bad args: dev is not a block device")
    mounts = _mounts()
    mp = "/media/" + os.path.basename(dev)
    if any(m == "/" and _same_dev(src, dev) for src, m in mounts) or _on_system_disk(mounts, dev):
        raise ValueError("bad args: dev is the system disk")
    if any(_same_dev(src, dev) for src, _ in mounts):
        raise ValueError("bad args: dev is already mounted")
    if any(m == mp for _, m in mounts):
        raise ValueError("bad args: mountpoint is in use")
    from . import system
    rc, out, err = system._mount_root(dev, mp)
    return json.dumps([rc, out[-20000:], err[-20000:]])


def umount_mp(args):
    args = _args_dict(args)
    if set(args) - {"mountpoint"}:
        raise ValueError("bad args: unexpected argument")
    mp = args.get("mountpoint")
    if not media_mp_ok(mp):
        raise ValueError("bad args: mountpoint")
    mounts = _mounts()
    sources = [src for src, m in mounts if m == mp]
    if not sources:
        raise ValueError("bad args: mountpoint is not mounted")
    if any(MOUNT_DEV_RE.fullmatch(src) is None for src in sources):
        raise ValueError("bad args: mountpoint is not a drive")
    if any(_on_system_disk(mounts, src) for src in sources):
        raise ValueError("bad args: system disk")
    from . import system
    rc, out, err = system._umount_root(mp)
    return json.dumps([rc, out[-20000:], err[-20000:]])


# Erasing a drive: a WHOLE disk only (sdb, nvme0n1, mmcblk0), never a partition, and only media that sysfs calls
# removable or that sits on USB. The label is what mkfs.exfat gets, so it is limited to the same plain characters.
SYS_BLOCK = "/sys/block"
FORMAT_DISK_RE = re.compile(r"/dev/(?:sd[a-z]{1,2}|nvme[0-9]n[0-9]|mmcblk[0-9])")
FORMAT_LABEL_RE = re.compile(r"[A-Za-z0-9 _-]{1,11}")


def _is_system_disk(mounts, disk):
    """True when the root filesystem ("/") is on this whole disk, or on one of its partitions."""
    return any(m == "/" and (s == disk or _whole_disk(s) == disk) for s, m in mounts)


def _removable_disk(disk):
    """True when sysfs marks the whole disk removable, or its device path runs through USB."""
    base = os.path.join(SYS_BLOCK, os.path.basename(disk))
    try:
        with open(os.path.join(base, "removable"), encoding="utf-8") as f:
            if f.read().strip() == "1":
                return True
    except OSError:
        pass
    return "/usb" in os.path.realpath(base)


def format_drive(args):
    args = _args_dict(args)
    if set(args) != {"disk", "label"}:
        raise ValueError("bad args: disk and label only")
    disk = args.get("disk")
    label = args.get("label")
    if not isinstance(disk, str) or FORMAT_DISK_RE.fullmatch(disk) is None:
        raise ValueError("bad args: disk")
    if not isinstance(label, str) or FORMAT_LABEL_RE.fullmatch(label) is None:
        raise ValueError("bad args: label")
    try:
        mode = os.stat(disk).st_mode
    except OSError:
        raise ValueError("bad args: disk is not a block device")
    if not stat.S_ISBLK(mode):
        raise ValueError("bad args: disk is not a block device")
    if _is_system_disk(_mounts(), disk):
        raise ValueError("bad args: disk is the system disk")
    if not _removable_disk(disk):
        raise ValueError("bad args: disk is not a USB stick or drive")
    from . import system
    rc, out, err = system._format_root(disk, label)
    return json.dumps([rc, out[-20000:], err[-20000:]])


# Printer queue names (lpadmin's -p NAME) and CUPS device addresses. A name never starts with "-" (lpadmin would
# read it as an option), and a URI must start with a CUPS scheme and contain no whitespace.
PRINTER_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}")
PRINTER_URI_RE = re.compile(r"(ipp|ipps|http|https|socket|lpd|dnssd)://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{1,500}")


def _printer_name(args):
    name = args.get("name")
    if not isinstance(name, str) or not PRINTER_NAME_RE.fullmatch(name):
        raise ValueError("bad args: name")
    return name


def _printer_uri(args):
    uri = args.get("uri")
    if not isinstance(uri, str) or uri.startswith("-") or not PRINTER_URI_RE.fullmatch(uri):
        raise ValueError("bad args: uri")
    return uri


def printer_add(args):
    args = _args_dict(args)
    if set(args) - {"name", "uri"}:
        raise ValueError("bad args: unexpected argument")
    name = _printer_name(args)
    uri = _printer_uri(args)
    from . import system
    rc, out, err = system._printer_add_root(name, uri)
    return json.dumps([rc, out[-20000:], err[-20000:]])


def printer_default(args):
    args = _args_dict(args)
    if set(args) - {"name", "timeout"}:
        raise ValueError("bad args: unexpected argument")
    name = _printer_name(args)
    timeout = args.get("timeout", 20)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 120:
        raise ValueError("bad args: timeout")
    from . import system
    rc, out, err = system._printer_default_root(name, timeout)
    return json.dumps([rc, out[-20000:], err[-20000:]])


def service(args):
    args = _args_dict(args)
    name = args.get("name")
    action = args.get("action")
    if not isinstance(name, str) or name not in SERVICE_NAMES:
        raise ValueError("bad args: name")
    if not isinstance(action, str) or action not in SERVICE_ACTIONS:
        raise ValueError("bad args: action")
    timeout = args.get("timeout", 60)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 300:
        raise ValueError("bad args: timeout")
    from . import system
    rc, out, err = system._service_root(name, action, timeout=timeout)
    return json.dumps([rc, out[-20000:], err[-20000:]])


BACKLIGHT_DEV_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


def set_backlight(args):
    args = _args_dict(args)
    device = args.get("device")
    value = args.get("value")
    if not isinstance(device, str) or not BACKLIGHT_DEV_RE.fullmatch(device) or device in (".", ".."):
        raise ValueError("bad args: device")
    from . import devices
    try:
        names = os.listdir(devices.BACKLIGHT_DIR)
    except OSError:
        names = []
    if device not in names:
        raise ValueError("bad args: device")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("bad args: value")
    with open(os.path.join(devices.BACKLIGHT_DIR, device, "max_brightness")) as f:
        mx = int(f.read())
    if not 0 <= value <= mx:
        raise ValueError("bad args: value")
    devices._write_backlight_root(device, value)
    return "ok"


def _no_args(args):
    args = _args_dict(args)
    if args:
        raise ValueError("bad args: this verb takes no arguments")


def sync_time(args):
    _no_args(args)
    from . import config
    # The owner's "no" holds even when a non-root process calls this verb directly.
    if config.settings.get("internet", "yes") == "no":
        return json.dumps(False)
    from . import system
    return json.dumps(system._sync_time_root())


def apk_update(args):
    _no_args(args)
    from . import system
    rc, out, err = system._apk_update_root()
    return json.dumps([rc, out[-20000:], err[-20000:]])


def apk_upgrade(args):
    args = _args_dict(args)
    if set(args) != {"simulate"} or not isinstance(args["simulate"], bool):
        raise ValueError("bad args: simulate")
    from . import system
    rc, out, err = system._apk_upgrade_root(simulate=args["simulate"])
    return json.dumps([rc, out[-20000:], err[-20000:]])


def clear_apk_cache(args):
    _no_args(args)
    from . import system
    freed, msg = system._clear_apk_cache_root()
    return json.dumps([freed, msg])


SHELL_CHOICES = ("/bin/sh", "/bin/ash", "/bin/bash", "/bin/zsh", "/bin/fish", "/usr/bin/zsh", "/usr/bin/fish")


def _is_shell_file(path):
    """True when path is an existing executable file (a symlink such as /bin/sh -> busybox counts)."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def run_shell(args):
    """Run one shell command as root and return [kind, rc, output]. The command is the caller's, unchanged.
    Output keeps its head and its tail so a login URL printed first is still there. No environment is
    taken from the caller."""
    args = _args_dict(args)
    if set(args) - {"command", "cwd", "timeout"} or "command" not in args:
        raise ValueError("bad args")
    cmd = args.get("command")
    if not isinstance(cmd, str) or "\x00" in cmd or "\n" in cmd:
        raise ValueError("bad args: command")
    cmd = cmd.strip()
    if not cmd or len(cmd) > 8000:
        raise ValueError("bad args: command")
    cwd = args.get("cwd", "/")
    if not isinstance(cwd, str) or "\x00" in cwd or "\n" in cwd or not cwd.startswith("/"):
        raise ValueError("bad args: cwd")
    if not os.path.isdir(cwd):
        cwd = "/"
    timeout = args.get("timeout", 600)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ValueError("bad args: timeout")
    from . import system
    kind, rc, out, _proc = system._run_shell_stream(
        cmd, cwd=cwd, env=system._root_shell_env(), timeout=timeout)
    out = out or ""
    if len(out) > 20000:
        out = out[:10000] + "\n…\n" + out[-10000:]
    return json.dumps([kind, rc, out])


def set_shell(args):
    """Change a login shell. Only root's line: the owner account's name is not recorded anywhere yet.
    The shell must be one of SHELL_CHOICES and installed; PASSWD and SHELLS must be plain files."""
    args = _args_dict(args)
    user = args.get("user")
    shell = args.get("shell")
    if not isinstance(user, str) or user != "root":
        raise ValueError("bad args: user")
    if not isinstance(shell, str) or shell not in SHELL_CHOICES:
        raise ValueError("bad args: shell")
    if not _is_shell_file(shell):
        raise ValueError("bad args: shell is not installed")
    from . import system
    for p in (system.PASSWD, system.SHELLS):
        if os.path.islink(p):
            raise ValueError("bad args: account file is not a plain file")
    system._set_shell_root(user, shell)
    return "ok"


VERBS = {
    "apk_add": apk_add,
    "apk_del": apk_del,
    "power": power,
    "radio": radio,
    "mount_dev": mount_dev,
    "umount_mp": umount_mp,
    "format_drive": format_drive,
    "printer_add": printer_add,
    "printer_default": printer_default,
    "service": service,
    "set_timezone": set_timezone,
    "set_hostname": set_hostname,
    "write_setting_file": write_setting_file,
    "remove_setting_file": remove_setting_file,
    "write_hosts": write_hosts,
    "firewall_apply": firewall_apply,
    "set_tor": set_tor,
    "set_shell": set_shell,
    "set_backlight": set_backlight,
    "apk_update": apk_update,
    "apk_upgrade": apk_upgrade,
    "clear_apk_cache": clear_apk_cache,
    "sync_time": sync_time,
    "run_shell": run_shell,
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


def _prepare_dir(d, gid):
    """Make the socket's directory. Refuse a symlink (or non-directory). Owner root:owner 0750 when the group
    exists (gid given); otherwise root-only 0700. A wrong owner is fixed; if that fails as root, refuse."""
    try:
        st = os.lstat(d)
    except FileNotFoundError:
        os.mkdir(d, 0o700)
        st = os.lstat(d)
    if not stat.S_ISDIR(st.st_mode):
        print(f"rootd: {d} is a symlink or not a directory; refusing to start", file=sys.stderr)
        sys.exit(1)
    try:
        os.chown(d, 0, gid if gid is not None else 0)
    except OSError:
        if os.geteuid() == 0:
            print(f"rootd: cannot set the owner of {d}; refusing to start", file=sys.stderr)
            sys.exit(1)
    os.chmod(d, 0o750 if gid is not None else 0o700)


def serve(path=SOCK_PATH, group="owner"):
    try:
        gid = grp.getgrnam(group).gr_gid
    except KeyError:
        gid = None
    _prepare_dir(os.path.dirname(path), gid)
    if os.path.lexists(path):
        os.unlink(path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    os.chmod(path, 0o660)
    if gid is None:
        # no owner group yet: keep the socket root-only rather than world-writable-by-group
        os.chmod(path, 0o600)
        print(f"rootd: group '{group}' missing; socket is root-only", file=sys.stderr)
    else:
        try:
            os.chown(path, -1, gid)
        except OSError:
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
