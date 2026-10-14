"""Over-the-air updates from the owner's own computer (the one that builds LLM OS).

Off until the owner pairs: "get updates from my computer" finds the update server on the local network (or the owner
names its address), pins its signing key, and from then on the llmos-ota service keeps one outbound request open to it.
When the owner publishes an update there, it arrives at once. Nothing listens on this machine: no inbound port.

Every update is a signed manifest plus a file archive:
  - the manifest's signature is checked against the key pinned at pairing (ssh-keygen -Y verify, Ed25519);
  - the archive must match the manifest's SHA-256 and may only hold LLM OS's own files (no owner data, no settings);
  - the files it replaces are backed up first; if the desk does not come back after the update, the backup is
    restored and the desk restarted, so a bad update never needs a USB stick to undo.
"Stop updates from my computer" forgets the server and its key.
"""
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request

from . import config

PORT = 8781
NAMESPACE = "llmos-ota"
STATE_DIR = os.environ.get("LLMOS_OTA_DIR", "/var/lib/llmos/ota")
ROOT = os.environ.get("LLMOS_OTA_ROOT", "/")
RELEASE = os.path.join(ROOT, "etc/llmos-release")
# what an update may change: LLM OS's own program files only (never /etc/llmos, the owner's data or generated files)
ALLOWED = ("usr/lib/llmos/", "usr/share/llmos/", "usr/bin/llmos", "usr/bin/llmos-model-run", "usr/libexec/llmos-",
           "etc/init.d/llmos-", "etc/xdg/")
NEVER = ("etc/nftables.nft",)
SERVICES = re.compile(r"llmos-[a-z]+")
APK_NAME = re.compile(r"[a-z0-9][a-z0-9._+-]{0,63}")


# ---- pairing (settings key "ota": {"url", "key", "fp", "name", "auto"})

def paired():
    o = config.settings.get("ota") or {}
    return o if o.get("url") and o.get("key") else None


def fingerprint(key):
    """Short form of a public key the owner can compare on both screens, e.g. 'A1B2-C3D4'."""
    h = hashlib.sha256(key.strip().encode()).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}"


def _get(url, timeout=5.0, limit=2 * 1024 * 1024):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("answer too large")
    return data


def hello(base, timeout=2.0):
    """The update server's own description: {"name", "key", "fp"}; None if nothing answers there."""
    try:
        d = json.loads(_get(base.rstrip("/") + "/ota/hello", timeout))
    except Exception:
        return None
    key = d.get("key", "")
    if not isinstance(key, str) or not key.startswith("ssh-ed25519 "):
        return None
    return {"url": base.rstrip("/"), "name": str(d.get("name", "computer"))[:60], "key": key.strip(),
            "fp": fingerprint(key)}


def _local_nets():
    nets = []
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for cidr in re.findall(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", out):
        net = ipaddress.ip_interface(cidr).network
        if net.is_private and not net.is_loopback:
            nets.append(net if net.prefixlen >= 24 else ipaddress.ip_interface(cidr.split("/")[0] + "/24").network)
    return nets


def find_servers(timeout=0.6):
    """Look for update servers on this machine's local networks (port PORT). A quick sweep of each /24."""
    hosts = []
    for net in _local_nets():
        hosts += [str(h) for h in net.hosts()]
    if any(h.startswith("10.0.2.") for h in hosts):
        hosts.insert(0, "10.0.2.2")       # a virtual machine's host computer
    found, lock = {}, threading.Lock()

    def probe(h):
        try:
            with socket.create_connection((h, PORT), timeout=timeout):
                pass
        except OSError:
            return
        d = hello(f"http://{h}:{PORT}")
        if d:
            with lock:
                found.setdefault(d["key"], d)

    threads = []
    for h in dict.fromkeys(hosts):
        t = threading.Thread(target=probe, args=(h,), daemon=True)
        t.start()
        threads.append(t)
        if len(threads) % 64 == 0:
            for t in threads[-64:]:
                t.join(timeout + 2.5)
    for t in threads:
        t.join(timeout + 2.5)
    return list(found.values())


def pair(server):
    """Trust this server's key for updates. server is a hello() result."""
    config.settings.set("ota", {"url": server["url"], "key": server["key"], "fp": server["fp"],
                                "name": server["name"], "auto": True, "since": int(time.time())})
    from . import system
    system.apply_firewall()                # its one address and port may now be reached, even with the internet off
    _service("start")
    return server


def unpair():
    o = paired()
    config.settings.set("ota", {})
    from . import system
    system.apply_firewall()
    _service("stop")
    return o


def _service(action):
    try:
        if os.geteuid() == 0:
            subprocess.run(["rc-service", "llmos-ota", action], capture_output=True, timeout=30)
        else:
            from . import rootd_client
            rootd_client.call("service", name="llmos-ota", action=action)
    except Exception:
        pass


def firewall_rule():
    """The outbound exception for the paired server, for system.firewall_rules(); "" when not paired."""
    o = paired()
    if not o:
        return ""
    m = re.match(r"http://(\d+\.\d+\.\d+\.\d+):(\d+)$", o["url"])
    if not m:
        return ""
    return f"    ip daddr {m.group(1)} tcp dport {int(m.group(2))} accept\n"


def status_text():
    o = paired()
    if not o:
        return "Updates from your own computer are off. Say “get updates from my computer” to turn them on."
    st = _state()
    last = st.get("last") or {}
    line = f"Getting updates from {o['name']} ({o['url'].split('//')[1]}, key {o['fp']})."
    if last:
        when = time.strftime("%b %d %H:%M", time.localtime(last.get("ts", 0)))
        line += f" Last update: {last.get('version', '?')} on {when}, " + ("installed." if last.get("ok") else
                                                                          f"undone ({last.get('detail', 'failed')}).")
    return line + " This computer is on " + current_version() + "."


# ---- the client service (root)

def _state():
    return config.load_json(os.path.join(STATE_DIR, "state.json"), {})


def _save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    config.save_json(os.path.join(STATE_DIR, "state.json"), st)


def current_version():
    try:
        with open(os.path.join(ROOT, "usr/lib/llmos/llmos/__init__.py")) as f:
            m = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M)
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def verify_manifest(raw, sig, key):
    """True when sig is a valid signature of raw by key (the pinned public key)."""
    with tempfile.TemporaryDirectory() as d:
        signers, sigf = os.path.join(d, "signers"), os.path.join(d, "m.sig")
        with open(signers, "w") as f:
            f.write(f"{NAMESPACE} {key}\n")
        with open(sigf, "wb") as f:
            f.write(sig)
        try:
            p = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", signers, "-I", NAMESPACE, "-n", NAMESPACE,
                                "-s", sigf], input=raw, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return False
        return p.returncode == 0


def check_manifest(m):
    if not isinstance(m, dict) or m.get("format") != 1:
        raise ValueError("unknown update format")
    for k in ("id", "version", "payload", "sha256"):
        if not isinstance(m.get(k), str) or not m[k]:
            raise ValueError(f"update has no {k}")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", m["id"]) or not re.fullmatch(r"payload-[A-Za-z0-9._-]+\.tar", m["payload"]):
        raise ValueError("bad update name")
    if not re.fullmatch(r"[0-9a-f]{64}", m["sha256"]):
        raise ValueError("bad checksum")
    for s in m.get("restart", []):
        if s != "desk" and not SERVICES.fullmatch(s):
            raise ValueError(f"bad service {s!r}")
    for p in m.get("apk", []):
        if not APK_NAME.fullmatch(p):
            raise ValueError(f"bad package {p!r}")
    return m


def _member_ok(t):
    name = t.name[2:] if t.name.startswith("./") else t.name
    if not name or name in (".",):
        return None
    if name.startswith("/") or ".." in name.split("/") or name in NEVER:
        raise ValueError(f"refused path {t.name}")
    if t.isdir():
        return name
    if not (t.isfile() or t.issym()) or not any(name.startswith(a) for a in ALLOWED):
        raise ValueError(f"refused path {t.name}")
    if t.issym() and (t.linkname.startswith("/") or ".." in t.linkname.split("/")):
        raise ValueError(f"refused link {t.name}")
    return name


def check_payload(path):
    """The files the archive holds (relative paths); raises ValueError on anything outside ALLOWED."""
    with tarfile.open(path) as tf:
        names = [n for n in (_member_ok(t) for t in tf.getmembers()) if n]
    return names


def apply_files(payload, backup):
    """Back up what the payload will replace, then install it. Returns the rollback record."""
    names = check_payload(payload)
    with tarfile.open(payload) as tf:
        files = [t for t in tf.getmembers() if not t.isdir()]
    existing, new = [], []
    for t in files:
        name = t.name[2:] if t.name.startswith("./") else t.name
        (existing if os.path.lexists(os.path.join(ROOT, name)) else new).append(name)
    with tarfile.open(backup, "w") as bt:
        for name in existing:
            bt.add(os.path.join(ROOT, name), arcname=name, recursive=False)
    with tarfile.open(payload) as tf:
        for t in tf.getmembers():
            name = t.name[2:] if t.name.startswith("./") else t.name
            if not name or name == ".":
                continue
            t.name = name
            t.uid = t.gid = 0
            t.uname = t.gname = "root"
            dest = os.path.join(ROOT, name)
            if not t.isdir() and os.path.lexists(dest) and not os.path.isdir(dest):
                os.unlink(dest)                 # a new copy, never rewritten in place (a running script keeps its old one)
            tf.extract(t, ROOT, set_attrs=True, filter="fully_trusted") if _has_filter() else tf.extract(t, ROOT)
    return {"backup": backup, "new": new, "names": names}


def _has_filter():
    return hasattr(tarfile, "data_filter")


def rollback(rec):
    with tarfile.open(rec["backup"]) as bt:
        for t in bt.getmembers():
            dest = os.path.join(ROOT, t.name)
            if os.path.lexists(dest) and not os.path.isdir(dest):
                os.unlink(dest)
            bt.extract(t, ROOT, set_attrs=True, filter="fully_trusted") if _has_filter() else bt.extract(t, ROOT)
    for name in rec["new"]:
        p = os.path.join(ROOT, name)
        if os.path.lexists(p) and not os.path.isdir(p):
            os.unlink(p)


def _stamp_release(version):
    try:
        with open(RELEASE) as f:
            text = f.read()
    except OSError:
        return
    text = re.sub(r"^VERSION=.*$", f"VERSION={version}", text, flags=re.M)
    text = re.sub(r"^BUILD=.*$", f"BUILD={time.strftime('%Y-%m-%d')}", text, flags=re.M)
    with open(RELEASE, "w") as f:
        f.write(text)


def _desk_up(wait):
    end = time.time() + wait
    while time.time() < end:
        if os.path.exists("/run/llmos/desk.sock"):
            try:
                p = subprocess.run(["/usr/bin/llmos", "desk-state"], capture_output=True, text=True, timeout=20)
                if p.returncode == 0 and p.stdout.strip().startswith("{"):
                    return True
            except (OSError, subprocess.SubprocessError):
                pass
        time.sleep(3)
    return False


def _desk_app():
    """(pid, environ, uid, gid) of the running desk program ("llmos desk-app" inside the compositor), or None."""
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
            if b"desk-app" not in argv or not any(x.endswith(b"llmos") for x in argv):
                continue
            with open(f"/proc/{d}/environ", "rb") as f:
                env = dict(kv.split(b"=", 1) for kv in f.read().split(b"\0") if b"=" in kv)
            st = os.stat(f"/proc/{d}")
            return int(d), {k.decode(): v.decode() for k, v in env.items()}, st.st_uid, st.st_gid
        except (OSError, ValueError):
            continue
    return None


def restart_desk():
    """Start the desk program again with the new files, in the same screen session: only "llmos desk-app" is
    replaced (same environment, same user); the compositor and the login session stay up. (Ending the compositor
    instead made the login fall back to the text console on a real install.)"""
    found = _desk_app()
    if found:
        pid, env, uid, gid = found
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        for _ in range(50):
            if not os.path.exists(f"/proc/{pid}"):
                break
            time.sleep(0.2)
        else:
            try:
                os.kill(pid, 9)
            except OSError:
                pass
            time.sleep(0.5)
        try:
            os.unlink("/run/llmos/desk.sock")      # the new desk makes its own
        except OSError:
            pass

        def become():
            os.setsid()
            if uid != 0:
                import pwd
                try:
                    os.initgroups(pwd.getpwuid(uid).pw_name, gid)
                except (KeyError, OSError):
                    pass
                os.setgid(gid)
                os.setuid(uid)
        subprocess.Popen(["/usr/bin/llmos", "desk-app"], env=env, cwd=env.get("HOME", "/"), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=become, close_fds=True)
        return
    # no desk program running at all (a test shell, or the desk was closed): start the whole desk session
    if subprocess.run(["pgrep", "-x", "labwc"], capture_output=True).returncode:
        for f in ("/run/seatd.sock", "/run/llmos/desk.sock"):
            try:
                os.unlink(f)
            except OSError:
                pass
        subprocess.Popen(["setsid", "/usr/libexec/llmos-desk"], stdin=subprocess.DEVNULL,
                         stdout=open("/run/llmos/desk.log", "a"), stderr=subprocess.STDOUT, start_new_session=True)


def desk_behind():
    """True when the desk program started before the last update was installed (it still runs the old files):
    an update installed by an older client that could not restart the desk properly leaves it that way."""
    found = _desk_app()
    last = (_state().get("last") or {})
    if not found or not last.get("ok") or last.get("desk_restarted"):
        return False
    try:
        with open("/proc/uptime") as f:
            up = float(f.read().split()[0])
        with open(f"/proc/{found[0]}/stat") as f:
            started_ticks = int(f.read().rsplit(")", 1)[1].split()[19])
        started = time.time() - up + started_ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return False
    return started < float(last.get("files_at", last.get("ts", 0)))


def _restart(services, desk_was_up):
    for s in services:
        if s != "desk" and s != "llmos-ota":
            subprocess.run(["rc-service", s, "restart"], capture_output=True, timeout=120)
    if "desk" in services and desk_was_up:
        restart_desk()
        return _desk_up(90)
    return True


def _report(base, body):
    try:
        req = urllib.request.Request(base + "/ota/report", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def _notify(title, text):
    try:
        from . import store
        store.notify(title, text)
    except Exception:
        pass


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def install(base, m, key, log=print):
    """Fetch, verify and install update manifest m from base. Returns (ok, detail)."""
    data = _get(f"{base}/ota/{m['payload']}", timeout=120, limit=2 * 1024 ** 3)
    if hashlib.sha256(data).hexdigest() != m["sha256"]:
        return False, "the files did not match the signed checksum, so nothing was changed"
    os.makedirs(STATE_DIR, exist_ok=True)
    payload = os.path.join(STATE_DIR, "incoming.tar")
    with open(payload, "wb") as f:
        f.write(data)
    try:
        check_payload(payload)
    except (ValueError, tarfile.TarError) as e:
        return False, f"refused: {e}"
    for p in m.get("apk", []):
        r = subprocess.run(["apk", "add", "-q", p], capture_output=True, text=True, timeout=900)
        if r.returncode:
            return False, f"package {p} could not be installed: {r.stderr.strip()[:200]}"
    desk_was_up = os.path.exists("/run/llmos/desk.sock")
    me = os.path.join(ROOT, "usr/lib/llmos/llmos/ota.py")
    before = _sha(me)
    rec = apply_files(payload, os.path.join(STATE_DIR, f"backup-{m['id']}.tar"))
    install.files_at, install.self_changed = time.time(), _sha(me) != before
    if _restart(m.get("restart", ["desk"]), desk_was_up):
        _stamp_release(m["version"])      # only once it is kept: a rolled-back update leaves the stamp as it was
        return True, f"{len(rec['names'])} files"
    log("the desk did not come back after the update: undoing it")
    rollback(rec)
    _restart(m.get("restart", ["desk"]), desk_was_up)
    return False, "the desk did not start after the update, so the previous version was put back"


def client():
    """The llmos-ota service: wait for updates from the paired server, install each new one once."""
    try:
        if paired() and desk_behind():
            print("ota: the desk still runs the files from before the last update: starting it again", flush=True)
            restart_desk()
    except Exception as e:
        print(f"ota: could not restart the desk: {e}", flush=True)
    while True:
        o = paired()
        if not o:
            time.sleep(30)
            continue
        st = _state()
        base = o["url"]
        try:
            ans = json.loads(_get(f"{base}/ota/wait?have={st.get('id', '')}", timeout=70) or b"{}")
        except Exception:
            time.sleep(15)
            continue
        uid = ans.get("id") if isinstance(ans, dict) else None
        if not isinstance(uid, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", uid):
            continue                      # nothing new: ask again
        if uid == st.get("id") or uid in st.get("failed", []):
            time.sleep(5)
            continue
        try:
            raw = _get(f"{base}/ota/manifest-{uid}.json", timeout=20)
            sig = _get(f"{base}/ota/manifest-{uid}.json.sig", timeout=20)
            if not verify_manifest(raw, sig, o["key"]):
                print("ota: refused an update whose signature does not match the paired key", flush=True)
                _report(base, {"host": socket.gethostname(), "id": uid, "ok": False, "detail": "bad signature: refused"})
                st["failed"] = (st.get("failed", []) + [uid])[-20:]
                _save_state(st)
                continue
            m = check_manifest(json.loads(raw))
            if m["id"] != uid:
                raise ValueError("manifest id mismatch")
        except Exception as e:
            print(f"ota: bad update: {e}", flush=True)
            time.sleep(60)
            continue
        print(f"ota: installing {m['version']} ({m['id']})", flush=True)
        try:
            ok, detail = install(base, m, o["key"])
        except Exception as e:
            ok, detail = False, f"error: {e}"
        live = "MEDIUM=live" in (open(RELEASE).read() if os.path.exists(RELEASE) else "")
        st = _state()
        st["last"] = {"id": m["id"], "version": m["version"], "ok": ok, "detail": detail, "ts": time.time(),
                      "files_at": getattr(install, "files_at", time.time()),
                      "desk_restarted": ok and "desk" in m.get("restart", [])}
        if ok:
            st["id"] = m["id"]
        else:
            st["failed"] = (st.get("failed", []) + [m["id"]])[-20:]
        _save_state(st)
        print(f"ota: {'installed' if ok else 'not installed'}: {detail}", flush=True)
        _report(base, {"host": socket.gethostname(), "id": m["id"], "version": m["version"], "ok": ok,
                       "detail": detail, "now": current_version(), "live": live})
        if ok:
            _notify("Updated", f"LLM OS {m['version']} from {o['name']} is installed."
                    + (" This is the live USB, so it lasts until restart." if live else ""))
        else:
            _notify("Update undone", f"An update from {o['name']} was not kept: {detail}.")
        if ok and getattr(install, "self_changed", False):
            os._exit(0)                   # this program itself changed: the service starts the new one
