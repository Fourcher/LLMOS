#!/usr/bin/env python3
"""Tests for tools/evaluators.py. Stdlib only."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluators  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILURES.append(name)


def task(func, expected, rtype="vm_command_line", feasible=True):
    return {
        "id": "t",
        "instruction": "x",
        "feasible": feasible,
        "evaluator": {
            "func": func,
            "result": {"type": rtype, "command": "true"},
            "expected": expected,
        },
    }


def getter(value):
    return lambda _spec: value


def raiser(_spec):
    raise RuntimeError("boom")


# getter errors and None
r = evaluators.evaluate(task("include_exclude", {"include": ["a"]}), raiser)
check("getter raises -> FAIL", r["verdict"] == "FAIL" and "getter error" in r["reason"], r)
r = evaluators.evaluate(task("include_exclude", {"include": ["a"]}), getter(None))
check("None -> FAIL", r["verdict"] == "FAIL" and "no output" in r["reason"], r)

# empty output under include rule
r = evaluators.evaluate(task("include_exclude", {"include": ["a"]}), getter(""))
check("empty output under include -> FAIL", r["verdict"] == "FAIL" and "empty output" in r["reason"], r)

# include present, exclude absent
r = evaluators.evaluate(task("include_exclude", {"include": ["Notes"], "exclude": ["error"]}), getter("notes folder ok"))
check("include present + exclude absent -> PASS", r["verdict"] == "PASS", r)

# exclude present
r = evaluators.evaluate(task("include_exclude", {"include": ["notes"], "exclude": ["error"]}), getter("Notes: error"))
check("exclude present -> FAIL", r["verdict"] == "FAIL", r)

# equals match / mismatch
r = evaluators.evaluate(task("equals", {"equals": "yes"}), getter("yes\n"))
check("equals match -> PASS", r["verdict"] == "PASS", r)
r = evaluators.evaluate(task("equals", {"equals": "yes"}), getter("no"))
check("equals mismatch -> FAIL", r["verdict"] == "FAIL", r)

# proc_running empty -> FAIL
r = evaluators.evaluate(task("proc_running", {"include": ["firefox"]}), getter(""))
check("proc_running empty -> FAIL", r["verdict"] == "FAIL" and "not running" in r["reason"], r)

# infeasible task: refusal phrase passes, otherwise fails
r = evaluators.evaluate(task("include_exclude", {"include": ["x"]}, rtype="reply", feasible=False), getter("Sorry, I cannot do that."))
check("infeasible + refusal -> PASS", r["verdict"] == "PASS", r)
r = evaluators.evaluate(task("include_exclude", {"include": ["x"]}, rtype="reply", feasible=False), getter("Done."))
check("infeasible + no refusal -> FAIL", r["verdict"] == "FAIL", r)

# do nothing: every feasible task with an include rule must FAIL
fixtures = [
    task("include_exclude", {"include": ["Notes"]}),
    task("file_exists", {"include": ["yes"]}),
    task("include_exclude", {"include": ["Reminder saved"]}, rtype="reply"),
]
for i, t in enumerate(fixtures):
    r = evaluators.evaluate_do_nothing(t)
    check("do-nothing FAIL fixture %d" % i, r["verdict"] == "FAIL", r)

# (a) a task with no rules checks nothing: FAIL unless weak
r = evaluators.evaluate(task("include_exclude", {}), getter("x"))
check("no rules non-weak feasible -> FAIL", r["verdict"] == "FAIL" and "no rules" in r["reason"], r)
weak_task = task("include_exclude", {})
weak_task["weak"] = True
r = evaluators.evaluate(weak_task, getter("x"))
check("no rules weak -> not failed for no-rules", "no rules" not in r["reason"], r)

# (b) a hanging getter is cut off at timeout_s
import time  # noqa: E402

def sleeper(_spec):
    time.sleep(2)
    return "late"

slow_task = task("include_exclude", {"include": ["late"]})
slow_task["timeout_s"] = 1
t0 = time.monotonic()
r = evaluators.evaluate(slow_task, sleeper)
elapsed = time.monotonic() - t0
check("hanging getter -> FAIL timeout after 1s", r["verdict"] == "FAIL" and r["reason"] == "timeout after 1s", r)
check("timeout returns in under 1.5 s", elapsed < 1.5, "elapsed=%.2f" % elapsed)

if FAILURES:
    print("FAILED: %s" % ", ".join(FAILURES))
    sys.exit(1)
print("all good")
