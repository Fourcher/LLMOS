"""On-device models: a catalog of official releases pinned by SHA-256,
download with verification, switching, and the llama-server launch line."""
import hashlib
import json
import os
import subprocess
import time

from . import config, system

CATALOG_PATH = os.path.join(config.SHARE, "catalog.json")


def _extra_path():
    # models the owner added through the refresh/discovery flow; kept with their data (inside the vault)
    return config.data("catalog-extra.json")


def catalog():
    """The built-in, hash-pinned models plus any the owner added. A built-in id always wins, so an added
    entry can never shadow a pinned one."""
    base = config.load_json(CATALOG_PATH, [])
    extra = config.load_json(_extra_path(), [])
    if not isinstance(extra, list) or not extra:
        return base
    ids = {m.get("id") for m in base}
    return base + [m for m in extra if isinstance(m, dict) and m.get("id") and m["id"] not in ids]


def added_ids():
    extra = config.load_json(_extra_path(), [])
    return {m.get("id") for m in extra if isinstance(m, dict)} if isinstance(extra, list) else set()


def add_catalog_entry(entry):
    """Add (or replace) an owner-added model in the extra catalog. Returns the stored entry.
    A built-in id is refused so a pinned model can never be overridden."""
    if entry.get("id") in {m.get("id") for m in config.load_json(CATALOG_PATH, [])}:
        raise ValueError(f"'{entry['id']}' is a built-in model already in the list")
    extra = config.load_json(_extra_path(), [])
    if not isinstance(extra, list):
        extra = []
    extra = [m for m in extra if isinstance(m, dict) and m.get("id") != entry["id"]]
    extra.append(entry)
    config.save_json(_extra_path(), extra)
    return entry


def by_id(mid):
    mid = (mid or "").lower().strip()
    for m in catalog():
        if m["id"] == mid:
            return m
    # forgiving match on name words ("ministral 8b", "gemma 12b")
    words = [w for w in mid.replace("-", " ").split() if w]
    hits = [m for m in catalog() if words and all(w in (m["id"] + " " + m["name"].lower()).replace("-", " ") for w in words)]
    return hits[0] if len(hits) == 1 else None


def path_of(m):
    return os.path.join(config.MODELS, m["file"])


def installed():
    return [m for m in catalog() if os.path.exists(path_of(m))]


def host_mode():
    """True when the VM launcher serves the model on the host's GPU."""
    return bool(config.host_model_id()) or os.path.exists(config.HOST_MODEL_URL_FILE)


def active():
    if host_mode():
        return by_id(config.host_model_id()) or {"id": "host", "name": "host model", "maker": "",
                                                    "origin": "", "license": "", "file": "", "size": 0,
                                                    "sha256": "", "ram_gb": 0, "note": ""}
    want = config.settings.get("model")
    inst = installed()
    for m in inst:
        if m["id"] == want:
            return m
    return inst[0] if inst else None


HOST_MODE_MSG = ("the model is served by the launcher on the host machine's GPU; choose it with "
                 "LLMOS_MODEL=<id> when starting LLM OS (see the models list for ids)")


def ram_gb():
    try:
        with open("/proc/meminfo") as f:
            for ln in f:
                if ln.startswith("MemTotal:"):
                    return int(ln.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 0


def free_disk_gb(path=None):
    if path is None:
        path = config.MODELS if os.path.isdir(config.MODELS) else "/"
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1024 ** 3


def sha256_file(path, progress=None):
    h = hashlib.sha256()
    total = os.path.getsize(path)
    done = 0
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
            done += len(block)
            if progress:
                progress("verify", done, total)
    return h.hexdigest()


def download(mid, progress=None):
    """Fetch a catalog model from its official repo and verify its SHA-256
    before it is ever loaded."""
    if host_mode():
        raise ValueError(HOST_MODE_MSG)
    m = by_id(mid)
    if not m:
        raise ValueError(f"unknown model '{mid}'")
    if os.path.exists(path_of(m)):
        if verified(path_of(m), m["sha256"], progress):
            return m
        os.unlink(path_of(m))           # a damaged or replaced file is never used: it is fetched again
    need = m["size"] / 1024 ** 3 + 0.5
    if _read_only(config.MODELS):
        raise ValueError("this is the live USB/DVD, whose models can't be changed; say \"install LLM OS\" first, "
                         "then models can be added and switched")
    if free_disk_gb() < need:
        raise ValueError(f"not enough disk space: {m['name']} needs {need:.1f} GB free")
    os.makedirs(config.MODELS, exist_ok=True)
    part = path_of(m) + ".part"
    url = f"https://huggingface.co/{m['repo']}/resolve/main/{m['file']}"
    cmd = ["curl", "-sSL", "--fail", "-C", "-", "--retry", "3", "-o", part, url]
    if config.settings.get("tor"):
        cmd[1:1] = ["--socks5-hostname", "127.0.0.1:9050"]
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
    while p.poll() is None:
        if progress:
            try:
                progress("download", os.path.getsize(part), m["size"])
            except OSError:
                pass
        time.sleep(1)
    if p.returncode != 0:
        raise RuntimeError("download failed: " + (p.stderr.read().strip() or f"curl exit {p.returncode}")[:300])
    digest = sha256_file(part, progress)
    if digest != m["sha256"]:
        os.unlink(part)
        raise RuntimeError(f"checksum mismatch for {m['file']}: file deleted, nothing was loaded")
    os.replace(part, path_of(m))
    _mark_verified(path_of(m), m["sha256"])
    if m.get("draft_file"):
        _download_draft(m, progress)
    return m


def _read_only(path):
    """True when nothing new can be written here (the live medium bind-mounts the models folder read-only)."""
    d = path if os.path.isdir(path) else os.path.dirname(path) or "/"
    try:
        probe = os.path.join(d, ".llmos-wtest")
        fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        os.unlink(probe)
        return False
    except OSError:
        return os.path.isdir(d)        # exists but cannot be written to


def _stamp(path, sha):
    st = os.stat(path)
    return f"{st.st_size}:{int(st.st_mtime)}:{sha}"


def _mark_verified(path, sha):
    try:
        with open(path + ".verified", "w") as f:
            f.write(_stamp(path, sha))
    except OSError:
        pass                            # a read-only medium (the live ISO): it is simply checked again next time


def verified(path, sha, progress=None):
    """Does a model file on disk match its pinned SHA-256? Hashed once per version of the file (size and time)."""
    try:
        if open(path + ".verified").read().strip() == _stamp(path, sha):
            return True
    except OSError:
        pass
    if sha256_file(path, progress) != sha:
        return False
    _mark_verified(path, sha)
    return True


def draft_path(m):
    return os.path.join(config.MODELS, m["draft_file"]) if m.get("draft_file") else None


def _download_draft(m, progress=None):
    """The model's speculative-decoding draft head (Gemma 4 ships one): a
    small file from the same official repo, verified like the model. Optional:
    the model works without it, just slower."""
    dest = draft_path(m)
    if os.path.exists(dest):
        return
    part = dest + ".part"
    url = f"https://huggingface.co/{m['draft_repo']}/resolve/main/{m['draft_file']}"
    cmd = ["curl", "-sSL", "--fail", "-C", "-", "--retry", "3", "-o", part, url]
    if config.settings.get("tor"):
        cmd[1:1] = ["--socks5-hostname", "127.0.0.1:9050"]
    if subprocess.run(cmd, capture_output=True).returncode != 0:
        return
    if sha256_file(part) != m["draft_sha256"]:
        os.unlink(part)
        return
    os.replace(part, dest)


def remove(mid):
    m = by_id(mid)
    if not m or not os.path.exists(path_of(m)):
        raise ValueError(f"'{mid}' is not installed")
    if active() and active()["id"] == m["id"]:
        raise ValueError("that model is in use; switch to another one first")
    os.unlink(path_of(m))
    return m


def _bigger_than_ram(m, mem):
    """A model that needs more memory than the machine has. Unknown memory (0) is never 'bigger'."""
    return mem > 0 and m.get("ram_gb", 0) > mem + 0.5


def use(mid):
    if host_mode():
        raise ValueError(HOST_MODE_MSG)
    m = by_id(mid)
    if not m:
        raise ValueError(f"unknown model '{mid}'")
    if not os.path.exists(path_of(m)):
        raise ValueError(f"{m['name']} is not downloaded yet")
    mem = ram_gb()
    if m.get("ram_gb", 0) > mem + 0.5:
        if mem <= 0:
            # memory size unknown: the refusal stays exactly as it was
            raise ValueError(f"{m['name']} needs about {m['ram_gb']} GB of memory; this machine has {mem:.1f} GB")
        # bigger than memory: allowed, disclosed. llama-server maps the file from disk, so it runs, much slower.
        m = dict(m, bigger_than_ram_note=f"This model is bigger than memory ({m['ram_gb']} GB vs {mem:.1f} GB). "
                                         "It will run from disk, much slower.")
    config.settings.set("model", m["id"])
    system.service("llmos-model", "restart", timeout=60)
    return m


def serve_argv():
    """Command line for llama-server with the active model. Bound to
    127.0.0.1: the model is reachable from this machine only."""
    m = active()
    if not m:
        return None
    threads = os.cpu_count() or 2
    spare = ram_gb() - m["size"] / 1024 ** 3 - 1.0
    big = _bigger_than_ram(m, ram_gb())   # runs from disk: smallest context, and no pinning or no-mmap flags, ever
    # Context size from the RAM left after the weights (f16 KV cache: about
    # 110 KB per token for a 3B model, so 8k ~ 0.9 GB, 16k ~ 1.8 GB). A
    # quantized KV cache would fit more but makes CPU prompt processing
    # several times slower, which matters more than the extra room.
    # 6k is the floor that still fits a research request (prompt + tools
    # ~3.2k, search results + a page excerpt ~1k, answer) on a 4 GB machine.
    ctx = 4096 if big and spare <= 0 else 16384 if spare > 2.5 else 8192 if spare > 1.6 else 6144 if spare > 0.5 else 4096
    argv = ["llama-server", "-m", path_of(m), "--host", "127.0.0.1", "--port", "8080",
            "--jinja", "-c", str(ctx), "-t", str(threads), "-np", "1",
            "--no-webui", "--no-slots", "--cache-reuse", "256",
            # with memory to spare, earlier prompts are kept in RAM: a side job (a translation, a style, a decision) no
            # longer pushes out the main prompt, which a CPU would otherwise read again for minutes
            "--cache-ram", "1024" if spare > 4.0 else "512" if spare > 3.0 else "0"]
    if m.get("chat_kwargs"):                     # e.g. a model that thinks before answering by default: off, for CPU speed
        argv += ["--chat-template-kwargs", json.dumps(m["chat_kwargs"], separators=(",", ":"))]  # no spaces: exec $argv word-splits
    d = draft_path(m)
    if d and os.path.exists(d):
        # multi-token-prediction draft head: ~1.5x faster generation, same output
        argv += ["--spec-type", "draft-mtp", "-md", d]
    return argv


if __name__ == "__main__":
    print(json.dumps(serve_argv()))
