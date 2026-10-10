#!/usr/bin/env python3
"""Loader and validator for task files (see tools/tasks/schema.md). Stdlib only."""

import json

ALLOWED_FUNCS = {"include_exclude", "equals", "file_exists", "setting_is", "proc_running"}
ALLOWED_RESULT_TYPES = {"vm_command_line", "reply", "rect"}

DEFAULTS = {
    "variants": [],
    "setup": [],
    "feasible": True,
    "expect_refusal": False,
    "expect_question": False,
    "timeout_s": 120,
    "reachable_by_agent": True,
    "weak": False,
}


def _fail(task_id, problem):
    raise ValueError("task %s: %s" % (task_id, problem))


def _validate_task(task, index, seen_ids):
    if not isinstance(task, dict):
        raise ValueError("task #%d: not an object" % index)
    task_id = task.get("id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task #%d: missing or empty id" % index)
    if task_id in seen_ids:
        _fail(task_id, "duplicate id")
    seen_ids.add(task_id)
    instruction = task.get("instruction")
    if not isinstance(instruction, str) or not instruction:
        _fail(task_id, "missing or empty instruction")
    evaluator = task.get("evaluator")
    if evaluator is None:
        _fail(task_id, "missing evaluator")
    if not isinstance(evaluator, dict):
        _fail(task_id, "evaluator is not an object")
    func = evaluator.get("func")
    if func not in ALLOWED_FUNCS:
        _fail(task_id, "bad evaluator func %r (allowed: %s)" % (func, ", ".join(sorted(ALLOWED_FUNCS))))
    result = evaluator.get("result")
    if not isinstance(result, dict):
        _fail(task_id, "evaluator.result missing or not an object")
    rtype = result.get("type")
    if rtype not in ALLOWED_RESULT_TYPES:
        _fail(task_id, "bad result.type %r (allowed: %s)" % (rtype, ", ".join(sorted(ALLOWED_RESULT_TYPES))))


def _fill_defaults(task):
    for key, value in DEFAULTS.items():
        if key not in task:
            task[key] = list(value) if isinstance(value, list) else value
    return task


def load(path):
    """Load and validate a task file. Returns the parsed dict with defaults filled in.

    Raises ValueError naming the task id and the problem on any violation.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError("top level must be an object with a \"tasks\" list")
    seen_ids = set()
    for index, task in enumerate(data["tasks"], start=1):
        _validate_task(task, index, seen_ids)
    for task in data["tasks"]:
        _fill_defaults(task)
    return data


def estimate_minutes(tasks):
    """Rough runtime estimate: sum of timeout_s, in minutes, times 0.4."""
    return sum(t.get("timeout_s", DEFAULTS["timeout_s"]) for t in tasks) / 60 * 0.4
