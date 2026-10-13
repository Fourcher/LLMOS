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


def make_tree(root):
    tools = os.path.join(root, "tools")
    os.makedirs(tools)
    for name, body in (("test-ok.py", OK), ("test-bad.py", BAD), ("test-flaky.py", FLAKY)):
        with open(os.path.join(tools, name), "w") as fh:
            fh.write(body)


def run(args):
    root = tempfile.mkdtemp(prefix="hostloop-")
    make_tree(root)
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

    print("all good")


if __name__ == "__main__":
    main()
