"""System policies that are enforced by the OS, not just promised by the
agent: the firewall (internet on/off), Tor routing, and focus mode."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata

from . import config, rootd, rootd_client
from .rootd import HOSTS_NAME_RE, PRINTER_NAME_RE, PRINTER_URI_RE

NFT_RULES = "/etc/nftables.nft"
HOSTS = "/etc/hosts"
PASSWD = "/etc/passwd"
SHELLS = "/etc/shells"
FOCUS_BEGIN = "# llmos-focus begin"
FOCUS_END = "# llmos-focus end"
DISTRACTIONS = [
    "facebook.com", "www.facebook.com", "m.facebook.com", "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com", "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    "reddit.com", "www.reddit.com", "old.reddit.com", "snapchat.com", "www.snapchat.com",
    "threads.net", "www.threads.net", "pinterest.com", "www.pinterest.com",
    "tumblr.com", "www.tumblr.com", "9gag.com", "twitch.tv", "www.twitch.tv",
    "bsky.app", "linkedin.com", "www.linkedin.com",
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "shorts.youtube.com",
]


FWCFG = "/sys/firmware/qemu_fw_cfg/by_name/opt/llmos"


def launcher_says(key):
    """Did the VM launcher (dist/run-llmos.sh, through QEMU's fw_cfg) provide this service? On real hardware
    or in any other VM nothing is provided, so nothing at the launcher's address is trusted or reachable."""
    return os.path.exists(os.path.join(FWCFG, key, "raw"))


def launcher_value(key):
    """The value the VM launcher passed for a key (fw_cfg), or ""."""
    try:
        with open(os.path.join(FWCFG, key, "raw")) as f:
            return re.sub(r"[^A-Za-z0-9._:/+-]", "", f.read())[:128]
    except OSError:
        return ""


def _host_ports():
    """Ports of the VM launcher's services on the host machine that this boot was actually given: the model
    server (host-GPU mode, whatever port the launcher found free) and the mic bridge."""
    ports = set()
    try:
        m = re.search(r"^http://10\.0\.2\.2:(\d+)", config.llama_url())
        if m:
            ports.add(int(m.group(1)))
    except Exception:
        pass
    if launcher_says("mic"):
        ports.add(8766)
    return ", ".join(str(p) for p in sorted(ports))


def _tor_uid():
    try:
        import pwd
        return pwd.getpwnam("tor").pw_uid
    except (KeyError, ImportError):
        return None


def firewall_rules(internet, tor=False, firewall=True):
    """Inbound: nothing (this machine offers no services). With the owner's firewall switched off, inbound is
    open (policy accept, no rules); outbound is unchanged either way. Outbound: allowed unless the owner said no
    internet, in which case only loopback and DHCP -- and connections opened before the switch are cut too,
    not left running. With Tor on, only the Tor daemon itself may reach the network: everything else must go
    through it (127.0.0.1:9050), so a program that does not use it fails instead of leaking (fail closed)."""
    tor_uid = _tor_uid() if tor and internet != "no" else None
    out_policy = "drop" if internet == "no" or tor_uid is not None else "accept"
    host_ports = _host_ports()
    launcher = (f"""    # the VM launcher's services on the host machine (model server, mic bridge), only when this boot
    # was given them: part of this computer, so allowed even with internet off
    ip daddr 10.0.2.2 tcp dport {{ {host_ports} }} accept
""" if host_ports else "")
    established = "" if internet == "no" or tor_uid is not None else "    ct state established,related accept\n"
    try:
        from . import share
        shared = share.current()
    except Exception:
        shared = None
    # a folder the owner shared ("share this folder with my other computer"): its one port, from the local network only
    sharing = (f"    ip saddr {{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 }} tcp dport {int(shared['port'])} accept\n"
               if shared else "")
    # its answers go back even with the internet off (to local addresses, from that port only)
    share_out = (f"    ip daddr {{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 }} tcp sport {int(shared['port'])} accept\n" if shared else "")
    via_tor = f"    meta skuid {tor_uid} accept\n" if tor_uid is not None else ""
    # a test computer with remote testing on: the owner's own computer may log in (SSH, key only) and ping it, from the
    # local network only (devaccess.py); nothing of this on any other machine
    devssh = ("    ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } tcp dport 22 accept\n"
              "    ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } icmp type echo-request accept\n"
              if config.settings.get("devlink") and config.settings.get("devssh_key") else "")
    if firewall:
        in_policy = "drop"
        inbound = f"""    iif lo accept
    ct state established,related accept
    ip protocol icmp icmp type {{ echo-reply, destination-unreachable, time-exceeded }} accept
    ip6 nexthdr icmpv6 accept
    udp sport 67 udp dport 68 accept
    # printers and other devices announce themselves on the local network (mDNS): answers from local addresses only
    ip saddr {{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 }} udp dport 5353 accept
    ip6 saddr fe80::/10 udp dport 5353 accept
{sharing}{devssh}"""
    else:
        # the owner switched the firewall off: inbound is open; the output chain below is the same either way
        in_policy = "accept"
        inbound = ""
    try:
        from . import ota
        ota_out = ota.firewall_rule()      # the owner's paired update server: its one address and port, even offline
    except Exception:
        ota_out = ""
    return f"""#!/usr/sbin/nft -f
# generated by LLM OS -- edit through settings, not by hand
flush ruleset
table inet llmos {{
  chain input {{
    type filter hook input priority 0; policy {in_policy};
{inbound}  }}
  chain forward {{
    type filter hook forward priority 0; policy drop;
  }}
  chain output {{
    type filter hook output priority 0; policy {out_policy};
    oif lo accept
{established}{via_tor}{share_out}{ota_out}    udp sport 68 udp dport 67 accept
{launcher}  }}
}}
"""


def _apply_firewall_root(internet=None, firewall=None):
    internet = internet or config.settings.get("internet", "yes")
    if firewall is None:
        firewall = config.settings.get("firewall", "on") != "off"
    os.makedirs(os.path.dirname(NFT_RULES), exist_ok=True)
    with open(NFT_RULES, "w") as f:
        f.write(firewall_rules(internet, bool(config.settings.get("tor")), firewall=firewall))
    p = subprocess.run(["nft", "-f", NFT_RULES], capture_output=True, text=True)
    return p.returncode == 0, p.stderr.strip()


def apply_firewall(internet=None):
    """Apply the firewall: directly as root, else through rootd's firewall_apply verb."""
    if os.geteuid() == 0:
        return _apply_firewall_root(internet)
    try:
        ok, err = json.loads(rootd_client.call("firewall_apply", internet=internet))
        return ok, err
    except rootd_client.RootdError as e:
        return False, str(e)


def _set_tor_root(on):
    if on:
        subprocess.run(["rc-update", "add", "tor", "default"], capture_output=True)
        p = subprocess.run(["rc-service", "tor", "start"], capture_output=True, text=True)
        if p.returncode != 0:
            return False, p.stderr.strip()[:200]
        # wait for Tor to finish bootstrapping (up to ~60 s)
        for _ in range(60):
            p = subprocess.run(["curl", "-s", "--max-time", "5", "--socks5-hostname",
                                "127.0.0.1:9050", "https://check.torproject.org/api/ip"],
                               capture_output=True, text=True)
            if '"IsTor":true' in p.stdout.replace(" ", ""):
                config.settings.set("tor", True)
                _apply_firewall_root()
                return True, ""
            time.sleep(1)
        config.settings.set("tor", True)
        _apply_firewall_root()
        return True, "Tor is still connecting; requests will work once it is ready."
    config.settings.set("tor", False)
    _apply_firewall_root()
    subprocess.run(["rc-service", "tor", "stop"], capture_output=True)
    subprocess.run(["rc-update", "del", "tor", "default"], capture_output=True)
    return True, ""


def set_tor(on):
    """Turn Tor on or off: directly as root, else through rootd's set_tor verb."""
    if os.geteuid() == 0:
        return _set_tor_root(on)
    try:
        ok, note = json.loads(rootd_client.call("set_tor", _timeout=120, on=on))
        return ok, note
    except rootd_client.RootdError as e:
        return False, str(e)


def _replace_keep_owner(path, text):
    """Replace path with text: a temp file in the same folder, then os.replace. The mode and owner of the original are kept."""
    st = os.stat(path)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix="." + os.path.basename(path) + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, st.st_mode & 0o7777)
        os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


SHELL_USER_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
SHELL_PATH_RE = re.compile(r"/[A-Za-z0-9_./+-]{1,100}")


def check_shell_change(user, shell):
    """Shared input check for a login-shell change (rootd's set_shell verb and _set_shell_root). Raises ValueError.
    fullmatch, not match with $: "$" accepts a trailing newline. The executable test is rootd._is_shell_file."""
    if not isinstance(user, str) or not SHELL_USER_RE.fullmatch(user):
        raise ValueError("bad user")
    if not isinstance(shell, str) or not SHELL_PATH_RE.fullmatch(shell) or ".." in shell.split("/"):
        raise ValueError("bad shell")
    if not rootd._is_shell_file(shell):
        raise ValueError("bad shell")


def _set_shell_root(user, shell):
    """As root: point the user's line in PASSWD at shell, and add shell to SHELLS once. PASSWD is written first.
    Checks everything before writing: a bad input, or a user with no line in PASSWD, raises ValueError and writes nothing."""
    check_shell_change(user, shell)
    for p in (PASSWD, SHELLS):
        if os.path.islink(p):
            raise ValueError("refusing a linked file")
    pw = open(PASSWD).read()
    pw, n = re.subn(r"^(" + re.escape(user) + r":[^:]*:0:0:[^:]*:[^:]*:)[^\n]*$", lambda mm: mm.group(1) + shell, pw, count=1, flags=re.M)
    if n != 1:
        raise ValueError("no such user")
    shells = open(SHELLS).read()
    _replace_keep_owner(PASSWD, pw)
    if shell not in [line.strip() for line in shells.splitlines()]:
        if shells and not shells.endswith("\n"):
            shells += "\n"
        _replace_keep_owner(SHELLS, shells + shell + "\n")


def set_shell(user, shell):
    """Change a user's login shell: directly as root, else through rootd's set_shell verb. Raises OSError on failure."""
    if user == "root":
        return _set_shell_root(user, shell)
    try:
        reply = rootd_client.call("set_shell", user=user, shell=shell)
    except rootd_client.RootdError as e:
        raise OSError(str(e))
    if reply != "ok":
        raise OSError(str(reply))


def _apk_add_root(names, quiet=False, timeout=900):
    """Install packages with apk, as root. Returns (returncode, stdout, stderr)."""
    argv = ["apk", "add", "-q", *names] if quiet else ["apk", "add", "--no-progress", *names]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout} s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def _apk_del_root(name, force=False, timeout=600):
    """Remove one package with apk, as root. Returns (returncode, stdout, stderr)."""
    argv = ["apk", "del", "--no-progress"] + (["--force-broken-world"] if force else []) + [name]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout} s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def apk_add(names, quiet=False, timeout=900):
    """Install packages: directly as root, else through rootd's apk_add verb. Returns (returncode, stdout, stderr)."""
    if os.geteuid() == 0:
        return _apk_add_root(list(names), quiet=bool(quiet), timeout=timeout)
    try:
        rc, out, err = json.loads(rootd_client.call("apk_add", names=list(names), quiet=bool(quiet),
                                                    timeout=timeout, _timeout=timeout + 60))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def apk_del(name, force=False, timeout=600):
    """Remove a package: directly as root, else through rootd's apk_del verb. Returns (returncode, stdout, stderr)."""
    if os.geteuid() == 0:
        return _apk_del_root(name, force=bool(force), timeout=timeout)
    try:
        rc, out, err = json.loads(rootd_client.call("apk_del", name=name, force=bool(force),
                                                    timeout=timeout, _timeout=timeout + 60))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


APK_CACHE = "/var/cache/apk"


def _apk_run_root(argv, timeout):
    """Run an apk command as root. Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout} s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def _apk_update_root():
    """Refresh the package index with apk (120 s), as root. Returns (returncode, stdout, stderr)."""
    return _apk_run_root(["apk", "update"], 120)


def _apk_upgrade_root(simulate=False):
    """Upgrade with apk, as root: simulate=True only lists the changes (120 s); otherwise installs (1800 s)."""
    if simulate:
        return _apk_run_root(["apk", "upgrade", "--simulate"], 120)
    return _apk_run_root(["apk", "upgrade", "--no-interactive"], 1800)


def _tree_size(path):
    """Bytes of files under path. Symlinks are counted as links (their own size), never followed."""
    total = 0
    for d, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(d, f)).st_size
            except OSError:
                pass
        for f in dirs:  # a symlink to a directory is listed in dirs: count the link, do not walk it
            p = os.path.join(d, f)
            if os.path.islink(p):
                try:
                    total += os.lstat(p).st_size
                except OSError:
                    pass
    return total


def _clear_apk_cache_root():
    """Delete the entries directly inside APK_CACHE (the apk cache that the Storage panel clears), as root.
    Returns (freed_bytes, msg). A symlink is unlinked, never followed, so its target is untouched; real
    directories are removed with shutil.rmtree, which does not follow symlinks inside them."""
    if os.path.islink(APK_CACHE) or not os.path.isdir(APK_CACHE):
        return 0, "cleared 0 bytes of apk cache"
    freed = 0
    for n in os.listdir(APK_CACHE):
        p = os.path.join(APK_CACHE, n)
        try:
            real_dir = os.path.isdir(p) and not os.path.islink(p)
            size = _tree_size(p) if real_dir else os.lstat(p).st_size
            shutil.rmtree(p) if real_dir else os.unlink(p)
            freed += size
        except OSError:
            pass
    return freed, f"cleared {freed} bytes of apk cache"


def apk_update():
    """Refresh the package index: directly as root, else through rootd's apk_update verb. Returns (rc, out, err)."""
    if os.geteuid() == 0:
        return _apk_update_root()
    try:
        rc, out, err = json.loads(rootd_client.call("apk_update", _timeout=120 + 60))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def apk_upgrade(simulate=False):
    """Upgrade (or simulate the upgrade): directly as root, else through rootd's apk_upgrade verb. Returns (rc, out, err)."""
    simulate = bool(simulate)
    if os.geteuid() == 0:
        return _apk_upgrade_root(simulate=simulate)
    try:
        rc, out, err = json.loads(rootd_client.call("apk_upgrade", simulate=simulate,
                                                    _timeout=(120 if simulate else 1800) + 60))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def clear_apk_cache():
    """Clear the apk cache: directly as root, else through rootd's clear_apk_cache verb. Returns (freed_bytes, msg)."""
    if os.geteuid() == 0:
        return _clear_apk_cache_root()
    try:
        freed, msg = json.loads(rootd_client.call("clear_apk_cache"))
        return freed, msg
    except rootd_client.RootdError as e:
        return 0, str(e)


POWER_ACTIONS = ("poweroff", "reboot", "suspend")


def _power_root(action):
    """Power off, reboot, or suspend, as root. Returns (ok, msg). Never builds a shell string from input."""
    try:
        if action == "poweroff":
            rc = os.system("poweroff")
            return rc == 0, "" if rc == 0 else f"exit {rc}"
        if action == "reboot":
            rc = os.system("reboot")
            return rc == 0, "" if rc == 0 else f"exit {rc}"
        if action == "suspend":
            try:
                subprocess.run(["sync"], timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass  # a failed or slow sync must not block the suspend, as before
            try:
                with open("/sys/power/state", "w") as f:
                    f.write("mem")
            except OSError as e:
                return False, str(e)
            return True, ""
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return False, "unknown action"


def power(action):
    """Power off, reboot, or suspend: directly as root, else through rootd's power verb. Returns (ok, msg)."""
    if action not in POWER_ACTIONS:
        raise ValueError(f"unknown power action '{action}'")
    if os.geteuid() == 0:
        return _power_root(action)
    try:
        ok, msg = json.loads(rootd_client.call("power", action=action, _timeout=60))
        return ok, msg
    except rootd_client.RootdError as e:
        return False, str(e)


RADIO_KINDS = ("wifi", "bluetooth", "all")


def _radio_root(kind, on):
    """Block or unblock a radio with rfkill, as root. Returns (returncode, stdout, stderr). Never builds a shell string."""
    try:
        p = subprocess.run(["rfkill", "unblock" if on else "block", kind], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after 10 s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def radio(kind, on):
    """Turn a radio on or off (rfkill): directly as root, else through rootd's radio verb. Returns (rc, out, err)."""
    if kind not in RADIO_KINDS:
        raise ValueError(f"unknown radio kind '{kind}'")
    if not isinstance(on, bool):
        raise ValueError("on must be a bool")
    if os.geteuid() == 0:
        return _radio_root(kind, on)
    try:
        rc, out, err = json.loads(rootd_client.call("radio", kind=kind, on=on, _timeout=40))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def _mount_root(dev, mountpoint):
    """Mount a drive partition at mountpoint, as root (never a shell). Makes the folder if missing.
    Returns (returncode, stdout, stderr)."""
    try:
        os.makedirs(mountpoint, exist_ok=True)
        p = subprocess.run(["mount", dev, mountpoint], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after 30 s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def _umount_root(mountpoint):
    """Unmount one mount point, as root (never a shell). Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(["umount", mountpoint], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after 30 s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def mount_dev(dev):
    """Mount a drive partition under /media/<name> through rootd's mount_dev verb (root runs the same checks in-process).
    Returns (rc, out, err). A refused request gives (1, "", "") so the caller says it could not open the drive."""
    if not isinstance(dev, str) or rootd.MOUNT_DEV_RE.fullmatch(dev) is None:
        raise ValueError("bad drive name")
    try:
        rc, out, err = json.loads(rootd_client.call("mount_dev", dev=dev, _timeout=40))
        return rc, out, err
    except rootd_client.RootdError:
        return 1, "", ""


def umount_mp(mountpoint):
    """Unmount a /media/<name> mount point through rootd's umount_mp verb (root runs the same checks in-process).
    Returns (rc, out, err). A mount point outside /media/<name> is refused as (1, "", ...)."""
    if not rootd.media_mp_ok(mountpoint):
        return 1, "", "not a drive folder under /media"
    try:
        rc, out, err = json.loads(rootd_client.call("umount_mp", mountpoint=mountpoint, _timeout=40))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


FORMAT_PARTITION_SCRIPT = "label: dos\n,,7\n"


def _run_step(argv, timeout, input_text=None):
    """One step of a drive format, as a plain argv list (never a shell). Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=input_text)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout} s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def _format_root(disk, label):
    """Erase a whole USB disk and make one exFAT partition on it, as root. The steps run in order and stop at the
    first failure. Returns (returncode, stdout, stderr), or (0, "", "") when the drive is ready."""
    mkfs = shutil.which("mkfs.exfat") or shutil.which("mkexfatfs")
    if not mkfs:
        return 127, "", "the formatting program is missing"
    for src, mp in rootd._mounts():
        if mp != "/" and rootd._whole_disk(src) == disk:
            rc, out, err = _run_step(["umount", mp], 60)
            if rc:
                return rc, out, err
    rc, out, err = _run_step(["wipefs", "-a", disk], 60)
    if rc:
        return rc, out, err
    rc, out, err = _run_step(["sfdisk", "-q", disk], 60, input_text=FORMAT_PARTITION_SCRIPT)
    if rc:
        return rc, out, err
    part = disk + ("p1" if re.search(r"\d$", disk) else "1")
    time.sleep(1.5)
    rc, out, err = _run_step([mkfs, "-L" if "mkfs" in mkfs else "-n", label, part], 600)
    if rc:
        return rc, out, err
    return 0, "", ""


def format_drive(disk, label):
    """Erase a USB drive through rootd's format_drive verb (root runs the same checks in-process).
    Returns (rc, out, err). A refused request gives (1, "", message)."""
    try:
        rc, out, err = json.loads(rootd_client.call("format_drive", disk=disk, label=label, _timeout=900))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def _printer_name_ok(name):
    return isinstance(name, str) and PRINTER_NAME_RE.fullmatch(name) is not None


def _printer_uri_ok(uri):
    return isinstance(uri, str) and not uri.startswith("-") and PRINTER_URI_RE.fullmatch(uri) is not None


def _lp_root(argv, timeout):
    """Run one CUPS command as root (never a shell). Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", "it took too long to answer"
    except OSError:
        return 1, "", "this system doesn't have " + argv[0] + " installed"
    except subprocess.SubprocessError as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def _printer_add_root(name, uri):
    """Add a printer queue with lpadmin, as root. Returns (returncode, stdout, stderr)."""
    return _lp_root(["lpadmin", "-p", name, "-E", "-v", uri, "-m", "everywhere"], 60)


def _printer_default_root(name, timeout):
    """Make a printer the default with lpadmin, as root. Returns (returncode, stdout, stderr)."""
    return _lp_root(["lpadmin", "-d", name], timeout)


def printer_add(name, uri):
    """Add a printer: directly as root, else through rootd's printer_add verb. Returns (rc, out, err)."""
    if not _printer_name_ok(name) or not _printer_uri_ok(uri):
        return 1, "", "bad args: printer name or address"
    if os.geteuid() == 0:
        return _printer_add_root(name, uri)
    try:
        rc, out, err = json.loads(rootd_client.call("printer_add", name=name, uri=uri, _timeout=120))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def printer_default(name, timeout=20):
    """Make a printer the default: directly as root, else through rootd's printer_default verb. Returns (rc, out, err)."""
    if not _printer_name_ok(name) or isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 120:
        return 1, "", "bad args: printer name or timeout"
    if os.geteuid() == 0:
        return _printer_default_root(name, timeout)
    try:
        rc, out, err = json.loads(rootd_client.call("printer_default", name=name, timeout=timeout, _timeout=timeout + 30))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def _service_root(name, action, timeout=60):
    """Run rc-service for one service, as root. Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(["rc-service", name, action], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout} s"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return p.returncode, p.stdout, p.stderr


def service(name, action, timeout=60):
    """Start, stop, or restart a service: directly as root, else through rootd's service verb. Returns (returncode, stdout, stderr)."""
    if os.geteuid() == 0:
        return _service_root(name, action, timeout=timeout)
    try:
        rc, out, err = json.loads(rootd_client.call("service", name=name, action=action,
                                                    timeout=timeout, _timeout=timeout + 30))
        return rc, out, err
    except rootd_client.RootdError as e:
        return 1, "", str(e)


def _hosts_name_ok(name):
    """Would rootd's write_hosts accept this name? (A name it refuses would make the whole write fail.)"""
    return len(name) <= 253 and HOSTS_NAME_RE.fullmatch(name) is not None


def _write_hosts(text):
    """Write the hosts file: directly when this process may write it (root), else through rootd's write_hosts verb."""
    if os.access(HOSTS, os.W_OK):
        with open(HOSTS, "w") as f:
            f.write(text)
        return
    try:
        rootd_client.call("write_hosts", text=text)
    except rootd_client.RootdError as e:
        raise OSError(str(e)) from None


def _hosts_without_focus():
    try:
        with open(HOSTS) as f:
            text = f.read()
    except OSError:
        text = ""
    return re.sub(rf"\n?{FOCUS_BEGIN}.*?{FOCUS_END}\n?", "\n", text, flags=re.S).rstrip("\n") + "\n"


def focus(on, minutes=None, extra=None):
    base = _hosts_without_focus()
    if on:
        sites = [s for s in DISTRACTIONS + [s.strip().lower() for s in (extra or []) if s.strip()] if _hosts_name_ok(s)]
        block = "\n".join(f"0.0.0.0 {s}" for s in sites)
        base += f"{FOCUS_BEGIN}\n{block}\n{FOCUS_END}\n"
        until = time.time() + minutes * 60 if minutes else 0
        config.settings.set("focus", {"on": True, "until": until, "extra": extra or []})
    else:
        config.settings.set("focus", {"on": False, "until": 0})
    _write_hosts(base)


def focus_list():
    """The hosts blocked right now (empty when focus is off): the owner's distractions plus any extras. Checked in
    code by web.fetch and media.find, because with Tor on, curl resolves names remotely and never reads /etc/hosts."""
    f = config.settings.get("focus", {})
    if not f.get("on"):
        return set()
    return set(DISTRACTIONS) | {s.strip().lower() for s in (f.get("extra") or []) if s.strip()}


def is_blocked(url):
    """Is this URL (or bare host) blocked by focus mode? Matches the host and its parent domains."""
    host = re.sub(r"^\w+://", "", str(url or "")).split("/")[0].split("@")[-1].split(":")[0].lower().strip(".")
    if not host:
        return False
    blocked = focus_list()
    parts = host.split(".")
    return any(".".join(parts[i:]) in blocked for i in range(len(parts)))


def focus_tick():
    """Called by the scheduler: end a timed focus session."""
    f = config.settings.get("focus", {})
    if f.get("on") and f.get("until") and time.time() > f["until"]:
        focus(False)
        return True
    return False


# ------------------------------------------------------------------ time zone

ZONEINFO = "/usr/share/zoneinfo"


def timezone():
    """Current zone name, e.g. 'America/Phoenix'."""
    try:
        target = os.readlink("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    try:
        with open("/etc/timezone") as f:
            return f.read().strip() or "UTC"
    except OSError:
        return "UTC"


def apply_timezone_env():
    """Make this process use the system zone. musl caches the zone it read
    at first use, so we set TZ explicitly and call tzset() to pick up a zone
    changed after the process started (by the launcher or the owner)."""
    os.environ["TZ"] = timezone()
    time.tzset()


def _zone_key(s):
    """Match key for a place name or zone name: lowercase ASCII letters only.
    Accents are folded (NFKD, combining marks dropped), so 'zürich' -> 'zurich',
    'são paulo' -> 'saopaulo', and 'ß' -> 'ss'. Other non-ASCII is dropped."""
    s = unicodedata.normalize("NFKD", str(s).lower()).replace("ß", "ss")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s)


def find_timezone(name):
    """Resolve what the user said ('Tokyo', 'arizona', 'Europe/Paris') to a zone."""
    q = str(name).strip()
    if not q:
        return None
    if os.path.exists(os.path.join(ZONEINFO, q)) and "/" in q or q in ("UTC", "GMT"):
        return q
    key = _zone_key(q)
    aliases = {"arizona": "America/Phoenix", "phoenix": "America/Phoenix", "pacific": "America/Los_Angeles",
               "eastern": "America/New_York", "central": "America/Chicago", "mountain": "America/Denver",
               "uk": "Europe/London", "britain": "Europe/London", "cet": "Europe/Berlin", "india": "Asia/Kolkata",
               "china": "Asia/Shanghai", "japan": "Asia/Tokyo", "korea": "Asia/Seoul", "australia": "Australia/Sydney"}
    if key in aliases:
        return aliases[key]
    best = None
    for region in ("America", "Europe", "Asia", "Africa", "Australia", "Pacific", "Atlantic", "Indian", "Antarctica"):
        d = os.path.join(ZONEINFO, region)
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                zone = os.path.relpath(os.path.join(root, f), ZONEINFO)
                if _zone_key(f) == key:
                    return zone
                if key and key in _zone_key(zone) and best is None:
                    best = zone
    return best


_CITY_ALIASES = {
    "newyork": "America/New_York", "nyc": "America/New_York", "losangeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "sanfrancisco": "America/Los_Angeles", "seattle": "America/Los_Angeles", "chicago": "America/Chicago",
    "houston": "America/Chicago", "dallas": "America/Chicago", "denver": "America/Denver", "phoenix": "America/Phoenix",
    "toronto": "America/Toronto", "vancouver": "America/Vancouver", "mexicocity": "America/Mexico_City",
    "saopaulo": "America/Sao_Paulo", "buenosaires": "America/Argentina/Buenos_Aires", "london": "Europe/London",
    "dublin": "Europe/Dublin", "paris": "Europe/Paris", "berlin": "Europe/Berlin", "madrid": "Europe/Madrid",
    "rome": "Europe/Rome", "amsterdam": "Europe/Amsterdam", "zurich": "Europe/Zurich", "stockholm": "Europe/Stockholm",
    "warsaw": "Europe/Warsaw", "athens": "Europe/Athens", "istanbul": "Europe/Istanbul", "moscow": "Europe/Moscow",
    "cairo": "Africa/Cairo", "lagos": "Africa/Lagos", "nairobi": "Africa/Nairobi", "johannesburg": "Africa/Johannesburg",
    "dubai": "Asia/Dubai", "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata", "bangalore": "Asia/Kolkata",
    "karachi": "Asia/Karachi", "dhaka": "Asia/Dhaka", "bangkok": "Asia/Bangkok", "jakarta": "Asia/Jakarta",
    "singapore": "Asia/Singapore", "hongkong": "Asia/Hong_Kong", "shanghai": "Asia/Shanghai", "beijing": "Asia/Shanghai",
    "taipei": "Asia/Taipei", "seoul": "Asia/Seoul", "tokyo": "Asia/Tokyo", "manila": "Asia/Manila",
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne", "perth": "Australia/Perth",
    "auckland": "Pacific/Auckland", "honolulu": "Pacific/Honolulu", "anchorage": "America/Anchorage",
}


def _zone_offset(zone):
    """'UTC+09:00' for a zone, right now."""
    try:
        import datetime
        import zoneinfo
        off = datetime.datetime.now(zoneinfo.ZoneInfo(zone)).utcoffset()
        secs = int(off.total_seconds()) if off else 0
        sign = "+" if secs >= 0 else "-"
        secs = abs(secs)
        return f"UTC{sign}{secs // 3600:02d}:{secs % 3600 // 60:02d}"
    except Exception:
        return ""


def _all_zones():
    zones = []
    for region in ("America", "Europe", "Asia", "Africa", "Australia", "Pacific", "Atlantic", "Indian"):
        d = os.path.join(ZONEINFO, region)
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f[0].isupper():
                    zones.append(os.path.relpath(os.path.join(root, f), ZONEINFO))
    return sorted(set(zones))


def timezone_search(query, limit=8):
    """Time zones for a typed city or region ('tok' -> Asia/Tokyo), with the
    current UTC offset, for a picker. An empty query gives the current zone
    and a few big cities."""
    q = re.sub(r"[^a-z]", "", str(query or "").lower())
    hits = []
    if not q:
        cur = timezone()
        hits = [cur] + [z for z in ("America/New_York", "America/Los_Angeles", "Europe/London", "Europe/Berlin",
                                    "Asia/Kolkata", "Asia/Tokyo", "Australia/Sydney") if z != cur]
    else:
        if q in _CITY_ALIASES:
            hits.append(_CITY_ALIASES[q])
        for alias, zone in _CITY_ALIASES.items():
            if alias.startswith(q) and zone not in hits:
                hits.append(zone)
        starts, inside = [], []
        for z in _all_zones():
            city = re.sub(r"[^a-z]", "", z.rsplit("/", 1)[-1].lower())
            whole = re.sub(r"[^a-z]", "", z.lower())
            if city.startswith(q):
                starts.append(z)
            elif q in whole:
                inside.append(z)
        for z in starts + inside:
            if z not in hits:
                hits.append(z)
    out = []
    for z in hits[:limit]:
        city = z.rsplit("/", 1)[-1].replace("_", " ")
        region = z.split("/", 1)[0]
        out.append({"zone": z, "label": f"{city}, {region}", "offset": _zone_offset(z)})
    return out


def set_timezone(name, chosen_by_user=True):
    zone = find_timezone(name)
    if not zone:
        raise ValueError(f"unknown time zone '{name}'")
    try:
        rootd_client.call("set_timezone", zone=zone, chosen=bool(chosen_by_user))
    except rootd_client.RootdError as e:
        raise ValueError(str(e))
    apply_timezone_env()
    return zone


def _sync_time_root():
    """Run ntpd and set the hardware clock, as root. Returns True when ntpd succeeded."""
    import shutil
    import subprocess
    try:
        p = subprocess.run(["ntpd", "-q", "-n", "-p", "pool.ntp.org"], capture_output=True, timeout=30)
        if p.returncode == 0 and shutil.which("hwclock"):
            subprocess.run(["hwclock", "-w", "-u"], capture_output=True, timeout=10)
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sync_time(automatic=False):
    """Set the clock from the network once (busybox ntpd), when the owner allows the internet. A PC's clock is
    often off after another OS used it, and a wrong clock breaks every secure web site.
    automatic=True (the boot timer) only runs when internet is "yes"; the owner's own ask runs unless "no".
    As root it runs directly; else through rootd's sync_time verb."""
    import shutil
    from . import config as _c
    internet = _c.settings.get("internet", "yes")
    if (internet != "yes" if automatic else internet == "no") or not shutil.which("ntpd"):
        return False
    if os.geteuid() == 0:
        return _sync_time_root()
    try:
        return bool(json.loads(rootd_client.call("sync_time", _timeout=60)))
    except rootd_client.RootdError:
        return False
