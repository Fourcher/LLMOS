#!/usr/bin/env python3
"""Use the test VM like a person: look at the screen, click, type, press keys. For feature-test agents.

All input goes through the VM's virtual mouse and keyboard (QMP), exactly as a person's would. Run from
"Support files". One command per call:

  vmuser.py shot NAME              screenshot -> run/sweep/shots/NAME.png (prints its path and size); open it to look
  vmuser.py find TEXT              where TEXT is on screen now (OCR): prints "x y" of its centre, or NOT FOUND
  vmuser.py clicktext TEXT [N]     click the Nth (default 1st) place TEXT appears on screen
  vmuser.py click X Y [right|double]   click at screen pixel X,Y (the same pixels as the screenshot)
  vmuser.py drag X1 Y1 X2 Y2       press at X1,Y1, move to X2,Y2, release (move a window by its title bar, resize by a corner)
  vmuser.py scroll X Y up|down [N] turn the mouse wheel N notches (default 3) over X,Y
  vmuser.py type TEXT              type TEXT on the keyboard (into whatever has focus)
  vmuser.py key NAME [NAME...]     press keys together, e.g. ret | esc | tab | backspace | ctrl l | alt f4 | super
  vmuser.py say TEXT               click the desk's request box, type TEXT, press Enter (like asking the computer)
  vmuser.py waitreply [SECONDS]    wait until the computer is no longer busy (default 300 s); prints the reply,
                                   open windows and how long it took
  vmuser.py state                  what the desk shows now: screen, busy, reply, windows, queue
  vmuser.py vm COMMAND             run a shell command inside the VM to CHECK a result (a file exists, a setting, a
                                   program runs). Never use it to do the task itself: do the task with the screen.
  vmuser.py wait SECONDS
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qmp as qmpmod  # noqa: E402
import vmjson  # noqa: E402

SHOTS = os.path.join(SUPPORT, "run", "sweep", "shots")
CUR = os.path.join(SUPPORT, "run", "sweep", "now.png")


def tsh(cmd, timeout=120):
    p = subprocess.run([os.path.join(HERE, "tsh"), cmd, str(timeout)], capture_output=True, text=True, timeout=timeout + 30)
    lines = [ln for ln in p.stdout.splitlines() if not ln.startswith("[vmctl:")]
    return "\n".join(lines).strip()


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def grab(q, path=CUR):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    q.shot(path, "png")
    for _ in range(20):
        if os.path.exists(path) and os.path.getsize(path) > 100:
            break
        time.sleep(0.1)
    return path


def ocr_words(path):
    """[(text, x, y, w, h, line_key)] from tesseract on a 2x upscale (UI text is small)."""
    p = subprocess.run(["tesseract", path, "-", "--psm", "11", "-c", "tessedit_create_tsv=1", "tsv"],
                       capture_output=True, text=True, timeout=120)
    words = []
    for ln in p.stdout.splitlines()[1:]:
        f = ln.split("\t")
        if len(f) < 12 or not f[11].strip():
            continue
        try:
            conf = float(f[10])
        except ValueError:
            continue
        if conf < 30:
            continue
        words.append((f[11].strip(), int(f[6]), int(f[7]), int(f[8]), int(f[9]), (f[2], f[3], f[4])))
    return words


def find(q, text):
    """Centres of every place TEXT (one or more words) appears, top to bottom."""
    path = grab(q)
    want = [w for w in re.findall(r"\w+", text.lower())]
    if not want:
        return []
    words = ocr_words(path)
    hits = []
    for i, (t, x, y, w, h, line) in enumerate(words):
        seq = words[i:i + len(want)]
        if len(seq) < len(want):
            continue
        if all(re.sub(r"\W", "", a[0].lower()).startswith(b) or b in re.sub(r"\W", "", a[0].lower())
               for a, b in zip(seq, want)):
            x0 = min(s[1] for s in seq)
            x1 = max(s[1] + s[3] for s in seq)
            y0 = min(s[2] for s in seq)
            y1 = max(s[2] + s[4] for s in seq)
            hits.append(((x0 + x1) // 2, (y0 + y1) // 2))
    return sorted(set(hits), key=lambda c: (c[1], c[0]))


def desk_state():
    obj = vmjson.vm_json(tsh("llmos desk-state", 60))
    return obj or {}


def show_state(s):
    wins = [w.get("title") for w in s.get("windows", [])]
    print(json.dumps({"screen": s.get("screen"), "busy": s.get("busy"), "reply": (s.get("reply") or "")[:600],
                      "windows": wins, "queued": s.get("queued"), "dialogs": s.get("dialogs")}, ensure_ascii=False))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    cmd, rest = a[0], a[1:]
    if cmd == "vm":
        print(tsh(" ".join(rest), 300))
        return
    if cmd == "state":
        show_state(desk_state())
        return
    if cmd == "wait":
        time.sleep(float(rest[0]) if rest else 5)
        print("waited")
        return
    if cmd == "waitreply":
        limit = float(rest[0]) if rest else 300
        t0 = time.time()
        time.sleep(2)
        s = desk_state()
        while s.get("busy") and time.time() - t0 < limit:
            time.sleep(5)
            s = desk_state()
        print(f"took {time.time() - t0:.0f} s" + (" (STILL BUSY: gave up waiting)" if s.get("busy") else ""))
        show_state(s)
        return
    q = qmpmod.QMP()
    try:
        if cmd == "shot":
            name = re.sub(r"[^\w.-]", "_", rest[0] if rest else time.strftime("%H%M%S"))
            path = grab(q, os.path.join(SHOTS, name + ".png"))
            w, h = png_size(path)
            print(f"{path}  ({w}x{h} pixels; click uses these pixel coordinates)")
        elif cmd == "find":
            hits = find(q, " ".join(rest))
            print("\n".join(f"{x} {y}" for x, y in hits) if hits else "NOT FOUND")
        elif cmd == "clicktext":
            n = 1
            if len(rest) > 1 and rest[-1].isdigit():
                n, rest = int(rest[-1]), rest[:-1]
            hits = find(q, " ".join(rest))
            if len(hits) < n:
                print("NOT FOUND")
                sys.exit(1)
            w, h = png_size(CUR)
            x, y = hits[n - 1]
            q.click(x, y, w, h)
            print(f"clicked '{' '.join(rest)}' at {x} {y}")
        elif cmd == "click":
            x, y = float(rest[0]), float(rest[1])
            w, h = png_size(grab(q))
            how = rest[2] if len(rest) > 2 else "left"
            q.click(x, y, w, h, button="right" if how == "right" else "left")
            if how == "double":
                time.sleep(0.08)
                q.click(x, y, w, h)
            print(f"clicked {x:.0f} {y:.0f} {how}")
        elif cmd == "drag":
            x1, y1, x2, y2 = (float(v) for v in rest[:4])
            w, h = png_size(grab(q))
            ax = lambda v, d: qmpmod._axis(v, d)
            q.cmd("input-send-event", events=[{"type": "abs", "data": {"axis": "x", "value": ax(x1, w)}},
                                              {"type": "abs", "data": {"axis": "y", "value": ax(y1, h)}}])
            q.cmd("input-send-event", events=[{"type": "btn", "data": {"down": True, "button": "left"}}])
            for i in range(1, 13):
                x, y = x1 + (x2 - x1) * i / 12, y1 + (y2 - y1) * i / 12
                q.cmd("input-send-event", events=[{"type": "abs", "data": {"axis": "x", "value": ax(x, w)}},
                                                  {"type": "abs", "data": {"axis": "y", "value": ax(y, h)}}])
                time.sleep(0.03)
            q.cmd("input-send-event", events=[{"type": "btn", "data": {"down": False, "button": "left"}}])
            print(f"dragged {x1:.0f},{y1:.0f} -> {x2:.0f},{y2:.0f}")
        elif cmd == "scroll":
            x, y, way = float(rest[0]), float(rest[1]), rest[2]
            n = int(rest[3]) if len(rest) > 3 else 3
            w, h = png_size(grab(q))
            q.cmd("input-send-event", events=[{"type": "abs", "data": {"axis": "x", "value": qmpmod._axis(x, w)}},
                                              {"type": "abs", "data": {"axis": "y", "value": qmpmod._axis(y, h)}}])
            b = "wheel-up" if way == "up" else "wheel-down"
            for _ in range(n):
                q.cmd("input-send-event", events=[{"type": "btn", "data": {"down": True, "button": b}}])
                q.cmd("input-send-event", events=[{"type": "btn", "data": {"down": False, "button": b}}])
                time.sleep(0.05)
            print(f"scrolled {way} {n}")
        elif cmd == "type":
            q.type(" ".join(rest))
            print("typed")
        elif cmd == "key":
            q.combo(*rest)
            print("pressed " + "+".join(rest))
        elif cmd == "say":
            text = " ".join(rest)
            r = vmjson.vm_json(tsh("llmos desk-ctl rect 1 '#in'", 60)) or {}
            w, h = png_size(grab(q))
            if r.get("w"):
                s = w / r["vw"]
                q.click((r["x"] + r["w"] / 2) * s, (r["y"] + r["h"] / 2) * s, w, h)
            else:
                hits = find(q, "Tell me what you want")
                if not hits:
                    print("could not find the request box")
                    sys.exit(1)
                q.click(hits[0][0], hits[0][1], w, h)
            time.sleep(0.3)
            q.type(text)
            time.sleep(0.2)
            q.key("ret")
            print(f"said: {text}")
        else:
            print(__doc__)
            sys.exit(2)
    finally:
        q.close()


if __name__ == "__main__":
    main()
