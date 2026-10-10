#!/usr/bin/env python3
"""Checks usecase-checks.json against the generated task files. Stdlib only.

Every key must be the exact instruction of a task in some generated usecases-N.json or
parity-N.json, and that task's evaluator must equal the entry's evaluator and be not weak.
Every generated file must load through tasklib.load and hold at most 40 tasks.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks")
sys.path.insert(0, HERE)

import tasklib  # noqa: E402

CHECKS = os.path.join(TASKS, "usecase-checks.json")
PATTERNS = ("usecases-*.json", "parity-*.json")


def generated_files():
    files = []
    for pattern in PATTERNS:
        files.extend(sorted(glob.glob(os.path.join(TASKS, pattern))))
    return files


def main():
    failures = []
    with open(CHECKS, encoding="utf-8") as f:
        checks = json.load(f)

    by_instruction = {}
    for path in generated_files():
        data = tasklib.load(path)
        count = len(data["tasks"])
        print("ok %s loads, %d task(s)" % (os.path.basename(path), count))
        if count > 40:
            failures.append("%s has %d tasks (max 40)" % (os.path.basename(path), count))
        for task in data["tasks"]:
            by_instruction.setdefault(task["instruction"], []).append((os.path.basename(path), task))

    for instruction, entry in checks.items():
        matches = by_instruction.get(instruction, [])
        if not matches:
            failures.append("no generated task has instruction %r" % instruction)
            continue
        for fname, task in matches:
            if task["evaluator"] != entry["evaluator"]:
                failures.append("%s in %s: evaluator differs from usecase-checks.json" % (instruction, fname))
            if task.get("weak") is not False:
                failures.append("%s in %s: weak is not false" % (instruction, fname))
            if task.get("setup", []) != entry.get("setup", []):
                failures.append("%s in %s: setup differs from usecase-checks.json" % (instruction, fname))
        print("ok %r -> %s" % (instruction, ", ".join(f for f, _ in matches)))

    if failures:
        for line in failures:
            print("FAIL " + line)
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
