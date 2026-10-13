#!/usr/bin/env python3
"""Test tools/hostloop.sh with fake tests in a temp directory."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "hostloop.sh")

OK = "import sys; sys.exit(0)\n"
BAD = "import sys; sys.exit(1)\n"
FLAKY = (
    "import os, sys\n"
    "m = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flaky.marker')\n"
    "if os.path.exists(m):\n"
    "    sys.exit(0)\n"
    "open(m, 'w').close()\n"
    "sys.exit(1)\n"
)


OUTAGE_ONCE = (
    "import os, sys\n"
    "m = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outage.marker')\n"
    "if os.path.exists(m):\n"
    "    sys.exit(0)\n"
    "open(m, 'w').close()\n"
    "sys.stderr.write('Operation not permitted\\n')\n"
    "sys.exit(1)\n"
)
OUTAGE_ALWAYS = (
    "import sys\n"
    "sys.stderr.write('Operation not permitted\\n')\n"
    "sys.exit(1)\n"
)
DEFAULT_FILES = (("test-ok.py", OK), ("test-bad.py", BAD), ("test-flaky.py", FLAKY))


def make_tree(root, files=DEFAULT_FILES):
    tools = os.path.join(root, "tools")
    os.makedirs(tools)
    for name, body in files:
        with open(os.path.join(tools, name), "w") as fh:
            fh.write(body)


def run(args, files=DEFAULT_FILES):
    root = tempfile.mkdtemp(prefix="hostloop-")
    make_tree(root, files)
    env = dict(os.environ, HOSTLOOP_SLEEP="0")
    proc = subprocess.run(
        ["bash", SCRIPT] + args,
        cwd=root, env=env, capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout + proc.stderr


def check(cond, msg):
    if not cond:
        print("FAILED: " + msg)
        sys.exit(1)


def main():
    rc, out = run([])
    check("FAIL tools/test-bad.py" in out, "bad test not reported as FAIL\n" + out)
    check("FAIL tools/test-flaky.py" not in out, "flaky test reported as FAIL\n" + out)
    check("FAIL tools/test-ok.py" not in out, "ok test reported as FAIL\n" + out)
    check("HOSTLOOP: 3 run, 1 failed, 0 outage" in out, "summary line wrong\n" + out)
    check(rc == 1, "expected exit 1, got %d" % rc)
    print("ok failing run: FAIL bad only, flaky passes on re-run, exit 1")

    rc, out = run(["--skip", "test-bad.py"])
    check(rc == 0, "--skip run expected exit 0, got %d\n%s" % (rc, out))
    check("FAIL" not in out, "--skip run still reports FAIL\n" + out)
    check("HOSTLOOP: 2 run, 0 failed, 0 outage" in out, "--skip summary wrong\n" + out)
    print("ok --skip test-bad.py: exit 0")

    rc, out = run([], files=(("test-ok.py", OK), ("test-outage-once.py", OUTAGE_ONCE)))
    check("FAIL" not in out, "outage-once reported as FAIL\n" + out)
    check("OUTAGE" not in out, "outage-once reported as OUTAGE\n" + out)
    check("HOSTLOOP: 2 run, 0 failed, 0 outage" in out, "outage-once summary wrong\n" + out)
    check(rc == 0, "outage-once expected exit 0, got %d\n%s" % (rc, out))
    print("ok outage-once: passes on re-run, not FAIL, not OUTAGE")

    rc, out = run([], files=(("test-ok.py", OK), ("test-outage-always.py", OUTAGE_ALWAYS)))
    check("OUTAGE tools/test-outage-always.py" in out, "always-outage not reported as OUTAGE\n" + out)
    check("FAIL" not in out, "always-outage reported as FAIL\n" + out)
    check("HOSTLOOP: 2 run, 0 failed, 1 outage" in out, "always-outage summary wrong\n" + out)
    check(rc == 2, "always-outage expected exit 2, got %d\n%s" % (rc, out))
    print("ok outage-always: OUTAGE, exit 2")

    print("all good")


if __name__ == "__main__":
    main()
