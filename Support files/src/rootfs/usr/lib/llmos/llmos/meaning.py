"""Finding the owner's things by what they mean, not what they are called: "the photo of the dog on the beach",
"my letter about the car insurance". EmbeddingGemma 2 (Google, Apache-2.0) turns text and pictures into vectors on
this computer; similar meaning = nearby vectors. Nothing leaves the machine.

The model (310 MB, + 555 MB to understand pictures) is fetched on first use from llama.cpp's own conversions on
Hugging Face, pinned by SHA-256 like every model here, and served by a small llama-server of its own (a build new
enough for this model) that starts when needed and stops after a while unused. An index of the owner's documents,
notes and photos is kept in the vault; text is indexed as it is searched, pictures in the background (seconds each)."""
import array
import json
import math
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.request
import zipfile

from . import config, models

REPO, REV = "ggml-org/embeddinggemma-2-GGUF", "bfcd298762cc34d0357ece5ebdd31791a3a374d8"
TEXT = {"file": "embeddinggemma-2-Q8_0.gguf", "size": 309855456,
        "sha256": "2188ac1deca4b77dffefd603c2776a9d76d9d74ec01841392982ebb840b09135"}
VISION = {"file": "mmproj-embeddinggemma-2-Q8_0.gguf", "size": 554821024,
          "sha256": "c4a8a52691ecef40618438928bdf9e68379b854e24166f292592353db0aab64f"}
PORT = 8094
DIMS = 256                     # Matryoshka: the first 256 of 768 keep almost all the quality at a third of the size
IDLE_STOP = 600
SERVERS = ["/usr/lib/llmos/embed/llama-server", "/usr/local/bin/llama-server-embed"]
DOC_EXT = (".txt", ".md", ".pdf", ".docx", ".odt", ".rtf", ".html", ".htm", ".csv", ".json", ".xml", ".log", ".py", ".sh")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic")
FOLDERS = ["Documents", "Desktop", "Downloads", "Pictures", "Music", "Videos", "Projects"]

_lock = threading.Lock()
_proc = {"p": None, "vision": False, "last": 0.0}


def _dir():
    return os.path.join(config.MODELS, "embed")


def _file(m):
    return os.path.join(_dir(), m["file"])


def server_binary():
    return next((b for b in SERVERS if os.path.isfile(b) and os.access(b, os.X_OK)), None)


def available():
    """Can this computer search by meaning (a new enough llama-server is here)?"""
    return server_binary() is not None


def ready(vision=False):
    ok = os.path.exists(_file(TEXT))
    return ok and (not vision or os.path.exists(_file(VISION)))


def fetch(vision=False, progress=None):
    """Download the model (and the picture part when asked), verified before use. Raises with the reason."""
    if config.settings.get("internet") == "no":
        raise RuntimeError("the internet is switched off, so the search model can't be downloaded")
    os.makedirs(_dir(), exist_ok=True)
    for m in [TEXT] + ([VISION] if vision else []):
        dest = _file(m)
        if os.path.exists(dest) and models.verified(dest, m["sha256"]):
            continue
        if models.free_disk_gb(_dir()) < m["size"] / 1024 ** 3 + 0.3:
            raise RuntimeError("not enough free disk space for the search model")
        part = dest + ".part"
        cmd = ["curl", "-sSL", "--fail", "-C", "-", "--retry", "3", "-o", part, f"https://huggingface.co/{REPO}/resolve/{REV}/{m['file']}"]
        if config.settings.get("tor"):
            cmd[1:1] = ["--socks5-hostname", "127.0.0.1:9050"]
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
        while p.poll() is None:
            if progress:
                try:
                    progress(os.path.getsize(part), m["size"])
                except OSError:
                    pass
            time.sleep(1)
        if p.returncode != 0:
            raise RuntimeError("download failed: " + (p.stderr.read().strip() or f"curl {p.returncode}")[:200])
        if models.sha256_file(part) != m["sha256"]:
            os.unlink(part)
            raise RuntimeError(f"checksum mismatch for {m['file']}: deleted, not used")
        os.replace(part, dest)
        models._mark_verified(dest, m["sha256"])


def _up():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
            return b"ok" in r.read()
    except OSError:
        return False


def _start(vision):
    with _lock:
        p = _proc["p"]
        if p and p.poll() is None and (_proc["vision"] or not vision) and _up():
            _proc["last"] = time.time()
            return
        if p and p.poll() is None:
            p.terminate()
            p.wait(10)
        b = server_binary()
        if not b:
            raise RuntimeError("this system's model runtime is too old for the search model")
        argv = [b, "-m", _file(TEXT), "--embeddings", "--pooling", "mean", "--host", "127.0.0.1", "--port", str(PORT),
                "-t", str(max(1, (os.cpu_count() or 2) // 2)), "-c", "4096", "-b", "4096", "-ub", "4096", "--no-webui"]
        if vision and os.path.exists(_file(VISION)):
            argv += ["--mmproj", _file(VISION)]
        _proc["p"] = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        _proc["vision"] = "--mmproj" in argv
        for _ in range(120):
            if _up():
                break
            if _proc["p"].poll() is not None:
                raise RuntimeError("the search model did not start")
            time.sleep(0.5)
        _proc["last"] = time.time()
        threading.Thread(target=_idle_stop, daemon=True).start()


def _idle_stop():
    while True:
        time.sleep(30)
        p = _proc["p"]
        if not p or p.poll() is not None:
            return
        if time.time() - _proc["last"] > IDLE_STOP:
            p.terminate()
            return


def stop():
    p = _proc["p"]
    if p and p.poll() is None:
        p.terminate()


def _post(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        _proc["last"] = time.time()
        return json.load(r)


def _norm(v):
    v = list(v[:DIMS])
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed_texts(texts):
    _start(False)
    out = _post("/v1/embeddings", {"input": list(texts)})
    return [_norm(d["embedding"]) for d in sorted(out["data"], key=lambda d: d["index"])]


def embed_image(path):
    _start(True)
    import base64
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/props", timeout=5) as r:
        marker = json.load(r).get("media_marker", "<__media__>")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    out = _post("/embeddings", {"content": {"prompt_string": marker, "multimodal_data": [data]}})
    e = out[0]["embedding"] if isinstance(out, list) else out["embedding"]
    return _norm(e[0] if e and isinstance(e[0], list) else e)


# ------------------------------------------------------------------ the index

def _db():
    path = config.data("meaning.sqlite")
    config.guard_write(path)
    con = sqlite3.connect(path, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS items (path TEXT PRIMARY KEY, mtime REAL, kind TEXT, title TEXT, snippet TEXT, vec BLOB)")
    return con


def _text_of(path, limit=2000):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            r = subprocess.run(["pdftotext", "-l", "3", "-q", path, "-"], capture_output=True, text=True, timeout=60)
            return r.stdout[:limit]
        if ext in (".docx", ".odt"):
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml" if ext == ".docx" else "content.xml").decode("utf-8", "replace")
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))[:limit]
        if ext in (".html", ".htm", ".xml"):
            with open(path, encoding="utf-8", errors="replace") as f:
                return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", f.read(limit * 4)))[:limit]
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except (OSError, subprocess.SubprocessError, zipfile.BadZipFile, KeyError):
        return ""


def _candidates(kinds=("doc", "image", "other")):
    home = config.home()
    for name in FOLDERS:
        d = os.path.join(home, name)
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                p = os.path.join(root, f)
                low = f.lower()
                kind = "image" if low.endswith(IMG_EXT) else "doc" if low.endswith(DOC_EXT) else "other"
                if kind in kinds:
                    yield p, kind


def _pack(v):
    return array.array("f", v).tobytes()


def _unpack(b):
    a = array.array("f")
    a.frombytes(b)
    return a


def index(kinds=("doc", "other"), limit=400, progress=None):
    """Bring the index up to date for files of these kinds (new or changed ones only); returns how many were added."""
    con = _db()
    known = {p: m for p, m in con.execute("SELECT path, mtime FROM items")}
    todo = []
    for p, kind in _candidates(kinds):
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if known.get(p) != mt:
            todo.append((p, kind, mt))
    todo.sort(key=lambda x: -x[2])                 # the newest first
    todo = todo[:limit]
    done = 0
    batch = []
    for i, (p, kind, mt) in enumerate(todo):
        title = os.path.splitext(os.path.basename(p))[0].replace("_", " ").replace("-", " ")
        if kind == "image":
            try:
                v = embed_image(p)
            except Exception:
                continue
            con.execute("REPLACE INTO items VALUES (?,?,?,?,?,?)", (p, mt, kind, title, "", _pack(v)))
            con.commit()
            done += 1
        else:
            text = _text_of(p) if kind == "doc" else ""
            batch.append((p, kind, mt, title, text))
        if len(batch) >= 16 or (batch and i == len(todo) - 1):
            vecs = embed_texts([f"title: {t} | text: {x[:1500] or t}" for _, _, _, t, x in batch])
            for (bp, bk, bm, bt, bx), v in zip(batch, vecs):
                con.execute("REPLACE INTO items VALUES (?,?,?,?,?,?)", (bp, bm, bk, bt, " ".join(bx.split())[:200], _pack(v)))
            con.commit()
            done += len(batch)
            batch = []
        if progress:
            progress(i + 1, len(todo))
    # files that are gone leave the index
    gone = [p for p in known if not os.path.exists(p)]
    for p in gone:
        con.execute("DELETE FROM items WHERE path = ?", (p,))
    con.commit()
    con.close()
    return done


def search(query, kind="any", n=8, matches_only=False):
    """[(score, path, kind, snippet)] best first. matches_only: just the ones that stand out from the rest (a real
    match scores clearly above the typical file; when nothing does, there is no match, however close the best is)."""
    qv = embed_texts([f"task: search result | query: {query}"])[0]
    con = _db()
    rows = con.execute("SELECT path, kind, snippet, vec FROM items" + ("" if kind == "any" else " WHERE kind = ?"),
                       () if kind == "any" else ("image" if kind == "photos" else "doc",)).fetchall()
    con.close()
    scored = []
    for path, k, snip, vb in rows:
        if not os.path.exists(path):
            continue
        v = _unpack(vb)
        scored.append((sum(a * b for a, b in zip(qv, v)), path, k, snip))
    scored.sort(reverse=True)
    if matches_only and scored:
        mid = sorted(s for s, *_ in scored)[len(scored) // 2]
        top = scored[0][0]
        scored = [h for h in scored if h[0] >= mid + 0.05 and h[0] >= top - 0.04]
    return scored[:n]


def background_photos(stop_when=lambda: False):
    """Index the owner's pictures a few at a time while the computer is otherwise idle (seconds each)."""
    if not ready(vision=True) or not available():
        return 0
    added = 0
    while not stop_when():
        n = index(("image",), limit=5)
        if n == 0:
            break
        added += n
    return added
