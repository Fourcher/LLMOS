#!/usr/bin/env python3
"""Run real requests from docs/research/use-cases.md against LLM OS in the running test VM (tools/boot-target.sh +
LLMOS_TESTSHELL=1) and record what happened: the reply, the windows and dialogs it opened, the activity, how long it
took, and a screenshot. Dialogs are declined (nothing destructive runs) unless the ID is listed with --yes.
Results: run/usecases/<ID>.json + .png and run/usecases/summary.json, for review against "success looks like".

usage: tools/usecase-run.py [--ids B06,F01,...] [--priority P0] [--all-phrasings] [--yes ID,...] [--timeout 240]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = "/Volumes/Files/Claude Work Area/LLMOS/Support files"
os.chdir(ROOT)
OUT = "run/usecases"   # (--out)
SKIP = {"B01", "B02", "B04", "B05"}          # power off / restart / sleep / log out would end the run


def tsh(cmd, timeout=60):
    p = subprocess.run(["tools/tsh", cmd, str(timeout)], capture_output=True, text=True, timeout=timeout + 30)
    return p.stdout


def parse(path="docs/research/use-cases.md"):      # (--file)
    rows = []
    for ln in open(path, encoding="utf-8"):
        m = re.match(r"\|\s*([A-Z]\d\d)\s*\|(.*?)\|(.*?)\|\s*(P\d)\s*\|", ln)
        if not m:
            continue
        phr = re.findall(r'"([^"]+)"', m.group(2))
        if not phr:
            continue                      # a scenario ("first boot with no network"), not something a person types
        rows.append({"id": m.group(1), "phrasings": phr, "success": m.group(3).strip(), "priority": m.group(4)})
    return rows


def state():
    out = tsh("llmos desk-state", 30)
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


KEEP = False     # (--keep-programs) tasks that build on each other: leave the programs open between them


def run_one(case, phrase, yes, timeout):
    q = phrase.replace("'", "’").replace('"', "”")
    # a clean desk for each request: unlocked, no windows, nothing playing
    kill = "" if KEEP else "pkill -x mpv; pkill -f firefox; pkill -x thunar; "
    tsh(f"llmos desk-ctl testreset >/dev/null; {kill}rm -f /tmp/uc.json", 60)
    if state().get("screen") == "lock":            # a task locked the screen: the test VM's passphrase opens it
        tsh(f"llmos desk-ctl unlock {os.environ.get('LLMOS_TEST_PASS', 'correct horse battery')} >/dev/null", 60)
    t0 = time.time()
    tsh(f"( llmos say '{q}' > /tmp/uc.json 2>&1 & )", 20)
    answered, dialogs = [], []
    while time.time() - t0 < timeout:
        time.sleep(4)
        done = tsh("[ -s /tmp/uc.json ] && echo UC_DONE || llmos desk-state", 20)
        if "UC_DONE" in done:
            break
        m = re.search(r"\{.*\}", done, re.S)
        try:
            st = json.loads(m.group(0)) if m else {}
        except ValueError:
            st = {}
        for d in st.get("dialogs", []):
            dialogs.append(d.get("title", ""))
            # harmless confirmations are accepted like a person would; anything destructive is declined
            destructive = d.get("danger") or re.search(r"delete|erase|wipe|format|remove|shut|restart|reboot|power|uninstall|"
                                                      r"forget|empty|install llm os|kill|end ", (d.get("title", "") + " " + d.get("text", "")), re.I)
            ans = "yes" if yes or not destructive else "no"
            tsh(f"llmos desk-ctl dialog {ans} >/dev/null", 20)
            answered.append(ans)
    else:
        tsh("llmos desk-ctl cancel >/dev/null", 20)
    took = round(time.time() - t0, 1)
    raw = tsh("cat /tmp/uc.json", 30)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        res = json.loads(m.group(0)) if m else {}
    except ValueError:
        res = {}
    st = state()
    # a placeholder ("checking now; the result follows") is followed by the real answer from the desk: wait for it
    if re.search(r"the result follows|one moment", res.get("reply", "") or "", re.I):
        end = time.time() + 40
        while time.time() < end:
            time.sleep(3)
            st = state()
            if st.get("reply") and not re.search(r"the result follows|one moment", st.get("reply", ""), re.I):
                res["reply"] = st["reply"]
                break
        took = round(time.time() - t0, 1)
    shot = f"{OUT}/{case['id']}.png"
    subprocess.run(["python3", "tools/screendump.py", "run/tmon.sock", shot], capture_output=True)
    return {"id": case["id"], "phrase": phrase, "success_looks_like": case["success"], "priority": case["priority"],
            "seconds": took, "timed_out": took >= timeout, "reply": res.get("reply", "") or st.get("reply", ""),
            "windows": [{"title": w.get("title"), "rows": (w.get("rows") or [])[:12]} for w in (res.get("windows") or st.get("windows") or [])],
            "dialogs_seen": dialogs, "dialog_answers": answered, "screenshot": shot}


def main():
    global OUT, KEEP
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--priority", default="")
    ap.add_argument("--all-phrasings", action="store_true")
    ap.add_argument("--yes", default="")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--file", default="docs/research/use-cases.md")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--keep-programs", action="store_true")
    a = ap.parse_args()
    OUT = a.out
    KEEP = a.keep_programs
    cases = parse(a.file)
    if a.ids:
        want = set(a.ids.split(","))
        cases = [c for c in cases if c["id"] in want]
    if a.priority:
        cases = [c for c in cases if c["priority"] in a.priority.split(",")]
    cases = [c for c in cases if c["id"] not in SKIP]
    yes = set(a.yes.split(",")) if a.yes else set()
    os.makedirs(OUT, exist_ok=True)
    results = []
    for i, c in enumerate(cases):
        for phrase in (c["phrasings"] if a.all_phrasings else c["phrasings"][:1]):
            r = run_one(c, phrase, c["id"] in yes, a.timeout)
            results.append(r)
            with open(f"{OUT}/{c['id']}.json", "w") as f:
                json.dump(r, f, indent=1, ensure_ascii=False)
            print(f"[{i + 1}/{len(cases)}] {c['id']} {r['seconds']:>6}s  {phrase[:50]!r:52} -> {r['reply'][:90]!r}", flush=True)
    with open(f"{OUT}/summary.json", "w") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
