#!/usr/bin/env python3
"""Smoke test: a first-run user completes the desk wizard and asks one question, using only
real clicks and typing through QMP. Stdlib only.

complete_wizard(user, run_in_vm, grab, max_steps=15) -> {"ok", "reason", "steps"}
one_request(user, run_in_vm, text)                    -> {"ok", "reason", "reply"}
main(): boots the target on a fresh overlay, runs both, always quits the VM.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)

import settle  # noqa: E402
import realrun  # noqa: E402
from realuser import INPUT, WIZ_NEXT  # noqa: E402

SUPPORT_DIR = os.path.dirname(TOOLS)
IMAGE = "dist/llmos-arm64.qcow2"
WIZ_NAV_BUTTONS = "#wiz-nav > button"
SKIP_RE = re.compile(r"\b(skip|next|continue|done|start|finish)\b", re.I)
WIZARD = realrun.WIZARD_SCREEN
DESK = realrun.DESK_SCREEN
_pause = time.sleep  # tests replace this with a no-op


class StepFailure(Exception):
    pass


def _read_state(run_in_vm):
    """desk-state as a dict, or None when the output is not JSON."""
    return realrun.vm_json(run_in_vm("llmos desk-state"))


def _await_state(run_in_vm, tries=30):
    for _ in range(tries):
        st = _read_state(run_in_vm)
        if st is not None:
            return st
        _pause(2)
    return None


def _rects(run_in_vm, user, sel):
    user._n += 1
    out = run_in_vm("llmos desk-ctl rects %d %s" % (user._n, _quote(sel)))
    obj = realrun.vm_json(out)
    if obj is None:
        raise StepFailure("rects %s: reply is not JSON: %r" % (sel, str(out)[:200]))
    if obj.get("ok") is False or "items" not in obj:
        raise StepFailure("rects %s failed: %s" % (sel, obj.get("error")))
    return obj


def _quote(s):
    import shlex
    return shlex.quote(s)


def _button_texts(obj):
    return [str(i.get("text", "")).strip() for i in obj.get("items", [])]


def _find_next(run_in_vm, user):
    """(text, item, vw) for the step's button to press, or raise StepFailure naming the visible buttons."""
    nxt = _rects(run_in_vm, user, WIZ_NEXT)
    for it in nxt.get("items", []):
        if it.get("visible") and not it.get("disabled"):
            return (str(it.get("text", "")).strip() or "Next"), it, nxt["vw"]
    nav = _rects(run_in_vm, user, WIZ_NAV_BUTTONS)
    for it in nav.get("items", []):
        text = str(it.get("text", "")).strip()
        if it.get("visible") and not it.get("disabled") and SKIP_RE.search(text):
            return text, it, nav["vw"]
    raise StepFailure("no next/skip button on this step; visible buttons: %s"
                      % ([t for t in _button_texts(nav) if t] or "none"))


def _click_box(user, box, vw, frame):
    W, H, _ = settle.read_ppm(frame)
    s = W / vw
    user.qmp.click((box["x"] + box["w"] / 2) * s, (box["y"] + box["h"] / 2) * s, W, H)


def complete_wizard(user, run_in_vm, grab, max_steps=15):
    steps = []
    for _ in range(max_steps + 1):
        st = _await_state(run_in_vm)
        if st is None:
            return {"ok": False, "reason": "desk-state never returned JSON", "steps": steps}
        if st.get("screen") == DESK:
            return {"ok": True, "reason": "", "steps": steps}
        if len(steps) >= max_steps:
            break
        before = grab()
        try:
            text, box, vw = _find_next(run_in_vm, user)
        except StepFailure as e:
            return {"ok": False, "reason": "wizard step %d: %s" % (len(steps) + 1, e), "steps": steps}
        _click_box(user, box, vw, before)
        steps.append(text)
        if settle.wait_change(grab, before, timeout=10) is None:
            return {"ok": False, "reason": "wizard step %d: screen did not change after '%s'"
                    % (len(steps), text), "steps": steps}
    return {"ok": False, "reason": "wizard did not reach the desk in %d steps" % max_steps, "steps": steps}


def one_request(user, run_in_vm, text):
    if not user.type_into(INPUT, text):
        return {"ok": False, "reason": "typed text did not land in the input", "reply": ""}
    user.press("ret")
    run_in_vm("llmos desk-ctl wait 120")
    st = _await_state(run_in_vm)
    if st is None:
        return {"ok": False, "reason": "desk-state never returned JSON", "reply": ""}
    reply = st.get("reply") or ""
    if not str(reply).strip():
        return {"ok": False, "reason": "no reply after 120s", "reply": ""}
    return {"ok": True, "reason": "", "reply": reply}


def _quit_vm():
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect("run/tmon.sock")
        s.recv(999)
        s.sendall(b"quit\n")
        s.close()
    except OSError:
        pass
    time.sleep(1)


def _fail(reason):
    print("REALUSER FAIL: %s" % reason)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="First-run user smoke: wizard, then one question, through clicks and typing.")
    ap.add_argument("--run", action="store_true", help="boot the test VM and run the smoke (required)")
    ap.add_argument("--image", default=IMAGE, help="qcow2 image to boot (default %s)" % IMAGE)
    ap.add_argument("--mem", type=int, default=4096, help="VM memory in MB (default 4096)")
    args = ap.parse_args(argv)
    if not args.run:
        ap.print_usage()
        print("add --run to boot the test VM")
        return 0
    os.chdir(SUPPORT_DIR)
    image = os.path.join(SUPPORT_DIR, args.image)
    slow = realrun._slow()
    q = None
    try:
        subprocess.run(["/bin/bash", "tools/boot-target.sh", image, str(args.mem)],
                       env=dict(os.environ, LLMOS_TESTSHELL="1"), check=True, stdout=subprocess.DEVNULL)
        run_in_vm = realrun._vm_runner()
        if not realrun._poll(lambda: "up" in run_in_vm("echo up"), 300 * slow, time.monotonic, time.sleep):
            return _fail("VM did not answer 'echo up'")
        if not realrun._poll(lambda: (_read_state(run_in_vm) or {}).get("screen") == WIZARD,
                             120 * slow, time.monotonic, time.sleep):
            return _fail("desk never showed the wizard")
        from qmp import QMP
        from realuser import RealUser
        q = QMP("run/tqmp.sock")
        user = RealUser(q, run_in_vm)
        wiz = complete_wizard(user, run_in_vm, user.grab)
        for i, s in enumerate(wiz["steps"], 1):
            print("step %d: %s" % (i, s))
        if not wiz["ok"]:
            return _fail(wiz["reason"])
        print("wizard done: desk reached")
        req = one_request(user, run_in_vm, "hello")
        if not req["ok"]:
            return _fail(req["reason"])
        print("reply: %s" % req["reply"][:200])
        print("REALUSER OK")
        return 0
    finally:
        if q is not None:
            try:
                q.close()
            except OSError:
                pass
        _quit_vm()


if __name__ == "__main__":
    sys.exit(main())
