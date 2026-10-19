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
  devlink.py vm 'COMMAND'           the same as sh (so the VM testers' brief works unchanged)
  devlink.py find TEXT              where TEXT is on the screen now (OCR): "x y" of each place, or NOT FOUND
  devlink.py clicktext TEXT [N]     click the Nth place TEXT appears
  devlink.py waitreply [SECONDS]    wait until the computer is no longer busy; prints the desk state and the time
  devlink.py wait SECONDS
"say" types into the request box like a person: the Windows key brings the desk forward, then the words and Enter.
There is no drag on the real computer (its pointer tool can only move and click).
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
if os.environ.get("DEVLINK_TARGET") == "vm":          # the test VM, through the test update server (run/tmp/testota.py, 8782)
    DEVQ = os.path.join(PROJECT, "run", "ota", "testdev", "queue")
    DEVR = os.path.join(PROJECT, "run", "ota", "testdev", "results")
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


def _ocr_find(text):
    sys.path.insert(0, HERE)
    import vmuser                      # the same reading of the screen as the VM tests
    r = send({"op": "shot"}, 60)
    if not r.get("png"):
        return None
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, "dev-current.png")
    open(path, "wb").write(base64.b64decode(r["png"]))
    want = [w for w in __import__("re").findall(r"\w+", text.lower())]
    words = vmuser.ocr_words(path)
    hits = []
    norm = lambda t: __import__("re").sub(r"\W", "", t.lower())
    for i in range(len(words)):
        seq = words[i:i + len(want)]
        if len(seq) == len(want) and all(norm(a[0]).startswith(b) or b in norm(a[0]) for a, b in zip(seq, want)):
            x0, x1 = min(q[1] for q in seq), max(q[1] + q[3] for q in seq)
            y0, y1 = min(q[2] for q in seq), max(q[2] + q[4] for q in seq)
            hits.append(((x0 + x1) // 2, (y0 + y1) // 2))
    return sorted(set(hits), key=lambda c: (c[1], c[0]))


def _state():
    r = send({"op": "state"}, 40)
    try:
        return json.loads(r.get("out", "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def main(a):
    if not a:
        sys.exit(__doc__)
    op, rest = a[0], a[1:]
    if op == "vm":
        op = "sh"
    if op == "wait":
        time.sleep(float(rest[0]) if rest else 5)
        print("waited")
        return 0
    if op == "waitreply":
        limit, t0 = float(rest[0]) if rest else 300, time.time()
        time.sleep(2)
        st = _state()
        while st.get("busy") and time.time() - t0 < limit:
            time.sleep(4)
            st = _state()
        print(f"took {time.time() - t0:.0f} s" + (" (STILL BUSY: gave up waiting)" if st.get("busy") else ""))
        print(json.dumps({"screen": st.get("screen"), "busy": st.get("busy"), "reply": (st.get("reply") or "")[:600],
                          "windows": [w.get("title") for w in st.get("windows", [])], "queued": st.get("queued")},
                         ensure_ascii=False))
        return 0
    if op in ("find", "clicktext"):
        n = 1
        if op == "clicktext" and len(rest) > 1 and rest[-1].isdigit():
            n, rest = int(rest[-1]), rest[:-1]
        hits = _ocr_find(" ".join(rest))
        if not hits or len(hits) < n:
            print("NOT FOUND")
            return 1
        if op == "find":
            print("\n".join(f"{x} {y}" for x, y in hits))
            return 0
        x, y = hits[n - 1]
        r = send({"op": "click", "x": x, "y": y}, 30)
        print(f"clicked '{' '.join(rest)}' at {x} {y}" if r.get("ok") else r.get("out"))
        return 0 if r.get("ok") else 1
    if op == "say":
        for c in ({"op": "key", "keys": "super"}, {"op": "type", "text": " ".join(rest)}, {"op": "key", "keys": "enter"}):
            r = send(c, 60)
            if not r.get("ok"):
                print(r.get("out"))
                return 1
            time.sleep(0.4)
        print("asked: " + " ".join(rest))
        return 0
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
    elif op == "ask":                  # through the desk's control socket, waits for the answer (no screen)
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
