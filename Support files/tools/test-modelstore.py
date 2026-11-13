#!/usr/bin/env python3
"""The decentralized model store: signed manifests, hash checks, import, resume, and opt-in sharing.

No network beyond 127.0.0.1. Run: python3 tools/test-modelstore.py
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-store-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_LIB"] = os.path.join(home, "var")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
os.environ["LLMOS_RUN"] = os.path.join(home, "run")
from llmos import config, intent, modelstore  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


# the light gate finds this file because it imports modelstore and names modelstore.py
check("modelstore.py" in os.path.basename(modelstore.__file__), "this test reads modelstore.py")
check(modelstore.DEFAULT_INDEXES == (), "there is no built-in index to phone")
check(modelstore.configured_indexes() == [], "an owner who added nothing has no index URLs")
check(modelstore.sharing() is False, "sharing is off until asked")
check(config.PUBLIC_DEFAULTS.get("model_share") is False, "the setting defaults to not sharing")
check(config.PUBLIC_DEFAULTS.get("model_store_torrent") is False, "BitTorrent defaults to off")


def http_ok(url, loop=False):
    return modelstore.http_allowed(url, allow_loopback=loop)


check(http_ok("https://huggingface.co/org/repo/resolve/main/m.gguf"), "an https mirror is allowed")
check(not http_ok("http://huggingface.co/org/repo/resolve/main/m.gguf"), "plain http to a public name is refused")
check(http_ok("http://192.168.1.9:8766/blob/ab"), "a private-network mirror is allowed")
check(not http_ok("http://169.254.169.254/latest"), "link-local metadata is refused")
check(not http_ok("http://127.0.0.1/m"), "loopback is refused unless a test asks")
check(http_ok("http://127.0.0.1/m", loop=True), "loopback is allowed when the caller asked")
check(not http_ok("file:///etc/passwd"), "a file URL is not an HTTP source")
check(not http_ok("http://user:pw@192.168.1.9/m"), "a URL with a password is refused")
check(not modelstore.file_allowed("/etc/passwd", ["/media", config.MODELS]), "a system file is not a model source")

# --- sign, tamper, import ---
key = os.path.join(home, "publisher")
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "t", "-f", key], check=True)
pub = modelstore.pubkey_of(key)
blob = b"gguf-bytes"
digest = hashlib.sha256(blob).hexdigest()
folder = os.path.join(home, "usb")
os.makedirs(folder)
open(os.path.join(folder, "qwen.gguf"), "wb").write(blob)
open(os.path.join(folder, "MANIFEST.txt"), "w", encoding="utf-8").write(
    "name: Qwen3.8-27B\nversion: 1\nformat: gguf\nquant: Q4_K_M\nlicense: apache-2.0\n"
    f"{digest}  {len(blob)}  qwen.gguf\n")
row = modelstore.import_folder(folder)
man = row["manifest"]
check(man["name"] == "Qwen3.8-27B" and man["format"] == "gguf" and man["quant"] == "Q4_K_M",
      "import builds a manifest from MANIFEST.txt")
check(man["trust"] == "owner-import" and not man.get("signature"), "an import is unsigned until this computer signs it")
stored = row["paths"]["qwen.gguf"]
check(os.path.isfile(stored) and open(stored, "rb").read() == blob, "the file is kept only after the hash matches")
check(any(m["id"].startswith("qwen") and m.get("store") for m in __import__("llmos").models.catalog()),
      "a GGUF import is added to the on-device catalog")

bad_dir = os.path.join(home, "badusb")
os.makedirs(bad_dir)
open(os.path.join(bad_dir, "qwen.gguf"), "wb").write(b"nope")
open(os.path.join(bad_dir, "MANIFEST.txt"), "w", encoding="utf-8").write(
    f"name: Other\nformat: gguf\nlicense: mit\n{digest}  4  qwen.gguf\n")
try:
    modelstore.import_folder(bad_dir)
    check(False, "a mismatched folder is not imported")
except RuntimeError as e:
    check("nothing was imported" in str(e), "a mismatched hash imports nothing")
check(not modelstore.by_name("Other"), "a failed import is not in the store")

escape = os.path.join(home, "escape")
os.makedirs(escape)
open(os.path.join(escape, "MANIFEST.txt"), "w", encoding="utf-8").write(
    f"name: Escape\nformat: gguf\nlicense: mit\n{digest}  {len(blob)}  ../qwen.gguf\n")
try:
    modelstore.import_folder(escape)
    check(False, "a path outside the folder is refused")
except ValueError:
    check(True, "a path outside the folder is refused")

signed = modelstore.sign_manifest(dict(man, publisher=pub, trust="owner-import"), key)
check(modelstore.verify_manifest(signed), "a signature verifies")
tampered = dict(signed, name="Not-Qwen")
check(not modelstore.verify_manifest(tampered), "changing the name breaks the signature")
ok, reason = modelstore.accept_manifest(dict(signed, signature=""), True)
check(not ok and "signed" in reason, "a network manifest without a signature is refused")

# --- resume and hash gate over HTTP ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = self.server.data
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            body = data[start:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            body = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):
        pass


httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
httpd.data = blob
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{httpd.server_address[1]}/qwen.gguf"
part = os.path.join(home, "resume.part")
open(part, "wb").write(blob[:4])
modelstore.download_http(base, part, len(blob), allow_loopback=True)
check(open(part, "rb").read() == blob, "an HTTP download resumes from the bytes already on disk")
dest = os.path.join(home, "placed.gguf")
modelstore.place_verified(part, dest, digest, len(blob))
check(os.path.isfile(dest) and not os.path.exists(part), "a matching file is published and the part is gone")
wrong = os.path.join(home, "wrong.part")
open(wrong, "wb").write(b"xxxx")
try:
    modelstore.place_verified(wrong, os.path.join(home, "nope.gguf"), digest, 4)
    check(False, "a bad hash is not published")
except RuntimeError:
    check(not os.path.exists(wrong) and not os.path.exists(os.path.join(home, "nope.gguf")),
          "a bad hash deletes the part and does not publish")

signed_http = modelstore.sign_manifest({
    **{k: v for k, v in man.items() if k != "signature"},
    "publisher": pub, "trust": "owner-import", "sources": [base],
    "files": [{**man["files"][0], "sources": [base]}],
}, key)
rows = modelstore.index()
rows[-1]["manifest"] = signed_http
rows[-1]["id"] = modelstore.manifest_id(signed_http)
modelstore._save_index(rows)
os.unlink(stored)
net = modelstore.install("Qwen3.8-27B", allow_loopback=True, discover_packets=[], removable=False,
                         consent={"file": False, "http": True, "lan": False, "torrent": False})
check(open(net["paths"]["qwen.gguf"], "rb").read() == blob, "install uses the mirror and keeps the file only when it matches")
check(any(e.get("network") and e.get("action") == "fetch" for e in modelstore.activity_entries()),
      "the fetch is recorded as network activity")
check(all(not str(e.get("detail", "")).startswith("http://huggingface.co") or e.get("action") != "index"
          for e in modelstore.activity_entries()), "nothing fetched a default index")

# --- sharing is opt-in and only answers the address it bound ---
try:
    modelstore.start_share("8.8.8.8")
    check(False, "sharing refuses a public address")
except ValueError:
    check(modelstore.sharing() is False, "sharing refuses a public address and does not listen")
msg = modelstore.start_share("127.0.0.1", 0)
check(modelstore.sharing() and "Sharing is on" in msg, "sharing starts only when asked")
hello = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{modelstore._SHARE['port']}/hello", timeout=5).read())
check(hello.get("llmos_model_store") == 1 and any(m["name"] == "Qwen3.8-27B" for m in hello["models"]),
      "a peer sees the model name, not a file path")
sha = net["manifest"]["files"][0]["sha256"]
got = urllib.request.urlopen(f"http://127.0.0.1:{modelstore._SHARE['port']}/blob/{sha}", timeout=5).read()
check(got == blob, "a peer can fetch a file whose hash still matches")
stop = modelstore.stop_share()
check(not modelstore.sharing() and "off" in stop.lower(), "stop sharing closes the listener")

# torrent stays behind the interface and does not seed
client = modelstore.torrent_client()
check(isinstance(client, modelstore.StubTorrent), "BitTorrent is the stub while the setting is off")
try:
    client.fetch("magnet:?xt=urn:btih:" + "ab" * 20, home, "qwen.gguf", digest, len(blob))
    check(False, "the stub does not fetch a magnet")
except RuntimeError as e:
    check("not fetched" in str(e) and "seed" in str(e).lower(), "the stub says the magnet was not fetched and nothing was seeded")
cmd = modelstore.Aria2Torrent().command("magnet:?xt=urn:btih:" + "ab" * 20, home)
check("--seed-time=0" in cmd and "aria2c" == cmd[0], "the local client is told not to keep seeding")

# --- words ---
check(intent.match("install Qwen3.8-27B from the store") == ("model_store", {"action": "install", "name": "Qwen3.8-27B"}),
      "install from the store is a direct command")
check(intent.match("share my models") == ("model_store", {"action": "share"}), "share my models is opt-in")
check(intent.match("stop sharing my models") == ("model_store", {"action": "stop"}), "stop sharing is a direct command")
check(intent.match("verify my models") == ("model_store", {"action": "verify"}), "verify my models is a direct command")
check(intent.match("import models from /media/usb") == ("model_store", {"action": "import", "path": "/media/usb"}),
      "import folder is a direct command")
check(intent.match("what is the model store doing") == ("model_store", {"action": "activity"}),
      "activity is a direct command")
check(intent.match("download gemma 4 e2b")[0] == "manage_models", "a catalog download is still the catalog, not the store")
text = modelstore.verify()
check("match" in text.lower(), "verify reports the hash check")
lines = modelstore.summary_lines()
check(any("off" in ln.lower() or "Sharing" in ln for ln in lines), "the text panel says whether sharing is on")
blocks = modelstore.panel_blocks()
check(any(b.get("text") == "Model store" for b in blocks), "the models window has a store section")
check(any(b.get("type") == "buttons" and any(i.get("say") == "verify my models" for i in b.get("items", [])) for b in blocks),
      "the store buttons only say a command")

httpd.shutdown()
print("all good" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
