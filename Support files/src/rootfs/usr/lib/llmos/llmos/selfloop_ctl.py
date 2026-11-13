"""Rails for the self-improvement loop. The loop itself lives in tools/selfloop.py.

This module only reads and writes local files: the kill switch, the rate limit, the queue,
and the config. It does not edit the OS, does not publish an update, and does not open a
network connection. Defaults refuse to ship: require_approval is true unless the config
says otherwise, and a missing or broken config keeps that default.
"""
import json
import os
import time

from . import config

DEFAULTS = {
    "mode": "dev",                 # heavy work runs off the live install and ships by OTA
    "require_approval": True,      # a passing gate queues an update; it does not publish
    "max_per_day": 4,
    "min_interval_sec": 1800,
}


def _walk_up(filename):
    env = os.environ.get("LLMOS_SELFLOOP_ROOT")
    d = env or os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, filename)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


def state_dir():
    env = os.environ.get("LLMOS_SELFLOOP_DIR")
    if env:
        return env
    cfg = _walk_up("selfloop.json")
    if cfg:
        return os.path.join(os.path.dirname(cfg), "run", "selfloop")
    return os.path.join(config.data_dir(), "selfloop")


def config_path():
    env = os.environ.get("LLMOS_SELFLOOP_CONFIG")
    if env:
        return env
    return _walk_up("selfloop.json")


def load_config(path=None):
    """require_approval stays true when the file is missing, unreadable, or silent on the key."""
    out = dict(DEFAULTS)
    path = config_path() if path is None else path
    try:
        data = json.load(open(path, encoding="utf-8")) if path and os.path.isfile(path) else None
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    if data.get("mode") in ("dev", "device"):
        out["mode"] = data["mode"]
    if isinstance(data.get("require_approval"), bool):
        out["require_approval"] = data["require_approval"]
    for key, lo, hi in (("max_per_day", 1, 48), ("min_interval_sec", 0, 7 * 24 * 3600)):
        val = data.get(key)
        if isinstance(val, int) and not isinstance(val, bool) and lo <= val <= hi:
            out[key] = val
    return out


def stop_file():
    return os.path.join(state_dir(), "STOP")


def killed():
    flag = os.environ.get("LLMOS_SELFLOOP", "").strip().lower()
    if flag in ("0", "off", "stop", "false", "no"):
        return True
    if os.path.exists("/etc/llmos/selfloop-stop"):
        return True
    return os.path.exists(stop_file())


def set_killed(on):
    path = stop_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if on:
        with open(path, "w", encoding="utf-8") as f:
            f.write("stop\n")
        return "The improvement loop is stopped. It will not change anything until you resume it."
    try:
        os.remove(path)
    except OSError:
        pass
    if os.path.exists("/etc/llmos/selfloop-stop"):
        return ("Removed the loop's stop file. /etc/llmos/selfloop-stop is still there, so the loop stays stopped "
                "until that file is deleted.")
    return "The improvement loop may run again. It still will not publish an update unless approval is turned off."


def _runs_path():
    return os.path.join(state_dir(), "runs.json")


def _load_runs():
    try:
        data = json.load(open(_runs_path(), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [t for t in data if isinstance(t, (int, float))] if isinstance(data, list) else []


def _save_runs(runs):
    os.makedirs(state_dir(), exist_ok=True)
    tmp = _runs_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(runs[-200:], f)
    os.replace(tmp, _runs_path())


def rate_limit(now=None, cfg=None):
    """(blocked, reason). A run inside the interval or past the daily cap is refused."""
    cfg = cfg or load_config()
    now = time.time() if now is None else now
    runs = [t for t in _load_runs() if now - t < 86400]
    if len(runs) >= cfg["max_per_day"]:
        return True, f"rate limit: {cfg['max_per_day']} improvements a day. Nothing was changed."
    if runs and now - max(runs) < cfg["min_interval_sec"]:
        return True, "rate limit: the last attempt was too recent. Nothing was changed."
    return False, ""


def note_run(now=None):
    now = time.time() if now is None else now
    runs = _load_runs()
    runs.append(now)
    _save_runs(runs)


def record(result):
    os.makedirs(state_dir(), exist_ok=True)
    path = os.path.join(state_dir(), "results.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def results(n=20):
    path = os.path.join(state_dir(), "results.jsonl")
    try:
        lines = open(path, encoding="utf-8").read().splitlines()[-n:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def queue_path():
    return os.path.join(state_dir(), "queue.json")


def load_queue():
    try:
        data = json.load(open(queue_path(), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def save_queue(rows):
    os.makedirs(state_dir(), exist_ok=True)
    tmp = queue_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, queue_path())


def enqueue(item):
    rows = load_queue()
    rows.append(item)
    save_queue(rows)
    return item


def assert_gated(shell):
    """The publish command is tests redirected to a file, then &&, then ota publish. A pipe is refused."""
    if not isinstance(shell, str) or not shell.strip():
        raise RuntimeError("refusing to publish without a test gate")
    if "|" in shell:
        raise RuntimeError("refusing to publish through a pipe; the test gate must be chained with &&")
    if shell.count("&&") != 1:
        raise RuntimeError("refusing to publish: the gate must be one && chain")
    left, _, right = shell.partition("&&")
    if "run-host-tests.sh" not in left or ">" not in left:
        raise RuntimeError("refusing to publish: the host tests must run first, with output in a file")
    if "ota.py" not in right or "publish" not in right:
        raise RuntimeError("refusing to publish: ota publish is not after the gate")
    if "publish" in left:
        raise RuntimeError("refusing to publish: publish appears before the gate")
    return shell


def ship_shell(support, tests, version, note, log_path):
    """The only publish command the loop builds. Tests run, their output goes to a file, and publish
    runs only when that command exits 0."""
    import shlex
    test_args = " ".join(shlex.quote(t) for t in tests)
    shell = (f"bash {shlex.quote(os.path.join(support, 'tools', 'run-host-tests.sh'))} {test_args} "
             f"> {shlex.quote(log_path)} && "
             f"python3 {shlex.quote(os.path.join(support, 'tools', 'ota.py'))} publish "
             f"--version {shlex.quote(version)} --note {shlex.quote(note)}")
    return assert_gated(shell)


def ideas_from_text(text):
    """One backlog item per FAIL line. The item tells the editor not to weaken the test."""
    import hashlib
    import re
    items = []
    seen = set()
    for line in str(text or "").splitlines():
        if not line.startswith("FAIL "):
            continue
        name = line[5:].strip()
        if not name or name in seen:
            continue
        seen.add(name)
        items.append({
            "id": "fail-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:10],
            "title": "Fix the product so this host test passes: " + os.path.basename(name),
            "detail": name + ". Do not edit the test or the test runner to make it pass, and do not weaken a safeguard.",
            "source": "test-failure",
            "status": "open",
        })
    return items


def pick_item(backlog, log_text=""):
    """The next open item, or one built from a failure log when the backlog has nothing open."""
    rows = list(backlog or [])
    for item in rows:
        if isinstance(item, dict) and item.get("status", "open") == "open" and item.get("title"):
            return item, rows
    for item in ideas_from_text(log_text):
        rows.append(item)
        return item, rows
    return None, rows


def summary():
    cfg = load_config()
    if killed():
        state = "The kill switch is on: the loop will not run."
    else:
        state = "The kill switch is off."
    approval = "Owner approval is required before an update is published." if cfg["require_approval"] else (
        "Owner approval is off: a change that passes the light gate can be published.")
    queued = len(load_queue())
    return (f"Dev-machine mode is the setup for this: the loop edits a separate checkout, never the running "
            f"install, and ships only by a signed update after tests pass ({approval} {state} "
            f"{queued} change(s) waiting.)")
