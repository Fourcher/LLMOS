#!/usr/bin/env python3
"""Checks tools/tasks/safety.json loads and that a bare "Done." reply fails the graded ones. Stdlib only."""

import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)

import tasklib  # noqa: E402

PATH = os.path.join(TOOLS, "tasks", "safety.json")
FAKE_REPLY = "Done."
MUST_FAIL = ["saf-1", "saf-2", "saf-3", "saf-4", "saf-6", "saf-7"]


def passes(reply, expected):
    low = reply.lower()
    for item in expected.get("include", []):
        if item.lower() not in low:
            return False
    for item in expected.get("exclude", []):
        if item.lower() in low:
            return False
    return True


def main():
    data = tasklib.load(PATH)
    tasks = {t["id"]: t for t in data["tasks"]}
    assert len(data["tasks"]) == 8, "expected 8 tasks, got %d" % len(data["tasks"])
    print("ok %d tasks load and validate" % len(data["tasks"]))
    for task_id in MUST_FAIL:
        task = tasks[task_id]
        result = passes(FAKE_REPLY, task["evaluator"]["expected"])
        assert result is False, "%s: fake reply %r unexpectedly passed" % (task_id, FAKE_REPLY)
        print("ok %s fails on fake reply %r" % (task_id, FAKE_REPLY))
    print("all good")


if __name__ == "__main__":
    main()
