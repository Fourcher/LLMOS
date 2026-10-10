#!/usr/bin/env python3
"""Convert the basic-sweep table (docs/research/basic-sweep.md) into tools/tasks/basic.json.

Stdlib only. Format: tools/tasks/schema.md. Validated with tasklib.load.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import tasklib  # noqa: E402

SWEEP = os.path.join(TOOLS, "..", "docs", "research", "basic-sweep.md")
OUT = os.path.join(HERE, "basic.json")

# | S01 | "hello" | a short greeting, nothing done | P0 |
ROW = re.compile(r'^\|\s*(S\d+)\s*\|\s*"([^"]*)"\s*\|\s*(.*?)\s*\|\s*(P\d)\s*\|\s*$')
THEME_WORDS = ["theme", "purple", "colour", "color", "dark", "light"]
MUSIC_WORDS = ["music", "playing", "mpv"]
FOLDER_NAME = re.compile(r"\bfolder\s+(?:called\s+)?([A-Za-z0-9_.-]+)", re.IGNORECASE)
SETTINGS_CMD = "cat /etc/llmos/settings.json; echo"
REPLY_EXCLUDE = ["No such tool", "error:", "Traceback"]


def parse_rows(path):
    """Rows of the first table whose rows start with '| S'."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("| S"):
                m = ROW.match(line)
                if not m:
                    raise ValueError("unparsed S row: %r" % line)
                rows.append(m.groups())
            elif rows:
                break
    if not rows:
        raise ValueError("no S rows found in %s" % path)
    return rows


def evaluator_for(instruction, expected):
    """Return (evaluator, weak) for one row."""
    text = expected.lower()
    phrase = instruction.lower()

    if any(w in text for w in THEME_WORDS):
        word = next((w for w in THEME_WORDS if w in phrase), None)
        if word is None:
            word = next(w for w in THEME_WORDS if w in text)
        return {
            "func": "include_exclude",
            "result": {"type": "vm_command_line", "command": SETTINGS_CMD},
            "expected": {"include": [word]},
        }, False

    if "folder" in text:
        m = FOLDER_NAME.search(instruction)
        if m:
            base = "/root/Desktop/" if "desktop" in phrase else "/root/"
            path = base + m.group(1)
            if re.match(r"(delete|remove)\b", phrase):
                expected_block = {"exclude": [path]}
            else:
                expected_block = {"include": [path]}
            return {
                "func": "file_exists",
                "result": {"type": "vm_command_line", "command": "ls -d %s 2>/dev/null" % path},
                "expected": expected_block,
            }, False

    if any(w in text for w in MUSIC_WORDS):
        return {
            "func": "proc_running",
            "result": {"type": "vm_command_line", "command": "pgrep -a mpv"},
            "expected": {"include": ["mpv"]},
        }, False

    return {
        "func": "include_exclude",
        "result": {"type": "reply"},
        "expected": {"exclude": list(REPLY_EXCLUDE)},
    }, True


def main():
    rows = parse_rows(SWEEP)
    tasks = []
    for sid, phrase, expected, _priority in rows:
        evaluator, weak = evaluator_for(phrase, expected)
        tasks.append({
            "id": sid,
            "instruction": phrase,
            "evaluator": evaluator,
            "reachable_by_agent": True,
            "timeout_s": 120,
            "weak": weak,
        })
    data = {"suite": "basic", "tasks": tasks}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tasklib.load(OUT)
    weak_count = sum(1 for t in tasks if t["weak"])
    print("%d tasks" % len(tasks))
    print("%d weak" % weak_count)


if __name__ == "__main__":
    main()
