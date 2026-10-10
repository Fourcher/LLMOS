#!/usr/bin/env python3
"""Grade one LLM OS task result against its evaluator rules.

evaluate(task, get_result) -> {"verdict": "PASS"|"FAIL", "reason": str, "observed": str}
get_result(result_spec) is supplied by the runner; it returns the observed text
(command output, reply text, or rect JSON as text). It may raise or return None.
"""

REFUSAL_PHRASES = ("can't", "cannot", "isn't possible", "not able")
STATE_FUNCS = ("include_exclude", "equals", "file_exists", "setting_is", "proc_running")


def _verdict(passed, reason, observed):
    return {"verdict": "PASS" if passed else "FAIL", "reason": reason, "observed": observed}


def _include_exclude(observed, expected):
    """Every include present (case-insensitive), no exclude present. Empty output fails."""
    if not observed.strip():
        return False, "empty output"
    low = observed.lower()
    for inc in expected.get("include", []):
        if inc.lower() not in low:
            return False, "missing include: %r" % inc
    for exc in expected.get("exclude", []):
        if exc.lower() in low:
            return False, "found exclude: %r" % exc
    return True, "include/exclude rules satisfied"


def _check_rules(func, observed, expected):
    """Apply the rules for a state-grading function. Returns (passed, reason)."""
    if func == "proc_running" and not observed.strip():
        return False, "not running"
    has_rules = "include" in expected or "exclude" in expected
    if has_rules:
        return _include_exclude(observed, expected)
    if "equals" in expected:
        if observed.strip() == expected["equals"]:
            return True, "equals matched"
        return False, "equals mismatch: %r != %r" % (observed.strip(), expected["equals"])
    return False, "no expected rules"


def evaluate(task, get_result):
    """Grade a task. get_result(result_spec) -> observed text, or raises, or returns None."""
    evaluator = task["evaluator"]
    func = evaluator["func"]
    expected = evaluator.get("expected", {})
    spec = evaluator["result"]

    try:
        observed = get_result(spec)
    except TimeoutError as e:
        return _verdict(False, "timeout: %s" % e, "")
    except Exception as e:
        return _verdict(False, "getter error: %s" % e, "")

    if observed is None:
        return _verdict(False, "no output", "")
    observed = str(observed)

    if not task.get("feasible", True):
        low = observed.lower()
        if any(p in low for p in REFUSAL_PHRASES):
            return _verdict(True, "refused as expected", observed)
        return _verdict(False, "infeasible task not refused", observed)

    if func == "include_exclude":
        passed, reason = _include_exclude(observed, expected)
    elif func == "equals":
        if observed.strip() == expected.get("equals"):
            passed, reason = True, "equals matched"
        else:
            passed, reason = False, "equals mismatch: %r != %r" % (observed.strip(), expected.get("equals"))
    elif func in STATE_FUNCS:
        passed, reason = _check_rules(func, observed, expected)
    else:
        passed, reason = False, "unknown func: %r" % func
    return _verdict(passed, reason, observed)


def evaluate_do_nothing(task):
    """Verdict when the agent did nothing: observed is "" for state tasks, "Done." for reply tasks."""
    evaluator = task["evaluator"]
    spec = evaluator["result"]
    observed = "Done." if spec.get("type") == "reply" else ""
    return evaluate(task, lambda _spec: observed)
