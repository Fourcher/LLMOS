#!/usr/bin/env python3
"""Convert owner phrases in docs/research/use-cases.md and parity-tasks.md into task files.

Reads quoted phrases (regex "([^"]{6,120})") from table rows and list items, drops
duplicates (case-insensitive) and phrases that are destructive or power/account actions,
and writes task files of at most 40 tasks each:
  tools/tasks/usecases-1.json, usecases-2.json, ...   (from use-cases.md)
  tools/tasks/parity-1.json, parity-2.json, ...       (from parity-tasks.md)
Stdlib only.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import tasklib  # noqa: E402

PHRASE_RE = re.compile(r'"([^"]{6,120})"')
EXCLUDE_RE = re.compile(
    r"send|email|mail|buy|pay|post|delete|remove|format|wipe|uninstall|erase|"
    r"password|passphrase|shut|shutdown|reboot|restart|sleep|log out|power off|reset|factory",
    re.IGNORECASE,
)
# Destructive or power/process actions that must never reach the agent as tasks.
DROP_PATTERNS = [
    r"\bturn (?:it |the computer |the pc |the machine )?off\b",
    r"\bpower (?:off|down)\b",
    r"\brm\s+-",
    r"\bsudo\b",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r"\bkill(?:all)?\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
]
DROP_RE = re.compile("|".join("(?:%s)" % p for p in DROP_PATTERNS), re.IGNORECASE)
PER_FILE = 40
EXCLUDE_OUTPUT = ["No such tool", "error:", "Traceback", "I couldn't finish that"]

CHECKS_PATH = os.path.join(HERE, "usecase-checks.json")


def load_checks():
    """Per-instruction setup/evaluator/weak overrides. Missing file means no overrides."""
    if not os.path.exists(CHECKS_PATH):
        return {}
    with open(CHECKS_PATH, encoding="utf-8") as f:
        checks = json.load(f)
    if not isinstance(checks, dict):
        raise ValueError("%s must be a JSON object keyed by instruction" % CHECKS_PATH)
    return checks


def apply_check(task, checks):
    entry = checks.get(task["instruction"])
    if entry is None:
        return task
    task["setup"] = list(entry.get("setup", []))
    task["evaluator"] = json.loads(json.dumps(entry["evaluator"]))
    task["weak"] = bool(entry.get("weak", False))
    return task


SOURCES = [
    ("usecases", os.path.join(ROOT, "docs", "research", "use-cases.md")),
    ("parity", os.path.join(ROOT, "docs", "research", "parity-tasks.md")),
]


def is_row_or_item(line):
    stripped = line.lstrip()
    if stripped.startswith("|"):
        return True
    return bool(re.match(r"^([-*+]|\d+[.)])\s", stripped))


def collect(path, seen):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    phrases = []
    for line in lines:
        if not is_row_or_item(line):
            continue
        for phrase in PHRASE_RE.findall(line):
            key = phrase.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            if EXCLUDE_RE.search(phrase) or DROP_RE.search(phrase):
                continue
            phrases.append(phrase.strip())
    return phrases


def make_task(prefix, n, phrase):
    return {
        "id": "%s-%d" % (prefix, n),
        "instruction": phrase,
        "evaluator": {
            "func": "include_exclude",
            "result": {"type": "reply"},
            "expected": {"exclude": list(EXCLUDE_OUTPUT)},
        },
        "weak": True,
        "reachable_by_agent": True,
        "timeout_s": 120,
    }


def main():
    written = []
    # Remove stale generated files so no orphan usecases-N/parity-N remains.
    for stale in os.listdir(HERE):
        if re.match(r"^(usecases|parity)-\d+\.json$", stale):
            os.remove(os.path.join(HERE, stale))
    seen = set()  # de-duplicate across both sources; first occurrence (use-cases) wins
    checks = load_checks()
    for name, path in SOURCES:
        prefix = "uc" if name == "usecases" else "par"
        phrases = collect(path, seen)
        tasks = [apply_check(make_task(prefix, i, p), checks) for i, p in enumerate(phrases, start=1)]
        chunks = [tasks[i:i + PER_FILE] for i in range(0, len(tasks), PER_FILE)]
        for index, chunk in enumerate(chunks, start=1):
            out_name = "%s-%d.json" % (name, index)
            out_path = os.path.join(HERE, out_name)
            data = {"suite": "%s-%d" % (name, index), "tasks": chunk}
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            written.append(out_path)
        print("%s: %d unique phrases from %s, %d file(s)" % (name, len(tasks), os.path.basename(path), len(chunks)))

    ok = True
    for out_path in written:
        data = tasklib.load(out_path)
        count = len(data["tasks"])
        minutes = tasklib.estimate_minutes(data["tasks"])
        print("%s: tasks=%d estimate_minutes=%.1f" % (os.path.basename(out_path), count, minutes))
        assert count <= PER_FILE, "%s has %d tasks" % (out_path, count)
        assert minutes < 90, "%s estimates %.1f minutes" % (out_path, minutes)
    print("OK: %d files validated" % len(written))


if __name__ == "__main__":
    main()
