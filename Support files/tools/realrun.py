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


def vm_json(text):
    """The JSON object (a dict) in VM command output, or None. tsh output carries more than the
    reply (the echoed command, prompt lines, the "[vmctl: ...]" trailer), so: the whole text if it is
    one object; else the last line that is one object; else the span from the first "{" to the last "}".
    Output with no object (e.g. "[vmctl: TIMEOUT after 30.4s]") gives None."""
    if not isinstance(text, str):
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    for line in reversed([ln.strip() for ln in text.splitlines()]):
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        try:
            obj = json.loads(text[first:last + 1])
        except ValueError:
            return None
        if isinstance(obj, dict):
            return obj
    return None


PATHS = ("page", "say")


def run_task(task, user, run_in_vm, clock=time.monotonic, outdir=OUTDIR, path="page"):
    if path not in PATHS:
        raise ValueError("path must be one of %s, got %r" % (PATHS, path))
    tid = task["id"]
    steps = {}
    state = {"step": None}
    step_failed = None
    error = None
    verdict = "FAIL"
    reason = ""
    observed = ""
    typed_ok = None
    ctx = {"before_reply": "", "stale": False}
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
            obj = vm_json(run_in_vm("llmos desk-state"))
            if obj is None:
                raise ValueError("desk-state is not JSON")
            cur = obj[REPLY_KEY]
            if ctx["before_reply"] and cur == ctx["before_reply"]:
                ctx["stale"] = True  # reply left by the previous task: no new reply
                return ""
            return cur
        if rtype == "rect":
            return user.rect(spec["selector"])["text"]
        raise ValueError("unknown result type %r" % rtype)

    try:
        timed("reset", lambda: run_in_vm("llmos desk-ctl testreset"))
        for cmd in task.get("setup", []):
            timed("setup", lambda c=cmd: run_in_vm(c))
        before = timed("state", lambda: vm_json(run_in_vm("llmos desk-state")))
        if before is None:
            raise ValueError("desk-state is not JSON")
        ctx["before_reply"] = before.get(REPLY_KEY) or ""
        if path == "say":
            timed("say", lambda: run_in_vm("llmos say " + shlex.quote(task["instruction"])))
            typed_ok = True
        else:
            typed_ok = timed("type", lambda: user.type_into(INPUT, task["instruction"]))
            timed("press", lambda: user.press("ret"))
        timeout_s = task.get("timeout_s", 120)
        waited = timed("wait", lambda: run_in_vm("llmos desk-ctl wait %s" % timeout_s))
        wait_state = vm_json(waited)
        busy = isinstance(wait_state, dict) and bool(wait_state.get("busy"))
        if busy:
            step_failed = "wait"
            verdict = "FAIL"
            reason = "still busy after %ss" % timeout_s
        shot_path = os.path.join(outdir, "%s.png" % tid)
        timed("shot", lambda: user.shot(shot_path))
        if not busy:
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
        "stale_reply": ctx["stale"],
        "path": path,
    }
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "%s.json" % tid), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record


def _label(passes, repeat):
    if passes == repeat:
        return "pass"
    if passes == 0:
        return "fail"
    return "flaky"


def run_suite(path, user, run_in_vm, ids=None, outdir=OUTDIR, run_path="page", repeat=1, fresh=None):
    """Run every task `repeat` times. Before repeat r > 1, fresh() is called (a fresh overlay).
    repeat == 1 writes {outdir}/<id>.json; otherwise {outdir}/r{r}/<id>.json."""
    if repeat < 1:
        raise ValueError("repeat must be >= 1, got %r" % repeat)
    data = tasklib.load(path)
    tasks = data["tasks"]
    if ids:
        wanted = set(ids)
        tasks = [t for t in tasks if t["id"] in wanted]
    t0 = time.monotonic()
    per = {t["id"]: {"passes": 0, "seconds": 0.0} for t in tasks}
    for r in range(1, repeat + 1):
        if fresh is not None and r > 1:
            fresh()
        rdir = outdir if repeat == 1 else os.path.join(outdir, "r%d" % r)
        for task in tasks:
            rec = run_task(task, user, run_in_vm, outdir=rdir, path=run_path)
            per[rec["id"]]["seconds"] += rec["seconds"]
            if rec["verdict"] == "PASS":
                per[rec["id"]]["passes"] += 1
    rows = []
    for task in tasks:
        tid = task["id"]
        k = per[tid]["passes"]
        rows.append({
            "id": tid,
            "verdict": "PASS" if k == repeat else "FAIL",
            "seconds": per[tid]["seconds"],
            "runs": repeat,
            "passes": k,
            "rate": round(k / repeat, 2),
            "label": _label(k, repeat),
        })
    summary = {
        "suite": os.path.basename(path),
        "path": run_path,
        "repeat": repeat,
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
        if p.returncode != 0 and not p.stdout:
            raise RuntimeError(f"tsh exit {p.returncode}: {p.stderr[:200]}")
        return p.stdout
    return run_in_vm


FRESH_IMAGE = "dist/llmos-arm64.qcow2"  # a shipped image: boot-target.sh makes a new throwaway overlay for it


def _fresh_overlay():
    """Quit the running VM, then reboot the shipped image on a new overlay (tools/boot-target.sh
    deletes run/target-overlay.qcow2 and recreates it from the image when the image is under dist/)."""
    env = dict(os.environ, LLMOS_TESTSHELL="1")
    subprocess.run(["tools/boot-target.sh", FRESH_IMAGE, "4096"], env=env, check=True,
                   stdout=subprocess.DEVNULL)


# the onboarding command, quoted exactly as tools/calc-smoke.sh:21 sends it (the \" are literal)
ONBOARD_CMD = ('cd /usr/lib/llmos && python3 -c "from llmos import config; '
               'config.settings.set(\\"onboarded\\", True)"')
WIZARD_SCREEN = "wizard"  # desk.py:1289 set_screen("wizard"); desk.py:4038 _state() reports self.screen
DESK_SCREEN = "desk"      # desk.py:1315 set_screen("desk"); desk.py:4038 _state() reports self.screen


def _poll(probe, limit, clock, sleep):
    """Call probe() until it returns True; False when `limit` seconds of `clock()` have passed.
    A probe that raises counts as not ready. The only place that sleeps between tries."""
    deadline = clock() + limit
    while True:
        try:
            if probe():
                return True
        except Exception:
            pass
        if clock() >= deadline:
            return False
        sleep(2)


def _slow():
    return float(os.environ.get("LLMOS_SLOW", "1") or "1")


def _desk_ready(out):
    data = vm_json(out)
    return isinstance(data, dict) and data.get("screen") == DESK_SCREEN


def fresh_overlay(run_in_vm, boot=_fresh_overlay, clock=time.monotonic, sleep=time.sleep):
    """Reboot onto a fresh overlay, then wait until the VM answers, onboard it (as calc-smoke does)
    and wait until the desk is past the first-run wizard. Raises RuntimeError if either wait times out."""
    slow = _slow()
    boot()
    if not _poll(lambda: "up" in run_in_vm("echo up"), 300 * slow, clock, sleep):
        raise RuntimeError("fresh: VM not ready")
    run_in_vm(ONBOARD_CMD)
    if not _poll(lambda: _desk_ready(run_in_vm("llmos desk-state")), 120 * slow, clock, sleep):
        raise RuntimeError("fresh: desk not ready")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a task suite as a real user through QMP.")
    ap.add_argument("suite", help="task file (JSON with a tasks list)")
    ap.add_argument("--ids", nargs="+", default=None, help="only these task ids")
    ap.add_argument("--outdir", default=OUTDIR)
    ap.add_argument("--path", choices=PATHS, default="page",
                    help="page: type into the page and press Enter; say: llmos say <instruction>")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run the whole suite N times; repeats 2..N each start on a fresh overlay "
                         "(flake runs: use 3)")
    ap.add_argument("--run", action="store_true", help="boot the test VM and run the suite (required)")
    args = ap.parse_args(argv)
    if args.repeat < 1:
        ap.error("--repeat must be >= 1")
    if not args.run:
        tasks = tasklib.load(args.suite)["tasks"]
        if args.ids:
            wanted = set(args.ids)
            tasks = [t for t in tasks if t["id"] in wanted]
        print("dry: would run %d tasks from %s" % (len(tasks), args.suite))
        print("add --run to boot the test VM")
        return 0

    from qmp import QMP
    from realuser import RealUser

    q = QMP("run/tqmp.sock")
    run_in_vm = _vm_runner()
    user = RealUser(q, run_in_vm)

    def fresh():
        # the reboot kills the old QMP socket: close it, reboot on a new overlay, reconnect
        q.close()
        fresh_overlay(run_in_vm)
        user.qmp = QMP("run/tqmp.sock")

    try:
        summary = run_suite(args.suite, user, run_in_vm, ids=args.ids, outdir=args.outdir,
                            run_path=args.path, repeat=args.repeat,
                            fresh=fresh if args.repeat > 1 else None)
    finally:
        user.qmp.close()
    print(json.dumps({k: summary[k] for k in ("suite", "repeat", "total", "pass", "fail", "seconds")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
