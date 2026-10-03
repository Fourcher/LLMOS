"""On-device models: a catalog of official releases pinned by SHA-256,
download with verification, switching, and the llama-server launch line."""
import hashlib
import json
import os
import subprocess
import time

from . import config

CATALOG_PATH = os.path.join(config.SHARE, "catalog.json")


def catalog():
    return config.load_json(CATALOG_PATH, [])


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
        return m
    need = m["size"] / 1024 ** 3 + 0.5
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
    if m.get("draft_file"):
        _download_draft(m, progress)
    return m


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


def use(mid):
    if host_mode():
        raise ValueError(HOST_MODE_MSG)
    m = by_id(mid)
    if not m:
        raise ValueError(f"unknown model '{mid}'")
    if not os.path.exists(path_of(m)):
        raise ValueError(f"{m['name']} is not downloaded yet")
    if m.get("ram_gb", 0) > ram_gb() + 0.5:
        raise ValueError(f"{m['name']} needs about {m['ram_gb']} GB of memory; this machine has {ram_gb():.1f} GB")
    config.settings.set("model", m["id"])
    subprocess.run(["rc-service", "llmos-model", "restart"], capture_output=True)
    return m


def serve_argv():
    """Command line for llama-server with the active model. Bound to
    127.0.0.1: the model is reachable from this machine only."""
    m = active()
    if not m:
        return None
    threads = os.cpu_count() or 2
    spare = ram_gb() - m["size"] / 1024 ** 3 - 1.0
    # Context size from the RAM left after the weights (f16 KV cache: about
    # 110 KB per token for a 3B model, so 8k ~ 0.9 GB, 16k ~ 1.8 GB). A
    # quantized KV cache would fit more but makes CPU prompt processing
    # several times slower, which matters more than the extra room.
    # 6k is the floor that still fits a research request (prompt + tools
    # ~3.2k, search results + a page excerpt ~1k, answer) on a 4 GB machine.
    ctx = 16384 if spare > 2.5 else 8192 if spare > 1.6 else 6144 if spare > 0.5 else 4096
    argv = ["llama-server", "-m", path_of(m), "--host", "127.0.0.1", "--port", "8080",
            "--jinja", "-c", str(ctx), "-t", str(threads), "-np", "1",
            "--no-webui", "--no-slots", "--cache-reuse", "256", "--cache-ram", "0"]
    d = draft_path(m)
    if d and os.path.exists(d):
        # multi-token-prediction draft head: ~1.5x faster generation, same output
        argv += ["--spec-type", "draft-mtp", "-md", d]
    return argv


if __name__ == "__main__":
    print(json.dumps(serve_argv()))
