#!/usr/bin/env python3
"""Tests for tools/realrun-nightly.sh: syntax, wiring, rotation (dry mode), time guard.
Never boots a VM. Stdlib only."""
import datetime
import glob
import json
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # the "Support files" directory
SCRIPT = os.path.join(HERE, "realrun-nightly.sh")
FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILS.append(name)


def expected_suite(date_str):
    files = sorted(p for p in glob.glob(os.path.join(ROOT, "tools", "tasks", "*.json"))
                   if "schema" not in os.path.basename(p).lower())
    d = datetime.date.fromisoformat(date_str)
    idx = (d - datetime.date(2026, 1, 1)).days % len(files)
    return os.path.relpath(files[idx], ROOT)


def run_script(args, env_extra=None):
    env = dict(os.environ)
    env.pop("NIGHTLY_DRY", None)
    env.pop("NIGHTLY_DATE", None)
    env.update(env_extra or {})
    return subprocess.run(["bash", SCRIPT] + args, capture_output=True, text=True, env=env, timeout=120)


# 1. syntax and wiring
src = open(SCRIPT, encoding="utf-8").read()
r = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
check("bash -n", r.returncode == 0, r.stderr)
for needle in ["trap", "tmon.sock", "triage.py", "--queue", "estimate_minutes"]:
    check("script has %s" % needle, needle in src)

calc = open(os.path.join(ROOT, "tools", "calc-smoke.sh"), encoding="utf-8").read().splitlines()
onboard_line = calc[20]  # line 21 of calc-smoke.sh
onboard_cmd = onboard_line.split("R '", 1)[1].rsplit("' W2 90", 1)[0]
check("onboarding command equals calc-smoke.sh line 21", onboard_cmd in src, onboard_cmd)
check("no /Volumes/ literal", "/Volumes/" not in src)

def pid_files():
    found = set()
    run_dir = os.path.join(ROOT, "run")
    if os.path.isdir(run_dir):
        for dp, _, fns in os.walk(run_dir):
            if "target.pid" in fns:
                found.add(os.path.join(dp, "target.pid"))
    return found


# 1b. no arguments: no --run, so nothing boots; prints the chosen suite and exits 0
before = pid_files()
r = run_script([])
last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
check("no args exits 0 and names --run", r.returncode == 0 and "--run" in r.stdout, "rc=%s out=%r err=%s"
      % (r.returncode, r.stdout, r.stderr))
check("no args prints a suite json", last.endswith(".json"), repr(last))
check("no args creates no target.pid", not (pid_files() - before), str(pid_files() - before))

# 1c. -h and --help: usage on stdout, exit 0, no target.pid
for flag in ["--help", "-h"]:
    before = pid_files()
    r = run_script([flag])
    check("%s exits 0 and names --run" % flag, r.returncode == 0 and "--run" in r.stdout,
          "rc=%s out=%r err=%s" % (r.returncode, r.stdout, r.stderr))
    check("%s creates no target.pid" % flag, not (pid_files() - before), str(pid_files() - before))

# 2. rotation: script dry mode vs independent computation, three dates
for date_str in ["2026-01-01", "2026-10-10", "2027-03-15"]:
    want = expected_suite(date_str)
    r = run_script([], {"NIGHTLY_DRY": "1", "NIGHTLY_DATE": date_str})
    got = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    check("rotation %s -> %s" % (date_str, want), r.returncode == 0 and got == want,
          "rc=%s got=%r want=%r err=%s" % (r.returncode, got, want, r.stderr))

# 3. a suite name argument overrides the rotation (dry mode prints it)
basic = os.path.join(ROOT, "tools", "tasks", "basic.json")
r = run_script([basic], {"NIGHTLY_DRY": "1"})
check("suite argument override", r.returncode == 0 and r.stdout.strip() == basic,
      "rc=%s out=%r err=%s" % (r.returncode, r.stdout, r.stderr))

# 4. time guard: a suite estimated over 170 min exits 2 before any boot
tmp = tempfile.mkdtemp(prefix="nightly-guard-")
try:
    with open(basic, encoding="utf-8") as fh:
        data = json.load(fh)
    for t in data["tasks"]:
        t["timeout_s"] = 100000
    long_suite = os.path.join(tmp, "long suite.json")  # a name with a space
    with open(long_suite, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    r = run_script(["--run", long_suite])
    check("time guard exits 2", r.returncode == 2, "rc=%s out=%r err=%s" % (r.returncode, r.stdout, r.stderr))
    check("time guard prints suite too long", "suite too long" in r.stdout, r.stdout)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if FAILS:
    print("FAILED: %s" % ", ".join(FAILS))
    raise SystemExit(1)
print("all good")
