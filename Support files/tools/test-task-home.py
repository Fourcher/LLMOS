#!/usr/bin/env python3
"""Task setups and evaluators use {home}, which realrun replaces with the owner's home (the desk's user).
Fake VM only. Stdlib only."""
import json
import glob
import os
import shlex
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import realrun  # noqa: E402
import tasklib  # noqa: E402

FAILS = []
OWNER_FOLDERS = ("Documents", "Downloads", "Pictures", "Desktop", "Music", "Videos", ".local", "notes")


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILS.append(name)


class FakeUser:
    def type_into(self, sel, text, secret=False):
        return True

    def press(self, key):
        pass

    def shot(self, path):
        pass

    def rect(self, sel):
        return {"ok": True, "text": ""}


class FakeVM:
    """Answers the home probe with `home_out` (or raises when home_out is an exception), desk commands
    with fixed JSON, and every other command with `other`."""

    def __init__(self, home_out="/home/owner\n", other="yes\n"):
        self.home_out = home_out
        self.other = other
        self.sent = []

    def __call__(self, cmd):
        self.sent.append(cmd)
        if cmd == realrun._HOME_CMD:
            if isinstance(self.home_out, Exception):
                raise self.home_out
            return self.home_out
        if cmd == "echo up":
            return "up\n"
        if cmd == "llmos desk-state":
            return json.dumps({"screen": "desk", "reply": "", "busy": False, "queued": 0})
        if cmd.startswith("llmos desk-ctl wait"):
            return json.dumps({"busy": False, "queued": 0})
        if cmd == realrun.ONBOARD_CMD:
            return ""
        return self.other


def task_for(home_token_setup):
    return {
        "id": "T-home",
        "instruction": "make a folder called Taxes 2026",
        "setup": [home_token_setup],
        "evaluator": {
            "func": "include_exclude",
            "result": {"type": "vm_command_line", "command": "test -d '{home}/Documents' && echo yes"},
            "expected": {"include": ["yes"]},
        },
        "weak": False,
        "timeout_s": 5,
    }


def run_one(vm, task):
    outdir = tempfile.mkdtemp(prefix="task-home-")
    realrun.reset_home_cache()
    return realrun.run_task(task, FakeUser(), vm, outdir=outdir, sleep=lambda s: None)


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, list):
        for x in obj:
            yield from walk_strings(x)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)


def main():
    # owner_home: trailing newline stripped, value cached
    realrun.reset_home_cache()
    vm = FakeVM(home_out="/home/owner\n")
    check("home strips trailing newline", realrun.owner_home(vm) == "/home/owner",
          repr(realrun.owner_home(vm)))
    check("home cached: probe runs once", vm.sent.count(realrun._HOME_CMD) == 1, repr(vm.sent))

    # empty output and a raising VM both give /root
    realrun.reset_home_cache()
    check("empty output gives /root", realrun.owner_home(FakeVM(home_out="")) == "/root")
    realrun.reset_home_cache()
    check("raising VM gives /root", realrun.owner_home(FakeVM(home_out=RuntimeError("tsh down"))) == "/root")

    # cache reset after fresh_overlay: the next boot's home is read again
    realrun.reset_home_cache()
    first = FakeVM(home_out="/home/a\n")
    check("first boot home", realrun.owner_home(first) == "/home/a")
    second = FakeVM(home_out="/home/b\n")
    realrun.fresh_overlay(second, boot=lambda: None, clock=lambda: 0.0, sleep=lambda s: None)
    check("fresh_overlay resets home cache", realrun.owner_home(second) == "/home/b",
          repr(realrun.owner_home(second)))

    # run_task: setup gets the owner home, no {home} is sent to the VM, and chown follows setup
    realrun.reset_home_cache()
    vm = FakeVM(home_out="/home/owner\n")
    rec = run_one(vm, task_for("mkdir -p '{home}/Documents'"))
    check("setup uses owner home", "mkdir -p '/home/owner/Documents'" in vm.sent, repr(vm.sent))
    check("chown follows setup for owner home",
          "chown -R \"$(cat /etc/llmos/owner-user)\" /home/owner" in vm.sent, repr(vm.sent))
    check("no {home} sent to VM", not any("{home}" in c for c in vm.sent), repr(vm.sent))
    check("evaluator reads owner home and passes", rec["verdict"] == "PASS", repr(rec))

    # home with a space: quoted in the chown
    realrun.reset_home_cache()
    vm = FakeVM(home_out="/home/my owner\n")
    run_one(vm, task_for("mkdir -p '{home}/Documents'"))
    check("setup keeps spaced home quoted", "mkdir -p '/home/my owner/Documents'" in vm.sent, repr(vm.sent))
    check("chown quotes spaced home",
          "chown -R \"$(cat /etc/llmos/owner-user)\" " + shlex.quote("/home/my owner") in vm.sent, repr(vm.sent))

    # /root: no chown
    realrun.reset_home_cache()
    vm = FakeVM(home_out="/root\n")
    run_one(vm, task_for("mkdir -p '{home}/Documents'"))
    check("no chown when home is /root", not any(c.startswith("chown") for c in vm.sent), repr(vm.sent))
    check("setup uses /root when home is /root", "mkdir -p '/root/Documents'" in vm.sent, repr(vm.sent))

    # tasks with no {home} and no setup: unchanged, no chown
    realrun.reset_home_cache()
    vm = FakeVM(home_out="/home/owner\n")
    plain = {"id": "T-plain", "instruction": "x", "setup": ["echo hi"],
             "evaluator": {"func": "include_exclude", "result": {"type": "vm_command_line", "command": "echo yes"},
                           "expected": {"include": ["yes"]}}, "weak": False, "timeout_s": 5}
    run_one(vm, plain)
    check("setup without {home} is sent as written", "echo hi" in vm.sent, repr(vm.sent))
    check("chown only when the task has setup", sum(c.startswith("chown") for c in vm.sent) == 1, repr(vm.sent))

    # every task file loads and no owner-file path still points at /root
    tasks_dir = os.path.join(HERE, "tasks")
    for path in sorted(glob.glob(os.path.join(tasks_dir, "*.json"))):
        name = os.path.basename(path)
        if name == "usecase-checks.json":
            # a map from instruction to {evaluator, setup}, not a task file: checked entry by entry
            with open(path, encoding="utf-8") as f:
                entries = json.load(f)
            bad = []
            for instruction, entry in entries.items():
                for s in walk_strings(entry):
                    for folder in OWNER_FOLDERS:
                        if ("/root/" + folder) in s:
                            bad.append("%s: %s" % (instruction, s[:80]))
            check("%s has no /root owner paths" % name, not bad, "; ".join(bad[:3]))
            continue
        try:
            data = tasklib.load(path)
        except Exception as e:  # noqa: BLE001 - reported as FAIL
            check("%s loads via tasklib" % name, False, repr(e)[:200])
            continue
        bad = []
        for task in data["tasks"]:
            for key in ("setup", "evaluator"):
                for s in walk_strings(task.get(key, [] if key == "setup" else {})):
                    for folder in OWNER_FOLDERS:
                        if ("/root/" + folder) in s:
                            bad.append("%s %s: %s" % (task["id"], key, s[:80]))
        check("%s has no /root owner paths in setup/evaluator" % name, not bad, "; ".join(bad[:3]))

    if FAILS:
        print("FAILED %d" % len(FAILS))
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
