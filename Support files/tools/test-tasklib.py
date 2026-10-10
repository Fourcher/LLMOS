#!/usr/bin/env python3
"""Tests for tasklib.load() and tasklib.estimate_minutes()."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tasklib  # noqa: E402


def evaluator(func="equals"):
    return {
        "func": func,
        "result": {"type": "reply"},
        "expected": {"equals": "yes"},
    }


def task(task_id, **extra):
    t = {"id": task_id, "instruction": "do the thing", "evaluator": evaluator()}
    t.update(extra)
    return t


def write_tmp(data):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f)
    return path


def expect_value_error(data, must_contain):
    path = write_tmp(data)
    try:
        tasklib.load(path)
    except ValueError as e:
        msg = str(e)
        assert must_contain in msg, "message %r does not contain %r" % (msg, must_contain)
        return msg
    finally:
        os.unlink(path)
    raise AssertionError("expected ValueError containing %r" % must_contain)


def main():
    # 1. valid file loads and gets defaults filled
    path = write_tmp({"suite": "s", "tasks": [task("t-ok")]})
    try:
        data = tasklib.load(path)
    finally:
        os.unlink(path)
    t = data["tasks"][0]
    assert t["feasible"] is True
    assert t["expect_refusal"] is False
    assert t["expect_question"] is False
    assert t["timeout_s"] == 120
    assert t["reachable_by_agent"] is True
    assert t["weak"] is False
    assert t["variants"] == [] and t["setup"] == []
    print("ok valid file loads with defaults")

    # 2. missing evaluator names the task id
    bad = task("t-noeval")
    del bad["evaluator"]
    msg = expect_value_error({"tasks": [bad]}, "t-noeval")
    assert "evaluator" in msg
    print("ok missing evaluator raises: %s" % msg)

    # 3. duplicate ids raise
    msg = expect_value_error({"tasks": [task("dup"), task("dup")]}, "dup")
    print("ok duplicate ids raise: %s" % msg)

    # 4. bad func raises
    msg = expect_value_error({"tasks": [task("t-func", evaluator=evaluator("nope"))]}, "t-func")
    print("ok bad func raises: %s" % msg)

    # 5. bad result.type raises
    ev = evaluator()
    ev["result"] = {"type": "bogus"}
    msg = expect_value_error({"tasks": [task("t-rtype", evaluator=ev)]}, "t-rtype")
    print("ok bad result.type raises: %s" % msg)

    # 6. estimate_minutes
    est = tasklib.estimate_minutes([{"timeout_s": 120}, {"timeout_s": 60}])
    assert abs(est - 180 / 60 * 0.4) < 1e-9
    print("ok estimate_minutes = %.2f" % est)

    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
