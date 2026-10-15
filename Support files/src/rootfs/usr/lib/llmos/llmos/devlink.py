"""Remote testing from the owner's computer (development only, off unless the owner's own signed update turns it on).

Runs inside the llmos-ota service. Like updates it only reaches out: one request stays open to the paired update
server, which hands over test commands; nothing listens on this machine. Every command must be signed with the same
key the owner pinned when pairing (ssh-keygen -Y, namespace "llmos-dev"), be fresh (2 minutes) and new (never run
twice), so nobody else on the network can drive the machine.

Commands: shot, click, type, key, scroll, say, state, sh. The result (and a screenshot as PNG) goes back to the
server. "stop remote testing" turns it off (setting "devlink").
"""
import base64
import json
import os
import re
import socket
import subprocess
import time
import urllib.request

from . import config

NAMESPACE = "llmos-dev"
SHOT = "/run/llmos/devlink-shot.png"
_seen = []


def enabled():
    return bool(config.settings.get("devlink"))


def _verify(raw, sig, key):
    from . import ota
    return ota.verify_manifest(raw, sig, key, NAMESPACE, timeout=120)


def _post(base, body):
    req = urllib.request.Request(base + "/dev/result", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=60).read()


def _env():
    from . import media
    return dict(os.environ, **(media.desk_env() or {}))


def _run(argv, timeout=60, **kw):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=_env(), **kw)
    return p.returncode, ((p.stdout or "") + (p.stderr or ""))[-20000:]


def do(cmd):
    """Run one command; (ok, text, png bytes or None)."""
    from . import control
    op = cmd.get("op")
    if op == "shot":
        rc, out = _run(["grim", "-t", "png", SHOT], timeout=30)
        if rc != 0:
            return False, out, None
        with open(SHOT, "rb") as f:
            data = f.read()
        os.unlink(SHOT)
        return True, "screenshot", data
    if op == "click":
        control.click(int(cmd["x"]), int(cmd["y"]), cmd.get("button", "left"), bool(cmd.get("double")))
        return True, f"clicked {cmd['x']} {cmd['y']}", None
    if op == "type":
        control.type_text(str(cmd["text"]))
        return True, "typed", None
    if op == "key":
        control.press(str(cmd["keys"]))
        return True, "pressed " + str(cmd["keys"]), None
    if op == "scroll":
        if "x" in cmd:
            control.move_to(int(cmd["x"]), int(cmd["y"]))
        control.scroll(cmd.get("direction", "down"), int(cmd.get("amount", 3)))
        return True, "scrolled", None
    if op == "say":
        rc, out = _run(["llmos", "say", str(cmd["text"])], timeout=int(cmd.get("timeout", 600)))
        return rc == 0, out, None
    if op == "state":
        rc, out = _run(["llmos", "desk-state"], timeout=30)
        return rc == 0, out, None
    if op == "sh":
        rc, out = _run(["/bin/sh", "-c", str(cmd["cmd"])], timeout=int(cmd.get("timeout", 120)))
        return rc == 0, f"exit {rc}\n{out}", None
    return False, f"unknown command {op!r}", None


def run():
    """Loop forever (a thread of the update service): wait for a signed command, run it, send the result back."""
    from . import ota
    host = socket.gethostname()
    while True:
        o = ota.paired()
        if not o or not enabled():
            time.sleep(20)
            continue
        base = o["url"]
        try:
            ans = json.loads(ota._get(f"{base}/dev/next?host={host}", timeout=70) or b"{}")
        except Exception:
            time.sleep(10)
            continue
        if not isinstance(ans, dict) or not ans.get("cmd"):
            continue
        raw, sig = str(ans["cmd"]).encode(), str(ans.get("sig", "")).encode()
        try:
            cmd = json.loads(raw)
        except ValueError:
            continue
        cid = str(cmd.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", cid):
            continue
        ok_sig = _verify(raw, sig, o["key"])
        if ok_sig is None:
            _post_safe(base, {"id": cid, "ok": False, "out": "busy: the signature check did not finish (the computer is short "
                                                             "of memory or very busy); try again"})
            continue
        if not ok_sig:
            _post_safe(base, {"id": cid, "ok": False, "out": "refused: the signature does not match the paired key"})
            continue
        if abs(time.time() - float(cmd.get("ts", 0))) > 120 or cid in _seen or cmd.get("host") not in (host, "*"):
            _post_safe(base, {"id": cid, "ok": False, "out": "refused: stale, repeated, or for another machine"})
            continue
        _seen.append(cid)
        del _seen[:-500]
        t0 = time.time()
        try:
            ok, out, png = do(cmd)
        except Exception as e:
            ok, out, png = False, f"error: {e}", None
        body = {"id": cid, "ok": ok, "out": out, "secs": round(time.time() - t0, 2)}
        if png:
            body["png"] = base64.b64encode(png).decode()
        _post_safe(base, body)


def _post_safe(base, body):
    try:
        _post(base, body)
    except Exception as e:
        print(f"devlink: result not sent: {e}", flush=True)
