"""A decentralized store of on-device models.

A model is a signed manifest plus the files it names. The manifest is content-addressed:
its id is the SHA-256 of the canonical body. The publisher's ed25519 key signs that body.
A file is copied into the store only after its size and SHA-256 match the manifest. Until
then it is a ".part" and nothing loads it.

Copies can live anywhere. The store fetches them, in order, from:

  * a folder or USB drive (file:// or a local path the owner pointed at)
  * an HTTP mirror, including a Hugging Face resolve URL written in the manifest
  * a peer on this network (lan://), only while handling a request the owner made
  * a magnet link, behind TorrentClient

There is no default index and no telemetry. Nothing is fetched or announced until the
owner asks, and every network attempt is written to the activity log (say "what is the
model store doing"). Sharing local models with peers is off until "share my models".
Torrent seeding is not implemented: a magnet is downloaded only when the owner turns
BitTorrent on and a local aria2c exists, and that client is told not to seed.
"""
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from . import config

NAMESPACE = "llmos-model"
PORT = 8766
FORMATS = ("gguf", "mlx", "nvfp4")
USER_AGENT = "LLMOS-model-store"
DEFAULT_INDEXES = ()          # no phone-home. The owner adds index URLs; there is no built-in one.
ACTIVITY_KEEP = 200
_SHARE = {"server": None, "host": "", "port": 0}
_http_ctx = threading.local()


# ---------------------------------------------------------------- manifest

def canonical_bytes(manifest):
    """The bytes the signature covers: every field except signature, in a fixed order."""
    body = json.loads(json.dumps({k: v for k, v in manifest.items() if k != "signature"}))
    files = body.get("files")
    if isinstance(files, list):
        for one in files:
            if isinstance(one, dict) and isinstance(one.get("sources"), list):
                one["sources"] = sorted(one["sources"])
        body["files"] = sorted(files, key=lambda f: (f.get("name") or "") if isinstance(f, dict) else "")
    if isinstance(body.get("sources"), list):
        body["sources"] = sorted(body["sources"])
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def manifest_id(manifest):
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def fingerprint(pubkey):
    h = hashlib.sha256((pubkey or "").strip().encode()).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}"


def _slug(name, version):
    base = re.sub(r"[^a-z0-9]+", "-", f"{name}-{version}".lower()).strip("-")
    return (base or "model")[:60]


def validate_manifest(manifest):
    """Raise ValueError when the manifest is not a store manifest. Does not check the signature."""
    if not isinstance(manifest, dict):
        raise ValueError("a manifest must be an object")
    if manifest.get("format_version") != 1:
        raise ValueError("unknown manifest format")
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or "/" in name:
        raise ValueError("the model name is missing")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip() or len(version) > 40:
        raise ValueError("the model version is missing")
    if manifest.get("format") not in FORMATS:
        raise ValueError("format must be gguf, mlx, or nvfp4")
    if not isinstance(manifest.get("quant", ""), str) or len(manifest.get("quant", "")) > 40:
        raise ValueError("quant must be short text")
    if not isinstance(manifest.get("license"), str) or not manifest["license"].strip():
        raise ValueError("the license is missing")
    files = manifest.get("files")
    if not isinstance(files, list) or not files or len(files) > 64:
        raise ValueError("the manifest needs its files")
    seen = set()
    for one in files:
        if not isinstance(one, dict):
            raise ValueError("a file entry is not an object")
        fname = one.get("name")
        if not isinstance(fname, str) or not _safe_name(fname) or fname in seen:
            raise ValueError("a file name is not safe")
        seen.add(fname)
        sha = str(one.get("sha256", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError(f"{fname} has no sha256")
        size = one.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"{fname} has no size")
        if "sources" in one and not isinstance(one["sources"], list):
            raise ValueError(f"{fname} sources must be a list")
    if not isinstance(manifest.get("sources", []), list):
        raise ValueError("sources must be a list")
    pub = manifest.get("publisher", "")
    if not isinstance(pub, str):
        raise ValueError("publisher must be a public key")
    if pub and not pub.startswith("ssh-ed25519 "):
        raise ValueError("publisher must be an ed25519 public key")
    sig = manifest.get("signature", "")
    if not isinstance(sig, str):
        raise ValueError("signature must be text")
    return manifest


def _safe_name(name):
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name and ".." not in name


def verify_manifest(manifest):
    """True when signature is an ed25519 signature of the canonical body by publisher."""
    validate_manifest(manifest)
    sig = manifest.get("signature") or ""
    pub = (manifest.get("publisher") or "").strip()
    if not sig or not pub.startswith("ssh-ed25519 "):
        return False
    from . import ota
    result = ota.verify_manifest(canonical_bytes(manifest), sig.encode("utf-8"), pub, namespace=NAMESPACE)
    return result is True


def sign_manifest(manifest, key_path):
    """Return a copy of manifest with signature set. The private key never leaves this machine."""
    body = dict(manifest)
    body.pop("signature", None)
    validate_manifest(body)
    data = canonical_bytes(body)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "body")
        with open(path, "wb") as f:
            f.write(data)
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", key_path, "-n", NAMESPACE, path],
                       check=True, stdout=subprocess.DEVNULL)
        body["signature"] = open(path + ".sig", encoding="utf-8").read()
    if not verify_manifest(body):
        raise RuntimeError("the signature just written does not verify")
    return body


def pubkey_of(key_path):
    out = subprocess.run(["ssh-keygen", "-y", "-f", key_path], check=True, capture_output=True, text=True)
    return out.stdout.strip()


def local_key_path():
    return os.path.join(config.data_dir(), "model-store-ed25519")


def ensure_local_key():
    """The key this computer signs its own imported models with. Created on first share, mode 0600."""
    path = local_key_path()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", NAMESPACE, "-f", path],
                       check=True, stdout=subprocess.DEVNULL)
        os.chmod(path, 0o600)
    pub = path + ".pub"
    if os.path.exists(pub):
        os.chmod(pub, 0o644)
    return path


def accept_manifest(manifest, from_network):
    """(ok, reason). A network manifest must verify. A local import may be unsigned: the owner
    pointed at the folder and every file hash was checked against MANIFEST.txt."""
    try:
        validate_manifest(manifest)
    except ValueError as e:
        return False, str(e)
    signed = bool(manifest.get("signature"))
    if from_network and not signed:
        return False, "a model from the network must be signed"
    if signed and not verify_manifest(manifest):
        return False, "the signature does not match the publisher key"
    trusted = config.settings.get("model_store_publishers") or []
    if from_network and isinstance(trusted, list) and trusted:
        if manifest.get("publisher") not in trusted:
            return False, "that publisher is not in your trusted list"
    if not signed and manifest.get("trust") != "owner-import":
        return False, "an unsigned manifest is only kept when you imported the folder"
    return True, "signed" if signed else "imported"


# ---------------------------------------------------------------- activity (local only)

def _activity_path():
    return config.data("model-store-activity.json")


def activity(action, detail, network=False):
    """Append one line the owner can read. This file is never uploaded."""
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "action": str(action)[:40],
           "detail": str(detail)[:300], "network": bool(network)}
    path = _activity_path()
    try:
        with config.data_lock():
            cur = config.load_json(path, [])
            if not isinstance(cur, list):
                cur = []
            cur.append(rec)
            config.save_json(path, cur[-ACTIVITY_KEEP:])
    except OSError:
        pass
    try:
        from . import store
        store.audit("model_store", {"action": rec["action"], "network": rec["network"]}, rec["detail"], who="owner")
    except Exception:
        pass
    return rec


def activity_entries():
    cur = config.load_json(_activity_path(), [])
    return cur if isinstance(cur, list) else []


def activity_text():
    rows = activity_entries()
    if not rows:
        return "The model store has not fetched or shared anything. Sharing is off until you ask."
    lines = ["Model store activity (newest last). Network lines are marked:"]
    for rec in rows[-20:]:
        kind = "network" if rec.get("network") else "local"
        lines.append(f"{rec.get('ts', '')}  {kind}  {rec.get('action', '')}: {rec.get('detail', '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------- index

def _index_path():
    return config.data("model-store.json")


def index():
    cur = config.load_json(_index_path(), [])
    return cur if isinstance(cur, list) else []


def _save_index(rows):
    config.save_json(_index_path(), rows)


def remember(manifest, paths):
    """Keep a manifest that has already been accepted, with the local path of each file."""
    rows = [r for r in index() if isinstance(r, dict) and r.get("id") != manifest_id(manifest)]
    rows.append({"id": manifest_id(manifest), "manifest": manifest, "paths": paths,
                 "added": time.strftime("%Y-%m-%d %H:%M:%S")})
    _save_index(rows)
    return rows[-1]


def by_name(name):
    want = (name or "").strip().casefold()
    hits = []
    for row in index():
        man = row.get("manifest") or {}
        label = str(man.get("name", "")).casefold()
        if want and (want == label or want == _slug(man.get("name", ""), man.get("version", ""))):
            hits.append(row)
    hits.sort(key=lambda r: r.get("added", ""))
    return hits


# ---------------------------------------------------------------- sources

def classify_source(src):
    s = str(src or "").strip()
    if s.startswith("magnet:?"):
        return "magnet"
    if s.startswith("lan://"):
        return "lan"
    if s.startswith("file:") or s.startswith("/"):
        return "file"
    if s.startswith("http://") or s.startswith("https://"):
        return "http"
    raise ValueError("unknown source")


def http_allowed(url, allow_loopback=False):
    """HTTPS mirrors and private-network HTTP only. No link-local, no credentials, no file redirects."""
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        return False
    host = parts.hostname
    if not host:
        return False
    if host.lower() == "localhost":
        return bool(allow_loopback)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return parts.scheme == "https"
    if ip.is_unspecified or ip.is_multicast or ip.is_link_local or ip.is_reserved:
        return False
    if ip.is_loopback:
        return bool(allow_loopback)
    if ip.is_private:
        return True
    return parts.scheme == "https"


def file_path_of(src):
    if str(src).startswith("file:"):
        return urllib.parse.unquote(urllib.parse.urlparse(src).path)
    if str(src).startswith("/"):
        return src
    return ""


def approved_roots(extra=None, removable=True):
    roots = []
    for one in list(extra or []) + list(config.settings.get("model_roots") or []):
        if isinstance(one, str) and one.startswith("/"):
            roots.append(one)
    roots.append(config.MODELS)
    if removable:
        for prefix in ("/media", "/mnt", "/run/media"):
            if os.path.isdir(prefix):
                roots.append(prefix)
    return roots


def file_allowed(path, roots):
    """A file:// source is read only under a root the owner approved, the model dir, or a removable drive."""
    try:
        real = os.path.realpath(path)
    except OSError:
        return False
    if not os.path.isfile(real):
        return False
    for root in roots:
        try:
            base = os.path.realpath(root)
        except OSError:
            continue
        if real == base or real.startswith(base + os.sep):
            return True
    return False


def sources_for(manifest, one):
    name = one["name"]
    found = []
    for src in list(one.get("sources") or []) + list(manifest.get("sources") or []):
        src = str(src).strip()
        if not src:
            continue
        try:
            kind = classify_source(src)
        except ValueError:
            continue
        if kind == "magnet":
            found.append(src)
        elif kind == "lan":
            found.append(src.rstrip("/") + "/" + name)
        elif src.endswith("/"):
            found.append(src + name)
        elif src.endswith("/" + name) or os.path.basename(file_path_of(src) or urllib.parse.urlparse(src).path) == name:
            found.append(src)
        elif len(manifest.get("files") or []) == 1 and kind in ("http", "file"):
            found.append(src)
    order = {"file": 0, "lan": 1, "http": 2, "magnet": 3}
    found.sort(key=lambda s: order.get(classify_source(s), 9))
    out = []
    for src in found:
        if src not in out:
            out.append(src)
    return out


class _GuardRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not http_allowed(newurl, allow_loopback=getattr(_http_ctx, "allow_loopback", False)):
            raise ValueError("refusing a redirect off the mirrors this store allows")
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(_GuardRedirect)


def download_http(url, part, size, progress=None, allow_loopback=False, timeout=120):
    """Resume into part. A server that ignores Range is rewritten from the start. Nothing is renamed here."""
    if not http_allowed(url, allow_loopback=allow_loopback):
        raise ValueError("refusing that address")
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if size is not None and have > size:
        os.unlink(part)
        have = 0
    headers = {"User-Agent": USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
    _http_ctx.allow_loopback = allow_loopback
    req = urllib.request.Request(url, headers=headers)
    with _opener().open(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        mode = "ab" if status == 206 and have else "wb"
        if mode == "wb":
            have = 0
        got = have
        with open(part, mode) as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                got += len(chunk)
                if size is not None and got > size:
                    raise ValueError("the file is larger than the signed size")
                out.write(chunk)
                if progress:
                    progress("download", got, size or got)
    return part


def copy_resume(src, part, size, progress=None):
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if size is not None and have > size:
        os.unlink(part)
        have = 0
    with open(src, "rb") as inp, open(part, "ab" if have else "wb") as out:
        inp.seek(have)
        got = have
        while True:
            chunk = inp.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
            if size is not None and got > size:
                raise ValueError("the file is larger than the signed size")
            out.write(chunk)
            if progress:
                progress("copy", got, size or got)
    return part


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def place_verified(part, dest, sha, size):
    """Move part onto dest only when size and sha256 match. Otherwise delete part and raise."""
    try:
        actual = os.path.getsize(part)
    except OSError as e:
        raise RuntimeError("the download is missing") from e
    if int(size) != actual or sha256_file(part) != sha.lower():
        try:
            os.unlink(part)
        except OSError:
            pass
        raise RuntimeError("checksum mismatch; the file was not kept")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(part, dest)
    return dest


# ---------------------------------------------------------------- torrent (interface; off unless the owner opts in)

class TorrentClient:
    """Fetch one magnet into dest_dir. Seeding stays off: this store does not announce the owner's files
    to a public swarm. LAN sharing is the opt-in way to give a model to a peer."""

    def available(self):
        return False

    def fetch(self, magnet, dest_dir, name, sha, size, progress=None):
        raise RuntimeError("BitTorrent is off. The magnet was not fetched and nothing was seeded.")


class StubTorrent(TorrentClient):
    def available(self):
        return False


class Aria2Torrent(TorrentClient):
    """aria2c, only when the owner set model_store_torrent and the binary is already installed.
    --seed-time=0 so finishing a download does not keep uploading it."""

    def available(self):
        return shutil.which("aria2c") is not None and torrent_enabled()

    def command(self, magnet, dest_dir):
        return ["aria2c", "--dir", dest_dir, "--seed-time=0", "--allow-overwrite=true",
                "--summary-interval=0", "--bt-stop-timeout=120", "--disable-ipv6=true",
                "--follow-torrent=mem", magnet]

    def fetch(self, magnet, dest_dir, name, sha, size, progress=None):
        if not self.available():
            raise RuntimeError("BitTorrent is off. The magnet was not fetched and nothing was seeded.")
        os.makedirs(dest_dir, exist_ok=True)
        activity("torrent", "fetching a magnet with the local client; seeding stays off", network=True)
        proc = subprocess.run(self.command(magnet, dest_dir), capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0:
            raise RuntimeError("the torrent client failed: " + (proc.stderr or proc.stdout or "")[-200:])
        found = os.path.join(dest_dir, name)
        if not os.path.isfile(found):
            cands = [os.path.join(dest_dir, n) for n in os.listdir(dest_dir) if n != name]
            files = [p for p in cands if os.path.isfile(p)]
            if len(files) == 1:
                found = files[0]
            else:
                raise RuntimeError("the torrent finished but the named file was not there")
        return found


def torrent_enabled():
    return bool(config.settings.get("model_store_torrent"))


def torrent_client():
    if torrent_enabled() and shutil.which("aria2c"):
        return Aria2Torrent()
    return StubTorrent()


# ---------------------------------------------------------------- import

_HASH_LINE = re.compile(r"^([0-9a-fA-F]{64})(?:\s+(\d+))?\s+\*?(\S.*?)\s*$")


def parse_manifest_txt(text):
    """MANIFEST.txt: header lines 'name: Qwen', then 'sha256  size  file' or a sha256sum line."""
    headers, files = {}, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            line = line[1:].strip()
            if not line:
                continue
        hashed = _HASH_LINE.match(line)
        if hashed and not (":" in line and not files and not re.match(r"^[0-9a-fA-F]{64}\b", line)):
            size = int(hashed.group(2)) if hashed.group(2) else None
            files.append({"sha256": hashed.group(1).lower(), "size": size, "name": hashed.group(3).strip()})
            continue
        if not files and ":" in line:
            key, _, val = line.partition(":")
            headers[key.strip().lower()] = val.strip()
    return headers, files


def _format_of(name, header):
    """The manifest's format, unless a file's extension is a different one of the three."""
    low = name.lower()
    ext = "gguf" if low.endswith(".gguf") else "nvfp4" if low.endswith(".nvfp4") else "mlx" if low.endswith(".mlx") else ""
    if header in FORMATS:
        return ext if ext and ext != header else header
    return ext


def import_folder(folder, progress=None):
    """Hash the folder the owner pointed at, check MANIFEST.txt, and keep the files only when they match."""
    folder = os.path.realpath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        raise ValueError("that folder is not there")
    man_path = os.path.join(folder, "MANIFEST.txt")
    if not os.path.isfile(man_path):
        alt = os.path.join(folder, "manifest.txt")
        man_path = alt if os.path.isfile(alt) else ""
    if not man_path:
        raise ValueError("that folder has no MANIFEST.txt")
    headers, listed = parse_manifest_txt(open(man_path, encoding="utf-8", errors="replace").read())
    if not listed:
        raise ValueError("MANIFEST.txt lists no files")
    fmt = ""
    files = []
    for one in listed:
        if not _safe_name(one["name"]):
            raise ValueError("MANIFEST.txt names a file outside the folder")
        src = os.path.join(folder, one["name"])
        if not file_allowed(src, [folder]):
            raise ValueError(f"{one['name']} is not in that folder")
        kind = _format_of(one["name"], headers.get("format", "").lower())
        fmt = fmt or kind
        if kind and fmt and kind != fmt:
            raise ValueError("the folder mixes gguf, mlx, and nvfp4")
        digest = sha256_file(src)
        if progress:
            progress("verify", 1, 1)
        if digest != one["sha256"]:
            raise RuntimeError(f"{one['name']} does not match the sha256 in MANIFEST.txt; nothing was imported")
        size = os.path.getsize(src)
        if one["size"] is not None and one["size"] != size:
            raise RuntimeError(f"{one['name']} size does not match MANIFEST.txt; nothing was imported")
        files.append({"name": os.path.basename(one["name"]), "sha256": digest, "size": size, "_src": src})
    if fmt not in FORMATS:
        raise ValueError("the files are not gguf, mlx, or nvfp4")
    name = headers.get("name") or os.path.basename(folder)
    manifest = {"format_version": 1, "name": name, "version": headers.get("version") or "1",
                "format": fmt, "quant": headers.get("quant", ""),
                "license": headers.get("license") or "unspecified",
                "files": [{"name": f["name"], "sha256": f["sha256"], "size": f["size"]} for f in files],
                "sources": ["file://" + folder + "/"], "publisher": "", "signature": "", "trust": "owner-import"}
    validate_manifest(manifest)
    mid = _slug(name, manifest["version"])
    _require_space(sum(f["size"] for f in files))
    paths = _commit_files(mid, files, progress)
    row = remember(manifest, paths)
    _register_catalog(manifest, paths)
    activity("import", f"imported {name} from {folder}; hashes matched", network=False)
    return row


def _require_space(nbytes):
    path = config.MODELS if os.path.isdir(config.MODELS) else config.data_dir()
    try:
        os.makedirs(path, exist_ok=True)
        st = os.statvfs(path)
    except OSError as e:
        raise ValueError("the models folder cannot be written") from e
    free = st.f_bavail * st.f_frsize
    if free < nbytes + 64 * 1024 * 1024:
        raise ValueError("not enough free disk for that model")


def _commit_files(mid, files, progress=None):
    """Copy each file to a .part, check the hash again, then publish them together."""
    dest_dir = os.path.join(config.MODELS, "store", mid)
    os.makedirs(dest_dir, exist_ok=True)
    staged = []
    try:
        for one in files:
            part = os.path.join(dest_dir, one["name"] + ".part")
            copy_resume(one["_src"], part, one["size"], progress)
            place_verified(part, os.path.join(dest_dir, one["name"]), one["sha256"], one["size"])
            staged.append(one["name"])
    except Exception:
        for name in staged:
            try:
                os.unlink(os.path.join(dest_dir, name))
            except OSError:
                pass
        raise
    return {one["name"]: os.path.join(dest_dir, one["name"]) for one in files}


def _register_catalog(manifest, paths):
    """A single GGUF can be selected with the existing model switch. MLX and NVFP4 stay in the store."""
    if manifest.get("format") != "gguf":
        return None
    ggufs = [f for f in manifest["files"] if f["name"].lower().endswith(".gguf")]
    if len(ggufs) != 1:
        return None
    one = ggufs[0]
    dest = paths.get(one["name"])
    if not dest:
        return None
    from . import models
    builtin = {m.get("id") for m in config.load_json(models.CATALOG_PATH, [])}
    mid = _slug(manifest["name"], manifest["version"])
    if mid in builtin:
        mid = (mid + "-store")[:60]
    rel = os.path.relpath(dest, config.MODELS)
    entry = {"id": mid, "name": manifest["name"], "maker": fingerprint(manifest.get("publisher") or "") or "you",
             "origin": "model store", "license": manifest.get("license") or "", "repo": "", "file": rel,
             "size": one["size"], "sha256": one["sha256"], "ram_gb": max(2, round(one["size"] / 1024 ** 3) + 1),
             "store": True, "note": "from the model store, checked by hash",
             "speed": "", "good_at": [], "limits": ["kept only because its hash matched"]}
    try:
        models.add_catalog_entry(entry)
    except ValueError:
        return None
    return entry


# ---------------------------------------------------------------- fetch

def _fetch_one(manifest, one, consent, progress, allow_loopback, roots):
    dest_dir = os.path.join(config.MODELS, "store", _slug(manifest["name"], manifest["version"]))
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, one["name"])
    if os.path.isfile(dest) and os.path.getsize(dest) == one["size"] and sha256_file(dest) == one["sha256"]:
        activity("have", one["name"] + " already matches", network=False)
        return dest
    if os.path.isfile(dest):
        os.replace(dest, dest + ".bad")
        activity("rejected", one["name"] + " was on disk but did not match; set aside", network=False)
    part = dest + ".part"
    errors = []
    for src in sources_for(manifest, one):
        kind = classify_source(src)
        try:
            if kind == "file":
                if not consent.get("file", True):
                    continue
                path = file_path_of(src)
                if not file_allowed(path, roots):
                    activity("refused", "a file source is outside the folders you approved", network=False)
                    errors.append("file source refused")
                    continue
                activity("copy", path, network=False)
                copy_resume(path, part, one["size"], progress)
            elif kind == "http":
                if not consent.get("http"):
                    activity("skipped", "HTTP was not asked for: " + urllib.parse.urlparse(src).hostname, network=False)
                    continue
                activity("fetch", src, network=True)
                download_http(src, part, one["size"], progress, allow_loopback=allow_loopback)
            elif kind == "lan":
                if not consent.get("lan"):
                    activity("skipped", "not looking at peers", network=False)
                    continue
                url = _lan_to_http(src)
                activity("fetch", url, network=True)
                download_http(url, part, one["size"], progress, allow_loopback=allow_loopback)
            else:
                if not consent.get("torrent") or not torrent_enabled():
                    activity("torrent-off", "magnet recorded, not fetched; BitTorrent is off and nothing is seeded",
                             network=False)
                    errors.append("torrent off")
                    continue
                client = torrent_client()
                got = client.fetch(src, dest_dir + ".torrent", one["name"], one["sha256"], one["size"], progress)
                copy_resume(got, part, one["size"], progress)
            return place_verified(part, dest, one["sha256"], one["size"])
        except Exception as e:
            errors.append(str(e)[:160])
            try:
                if os.path.exists(part) and (one["size"] is None or os.path.getsize(part) > one["size"]):
                    os.unlink(part)
            except OSError:
                pass
            activity("failed", f"{kind}: {e}"[:240], network=kind in ("http", "lan", "magnet"))
    raise RuntimeError("could not fetch " + one["name"] + (": " + "; ".join(errors[:3]) if errors else ""))


def _lan_to_http(src):
    """lan://192.168.1.5:8766/<sha>/<name> -> http://192.168.1.5:8766/blob/<sha>."""
    rest = src[len("lan://"):]
    hostport, _, tail = rest.partition("/")
    host, _, port = hostport.partition(":")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as e:
        raise ValueError("a peer address must be an IP") from e
    if ip.is_loopback:
        if not getattr(_http_ctx, "allow_loopback", False):
            raise ValueError("refusing a peer on loopback")
    elif not (ip.is_private and not ip.is_link_local and not ip.is_reserved):
        raise ValueError("a peer must be on this network")
    sha = tail.split("/", 1)[0]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("a peer link needs the file's sha256")
    use_port = port or str(PORT)
    if not use_port.isdigit() or not (1 <= int(use_port) <= 65535):
        raise ValueError("bad peer port")
    return f"http://{host}:{int(use_port)}/blob/{sha}"


def _iter_manifest_files(root, depth=2):
    if depth < 0 or not os.path.isdir(root) or os.path.islink(root):
        return
    for name in ("MANIFEST.txt", "manifest.txt"):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            yield path
    try:
        names = os.listdir(root)[:200]
    except OSError:
        return
    for name in names:
        path = os.path.join(root, name)
        if os.path.isdir(path) and not os.path.islink(path):
            yield from _iter_manifest_files(path, depth - 1)


def find_local(name, roots):
    hits = by_name(name)
    if hits:
        return hits[-1]["manifest"], False
    for root in roots:
        if not os.path.isdir(root):
            continue
        for path in _iter_manifest_files(root):
            try:
                headers, listed = parse_manifest_txt(open(path, encoding="utf-8", errors="replace").read())
            except OSError:
                continue
            if str(headers.get("name", "")).casefold() == name.strip().casefold():
                row = import_folder(os.path.dirname(path))
                return row["manifest"], False
    return None, False


def configured_indexes():
    raw = config.settings.get("model_store_indexes") or []
    if not isinstance(raw, list):
        return []
    out = []
    for url in raw:
        if isinstance(url, str) and url.startswith("https://") and http_allowed(url):
            out.append(url)
    return out


def _load_index_url(url, allow_loopback):
    activity("index", url, network=True)
    _http_ctx.allow_loopback = allow_loopback
    req = urllib.request.Request(url if url.endswith(".json") else url.rstrip("/") + "/index.json",
                                 headers={"User-Agent": USER_AGENT})
    with _opener().open(req, timeout=20) as resp:
        data = resp.read(2_000_000)
    parsed = json.loads(data.decode("utf-8"))
    rows = parsed.get("models") if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list):
        raise ValueError("index was not a list of manifests")
    return rows


def install(name, consent=None, progress=None, allow_loopback=False, roots=None, discover_packets=None,
            removable=True):
    """Fetch name from the store. consent defaults to what "install … from the store" means:
    local files, HTTP mirrors named by a signed manifest, and a short listen for LAN peers.
    BitTorrent stays off unless the owner turned it on. Nothing is used until every hash matches."""
    consent = dict(consent or {"file": True, "http": True, "lan": True, "torrent": torrent_enabled()})
    roots = approved_roots(roots, removable=removable)
    manifest, from_network = find_local(name, roots if consent.get("file", True) else [])
    if manifest is None and consent.get("http"):
        for url in configured_indexes():
            try:
                for row in _load_index_url(url, allow_loopback):
                    if isinstance(row, dict) and str(row.get("name", "")).casefold() == name.strip().casefold():
                        manifest, from_network = row, True
                        break
            except Exception as e:
                activity("index-failed", str(e)[:200], network=True)
            if manifest:
                break
    if manifest is None and consent.get("lan"):
        activity("lan-discover", "listening on this network for a few seconds", network=True)
        manifest = _manifest_from_peers(name, discover_packets, allow_loopback)
        from_network = manifest is not None
    if manifest is None:
        known = ", ".join(sorted({(r.get("manifest") or {}).get("name", "") for r in index() if r.get("manifest")})) or "none yet"
        raise ValueError(f"'{name}' is not in the store. Imported here: {known}. "
                         "Plug in the drive and say import models from that folder, or add a signed manifest.")
    ok, reason = accept_manifest(manifest, from_network)
    if not ok:
        activity("rejected", reason, network=from_network)
        raise ValueError(reason)
    _require_space(sum(f["size"] for f in manifest["files"]))
    paths = {}
    for one in manifest["files"]:
        paths[one["name"]] = _fetch_one(manifest, one, consent, progress, allow_loopback, roots)
    # A file is in paths only after place_verified. Check once more before it can be selected.
    for one in manifest["files"]:
        if sha256_file(paths[one["name"]]) != one["sha256"]:
            os.replace(paths[one["name"]], paths[one["name"]] + ".bad")
            raise RuntimeError("a file changed after it was checked; it was not kept")
    row = remember(manifest, paths)
    _register_catalog(manifest, paths)
    how = "signed by " + fingerprint(manifest.get("publisher", "")) if manifest.get("signature") else "imported, hashes matched"
    activity("installed", f"{manifest['name']} {manifest['version']} ({how})", network=False)
    return row


def verify():
    """Re-hash every stored file. A mismatch is moved aside so it cannot be loaded."""
    bad, good = [], 0
    for row in index():
        man = row.get("manifest") or {}
        ok, reason = accept_manifest(man, bool(man.get("signature")) and man.get("trust") != "owner-import")
        if man.get("signature") and not verify_manifest(man):
            bad.append(man.get("name", "?") + ": signature does not match")
            continue
        if not ok and man.get("trust") != "owner-import":
            bad.append(man.get("name", "?") + ": " + reason)
            continue
        for one in man.get("files") or []:
            path = (row.get("paths") or {}).get(one["name"], "")
            if not path or not os.path.isfile(path) or sha256_file(path) != one["sha256"] or os.path.getsize(path) != one["size"]:
                if path and os.path.isfile(path):
                    os.replace(path, path + ".bad")
                bad.append(f"{man.get('name', '?')}: {one['name']} does not match and will not be used")
            else:
                good += 1
    activity("verify", f"{good} file(s) match" + (f"; {len(bad)} problem(s)" if bad else ""), network=False)
    if bad:
        return "Checked the store. These will not be used:\n" + "\n".join("- " + b for b in bad)
    if good == 0:
        return "The store is empty. Say import models from a folder, or install a model from the store."
    return f"Checked the store: {good} file(s) match their hashes."


# ---------------------------------------------------------------- peers (opt-in)

def lan_ips():
    ips = []
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for ip in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)/", out):
        addr = ipaddress.ip_address(ip)
        if addr.is_private and not addr.is_loopback and not addr.is_link_local and not addr.is_reserved:
            ips.append(ip)
    return ips


def sharing():
    return _SHARE.get("server") is not None


def peer_allowed(ip, allow_loopback=False):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.is_loopback:
        return bool(allow_loopback)
    return bool(addr.is_private and not addr.is_link_local and not addr.is_reserved and not addr.is_multicast)


def _sign_owned():
    """Sign imported manifests with this computer's key so a peer can verify them. Unsigned ones are not served."""
    key = ensure_local_key()
    pub = pubkey_of(key)
    changed = False
    rows = index()
    for row in rows:
        man = row.get("manifest") or {}
        if man.get("signature"):
            continue
        if man.get("trust") != "owner-import":
            continue
        body = dict(man)
        body["publisher"] = pub
        body["trust"] = "owner-import"
        row["manifest"] = sign_manifest(body, key)
        row["id"] = manifest_id(row["manifest"])
        changed = True
    if changed:
        _save_index(rows)
        activity("sign", "signed imported models with this computer's key so peers can verify them", network=False)


def _make_handler(allow_loopback):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            peer = self.client_address[0] if self.client_address else "?"
            activity("peer", f"{peer} {args[0] if args else ''}"[:240], network=True)

        def _deny(self, code, text):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            peer = self.client_address[0] if self.client_address else ""
            if not peer_allowed(peer, allow_loopback):
                self._deny(403, "this store only answers peers on the local network\n")
                return
            path = urllib.parse.urlparse(self.path).path
            if path == "/hello":
                body = json.dumps(_hello_body()).encode("utf-8")
                self._send(200, "application/json", body)
                return
            if path.startswith("/manifest/"):
                mid = path[len("/manifest/"):]
                if not re.fullmatch(r"[0-9a-f]{64}", mid):
                    self._deny(404, "not found\n")
                    return
                for row in index():
                    if row.get("id") == mid and (row.get("manifest") or {}).get("signature"):
                        body = json.dumps(row["manifest"]).encode("utf-8")
                        self._send(200, "application/json", body)
                        return
                self._deny(404, "not found\n")
                return
            if path.startswith("/blob/"):
                sha = path[len("/blob/"):]
                if not re.fullmatch(r"[0-9a-f]{64}", sha):
                    self._deny(404, "not found\n")
                    return
                found = _blob_path(sha)
                if not found:
                    self._deny(404, "not found\n")
                    return
                if sha256_file(found) != sha:
                    self._deny(409, "this file no longer matches its hash and was not sent\n")
                    return
                length = os.path.getsize(found)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(length))
                self.send_header("Connection", "close")
                self.end_headers()
                with open(found, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return
            self._deny(404, "not found\n")

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _hello_body():
    models = []
    for row in index():
        man = row.get("manifest") or {}
        if not man.get("signature"):
            continue
        models.append({"name": man.get("name"), "version": man.get("version"), "id": row.get("id"),
                       "publisher": fingerprint(man.get("publisher", ""))})
    return {"llmos_model_store": 1, "name": str(config.settings.get("model_share_name") or "this computer")[:40],
            "port": _SHARE.get("port") or PORT, "models": models}


def _blob_path(sha):
    root = os.path.realpath(config.MODELS)
    for row in index():
        for one in (row.get("manifest") or {}).get("files") or []:
            if one.get("sha256") != sha:
                continue
            path = (row.get("paths") or {}).get(one["name"], "")
            try:
                real = os.path.realpath(path)
            except OSError:
                continue
            if real.startswith(root + os.sep) and os.path.isfile(real) and not os.path.islink(path):
                return real
    return ""


def start_share(host=None, port=PORT):
    """Listen for peers. Off until the owner says so. Binds a private address, never a public one."""
    if sharing():
        return f"already sharing at {_SHARE['host']}:{_SHARE['port']}"
    explicit = host is not None
    if host is None:
        ips = lan_ips()
        if not ips:
            raise ValueError("there is no private network address to share on. Nothing is listening.")
        host = ips[0]
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as e:
        raise ValueError("share only binds to an IP address") from e
    if addr.is_loopback:
        if not explicit:
            raise ValueError("there is no private network address to share on. Nothing is listening.")
    elif not (addr.is_private and not addr.is_link_local and not addr.is_reserved):
        raise ValueError("sharing only binds to a private network address. Nothing is listening.")
    _sign_owned()
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer((host, port), _make_handler(addr.is_loopback))
    bound = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, name="llmos-model-share", daemon=True)
    thread.start()
    _SHARE["server"] = httpd
    _SHARE["host"] = host
    _SHARE["port"] = bound
    try:
        config.settings.set("model_share", True)
    except OSError:
        pass
    activity("share-on", f"listening on {host}:{bound}. This network only. Say stop sharing my models to turn it off.",
             network=True)
    try:
        _announce(host, bound)
    except OSError as e:
        activity("announce-failed", str(e)[:200], network=True)
    return (f"Sharing is on at {host}:{bound}. Peers on this network can verify your models. "
            "Nothing is sent to the internet. Say “stop sharing my models” to turn it off.")


def stop_share():
    srv = _SHARE.get("server")
    _SHARE["server"] = None
    if srv is not None:
        srv.shutdown()
        srv.server_close()
    try:
        config.settings.set("model_share", False)
    except OSError:
        pass
    activity("share-off", "sharing is off. Nothing is listening.", network=False)
    return "Sharing is off. Nothing is listening."


def _announce(host, port):
    """One UDP broadcast on the local subnet. No public address, no payload beyond the model names and hashes."""
    body = json.dumps(_hello_body()).encode("utf-8")
    if len(body) > 1400:
        body = json.dumps({"llmos_model_store": 1, "port": port, "models": _hello_body()["models"][:20]}).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((host, 0))
        sock.sendto(body, ("255.255.255.255", PORT))
        activity("announce", f"told this subnet that {len(_hello_body()['models'])} signed model(s) are available",
                 network=True)
    finally:
        sock.close()


def discover(timeout=1.5, packets=None, allow_loopback=False):
    """Packets the owner asked us to hear. packets=[(bytes, ip), ...] skips the socket (tests)."""
    if packets is None:
        packets = _listen(timeout)
    found = []
    for raw, ip in packets:
        if not peer_allowed(ip, allow_loopback):
            continue
        try:
            msg = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError, AttributeError):
            continue
        if not isinstance(msg, dict) or msg.get("llmos_model_store") != 1:
            continue
        msg["_from"] = ip
        found.append(msg)
    return found


def _listen(timeout):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    packets = []
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", PORT))
        sock.settimeout(timeout)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            packets.append((data, addr[0]))
    except OSError:
        pass
    finally:
        sock.close()
    return packets


def _manifest_from_peers(name, packets, allow_loopback):
    want = name.strip().casefold()
    for msg in discover(packets=packets, allow_loopback=allow_loopback):
        host = msg.get("_from")
        port = int(msg.get("port") or PORT)
        for model in msg.get("models") or []:
            if str(model.get("name", "")).casefold() != want:
                continue
            mid = str(model.get("id") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", mid):
                continue
            if not peer_allowed(host, allow_loopback):
                continue
            url = f"http://{host}:{port}/manifest/{mid}"
            activity("fetch", url, network=True)
            _http_ctx.allow_loopback = allow_loopback
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with _opener().open(req, timeout=10) as resp:
                    man = json.loads(resp.read(1_000_000).decode("utf-8"))
            except Exception as e:
                activity("failed", str(e)[:200], network=True)
                continue
            # Point file sources at the peer blob so the fetch path stays the checked one.
            if isinstance(man, dict) and isinstance(man.get("files"), list):
                for one in man["files"]:
                    if isinstance(one, dict) and re.fullmatch(r"[0-9a-f]{64}", str(one.get("sha256", ""))):
                        one.setdefault("sources", [])
                        one["sources"].append(f"lan://{host}:{port}/{one['sha256']}/{one.get('name', '')}")
            return man
    return None


# ---------------------------------------------------------------- words for the desk

def summary_lines():
    share = "on" if sharing() else "off"
    net = [e for e in activity_entries() if e.get("network")]
    last = net[-1]["detail"] if net else "none yet"
    names = sorted({(r.get("manifest") or {}).get("name", "") for r in index() if (r.get("manifest") or {}).get("name")})
    have = ", ".join(names) if names else "no models yet"
    return [f"Model store: {have}.",
            f"Sharing is {share}. It stays off until you say share my models.",
            f"Last network activity: {last}."]


def panel_blocks():
    """Text blocks for the models window. Buttons only say what the owner could type."""
    items = []
    for row in index():
        man = row.get("manifest") or {}
        signed = "signed" if man.get("signature") else "imported, hash checked"
        items.append({"title": man.get("name") or "model",
                      "subtitle": f"{man.get('format', '')} {man.get('quant', '')} · {man.get('version', '')} · {signed}".strip(),
                      "meta": fingerprint(man.get("publisher", "")) if man.get("publisher") else ""})
    if not items:
        items = [{"title": "No store models yet",
                  "subtitle": "Say “import models from /media/usb” or “install a model from the store”"}]
    share_on = sharing()
    return [{"type": "heading", "text": "Model store"},
            {"type": "text", "dim": True,
             "text": "Models are signed and checked by hash before they are used. "
                     "Nothing is fetched or shared until you ask. " + summary_lines()[1]},
            {"type": "list", "items": items},
            {"type": "buttons", "items": [
                {"label": "Verify", "say": "verify my models"},
                {"label": "Stop sharing" if share_on else "Share on this network",
                 "say": "stop sharing my models" if share_on else "share my models"},
                {"label": "Activity", "say": "what is the model store doing"}]}]


def list_text():
    if not index():
        return "The model store is empty. " + summary_lines()[1]
    lines = summary_lines()
    for row in index():
        man = row.get("manifest") or {}
        lines.append(f"- {man.get('name')} {man.get('version')} ({man.get('format')}, {man.get('license')})")
    return "\n".join(lines)
