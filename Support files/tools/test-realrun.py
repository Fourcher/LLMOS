#!/usr/bin/env python3
"""Tests for tools/realrun.py with fake clock, user and VM runner. Stdlib only."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import realrun  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILS.append(name)


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.log = []

    def __call__(self):
        self.t += 1.0
        self.log.append(self.t)
        return self.t


class FakeUser:
    def __init__(self):
        self.pressed = []
        self.shots = []
        self.typed = []

    def type_into(self, sel, text, secret=False):
        self.typed.append((sel, text))
        return True

    def press(self, key):
        self.pressed.append(key)

    def shot(self, path):
        self.shots.append(path)

    def rect(self, sel):
        return {"ok": True, "text": "rect-text"}


DESK_STATE = json.dumps({"screen": "desk", "busy": False, "reply": "Canberra", "queued": 0,
                         "dialogs": [], "windows": [], "apps": []})


def fake_vm(cmd):
    if cmd.startswith("llmos desk-ctl testreset") or cmd.startswith("llmos desk-ctl wait"):
        return "ok"
    if cmd == "llmos desk-state":
        return DESK_STATE
    if "ls " in cmd:
        return "/root/Desktop/Test"
    return "ok"


def reply_task(tid="reply-1"):
    return {"id": tid, "instruction": "what is the capital of australia",
            "evaluator": {"func": "include_exclude", "expected": {"include": ["canberra"]},
                          "result": {"type": "reply"}}}


def state_task(tid="state-1"):
    return {"id": tid, "instruction": "make a folder called Test on the desktop",
            "evaluator": {"func": "include_exclude", "expected": {"include": ["Test"]},
                          "result": {"type": "vm_command_line", "command": "ls /root/Desktop"}}}


def main():
    outroot = tempfile.mkdtemp(prefix="realrun-test-")
    try:
        # 1. reply task PASSes
        rec = realrun.run_task(reply_task(), FakeUser(), fake_vm, clock=FakeClock(), outdir=outroot)
        check("reply task PASS", rec["verdict"] == "PASS" and rec["step_failed"] is None,
              json.dumps(rec)[:300])

        # 2. state task PASSes
        rec = realrun.run_task(state_task(), FakeUser(), fake_vm, clock=FakeClock(), outdir=outroot)
        check("state task PASS", rec["verdict"] == "PASS", json.dumps(rec)[:300])

        # 3. seconds equals the fake-clock difference between the first and last clock reads
        clock = FakeClock()
        rec = realrun.run_task(reply_task("reply-clock"), FakeUser(), fake_vm, clock=clock, outdir=outroot)
        expected = clock.log[-1] - clock.log[0]
        check("seconds equals fake-clock difference", rec["seconds"] == expected,
              "seconds=%r expected=%r" % (rec["seconds"], expected))
        check("record json written", os.path.exists(os.path.join(outroot, "reply-clock.json")))

        # 4. exception in setup -> FAIL with step_failed "setup"
        def boom_vm(cmd):
            if cmd == "bad-setup":
                raise RuntimeError("boom")
            return fake_vm(cmd)
        task = reply_task("setup-boom")
        task["setup"] = ["bad-setup", "never-run"]
        rec = realrun.run_task(task, FakeUser(), boom_vm, clock=FakeClock(), outdir=outroot)
        check("setup exception -> FAIL", rec["verdict"] == "FAIL", json.dumps(rec)[:300])
        check("step_failed is setup", rec["step_failed"] == "setup", repr(rec["step_failed"]))
        check("error recorded", rec["error"] is not None and "boom" in rec["error"], repr(rec["error"]))

        # 5. suite summary counts
        suite_dir = tempfile.mkdtemp(prefix="realrun-suite-")
        suite_path = os.path.join(suite_dir, "suite.json")
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("s-pass"), state_task("s-pass2"),
                                 {"id": "s-fail", "instruction": "x",
                                  "evaluator": {"func": "include_exclude",
                                                "expected": {"include": ["nope"]},
                                                "result": {"type": "reply"}}}]}, f)
        summary = realrun.run_suite(suite_path, FakeUser(), fake_vm, outdir=outroot)
        check("summary counts", (summary["total"], summary["pass"], summary["fail"]) == (3, 2, 1),
              json.dumps({k: summary[k] for k in ("total", "pass", "fail")}))
        check("summary.json written", os.path.exists(os.path.join(outroot, "summary.json")))
        only = realrun.run_suite(suite_path, FakeUser(), fake_vm, ids=["s-pass"], outdir=outroot)
        check("ids filter", only["total"] == 1 and only["pass"] == 1, json.dumps(only)[:200])
        shutil.rmtree(suite_dir, ignore_errors=True)

        # 6. no fixed sleeps in realrun.py
        with open(os.path.join(HERE, "realrun.py"), encoding="utf-8") as f:
            src = f.read()
        check("no sleep( in realrun.py", "sleep(" not in src)
    finally:
        shutil.rmtree(outroot, ignore_errors=True)

    if FAILS:
        print("FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
