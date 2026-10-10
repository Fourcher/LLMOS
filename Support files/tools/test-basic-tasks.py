#!/usr/bin/env python3
"""Host-side test of the S12/S13 dark-or-light evaluator in tools/tasks/basic.json. The command is read from the json,
split the way a shell would split it, and run locally against temp settings files. The VM's 'cd /usr/lib/llmos' is
replaced by putting the rootfs llmos package on sys.path, and the settings path is patched to a temp file.
Run: python3 tools/test-basic-tasks.py"""
import json
import os
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASIC = os.path.join(HERE, "tasks", "basic.json")
ROOTFS_LIB = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos")
VM_PREFIX = "cd /usr/lib/llmos && "
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


tasks = {t["id"]: t for t in json.load(open(BASIC, encoding="utf-8"))["tasks"]}

for sid, word, opposite in (("S12", "dark", "light"), ("S13", "light", "dark")):
    ev = tasks[sid]["evaluator"]
    cmd = ev["result"]["command"]
    check("!" not in cmd, "%s command has no '!' (tsh filter)" % sid)
    check(ev["expected"] == {"include": [word], "exclude": [opposite]}, "%s expects include %s, exclude %s" % (sid, word, opposite))
    check(cmd.startswith(VM_PREFIX), "%s command starts with the VM cd prefix" % sid)
    argv = shlex.split(cmd[len(VM_PREFIX):])
    check(argv[:2] == ["python3", "-c"] and len(argv) == 3, "%s command is python3 -c <one program>" % sid)
    prog = argv[2].replace("/etc/llmos/settings.json", "SETTINGS_PATH")
    assert "SETTINGS_PATH" in prog

    cases = [
        ({"onboarded": True, "appearance": {"scale": 120, "background": "#f6f6f8", "color": "#16171d", "accent": "#5b5bd6"}}, "light"),
        ({"onboarded": True, "appearance": {"background": "#1e1e24", "color": "#f0f0f0"}}, "dark"),
        ({"onboarded": True, "appearance": {"background": "#fff"}}, "light"),
        ({"onboarded": True, "appearance": {"background": "purple"}}, "light"),
        ({"onboarded": True, "appearance": {"background": "dark green"}}, "dark"),
        ({"onboarded": True, "appearance": {"background": "zzz"}}, "light"),
        ({"onboarded": True}, "light"),
    ]
    for settings, want in cases:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings, f)
            run_prog = prog.replace("SETTINGS_PATH", path)
            full = "import sys;sys.path.insert(0,%r);" % os.path.abspath(ROOTFS_LIB) + run_prog
            out = subprocess.run([sys.executable, "-I", "-c", full], capture_output=True, text=True, timeout=30)
            got = out.stdout.strip()
            label = settings.get("appearance", {}).get("background", "no appearance")
            check(out.returncode == 0 and got == want, "%s %s -> %r (want %r) rc=%d %s" % (sid, label, got, want, out.returncode, out.stderr.strip()[:200]))
            if sid == "S12" and want == "dark":
                check(got != "light", "S12 exclude 'light' holds for dark case")

print("all good" if not fails else "%d failure(s)" % fails)
sys.exit(1 if fails else 0)
