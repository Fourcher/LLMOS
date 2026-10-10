#!/usr/bin/env python3
"""package.sh names the zip for the BUILT version (dist/RELEASE.json, else dist/VERSION).

Runs package.sh with PACKAGE_PRINT_VERSION=1 (prints the chosen version and exits before any work)
and PACKAGE_ROOT pointing at a temp "Support files" tree, so the real tree is never touched.
Exit 0 on success, 1 on failure.
"""
import os
import subprocess
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(TOOLS, "package.sh")


def fail(msg):
    print(f"FAIL {msg}")
    sys.exit(1)


def run(root):
    env = dict(os.environ, PACKAGE_PRINT_VERSION="1", PACKAGE_ROOT=root)
    p = subprocess.run(["bash", SCRIPT], cwd=os.path.dirname(root), env=env,
                       capture_output=True, text=True)
    return p


def main():
    # 1. syntax
    p = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
    if p.returncode != 0:
        fail(f"bash -n: {p.stderr.strip()}")
    print("ok bash -n package.sh")

    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "Support files")
        os.makedirs(os.path.join(root, "dist"))
        with open(os.path.join(root, "dist", "RELEASE.json"), "w") as f:
            f.write('{"version": "1.2.3"}\n')
        with open(os.path.join(root, "dist", "VERSION"), "w") as f:
            f.write("1.2.3\n")
        with open(os.path.join(root, "VERSION"), "w") as f:
            f.write("9.9.9\n")

        p = run(root)
        if p.returncode != 0:
            fail(f"package.sh exit {p.returncode}: {p.stdout} {p.stderr}")
        lines = p.stdout.strip().splitlines()
        if not lines or lines[-1] != "1.2.3":
            fail(f"expected last line 1.2.3, got {lines!r}")
        note = "note: packaging built version 1.2.3 (source is 9.9.9)"
        if note not in lines:
            fail(f"missing warning {note!r} in {lines!r}")
        print("ok RELEASE.json wins; warning printed when source differs")

        # 2. RELEASE.json missing -> dist/VERSION
        os.remove(os.path.join(root, "dist", "RELEASE.json"))
        with open(os.path.join(root, "dist", "VERSION"), "w") as f:
            f.write("1.2.3\n")
        p = run(root)
        if p.returncode != 0 or p.stdout.strip().splitlines()[-1:] != ["1.2.3"]:
            fail(f"dist/VERSION fallback: exit {p.returncode}, out {p.stdout!r}")
        print("ok dist/VERSION fallback")

        # 3. both missing -> exit 1 with clear message
        os.remove(os.path.join(root, "dist", "VERSION"))
        p = run(root)
        if p.returncode != 1 or "both missing" not in p.stdout:
            fail(f"both missing: exit {p.returncode}, out {p.stdout!r}")
        print("ok both missing exits 1 with message")

        # 4. version with spaces stays one value
        with open(os.path.join(root, "dist", "RELEASE.json"), "w") as f:
            f.write('{"version": "1.2 beta"}\n')
        p = run(root)
        if p.returncode != 0 or p.stdout.strip().splitlines()[-1:] != ["1.2 beta"]:
            fail(f"spaces: exit {p.returncode}, out {p.stdout!r}")
        print("ok version with spaces")

    print("all good")


if __name__ == "__main__":
    main()
