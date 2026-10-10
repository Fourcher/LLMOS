#!/usr/bin/env python3
"""Offline tests for tools/realuser-smoke.py with a fake QMP, fake VM and fake frames. Stdlib only."""
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("realuser_smoke", os.path.join(HERE, "realuser-smoke.py"))
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)
from realuser import RealUser, WIZ_NEXT  # noqa: E402

FAILS = []
W = H = 80
VW = 80


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILS.append(name)


def frame(val):
    return b"P6\n%d %d\n255\n" % (W, H) + bytes([val]) * (W * H * 3)


class FakeQMP:
    def __init__(self, desk):
        self.desk = desk
        self.clicks = 0

    def click(self, px, py, w, h, button="left"):
        self.clicks += 1
        self.desk.on_click()

    def type(self, text, delay_ms=40, secret=False):
        self.desk.typed = text

    def combo(self, *names):
        pass

    def key(self, name):
        if name == "ret":
            self.desk.enter = True


class FakeDesk:
    """A wizard of `buttons` (one list of visible button texts per step). Each click moves to the next step;
    after the last step the screen is the desk. The primary button (WIZ_NEXT) is present only when
    `primary` is True for that step."""

    def __init__(self, steps, primary=True, state_junk=0, reply=""):
        self.steps = steps
        self.primary = primary
        self.i = 0
        self.typed = None
        self.enter = False
        self.junk = state_junk
        self.reply = reply
        self.qmp = FakeQMP(self)

    def on_click(self):
        self.i += 1

    def done(self):
        return self.i >= len(self.steps)

    def grab(self):
        return frame(self.i * 40 % 256)

    def run(self, cmd):
        if cmd == "llmos desk-state":
            if self.junk:
                self.junk -= 1
                return "<html>not json</html>"
            return json.dumps({"screen": "desk" if self.done() else "wizard", "reply": self.reply, "busy": False})
        if cmd.startswith("llmos desk-ctl rects "):
            sel = shlex.split(cmd.split(" ", 4)[4])[0]
            if self.done():
                return json.dumps({"ok": True, "items": [], "vw": VW})
            texts = [] if self.done() else self.steps[self.i]
            items = []
            for k, t in enumerate(texts):
                is_primary = k == 0 and self.primary
                if sel == WIZ_NEXT and not is_primary:
                    continue
                items.append({"i": k, "x": 10 + 30 * k, "y": 60, "w": 20, "h": 10, "text": t,
                              "visible": True, "disabled": False})
            return json.dumps({"ok": True, "items": items, "vw": VW, "vh": H})
        if cmd.startswith("llmos desk-ctl rect "):
            return json.dumps({"ok": True, "found": True, "x": 0, "y": 0, "w": 20, "h": 10, "vw": VW,
                               "vh": H, "text": "", "value": self.typed or ""})
        if cmd == "llmos desk-ctl wait 120":
            self.reply = "Hi"
            return json.dumps({"busy": False})
        if cmd == "echo up":
            return "up\n"
        raise AssertionError("unexpected VM command: %r" % cmd)


def make(desk):
    return RealUser(desk.qmp, desk.run, grab=desk.grab), desk.run


def quiet():
    smoke._pause = lambda s: None


def test_three_step_wizard():
    desk = FakeDesk([["Begin"], ["Next"], ["Finish"]])
    user, run = make(desk)
    res = smoke.complete_wizard(user, run, desk.grab)
    check("wizard 3 steps reaches desk", res["ok"] and desk.done(), json.dumps(res))
    check("wizard recorded 3 steps", res["steps"] == ["Begin", "Next", "Finish"], str(res["steps"]))


def test_restart_only_fails():
    desk = FakeDesk([["Restart"]], primary=False)
    user, run = make(desk)
    res = smoke.complete_wizard(user, run, desk.grab)
    check("restart-only step fails", res["ok"] is False, json.dumps(res))
    check("restart-only reason names the button", "Restart" in res["reason"], res["reason"])


def test_skip_fallback():
    desk = FakeDesk([["Back", "Skip"]], primary=False)
    user, run = make(desk)
    res = smoke.complete_wizard(user, run, desk.grab)
    check("skip button used when no primary", res["ok"] and res["steps"] == ["Skip"], json.dumps(res))


def test_json_polling():
    desk = FakeDesk([["Begin"]], state_junk=2)
    user, run = make(desk)
    res = smoke.complete_wizard(user, run, desk.grab)
    check("non-JSON desk-state keeps polling", res["ok"], json.dumps(res))


def test_one_request_pass():
    desk = FakeDesk([], reply="")
    user, run = make(desk)
    res = smoke.one_request(user, run, "hello")
    check("one_request PASSes on reply Hi", res["ok"] and res["reply"] == "Hi", json.dumps(res))
    check("one_request typed the text and pressed enter", desk.typed == "hello" and desk.enter,
          "typed=%r enter=%r" % (desk.typed, desk.enter))


def test_one_request_empty_fails():
    desk = FakeDesk([], reply="")
    desk.run = lambda cmd, inner=desk.run: "{}" if cmd == "llmos desk-ctl wait 120" else inner(cmd)
    user = RealUser(desk.qmp, desk.run, grab=desk.grab)
    res = smoke.one_request(user, desk.run, "hello")
    check("one_request FAILs on empty reply", res["ok"] is False, json.dumps(res))


def test_no_onboard_flag():
    needle = "onboard" + "ed"  # written split so this file does not contain it either
    hits = []
    for name in ("realuser-smoke.py", "realuser-smoke.sh"):
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if needle in f.read():
                    hits.append(name)
    check("no onboarded setting in the smoke scripts", not hits, str(hits))


def pid_files():
    found = set()
    run_dir = os.path.join(os.path.dirname(HERE), "run")
    if os.path.isdir(run_dir):
        for dp, _, fns in os.walk(run_dir):
            if "target.pid" in fns:
                found.add(os.path.join(dp, "target.pid"))
    return found


def test_no_args_no_boot():
    import subprocess
    script = os.path.join(HERE, "realuser-smoke.py")
    before = pid_files()
    p = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60,
                       cwd=os.path.dirname(HERE))
    check("realuser-smoke no args exits 0", p.returncode == 0, "rc=%s err=%s" % (p.returncode, p.stderr))
    check("realuser-smoke no args prints --run", "--run" in p.stdout, p.stdout)
    check("realuser-smoke no args creates no target.pid", not (pid_files() - before), str(pid_files() - before))


def main():
    quiet()
    test_no_args_no_boot()
    test_three_step_wizard()
    test_restart_only_fails()
    test_skip_fallback()
    test_json_polling()
    test_one_request_pass()
    test_one_request_empty_fails()
    test_no_onboard_flag()
    if FAILS:
        print("FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
