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
from vmjson import vm_json, vm_text  # noqa: E402

OUTDIR = "run/realrun"
REPLY_KEY = "reply"  # desk.py:4038 _state() -> {"reply": self.last_reply, ...}


def _add(steps, name, seconds):
    steps[name] = steps.get(name, 0.0) + seconds


HOME_TOKEN = "{home}"
OWNER_USER_FILE = "/etc/llmos/owner-user"
_HOME_CMD = ('u=$(cat %s 2>/dev/null); if [ -n "$u" ]; then getent passwd "$u" | cut -d: -f6; else echo /root; fi'
             % OWNER_USER_FILE)
_home_cache = {"value": None}  # the desk's home, resolved once per VM boot (reset by fresh_overlay)


def owner_home(run_in_vm):
    """The owner account's home (the desk runs as the owner), from the test shell. Cached until the next
    reboot. Any failure or empty output gives "/root"."""
    if _home_cache["value"] is None:
        try:
            home = (run_in_vm(_HOME_CMD) or "").strip()
        except Exception:  # noqa: BLE001 - default below
            home = ""
        _home_cache["value"] = home or "/root"
    return _home_cache["value"]


def reset_home_cache():
    _home_cache["value"] = None


def _expand_home(obj, home):
    """Replace {home} in every string of a task's setup/evaluator value. Other braces are untouched."""
    if isinstance(obj, str):
        return obj.replace(HOME_TOKEN, home)
    if isinstance(obj, list):
        return [_expand_home(x, home) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand_home(v, home) for k, v in obj.items()}
    return obj


def expand_task_home(task, home):
    """A copy of task with {home} replaced in its setup and evaluator. The instruction is left as it is."""
    out = dict(task)
    for key in ("setup", "evaluator"):
        if key in task:
            out[key] = _expand_home(task[key], home)
    return out


PATHS = ("page", "say")


def run_task(task, user, run_in_vm, clock=time.monotonic, outdir=OUTDIR, path="page", sleep=time.sleep):
    if path not in PATHS:
        raise ValueError("path must be one of %s, got %r" % (PATHS, path))
    # QMP resolves the screendump filename in QEMU's own working directory, so the shot path must be absolute
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    tid = task["id"]
    steps = {}
    state = {"step": None}
    step_failed = None
    error = None
    verdict = "FAIL"
    reason = ""
    observed = ""
    typed_ok = None
    shot_error = None
    cancelled = False
    stuck = False
    drain_seconds = None
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
            return vm_text(run_in_vm(spec["command"]))
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
        home = owner_home(run_in_vm)
        task = expand_task_home(task, home)
        for cmd in task.get("setup", []):
            timed("setup", lambda c=cmd: run_in_vm(c))
        if task.get("setup") and home != "/root":
            # setup runs as root: hand the seeded files to the owner so the desk can see them
            timed("setup", lambda: run_in_vm('chown -R "$(cat %s)" %s' % (OWNER_USER_FILE, shlex.quote(home))))
        before = timed("state", lambda: vm_json(run_in_vm("llmos desk-state")))
        if before is None:
            raise ValueError("desk-state is not JSON")
        ctx["before_reply"] = before.get(REPLY_KEY) or ""
        done0 = before.get("done")          # requests the desk had finished before this one (older desks: no key)
        if path == "say":
            timed("say", lambda: run_in_vm("llmos say " + shlex.quote(task["instruction"])))
            typed_ok = True
        else:
            typed_ok = timed("type", lambda: user.type_into(INPUT, task["instruction"]))
            timed("press", lambda: user.press("ret"))
        timeout_s = task.get("timeout_s", 120)
        if isinstance(done0, int) and not isinstance(done0, bool):
            wait_cmd = "llmos desk-ctl wait %s after %d" % (timeout_s, done0)
        else:
            wait_cmd = "llmos desk-ctl wait %s" % timeout_s
        waited = timed("wait", lambda: run_in_vm(wait_cmd))
        wait_state = vm_json(waited)
        busy = isinstance(wait_state, dict) and bool(wait_state.get("busy"))
        queued = _queued(wait_state)
        if busy:
            step_failed = "wait"
            verdict = "FAIL"
            reason = "still busy after %ss" % timeout_s
        shot_path = os.path.join(outdir, "%s.png" % tid)
        try:
            timed("shot", lambda: user.shot(shot_path))
        except Exception as e:  # noqa: BLE001 - recorded; the verdict comes from evaluate
            shot_error = repr(e)[:200]
        if busy or queued > 0:
            # stop the turn and whatever queued behind it, so the next task does not get a stale reply
            cancelled = True
            idle, drain_seconds = timed("drain", lambda: _drain(run_in_vm, clock, sleep))
            stuck = not idle
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
        "shot_error": shot_error,
        "cancelled": cancelled,
        "drain_seconds": drain_seconds,
        "stuck": stuck,
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


def run_suite(path, user, run_in_vm, ids=None, outdir=OUTDIR, run_path="page", repeat=1, fresh=None,
              sleep=time.sleep, clock=time.monotonic):
    """Run every task `repeat` times. Before repeat r > 1, fresh() is called (a fresh overlay).
    A task that left the desk stuck (record "stuck") is followed by fresh() before the next task.
    repeat == 1 writes {outdir}/<id>.json; otherwise {outdir}/r{r}/<id>.json."""
    if repeat < 1:
        raise ValueError("repeat must be >= 1, got %r" % repeat)
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    data = tasklib.load(path)
    tasks = data["tasks"]
    if ids:
        wanted = set(ids)
        tasks = [t for t in tasks if t["id"] in wanted]
    t0 = time.monotonic()
    per = {t["id"]: {"passes": 0, "seconds": 0.0} for t in tasks}
    stuck_prev = False
    for r in range(1, repeat + 1):
        if fresh is not None and r > 1:
            fresh()
            stuck_prev = False
        rdir = outdir if repeat == 1 else os.path.join(outdir, "r%d" % r)
        os.makedirs(rdir, exist_ok=True)
        for task in tasks:
            if fresh is not None and stuck_prev:
                fresh()
            stuck_prev = False
            rec = run_task(task, user, run_in_vm, clock=clock, outdir=rdir, path=run_path, sleep=sleep)
            stuck_prev = rec["stuck"]
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


def _poll(probe, limit, clock, sleep, interval=2):
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
        sleep(interval)


DRAIN_LIMIT = 60  # s to wait for a cancelled desk to go idle before it counts as stuck


def _queued(obj):
    """The queued request count in desk-state (desk.py _state). Missing or not a number counts as 0."""
    if not isinstance(obj, dict):
        return 0
    try:
        return int(obj.get("queued") or 0)
    except (TypeError, ValueError):
        return 0


def _desk_idle(out):
    data = vm_json(out)
    return isinstance(data, dict) and not data.get("busy") and _queued(data) == 0


def _drain(run_in_vm, clock, sleep):
    """Send `llmos desk-ctl cancel`, then poll desk-state once a second until it is idle (not busy, nothing
    queued) or DRAIN_LIMIT s pass. A failed cancel still polls. Returns (idle, seconds)."""
    t0 = clock()
    try:
        run_in_vm("llmos desk-ctl cancel")
    except Exception:  # noqa: BLE001 - the desk may still stop on its own; the poll decides
        pass
    idle = _poll(lambda: _desk_idle(run_in_vm("llmos desk-state")), DRAIN_LIMIT, clock, sleep, interval=1)
    return idle, clock() - t0


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
    reset_home_cache()
    if not _poll(lambda: "up" in run_in_vm("echo up"), 300 * slow, clock, sleep):
        raise RuntimeError("fresh: VM not ready")
    run_in_vm(ONBOARD_CMD)
    if not _poll(lambda: _desk_ready(run_in_vm("llmos desk-state")), 120 * slow, clock, sleep):
        raise RuntimeError("fresh: desk not ready")


def parse_ids(values):
    """--ids accepts space-separated, comma-joined (S12,S13) or both (S12, S13). Returns the id list."""
    return [x.strip() for a in (values or []) for x in a.split(",") if x.strip()]


def select_tasks(tasks, ids):
    """Tasks whose id is in ids, in suite order, and the ids that match no task."""
    known = {t["id"] for t in tasks}
    unknown = [i for i in ids if i not in known]
    wanted = set(ids)
    return [t for t in tasks if t["id"] in wanted], unknown


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
    ids = None
    tasks = tasklib.load(args.suite)["tasks"]
    if args.ids is not None:
        ids = parse_ids(args.ids)
        tasks, unknown = select_tasks(tasks, ids)
        if unknown:
            print("unknown ids: %s" % ", ".join(unknown), file=sys.stderr)
        if not tasks:
            print("no task matches --ids: %s" % ", ".join(ids), file=sys.stderr)
            return 2
        ids = [t["id"] for t in tasks]
    if not args.run:
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
        summary = run_suite(args.suite, user, run_in_vm, ids=ids, outdir=args.outdir,
                            run_path=args.path, repeat=args.repeat,
                            fresh=fresh)
    finally:
        user.qmp.close()
    print(json.dumps({k: summary[k] for k in ("suite", "repeat", "total", "pass", "fail", "seconds")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
