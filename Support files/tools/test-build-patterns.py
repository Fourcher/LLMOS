#!/usr/bin/env python3
"""Host test of the install-refusal wait pattern in build-image.sh and build-image-x86.sh.
The pattern (python re, as vmctl.py wait uses it) must match every "not enough (free) disk"
refusal line found in src, and the old wording, and must not match "enough disk space" or
"disk is fine". Run: python3 tools/test-build-patterns.py"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SRC = os.path.join(ROOT, "src")

fails = []


def check(cond, label):
    if cond:
        print("ok " + label)
    else:
        print("FAIL " + label)
        fails.append(label)


WAIT_RE = re.compile(r"""\$V wait "\$LOG" '([^']*)'""")
EXPECTED = {
    "build-image.sh": "LLMOS_INSTALL_OK|HASH MISMATCH|not enough (free )?disk|ERROR|fatal:|INSTALL FAILED",
    "build-image-x86.sh": "LLMOS_INSTALL_OK|HASH MISMATCH|not enough (free )?disk|ERROR|fatal:|INSTALL FAILED|GRUB config has no",
}

# Refusal lines in src (the install-time refusal and its siblings).
refusals = []
for dirpath, _dirs, files in os.walk(SRC):
    for f in files:
        if not f.endswith((".py", ".sh")):
            continue
        p = os.path.join(dirpath, f)
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "not enough free disk" in line or "not enough disk" in line:
                    refusals.append((os.path.relpath(p, ROOT), line.strip()))
check(len(refusals) >= 1, "found %d refusal line(s) in src" % len(refusals))
for where, line in refusals:
    print("   src: %s: %s" % (where, line[:120]))

for name, expected in EXPECTED.items():
    path = os.path.join(HERE, name)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    found = [m for m in WAIT_RE.findall(text) if "disk" in m]
    check(len(found) == 1, "%s has one disk wait pattern" % name)
    if len(found) != 1:
        continue
    pat = found[0]
    check(pat == expected, "%s pattern is the expected one with only the disk alternative widened" % name)
    rx = re.compile(pat, re.M)
    for where, line in refusals:
        check(rx.search(line) is not None, "%s matches src refusal (%s)" % (name, where))
    check(rx.search("not enough disk: need 2.0 GB, have 1.0 GB") is not None,
          "%s matches old wording 'not enough disk'" % name)
    check(rx.search("not enough free disk: need 2.0 GB, have 1.0 GB") is not None,
          "%s matches new wording 'not enough free disk'" % name)
    check(rx.search("enough disk space") is None, "%s does not match 'enough disk space'" % name)
    check(rx.search("disk is fine") is None, "%s does not match 'disk is fine'" % name)

if fails:
    print("FAILED: %d check(s)" % len(fails))
    sys.exit(1)
print("all good")
