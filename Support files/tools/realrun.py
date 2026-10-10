#!/usr/bin/env python3
"""Run task-file tasks the way a real user would: reset the desk in the VM,
type the instruction through QMP, press Enter, wait for the desk to finish,
photograph it, then grade the result. Stdlib only. No fixed sleeps.

run_task(task, user, run_in_vm, clock=time.monotonic, outdir=...) -> record dict
run_suite(path, user, run_in_vm, ids=None, outdir=...)           -> summary dict
main(): builds QMP, RealUser and the VM runner (tools/tsh), then runs a suite.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import evaluators  # noqa: E402
import tasklib  # noqa: E402
from realuser import INPUT  # noqa: E402

OUTDIR = "run/realrun"
REPLY_KEY = "reply"  # desk.py:4038 _state() -> {"reply": self.last_reply, ...}


def _add(steps, name, seconds):
    steps[name] = steps.get(name, 0.0) + seconds


def run_task(task, user, run_in_vm, clock=time.monotonic, outdir=OUTDIR):
    tid = task["id"]
    steps = {}
    state = {"step": None}
    step_failed = None
    error = None
    verdict = "FAIL"
    reason = ""
    observed = ""
    typed_ok = None
    start = clock()

    def timed(name, fn):
        state["step"] = name
        t0 = clock()
        try:
            return fn()
        finally:
            _add(steps, name, clock() - t0)

    def getter(spec):
        rtype = spec.get("type")
        if rtype == "vm_command_line":
            return run_in_vm(spec["command"])
        if rtype == "reply":
            obj = json.loads(run_in_vm("llmos desk-state"))
            return obj[REPLY_KEY]
        if rtype == "rect":
            return user.rect(spec["selector"])["text"]
        raise ValueError("unknown result type %r" % rtype)

    try:
        timed("reset", lambda: run_in_vm("llmos desk-ctl testreset"))
        for cmd in task.get("setup", []):
            timed("setup", lambda c=cmd: run_in_vm(c))
        typed_ok = timed("type", lambda: user.type_into(INPUT, task["instruction"]))
        timed("press", lambda: user.press("ret"))
        timed("wait", lambda: run_in_vm("llmos desk-ctl wait %s" % task.get("timeout_s", 120)))
        shot_path = os.path.join(outdir, "%s.png" % tid)
        timed("shot", lambda: user.shot(shot_path))
        graded = timed("grade", lambda: evaluators.evaluate(task, getter))
        verdict = graded["verdict"]
        reason = graded["reason"]
        observed = graded["observed"]
    except Exception as e:  # noqa: BLE001 - recorded, remaining steps skipped
        step_failed = state["step"]
        error = repr(e)[:300]
        verdict = "FAIL"
        reason = "step %s raised" % step_failed
        observed = ""
    seconds = clock() - start

    record = {
        "id": tid,
        "instruction": task.get("instruction", ""),
        "verdict": verdict,
        "reason": reason,
        "observed": str(observed)[:500],
        "typed_ok": typed_ok,
        "seconds": seconds,
        "steps": steps,
        "step_failed": step_failed,
        "error": error,
    }
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "%s.json" % tid), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record


def run_suite(path, user, run_in_vm, ids=None, outdir=OUTDIR):
    data = tasklib.load(path)
    tasks = data["tasks"]
    if ids:
        wanted = set(ids)
        tasks = [t for t in tasks if t["id"] in wanted]
    t0 = time.monotonic()
    rows = []
    for task in tasks:
        rec = run_task(task, user, run_in_vm, outdir=outdir)
        rows.append({"id": rec["id"], "verdict": rec["verdict"], "seconds": rec["seconds"]})
    summary = {
        "suite": os.path.basename(path),
        "total": len(rows),
        "pass": sum(1 for r in rows if r["verdict"] == "PASS"),
        "fail": sum(1 for r in rows if r["verdict"] != "PASS"),
        "seconds": time.monotonic() - t0,
        "tasks": rows,
    }
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def _vm_runner(timeout=900):
    """Run a shell command in the test VM through tools/tsh; return its stdout."""
    def run_in_vm(cmd):
        p = subprocess.run(["tools/tsh", cmd, str(timeout)], capture_output=True, text=True,
                           timeout=timeout + 30)
        return p.stdout
    return run_in_vm


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a task suite as a real user through QMP.")
    ap.add_argument("suite", help="task file (JSON with a tasks list)")
    ap.add_argument("--ids", nargs="+", default=None, help="only these task ids")
    ap.add_argument("--outdir", default=OUTDIR)
    args = ap.parse_args(argv)

    from qmp import QMP
    from realuser import RealUser

    q = QMP("run/tqmp.sock")
    run_in_vm = _vm_runner()
    user = RealUser(q, run_in_vm)
    try:
        summary = run_suite(args.suite, user, run_in_vm, ids=args.ids, outdir=args.outdir)
    finally:
        q.close()
    print(json.dumps({k: summary[k] for k in ("suite", "total", "pass", "fail", "seconds")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
