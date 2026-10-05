#!/usr/bin/env python3
"""Press every button LLM OS offers and check each one does something, in the running test VM (tools/boot-target.sh,
LLMOS_TESTSHELL=1): the top bar's items, the help window, Settings and every system panel, then every button inside
the windows those open (one level down). A button "does something" when, within a few seconds, a window opens or
changes, or a reply/notice appears. Buttons that would power off, erase, or end things are listed, not pressed.
Results: run/button-sweep.json and a summary on stdout.   usage: tools/button-sweep.py"""
import json
import os
import re
import subprocess
import time

ROOT = "/Volumes/Files/Claude Work Area/LLMOS/Support files"
os.chdir(ROOT)
START = ["settings", "show my apps", "network", "sound", "power", "conversations", "help", "task manager", "drives",
         "displays", "keyboard and mouse", "bluetooth", "printers", "storage", "about this computer", "models", "tasks",
         "memory", "audit", "show my files", "open the clock"]
SKIP = re.compile(r"shut ?down|restart|reboot|sleep|lock\b|end process|eject|forget|remove|delete|empty the trash|install the updates|"
                  r"install llm os|erase|uninstall|clear the caches|sign in|join wifi|add printer|bluetooth (?:connect|forget)|"
                  r"use the online model|connect another|set up my email|install a web browser|play some|open the file|show the folder", re.I)


def tsh(cmd, timeout=60):
    p = subprocess.run(["tools/tsh", cmd, str(timeout)], capture_output=True, text=True, timeout=timeout + 30)
    return p.stdout


def js(out):
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def state():
    return js(tsh("llmos desk-state", 30))


def press(words):
    q = words.replace("'", "’")
    # each button from the same clean state: a button pressed earlier ("hands-on mode") must not change what the next one does
    tsh("llmos desk-ctl testreset >/dev/null", 30)
    before = state()
    t0 = time.time()
    tsh(f"( llmos desk-ctl act '{q}' >/dev/null 2>&1 & )", 20)       # (a button that asks first must not hold up the sweep)
    time.sleep(4)
    after = state()
    bw = {w["id"]: json.dumps(w, sort_keys=True) for w in before.get("windows", [])}
    aw = {w["id"]: json.dumps(w, sort_keys=True) for w in after.get("windows", [])}
    changed = [w for w in aw if bw.get(w) != aw[w]]
    replied = after.get("reply") != before.get("reply")
    return {"button": words, "seconds": round(time.time() - t0 - 3, 1), "ok": bool(changed or replied),
            "opened_or_changed": [next((x["title"] for x in after["windows"] if x["id"] == w), w) for w in changed],
            "reply": after.get("reply", "") if replied else ""}, after


def main():
    results, seen = [], set()
    tsh("llmos desk-ctl act 'close all windows' >/dev/null", 30)
    for start in START:
        r, st = press(start)
        results.append(r)
        print(("ok   " if r["ok"] else "DEAD ") + f"{start!r} -> {r['opened_or_changed'] or r['reply'][:60]}", flush=True)
        for w in st.get("windows", []):
            for a in w.get("actions", []):
                say = a if isinstance(a, str) else a.get("say", "")
                if not say or say in seen or say in START:
                    continue
                seen.add(say)
                if SKIP.search(say):
                    results.append({"button": say, "skipped": "would change the machine for real"})
                    continue
                r2, _ = press(say)
                r2["inside"] = w.get("title")
                results.append(r2)
                print(("  ok   " if r2["ok"] else "  DEAD ") + f"[{w.get('title')}] {say!r} -> {r2['opened_or_changed'] or r2['reply'][:60]}", flush=True)
        tsh("llmos desk-ctl act 'close all windows' >/dev/null", 30)
    with open("run/button-sweep.json", "w") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    dead = [r for r in results if r.get("ok") is False]
    print(f"\n{len([r for r in results if 'ok' in r])} buttons pressed, {len(dead)} did nothing, "
          f"{len([r for r in results if 'skipped' in r])} not pressed (they change the machine)")


if __name__ == "__main__":
    main()
