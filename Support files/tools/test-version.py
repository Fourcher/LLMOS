#!/usr/bin/env python3
"""Assert the OS version is in lockstep across its two sources of truth.

  Support files/VERSION                                         read by build-iso.sh, release-json.py
  Support files/src/rootfs/usr/lib/llmos/llmos/__init__.py      VERSION = "x.y.z"; install.sh stamps /etc/llmos-release from it

The __init__.py file is parsed as text, never imported. The install.sh extraction
(sed -n 's/^VERSION = "\\(.*\\)"$/\\1/p') is run on that file too, so a line that the
installer could not read is caught here.

Usage: python3 tools/test-version.py   (works from any cwd; paths are relative to this script)
Exit 0 on match, 1 on mismatch or unreadable input.
"""
import os
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)  # "Support files"
VERSION_FILE = os.path.join(ROOT, "VERSION")
INIT_FILE = os.path.join(ROOT, "src", "rootfs", "usr", "lib", "llmos", "llmos", "__init__.py")
# Exact sed expression from src/install.sh (line 141).
INSTALL_SED = 's/^VERSION = "\\(.*\\)"$/\\1/p'


def fail(msg):
    print(f"version: FAIL - {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            version_file = f.read().strip()
    except OSError as e:
        fail(f"cannot read {VERSION_FILE}: {e}")
    if not version_file:
        fail(f"{VERSION_FILE} is empty")

    try:
        with open(INIT_FILE, encoding="utf-8") as f:
            init_text = f.read()
    except OSError as e:
        fail(f"cannot read {INIT_FILE}: {e}")

    # Parse the VERSION assignment as text (the same line format install.sh expects).
    matches = re.findall(r'^VERSION = "(.*)"$', init_text, flags=re.MULTILINE)
    if len(matches) != 1:
        fail(f"expected exactly one line 'VERSION = \"...\"' in __init__.py, found {len(matches)}")
    init_version = matches[0]

    # Prove install.sh's sed extracts the same value from the real file.
    sed = subprocess.run(["sed", "-n", INSTALL_SED, INIT_FILE],
                         capture_output=True, text=True)
    if sed.returncode != 0:
        fail(f"sed failed: {sed.stderr.strip()}")
    sed_lines = sed.stdout.splitlines()
    if sed_lines != [init_version]:
        fail(f"install.sh sed extracts {sed_lines!r}, expected [{init_version!r}]; "
             "the VERSION line format does not match what install.sh reads")

    if init_version != version_file:
        fail(f"version drift: VERSION file says {version_file!r} but __init__.py says {init_version!r}. "
             "Set both to the same value before building a release.")

    print(f"version: {version_file} in lockstep (VERSION, __init__.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
