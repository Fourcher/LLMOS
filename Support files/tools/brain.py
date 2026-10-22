#!/usr/bin/env python3
"""The brain server: this Mac runs a capable model on its GPU and lends it to the LLM OS laptop.

The model listens on this Mac's loopback only, so nothing connects in and the Mac's firewall never asks. The Mac
dials out to the laptop over the dev SSH link (tools/devssh.py: found by name, last address or MAC, so the Mac's
own address can change) and forwards the laptop's 127.0.0.1:8090 to the model. On the laptop it is the "home"
online model (llm.CLOUD_PROVIDERS["home"]): used while it answers; the laptop's own model takes over the moment it
doesn't (this Mac asleep, this stopped, the tunnel down), with no question and no error.

This Mac's memory comes first (two VMs at once crashed it): the server starts only while macOS reports normal
memory pressure with room for the model, and stops itself when pressure turns critical or stays at warning.

Run:  python3 tools/brain.py start [--model FILE.gguf]   (background; log in run/logs/brain.log)
      python3 tools/brain.py stop | status"""
import argparse
import json
import hashlib
import os
import re
import secrets
import signal
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import devssh  # noqa: E402

LLAMA = "/opt/homebrew/bin/llama-server"
PORT, LAPTOP_PORT = 8081, 8090
CTX = 16384
DEFAULT_MODEL = os.path.join(PROJECT, "models", "Huihui-Ornith-1.5-9B-abliterated.Q4_K_M.gguf")
CATALOG = os.path.join(PROJECT, "src/rootfs/usr/share/llmos/catalog.json")
KEYF = os.path.join(PROJECT, "ota-keys", "brain-key")             # ota-keys/ is never in git
PIDF = os.path.join(PROJECT, "run", "brain.pid")
STATEF = os.path.join(PROJECT, "run", "brain.json")
LOG = os.path.join(PROJECT, "run", "logs", "brain.log")
MODEL_LOG = os.path.join(PROJECT, "run", "logs", "brain-llama.log")
TOTAL = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip() or 0)


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)


def pressure():
    """macOS's own verdict: 1 normal, 2 warning, 4 critical."""
    try:
        return int(subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True, text=True).stdout)
    except ValueError:
        return 4


def free_pct():
    m = re.search(r"free percentage: (\d+)%", subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout)
    return int(m.group(1)) if m else 0


def need_pct(model):
    """The share of this Mac's memory the model takes: its weights plus an 8-bit cache for the whole context."""
    kv = 1.2 * 2 ** 30 * CTX / 16384
    return round(100 * (os.path.getsize(model) + kv) / TOTAL)


def catalog_entry(model):
    size = os.path.getsize(model)
    cat = json.load(open(CATALOG))
    for m in (cat if isinstance(cat, list) else cat.get("models", [])):
        if isinstance(m, dict) and m.get("size") == size:
            return m
    return None


def verified(model):
    """The file matches the catalog's sha256 (checked once, then remembered by size and mtime)."""
    st = os.stat(model)
    mark = f"{model}|{st.st_size}|{int(st.st_mtime)}"
    state = _state()
    if state.get("verified") == mark:
        return True
    ent = catalog_entry(model)
    if not ent or not ent.get("sha256"):
        log(f"{os.path.basename(model)} is not in the catalog; refusing an unverified model")
        return False
    h = hashlib.sha256()
    with open(model, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    if h.hexdigest() != ent["sha256"]:
        log(f"{os.path.basename(model)}: sha256 does not match the catalog")
        return False
    _save(verified=mark)
    return True


def _state():
    try:
        return json.load(open(STATEF))
    except (OSError, ValueError):
        return {}


def _save(**kw):
    st = _state()
    st.update(kw)
    json.dump(st, open(STATEF, "w"))


def key():
    if not os.path.exists(KEYF):
        with os.fdopen(os.open(KEYF, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            f.write(secrets.token_urlsafe(32))
    return open(KEYF).read().strip()


def running():
    try:
        pid = int(open(PIDF).read())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def healthy(port=PORT):
    try:
        return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)).get("status") == "ok"
    except Exception:
        return False


def ssh_argv(ip):
    return ["ssh", "-i", devssh.KEY, "-o", "IdentitiesOnly=yes", "-o", f"UserKnownHostsFile={devssh.KNOWN}",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            "-o", "LogLevel=ERROR", f"root@{ip}"]


SETUP = r'''
import sys
sys.path.insert(0, "/usr/lib/llmos")
from llmos import llm, config
ok, note = llm.cloud_setup({"provider": "home", "url": "http://127.0.0.1:%d/v1", "model": %r, "key": %r}, adopt=False)
if ok:
    c = config.cloud()
    c["label"] = %r
    config.save_cloud(c)
    config.settings.set("brain", "cloud")
print("SETUP", ok, note)
'''


def configure_laptop(ip, model_id, label):
    p = subprocess.run(ssh_argv(ip) + ["python3 -"], input=SETUP % (LAPTOP_PORT, model_id, key(), label),
                       text=True, capture_output=True, timeout=90)
    out = (p.stdout + p.stderr).strip()
    log("laptop: " + (out.splitlines()[-1] if out else f"ssh exit {p.returncode}"))
    return "SETUP True" in out


def serve(model):
    """The supervisor (runs in the background): model, tunnel, laptop setup, memory guard."""
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    signal.signal(signal.SIGINT, lambda *a: stop.append(1))
    ent = catalog_entry(model) or {}
    model_id = ent.get("id") or os.path.basename(model)
    label = f"{ent.get('name', model_id).split(' (')[0]} on {os.uname().nodename.split('.')[0]}"
    srv = subprocess.Popen([LLAMA, "-m", model, "--host", "127.0.0.1", "--port", str(PORT), "-ngl", "99", "-fa", "on",
                            "-c", str(CTX), "-np", "1", "-ctk", "q8_0", "-ctv", "q8_0", "--jinja", "--no-webui",
                            "--api-key", key()], stdout=open(MODEL_LOG, "a"), stderr=subprocess.STDOUT)
    for _ in range(120):
        if healthy() or srv.poll() is not None or stop:
            break
        time.sleep(1)
    if not healthy():
        log(f"the model did not start (see {MODEL_LOG})")
        srv.terminate()
        return
    log(f"model up: {label} (pressure {pressure()}, {free_pct()}% free)")
    tunnel, configured, warn_since = None, False, None
    try:
        while not stop:
            lvl = pressure()
            if lvl >= 4:
                log("memory pressure is critical: stopping to protect this Mac")
                break
            warn_since = (warn_since or time.time()) if lvl >= 2 else None
            if warn_since and time.time() - warn_since > 60:
                log("memory pressure stayed at warning for a minute: stopping to protect this Mac")
                break
            if srv.poll() is not None:
                log(f"the model stopped (exit {srv.returncode}); see {MODEL_LOG}")
                break
            if tunnel is None or tunnel.poll() is not None:
                ip = devssh.where()
                if ip:
                    tunnel = subprocess.Popen(ssh_argv(ip) + ["-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
                                                              "-o", "ServerAliveCountMax=3", "-R", f"127.0.0.1:{LAPTOP_PORT}:127.0.0.1:{PORT}"],
                                              stdout=subprocess.DEVNULL, stderr=open(LOG, "a"))
                    time.sleep(3)
                    if tunnel.poll() is None:
                        log(f"tunnel up to the laptop at {ip}")
                        if not configured:
                            configured = configure_laptop(ip, model_id, label)
                    else:
                        tunnel = None
            time.sleep(5)
    finally:
        for p in (tunnel, srv):
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
        log("brain server stopped; the laptop answers with its own model")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["start", "stop", "status", "_serve"])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    a = ap.parse_args()
    if a.cmd == "_serve":
        open(PIDF, "w").write(str(os.getpid()))
        try:
            serve(a.model)
        finally:
            os.unlink(PIDF)
        return 0
    if a.cmd == "status":
        pid = running()
        print(f"brain server: {'running (pid %d)' % pid if pid else 'stopped'}; model {'answering' if healthy() else 'not answering'}; "
              f"memory pressure {pressure()} (1 normal, 2 warning, 4 critical), {free_pct()}% free")
        return 0
    if a.cmd == "stop":
        pid = running()
        if not pid:
            print("brain server: already stopped")
            return 0
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not running():
                break
            time.sleep(1)
        print("brain server: stopped")
        return 0
    if running():
        print("brain server: already running")
        return 0
    if not os.path.exists(a.model):
        print(f"no model file at {a.model}")
        return 1
    lvl, free, need = pressure(), free_pct(), need_pct(a.model)
    if lvl != 1 or free < need + 15:
        print(f"not starting: this Mac needs room first (memory pressure {lvl}, {free}% free; the model takes about {need}% "
              f"and 15% must stay free). The laptop keeps answering with its own model.")
        return 2
    if not verified(a.model):
        return 1
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_serve", "--model", a.model],
                     stdout=open(LOG, "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(150):
        if healthy() or not running() and _ > 5:
            break
        time.sleep(1)
    print(f"brain server: {'running' if healthy() else 'did not start, see ' + LOG}")
    return 0 if healthy() else 1


if __name__ == "__main__":
    sys.exit(main())
