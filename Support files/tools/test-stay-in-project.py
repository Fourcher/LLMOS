#!/usr/bin/env python3
"""The stay-in-project guard (.claude/hooks/stay-in-project.py): blocks the owner's personal Mac folders, allows the
project, Claude's own ~/.claude, the one release-zip copy, and code that merely contains a "~" (source edits).
Run: python3 tools/test-stay-in-project.py  (exit status 0 = pass)"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".claude", "hooks",
                    "stay-in-project.py")
H = "/Users/" + "jordan"
T = "~"
CASES = [
    (f"ls {T}/Down" + "loads", 2),
    (f"cd {T}", 2),
    (f"du -sh {H}/Library/Mobile Documents", 2),
    (f"cat {H}/Mu" + "sic/x", 2),
    ("ls $HOME/Desk" + "top", 2),
    (f"cat {T}/.claude/projects/x", 0),
    (f"python3 - <<'EOF'\ns = r\"(?:{T}|/)[^ ]*\"\nprint(\"{T}/Documents\")\nEOF", 0),
    (f"grep -n \"(?:{T}|/)\" intent.py", 0),
    ("mkdir -p \"$S/Down" + "loads\"", 0),
    (f"cp \"/Volumes/Files/Claude Work Area/LLMOS/packages/LLM OS 1.8.7.zip\" \"{H}/Down" + "loads/\"", 0),
    ("ls \"/Volumes/Files/Claude Work Area/LLMOS/Support files\"", 0),
    ("ls /Volumes/Other", 2),
]
fails = 0
for cmd, want in CASES:
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                       capture_output=True, text=True)
    ok = p.returncode == want
    fails += not ok
    print(("ok   " if ok else "FAIL ") + f"{want} <- {cmd.splitlines()[0][:70]}" + ("" if ok else f"  (got {p.returncode})"))
print("all good" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
