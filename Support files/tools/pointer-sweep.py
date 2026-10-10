#!/usr/bin/env python3
"""Click every visible, enabled button on the desk in the running test VM, one at a time, with the mouse
(QMP), and report the ones that do nothing: no pixel change above 0.5% and no change in the desk state
(screen, reply, windows). Machine-changing buttons (power, restart, shut down, log out, erase, reset, ...)
are listed as skipped, never clicked. After each click: Esc, then `llmos desk-ctl testreset-min`.
Stdlib only.

list_buttons(run_in_vm, sel) -> [item, ...]   items carry "vw" (the CSS viewport width of the rects reply)
sweep(user, run_in_vm, grab, items, clock)    -> [record, ...]
    record: {"i", "text", "changed_pixels", "state_changed", "noop", "seconds"}
main(): builds QMP, RealUser and the VM runner (tools/tsh), sweeps the desk, writes run/pointer-sweep.json
        and prints the no-op button texts, one per line.   usage: tools/pointer-sweep.py
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import settle  # noqa: E402

SUPPORT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SUPPORT_DIR, "run", "pointer-sweep.json")
DEFAULT_SEL = "button, [role=button], .chip"
NOOP_RATIO = 0.005  # a click that changes at most 0.5% of sampled pixels (and no state) is a no-op
# button-sweep.py's SKIP list, plus the machine-changing words: power, log out, sign out, reset
SKIP = re.compile(r"\b(?:shut[ -]?down|restart|reboot|sleep|lock\b|end process|eject|forget|remove|delete|empty the trash|"
                  r"install the updates|install llm os|erase|uninstall|clear the caches|sign[ -]?in|join wifi|add printer|"
                  r"bluetooth (?:connect|forget)|use the online model|connect another|set up my email|"
                  r"install a web browser|play some|open the file|show the folder|"
                  r"power|log[ -]?out|sign[ -]?out|reset|empty\b|trash|format|turn[ -](?:it )?off|wipe|install|update|upgrade|"
                  r"send|buy|pay|purchase|order|post|publish|share|upload|kill|quit|close all|discard|overwrite|"
                  r"replace all|factory|firewall|password|passphrase|delete account|unpair|disconnect)", re.I)


def _rects(run_in_vm, sel):
    out = run_in_vm("llmos desk-ctl rects 1 %s" % shlex.quote(sel))
    try:
        obj = json.loads(out)
    except (TypeError, ValueError):
        raise RuntimeError("rects %s: reply is not JSON: %r" % (sel, str(out)[:200]))
    if not isinstance(obj, dict):
        raise RuntimeError("rects %s: reply is not an object" % sel)
    if "error" in obj:
        raise RuntimeError("rects %s failed: %s" % (sel, obj["error"]))
    return obj


def list_buttons(run_in_vm, sel=DEFAULT_SEL):
    """Visible, enabled, non-zero-size items whose text does not match SKIP."""
    obj = _rects(run_in_vm, sel)
    vw = obj.get("vw")
    rows = []
    for it in obj.get("items", []):
        if not it.get("visible") or it.get("disabled"):
            continue
        if not (it.get("w", 0) > 0 and it.get("h", 0) > 0):
            continue
        if SKIP.search(it.get("text") or ""):
            continue
        row = dict(it)
        row["vw"] = vw
        rows.append(row)
    return rows


def _state(run_in_vm):
    return json.loads(run_in_vm("llmos desk-state"))


def _state_key(st):
    return json.dumps({"screen": st.get("screen"), "reply": st.get("reply"), "windows": st.get("windows")},
                      sort_keys=True)


def _ratio(before, after):
    w, h, rgb1 = settle.read_ppm(before)
    w2, h2, rgb2 = settle.read_ppm(after)
    if (w, h) != (w2, h2):
        return 1.0  # resolution change counts as a change
    sw, sh, g1 = settle.small_gray(w, h, rgb1)
    _, _, g2 = settle.small_gray(w2, h2, rgb2)
    return settle.diff_ratio(g1, g2, sw, sh)


def sweep(user, run_in_vm, grab, items, clock=time.monotonic):
    results = []
    for it in items:
        if not (it.get("w", 0) > 0 and it.get("h", 0) > 0):
            continue  # zero-size: nothing to click
        vw = it.get("vw")
        if not vw:
            raise ValueError("item %s has no viewport width (vw)" % it.get("i"))
        t0 = clock()
        try:
            before_state = _state(run_in_vm)
            before = grab()
            W, H, _ = settle.read_ppm(before)
            s = W / float(vw)  # CSS px -> PPM px, as realuser.click_sel does
            cx = (it["x"] + it["w"] / 2.0) * s
            cy = (it["y"] + it["h"] / 2.0) * s
            user.qmp.click(cx, cy, W, H)
            moved = settle.wait_change(grab, before, timeout=3)
            after = moved if moved is not None else grab()
            after_state = _state(run_in_vm)
            ratio = _ratio(before, after)
            state_changed = _state_key(before_state) != _state_key(after_state)
        finally:
            try:
                user.press("esc")
            except Exception as e:  # the reset below must still run
                print("esc failed: %s" % e, file=sys.stderr)
            run_in_vm("llmos desk-ctl testreset-min")
        results.append({
            "i": it.get("i"),
            "text": it.get("text") or "",
            "changed_pixels": round(ratio, 4),
            "state_changed": state_changed,
            "noop": ratio <= NOOP_RATIO and not state_changed,
            "seconds": round(clock() - t0, 2),
        })
    return results


def _vm_runner(timeout=900):
    """Run a shell command in the test VM through tools/tsh; return its stdout."""
    def run_in_vm(cmd):
        p = subprocess.run(["tools/tsh", cmd, str(timeout)], capture_output=True, text=True,
                           timeout=timeout + 30)
        if p.returncode != 0 and not p.stdout:
            raise RuntimeError(f"tsh exit {p.returncode}: {p.stderr[:200]}")
        return p.stdout
    return run_in_vm


def main(argv=None):
    ap = argparse.ArgumentParser(description="Click every desk button and list the ones that do nothing.")
    ap.add_argument("--sel", default=DEFAULT_SEL, help="CSS selector for the buttons to sweep")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--run", action="store_true", help="connect to the running test VM and sweep its desk (required)")
    args = ap.parse_args(argv)
    if not args.run:
        ap.print_usage()
        print("add --run to boot the test VM")
        return 0
    os.chdir(SUPPORT_DIR)

    from qmp import QMP
    from realuser import RealUser

    q = QMP("run/tqmp.sock")
    run_in_vm = _vm_runner()
    user = RealUser(q, run_in_vm)
    try:
        items = list_buttons(run_in_vm, args.sel)
        results = sweep(user, run_in_vm, user.grab, items, time.monotonic)
    finally:
        q.close()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    for r in results:
        if r["noop"]:
            print(r["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
