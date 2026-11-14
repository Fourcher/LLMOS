"""Local-only model backend, and the on-device installer, for the self-improvement loop.

The model side talks to llama.cpp on this machine and nowhere else:

  server  HTTP chat on a loopback llama-server (the runtime the OS already runs)
  cli     llama-cli or llama-completion, reading a GGUF file that is already on disk

A URL whose host is not a loopback name is refused before any socket is opened. A loopback
name that resolves to any other address is refused too. Nothing in this file calls an online
model, and a redirect is not followed.

The installer is the local equivalent of tools/ota.py publish plus the device's install:
the same manifest, the same ssh-keygen signature check, the same path allow-list, a backup
taken before the files are replaced, and the previous files put back when the health check
fails. It does not restart services. Network services are refused before anything is written.
"""
import hashlib
import http.client
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse

# Names a llama.cpp one-shot binary has shipped under. The server is preferred; these are the fallback.
CLI_NAMES = ("llama-cli", "llama-completion")
# Hosts we will consider at all. Anything else is refused before DNS, so a public name is never looked up.
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1", "ip6-localhost"}
# Services that must not be restarted. Restarting Wi-Fi or the firewall from the updater has taken the
# laptop off the network before; the model server is on this list so a self-update does not kill the model
# that is doing the work.
NETWORK_SERVICES = {
    "networking", "network", "net", "iwd", "wpa_supplicant", "wpa_cli", "networkmanager",
    "nftables", "iptables", "firewall", "sshd", "ssh", "dropbear", "tailscale", "tailscaled",
    "dnsmasq", "udhcpc", "dhcpcd", "chronyd", "openntpd", "ntpd", "wlan", "wifi", "hostapd",
    "avahi-daemon", "bluetooth", "bluetoothd", "llmos-model",
}
# The only services a caller may even name. install_local does not restart them; naming one outside
# this set, or any network service, stops the install before a file is written.
RESTART_ALLOWED = {"desk", "llmos-rootd", "llmos-scheduler", "llmos-watchdog"}
# The loop must not be able to edit its own rails or the signature check in the same update it installs.
RAILS = {"selfloop_ctl.py", "ota.py"}
_PREFIXES = ("src/rootfs/usr/lib/llmos/", "usr/lib/llmos/")


class LocalModelError(RuntimeError):
    """The on-device model could not be asked, or refused to stay on this machine."""


def split_loopback(url):
    """(host, port) for an http URL whose host is a loopback name. Raises before any network call."""
    text = (url or "").strip()
    parts = urllib.parse.urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme != "http" or not host:
        raise LocalModelError("the local backend only uses http on this machine")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise LocalModelError("refusing a model URL with credentials or a query")
    if host not in LOOPBACK_NAMES:
        raise LocalModelError(f"refusing to connect to {host or text}: the local backend stays on this machine")
    return host, parts.port or 80


def assert_loopback(url):
    """Raise unless every address for this URL is a loopback address. No connection is opened."""
    host, port = split_loopback(url)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise LocalModelError(f"the model server name did not resolve: {e}") from e
    if not infos:
        raise LocalModelError("the model server name did not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_loopback:
            raise LocalModelError(f"refusing {ip}: {host} is not only this machine")
    return host, port


def _http(host, port, timeout, method, path, body=None):
    """One request. http.client does not read proxy variables and does not follow redirects."""
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        headers = {"Host": host, "Content-Type": "application/json"} if body is not None else {"Host": host}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read(2 * 1024 * 1024)
        return resp.status, data
    finally:
        conn.close()


def server_healthy(cfg, timeout=3):
    """True when the loopback llama-server answers /health. A bad URL raises; a down server returns False."""
    host, port = assert_loopback(cfg.get("local_url") or "http://127.0.0.1:8080")
    try:
        status, body = _http(host, port, timeout, "GET", "/health")
    except OSError:
        return False
    return status == 200 and b"ok" in body.lower()


def _content_from_body(raw):
    text = raw.decode("utf-8", "replace")
    if text.lstrip().startswith("data:"):
        parts = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            for choice in chunk.get("choices") or []:
                delta = (choice.get("delta") or choice.get("message") or {})
                if delta.get("content"):
                    parts.append(delta["content"])
        return "".join(parts).strip()
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise LocalModelError("the model server did not return JSON") from e
    err = doc.get("error")
    if err:
        message = err.get("message", err) if isinstance(err, dict) else err
        raise LocalModelError(str(message)[:200])
    choices = doc.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or choices[0].get("text") or "").strip()


def chat_server(cfg, messages):
    """One completion from llama-server. The URL is checked again here, immediately before the socket."""
    host, port = assert_loopback(cfg.get("local_url") or "http://127.0.0.1:8080")
    body = json.dumps({
        "messages": messages,
        "temperature": float(cfg.get("local_temperature", 0.1) or 0.1),
        "max_tokens": int(cfg.get("local_max_tokens") or 800),
        "stream": False,
        "cache_prompt": True,
    })
    timeout = int(cfg.get("local_timeout_sec") or 900)
    try:
        status, raw = _http(host, port, timeout, "POST", "/v1/chat/completions", body.encode("utf-8"))
    except OSError as e:
        raise LocalModelError(f"the model server on this machine did not answer: {e}") from e
    if status != 200:
        detail = raw[:200].decode("utf-8", "replace")
        raise LocalModelError(f"the model server refused the request ({status}): {detail}")
    return _content_from_body(raw)


def find_cli(cfg):
    explicit = (cfg.get("local_cli") or "").strip()
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise LocalModelError(f"the llama.cpp CLI was not found: {explicit}")
    for name in CLI_NAMES:
        found = shutil.which(name)
        if found:
            return found
    raise LocalModelError("llama-cli is not installed on this machine")


def model_file(cfg):
    """A GGUF that is already a regular file here. A URL or a hub id is refused."""
    raw = (cfg.get("local_model") or os.environ.get("LLMOS_SELFLOOP_MODEL") or "").strip()
    if not raw:
        try:
            from llmos import models
            active = models.active()
            if active:
                raw = models.path_of(active)
        except Exception:
            raw = ""
    if not raw:
        raise LocalModelError("no local model file is configured")
    if "://" in raw or raw.startswith("hf:") or raw.startswith("http:") or raw.startswith("https:"):
        raise LocalModelError("the local backend refuses a model that is not a file on this machine")
    if not os.path.isfile(raw):
        raise LocalModelError("the model file is not on this machine")
    return os.path.realpath(raw)


def cli_argv(cli, model, prompt_path, max_tokens, temperature):
    """Arguments for a one-shot llama.cpp CLI. No URL is passed, so the process has nothing to fetch."""
    return [cli, "-m", model, "-f", prompt_path, "-n", str(int(max_tokens)),
            "--temp", str(temperature), "-c", "4096"]


def nice_argv(argv, level=19):
    """nice, then idle ionice when it works. The model and the test suite are the heavy work on a 16 GB machine."""
    import selfdev
    out = list(argv)
    level = 19 if not isinstance(level, int) or isinstance(level, bool) else max(0, min(19, level))
    if shutil.which("nice"):
        out = ["nice", "-n", str(level)] + out
    if selfdev._ionice_ok():
        out = ["ionice", "-c", "3"] + out
    return out


def render_prompt(messages):
    chunks = []
    for message in messages or []:
        role = message.get("role") or "user"
        text = message.get("content") or ""
        chunks.append(f"### {role}\n{text}")
    chunks.append("### assistant\n")
    return "\n\n".join(chunks)


def chat_cli(cfg, messages, runner=None):
    """One completion from the local CLI. runner replaces subprocess.run in tests."""
    cli = find_cli(cfg)
    model = model_file(cfg)
    prompt = render_prompt(messages)
    fd, path = tempfile.mkstemp(prefix="llmos-selfloop-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prompt)
        argv = nice_argv(
            cli_argv(cli, model, path, cfg.get("local_max_tokens") or 800, cfg.get("local_temperature", 0.1) or 0.1),
            cfg.get("nice", 19))
        run = runner or subprocess.run
        try:
            proc = run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       timeout=int(cfg.get("local_timeout_sec") or 900))
        except subprocess.TimeoutExpired as e:
            raise LocalModelError("the local model took too long and was stopped") from e
        except OSError as e:
            raise LocalModelError(f"the local model could not be started: {e}") from e
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "llama-cli failed")[-300:]
        raise LocalModelError(detail)
    return (proc.stdout or "").strip()


def complete(cfg, messages):
    """The configured local transport. auto prefers the server and uses the CLI only when it is down."""
    transport = cfg.get("local_transport") or "auto"
    if transport == "server":
        return chat_server(cfg, messages)
    if transport == "cli":
        return chat_cli(cfg, messages)
    if transport == "auto":
        # A URL that leaves the machine raises here. It does not fall through to somewhere else.
        if server_healthy(cfg):
            return chat_server(cfg, messages)
        return chat_cli(cfg, messages)
    raise LocalModelError(f"unknown local transport: {transport}")


def prompt_messages(pkg_dir, item, note=""):
    """A short prompt. A 9B model on CPU is slow, and a long prompt crowds the edit out of the context."""
    title = str((item or {}).get("title") or "")
    detail = str((item or {}).get("detail") or "")
    excerpt = _excerpt(pkg_dir, title + " " + detail)
    system = (
        "You edit LLM OS, on this computer, to carry out one change its owner asked for. "
        "Make the smallest change that does it. Never weaken a safety check, a permission prompt, "
        "the firewall, the update signature, or the self-improvement kill switch. "
        "Do not edit tests, selfloop_ctl.py, or ota.py. "
        "Return ONLY changes, in this EXACT format. No markdown fences, no explanation.\n"
        "=== FILE: llmos/web.py\n"
        "<<<<<<< SEARCH\n"
        "old line\n"
        "=======\n"
        "new line\n"
        ">>>>>>> REPLACE\n"
        "The SEARCH text is copied verbatim from the file shown to you. One block per change."
    )
    user = f"TASK: {title}\n"
    if detail:
        user += f"\nDETAIL: {detail}\n"
    if note:
        user += f"\nThe last attempt did not work: {note}\n"
    user += f"\nRELEVANT FILES:\n{excerpt or '(no excerpt)'}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _excerpt(pkg_dir, task, limit=1600):
    import math
    import re
    package = os.path.join(pkg_dir, "llmos")
    if not os.path.isdir(package):
        return ""
    words = set(re.findall(r"[a-z_]{4,}", (task or "").lower()))
    words -= {"that", "this", "with", "from", "selfloop", "llmos", "file", "test"}
    scored = []
    try:
        names = sorted(os.listdir(package))
    except OSError:
        return ""
    for name in names:
        if not name.endswith(".py") or name in RAILS:
            continue
        try:
            text = open(os.path.join(package, name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        low = text.lower()
        score = sum(low.count(w) for w in words) / math.sqrt(max(len(text), 1))
        if name[:-3] in task:
            score += 3
        scored.append((score, name, text))
    scored.sort(key=lambda row: row[0], reverse=True)
    if not scored or scored[0][0] == 0:
        return ""
    _score, name, text = scored[0]
    return f"--- llmos/{name} ---\n{text[:limit]}"


def _normalize(pkg_dir, rel):
    raw = (rel or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or raw.startswith("~"):
        return None, f"{rel}: edits are limited to the OS package"
    if any(part in ("", ".", "..") for part in raw.split("/")):
        return None, f"{raw}: path escapes the OS package"
    for prefix in _PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    parts = [p for p in raw.split("/") if p]
    if len(parts) == 1:
        parts = ["llmos", parts[0]]
    if not parts or parts[0] != "llmos" or any(p in ("", ".", "..") for p in parts):
        return None, f"{raw}: edits are limited to the OS package"
    base = parts[-1]
    if not base.endswith(".py"):
        return None, f"{raw}: edits are limited to Python files in the OS package"
    if base.startswith("test-") or base == "run-host-tests.sh" or base in RAILS:
        return None, f"{raw}: a patch cannot edit the test gate or the update rails"
    full = os.path.realpath(os.path.join(pkg_dir, *parts))
    root = os.path.realpath(pkg_dir)
    if full != root and not full.startswith(root + os.sep):
        return None, f"{raw}: path escapes the OS package"
    if not full.endswith(".py") or os.path.basename(full) in RAILS:
        return None, f"{raw}: a patch cannot edit the update rails"
    cleaned = "src/rootfs/usr/lib/llmos/" + "/".join(parts)
    return (full, cleaned), None


def apply_edits(pkg_dir, edits):
    """Apply SEARCH/REPLACE only inside pkg_dir. A forbidden path rejects the whole patch.
    Returns (count, problems, repo-relative paths)."""
    edits = list(edits or [])
    # Any path _normalize rejects (escape, rails, non-Python) rejects the whole patch before a write.
    blocked = []
    for edit in edits:
        _resolved, err = _normalize(pkg_dir, edit.get("path", ""))
        if err:
            blocked.append(err)
    if blocked:
        return 0, blocked, []
    pending, originals, problems = {}, {}, []
    for edit in edits:
        resolved, err = _normalize(pkg_dir, edit.get("path", ""))
        if err or not resolved:
            problems.append(err or "no path")
            continue
        full, cleaned = resolved
        if not os.path.isfile(full):
            problems.append(f"{cleaned}: no such file")
            continue
        if cleaned not in pending:
            text0 = open(full, encoding="utf-8").read()
            pending[cleaned] = text0
            originals[cleaned] = text0
        text = pending[cleaned]
        search, replace = edit.get("search", ""), edit.get("replace", "")
        if search not in text:
            problems.append(f"{cleaned}: the SEARCH text was not found exactly")
            continue
        if text.count(search) > 1:
            problems.append(f"{cleaned}: the SEARCH text is not unique")
            continue
        pending[cleaned] = text.replace(search, replace, 1)
    changed = {rel: pending[rel] for rel in pending if pending[rel] != originals.get(rel)}
    if not changed:
        return 0, problems, []
    staged = []
    for rel, text in changed.items():
        resolved, err = _normalize(pkg_dir, rel)
        if err or not resolved:
            return 0, problems + [err or f"{rel}: no path"], []
        full, _cleaned = resolved
        tmp = full + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        staged.append((tmp, full))
    for tmp, full in staged:
        os.replace(tmp, full)
    return len(changed), problems, sorted(changed)


def assert_restart(services):
    """Raise when a restart list names a network service or anything the loop does not restart.
    This does not restart anything."""
    bad_net, bad_other = [], []
    for name in services or []:
        low = str(name).strip().lower()
        if not low:
            continue
        if low in NETWORK_SERVICES or _looks_network(low):
            bad_net.append(str(name))
        elif str(name) not in RESTART_ALLOWED:
            bad_other.append(str(name))
    if bad_net:
        raise LocalModelError("refusing to restart network services: " + ", ".join(bad_net))
    if bad_other:
        raise LocalModelError("refusing to restart services: " + ", ".join(bad_other))
    return [s for s in (services or []) if s in RESTART_ALLOWED]


def _looks_network(name):
    for needle in ("iwd", "wifi", "wlan", "nft", "ssh", "tailscale", "network", "resolv", "dhcp", "ntp"):
        if needle in name:
            return True
    return False


def _walk_files(root):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for fn in sorted(files):
            if fn.endswith((".pyc", ".pyo")) or fn == ".DS_Store":
                continue
            full = os.path.join(dirpath, fn)
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if not rel or rel.startswith("/") or ".." in rel.split("/"):
                continue
            yield rel, full


def changed_files(live_pkg, staging_pkg):
    """(arcname, source path) for files under the staging package whose bytes differ from the live one.
    arcname is usr/lib/llmos/... which is what the signed update is allowed to replace."""
    out = []
    for rel, full in _walk_files(staging_pkg):
        arc = "usr/lib/llmos/" + rel
        live = os.path.join(live_pkg, rel)
        try:
            new = open(full, "rb").read()
        except OSError:
            continue
        try:
            old = open(live, "rb").read() if os.path.isfile(live) else None
        except OSError:
            old = None
        if old != new:
            out.append((arc, full, new))
    return out


def build_payload(files):
    """A ustar of just the changed program files, owned by root, matching the OTA payload rules."""
    buf_path = tempfile.NamedTemporaryFile(prefix="llmos-payload-", suffix=".tar", delete=False)
    buf_path.close()
    try:
        with tarfile.open(buf_path.name, "w", format=tarfile.USTAR_FORMAT) as tf:
            for arc, _full, data in files:
                if not arc.startswith("usr/lib/llmos/") or ".." in arc.split("/"):
                    raise LocalModelError(f"refusing to pack {arc}")
                info = tarfile.TarInfo(arc)
                info.size = len(data)
                info.mode = 0o755 if arc.startswith(("usr/bin/", "usr/libexec/")) or os.access(_full, os.X_OK) else 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = int(time.time())
                tf.addfile(info, __import__("io").BytesIO(data))
        blob = open(buf_path.name, "rb").read()
    finally:
        try:
            os.unlink(buf_path.name)
        except OSError:
            pass
    return blob


def _version_of(staging_pkg):
    path = os.path.join(staging_pkg, "llmos", "__init__.py")
    try:
        for line in open(path, encoding="utf-8"):
            if line.startswith('VERSION = "'):
                return line.split('"', 2)[1]
    except OSError:
        pass
    return "0"


def ensure_signing_key(directory):
    """(private path, pinned public line). The pin is written once. A later private key that does not
    match it fails verification, so swapping the key file does not authorize an update."""
    env = os.environ.get("LLMOS_SELFLOOP_SIGNING_KEY", "").strip()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if env:
        priv = env
        pub_path = env + ".pub"
        if not os.path.isfile(priv) or not os.path.isfile(pub_path):
            raise LocalModelError("LLMOS_SELFLOOP_SIGNING_KEY is not an ssh-keygen key pair")
    else:
        priv = os.path.join(directory, "selfloop")
        pub_path = priv + ".pub"
        if not os.path.isfile(priv):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "llmos-selfloop", "-f", priv],
                           check=True, stdout=subprocess.DEVNULL)
            os.chmod(priv, 0o600)
    pubkey = open(pub_path, encoding="utf-8").read().strip()
    pin = os.path.join(directory, "pinned.pub")
    if not os.path.isfile(pin):
        with open(pin, "w", encoding="utf-8") as handle:
            handle.write(pubkey + "\n")
        os.chmod(pin, 0o644)
    return priv, open(pin, encoding="utf-8").read().strip()


def sign_manifest(manifest_path, private_key):
    sig_path = manifest_path + ".sig"
    try:
        os.unlink(sig_path)
    except OSError:
        pass
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", private_key, "-n", "llmos-ota", manifest_path],
                   check=True, stdout=subprocess.DEVNULL)
    return open(sig_path, "rb").read()


def compile_tree(pkg_dir):
    """True when every Python file under the installed package compiles. Runs in a subprocess."""
    code = (
        "import sys, os\n"
        "root = sys.argv[1]\n"
        "bad = []\n"
        "for dirpath, dirs, files in os.walk(root):\n"
        "    dirs[:] = [d for d in dirs if d != '__pycache__']\n"
        "    for fn in files:\n"
        "        if not fn.endswith('.py'):\n"
        "            continue\n"
        "        path = os.path.join(dirpath, fn)\n"
        "        try:\n"
        "            src = open(path, encoding='utf-8').read()\n"
        "            compile(src, path, 'exec')\n"
        "        except Exception as e:\n"
        "            bad.append('%s: %s' % (fn, e))\n"
        "if bad:\n"
        "    sys.stderr.write('\\n'.join(bad[:5]))\n"
        "    sys.exit(1)\n"
    )
    argv = nice_argv([sys.executable, "-c", code, pkg_dir])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"the health check could not compile the new files: {e}"[:200]
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "the new files do not compile")[:200]
    return True, "ok"


def install_local(live_pkg, staging_pkg, state_dir, restart=None, signing_dir=None):
    """Sign the changed files, verify that signature, install into live_pkg, then health-check.
    Returns (ok, detail). On any failure the previous files are put back when they were already
    replaced, and a failure before that point does not write them. Services are not restarted.
    """
    try:
        assert_restart(list(restart or []))
    except LocalModelError as e:
        return False, str(e)
    # The names that passed are not started. This installer does not restart services.
    files = changed_files(live_pkg, staging_pkg)
    if not files:
        return False, "nothing changed, so nothing was installed"
    try:
        blob = build_payload(files)
    except (LocalModelError, OSError, tarfile.TarError) as e:
        return False, f"could not pack the update: {e}"[:200]
    digest = hashlib.sha256(blob).hexdigest()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    mid = f"selfloop-{stamp}-{digest[:8]}"
    os.makedirs(state_dir, exist_ok=True)
    payload = os.path.join(state_dir, f"payload-{mid}.tar")
    mpath = os.path.join(state_dir, f"manifest-{mid}.json")
    with open(payload, "wb") as handle:
        handle.write(blob)
    manifest = {
        "format": 1, "id": mid, "version": _version_of(staging_pkg),
        "payload": f"payload-{mid}.tar", "sha256": digest, "size": len(blob),
        "files": len(files), "created": int(time.time()), "restart": [], "apk": [],
        "note": "selfloop local install",
    }
    with open(mpath, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=1)
        handle.write("\n")
    try:
        priv, pinned = ensure_signing_key(signing_dir or os.path.join(state_dir, "keys"))
        sig = sign_manifest(mpath, priv)
    except (OSError, subprocess.CalledProcessError, LocalModelError) as e:
        return False, f"could not sign the update: {e}"[:200]
    raw = open(mpath, "rb").read()
    from llmos import ota
    verified = ota.verify_manifest(raw, sig, pinned)
    if verified is not True:
        return False, "the signature does not match the pinned key, so nothing was changed"
    try:
        checked = ota.check_manifest(json.loads(raw))
    except ValueError as e:
        return False, f"refusing the update: {e}"[:200]
    if hashlib.sha256(open(payload, "rb").read()).hexdigest() != checked["sha256"]:
        return False, "the files did not match the signed checksum, so nothing was changed"
    root = _ota_root(live_pkg)
    old_root, old_state = ota.ROOT, ota.STATE_DIR
    ota.ROOT = root
    ota.STATE_DIR = state_dir
    rec = None
    try:
        try:
            ota.check_payload(payload)
        except (ValueError, tarfile.TarError) as e:
            return False, f"refusing the update: {e}"[:200]
        rec = ota.apply_files(payload, os.path.join(state_dir, f"backup-{mid}.tar"))
        compiled, why_c = compile_tree(live_pkg)
        healthy, why_h = ota.health_ok()
        if not compiled or not healthy:
            ota.rollback(rec)
            why = why_c if not compiled else why_h
            return False, "the health check failed, so the previous version was put back (" + why + ")"
        return True, f"{len(files)} files installed"
    except Exception as e:
        if rec:
            try:
                ota.rollback(rec)
            except Exception as rollback_error:
                return False, f"install failed ({e}); rollback also failed ({rollback_error})"[:300]
        return False, f"install failed, and the previous files were kept: {e}"[:300]
    finally:
        ota.ROOT, ota.STATE_DIR = old_root, old_state


def _ota_root(live_pkg):
    """The OTA root whose usr/lib/llmos is live_pkg. '/' when the package is the real install."""
    real = os.path.realpath(live_pkg).rstrip(os.sep)
    suffix = os.path.join(os.sep, "usr", "lib", "llmos")
    if real == "/usr/lib/llmos":
        return "/"
    if real.endswith(suffix):
        root = real[: -len(suffix)]
        return root or "/"
    raise LocalModelError("the install target is not an llmos package directory")


def is_source_tree(path):
    """True when path is this checkout's package, which on-device mode must not install into."""
    if not path:
        return False
    here = os.path.dirname(os.path.abspath(__file__))
    repo_pkg = os.path.realpath(os.path.join(here, "..", "src", "rootfs", "usr", "lib", "llmos"))
    real = os.path.realpath(path)
    return real == repo_pkg or real.startswith(repo_pkg + os.sep)
