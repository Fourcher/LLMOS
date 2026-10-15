#!/usr/bin/env python3
"""Remote testing of the real LLM OS computer paired with this Mac (development only).

The computer must be paired for updates and have remote testing on (publish an update with --enable devlink). The
update server (tools/ota.py serve) must be running: commands are signed here with the update key, queued for the
computer, and its answers come back through the same server. Use it like tools/vmuser.py:

  devlink.py shot NAME              screenshot -> run/sweep/shots/dev-NAME.png (prints the path); open it to look
  devlink.py click X Y [right|double]
  devlink.py type TEXT              type on the keyboard (into whatever has focus)
  devlink.py key KEYS               e.g. ret | esc | ctrl+l | super
  devlink.py scroll X Y up|down [N]
  devlink.py say TEXT               ask the computer (like typing in its request box); prints the desk state after
  devlink.py state                  what the desk shows now
  devlink.py sh 'COMMAND'           run a shell command there to CHECK something (exit code and output)
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
KEY = os.path.join(PROJECT, "ota-keys", "ota_ed25519")
DEVQ = os.path.join(PROJECT, "run", "ota", "dev", "queue")
DEVR = os.path.join(PROJECT, "run", "ota", "dev", "results")
SHOTS = os.path.join(PROJECT, "run", "sweep", "shots")


def send(cmd, timeout):
    cid = uuid.uuid4().hex[:16]
    cmd = dict(cmd, id=cid, ts=time.time(), host="*")
    raw = json.dumps(cmd, sort_keys=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(PROJECT, "run", "tmp")) as d:
        f = os.path.join(d, "c")
        open(f, "w").write(raw)
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", KEY, "-n", "llmos-dev", f], check=True,
                       stdout=subprocess.DEVNULL)
        sig = open(f + ".sig").read()
    os.makedirs(DEVQ, exist_ok=True)
    tmp = os.path.join(DEVQ, f"{time.time():.6f}-{cid}.tmp")
    json.dump({"cmd": raw, "sig": sig}, open(tmp, "w"))
    os.replace(tmp, tmp[:-4] + ".json")
    res = os.path.join(DEVR, cid + ".json")
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(res):
            out = json.load(open(res))
            os.unlink(res)
            return out
        time.sleep(0.2)
    return {"ok": False, "out": f"no answer in {timeout} s (is the computer on, paired, and remote testing on?)"}


def main(a):
    if not a:
        sys.exit(__doc__)
    op, rest = a[0], a[1:]
    if op == "shot":
        r = send({"op": "shot"}, 60)
        if r.get("png"):
            os.makedirs(SHOTS, exist_ok=True)
            path = os.path.join(SHOTS, f"dev-{rest[0] if rest else 'shot'}.png")
            open(path, "wb").write(base64.b64decode(r["png"]))
            print(path)
            return 0
    elif op == "click":
        extra = rest[2] if len(rest) > 2 else ""
        r = send({"op": "click", "x": int(rest[0]), "y": int(rest[1]), "button": "right" if extra == "right" else "left",
                  "double": extra == "double"}, 30)
    elif op == "type":
        r = send({"op": "type", "text": " ".join(rest)}, 60)
    elif op == "key":
        r = send({"op": "key", "keys": " ".join(rest)}, 30)
    elif op == "scroll":
        r = send({"op": "scroll", "x": int(rest[0]), "y": int(rest[1]), "direction": rest[2],
                  "amount": int(rest[3]) if len(rest) > 3 else 3}, 30)
    elif op == "say":
        r = send({"op": "say", "text": " ".join(rest), "timeout": 600}, 660)
    elif op == "state":
        r = send({"op": "state"}, 40)
    elif op == "sh":
        r = send({"op": "sh", "cmd": " ".join(rest), "timeout": 300}, 330)
    else:
        sys.exit(f"unknown command {op}\n" + __doc__)
    print(r.get("out", ""))
    if "secs" in r:
        print(f"[{'ok' if r.get('ok') else 'failed'} in {r['secs']} s]")
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
