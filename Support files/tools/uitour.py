#!/usr/bin/env python3
"""The same tour of the desk every time, measured (development): each step starts from a clean desk, asks for one
screen, waits, and runs tools/uiaudit.py on it. A table at the end; the reports and screenshots are in run/uiaudit/.

    tools/uitour.py vm|laptop [TAG]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [("greet", None), ("settings", "settings"), ("files", "show my files"), ("models", "show my models"),
         ("apps", "show my apps"), ("answer", "what is the tallest mountain in europe"), ("lists", "show my lists"),
         ("pictures", "show my pictures"), ("power", None)]


def dl(where, *args, timeout=400):
    env = dict(os.environ, **({"DEVLINK_TARGET": "vm"} if where == "vm" else {}))
    return subprocess.run([sys.executable, os.path.join(HERE, "devlink.py"), *args], capture_output=True, text=True,
                          timeout=timeout, env=env).stdout


def clean(where):
    st = dl(where, "state")
    try:
        ids = [w["id"] for w in json.loads(st[st.find("{"):st.rfind("}") + 1]).get("windows", [])]
    except ValueError:
        ids = []
    if ids:
        dl(where, "sh", "; ".join(f"llmos desk-ctl close {i}" for i in ids))
    dl(where, "key", "esc")


def main():
    where = sys.argv[1] if len(sys.argv) > 1 else "vm"
    tag = sys.argv[2] if len(sys.argv) > 2 else "tour"
    rows = []
    for name, ask in STEPS:
        clean(where)
        if ask:
            dl(where, "say", ask)
            dl(where, "waitreply", "120")
        elif name == "power":
            dl(where, "clicktext", "Power") if False else dl(where, "sh", "llmos desk-ctl say power >/dev/null 2>&1 || true")
        out = subprocess.run([sys.executable, os.path.join(HERE, "uiaudit.py"), where, f"{tag}-{name}"], capture_output=True,
                             text=True, timeout=900).stdout
        rep = os.path.join(HERE, "..", "run", "uiaudit", f"{where}-{tag}-{name}.json")
        try:
            r = json.load(open(rep))
            c = r["counts"]
            rows.append((name, c["texts"], c["contrastFails"], c.get("glassFails", 0), c["clipped"], c["smallFails"], c["smallTargets"],
                         c["offscreen"], c["overlaps"], c["fontSizes"]))
        except (OSError, ValueError, KeyError):
            rows.append((name, "no report", out[-200:]))
    print(f"{'screen':10} {'texts':>5} {'lowC':>5} {'lowC/photo':>10} {'cut':>4} {'<24px':>6} {'<32px':>6} {'off':>4} {'overlap':>7} {'sizes':>5}")
    for r in rows:
        print(f"{r[0]:10} " + " ".join(f"{str(v):>{w}}" for v, w in zip(r[1:], (5, 5, 10, 4, 6, 6, 4, 7, 5))))


if __name__ == "__main__":
    main()
