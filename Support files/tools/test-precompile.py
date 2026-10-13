#!/usr/bin/env python3
"""Static host test: src/install.sh byte-compiles the installed package inside the target.

Checks, by line order in install.sh:
  - python3 is in the apk package list and the apk add runs before the payload is extracted,
  - the payload extraction runs,
  - a compileall line runs chroot $TARGET after the extraction and cannot abort the script (|| ...),
  - install.sh still passes `sh -n`.
Run: python3 tools/test-precompile.py   (no VM needed). Exit status 0 = pass."""
import os
import subprocess
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(os.path.dirname(tools_dir), "src", "install.sh")

fails = []


def check(name, ok, detail=""):
    if ok:
        print(f"ok {name}")
    else:
        print(f"FAIL {name} {detail}".rstrip())
        fails.append(name)


with open(INSTALL) as f:
    lines = f.read().split("\n")


def first(pred, start=0):
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    return -1


apk_add = first(lambda l: l.startswith("apk add --root $TARGET") and "$PKGS" in l)
python_pkg = first(lambda l: l.strip().split()[:1] == ["python3"] or " python3 " in f" {l.strip()} ")
payload = first(lambda l: "payload.tar" in l and "tar -x" in l)
compile_line = first(lambda l: "compileall" in l and "chroot $TARGET" in l)

check("apk add with $PKGS exists", apk_add >= 0, f"(line {apk_add + 1})")
check("python3 in the package list", python_pkg >= 0 and python_pkg < apk_add, f"(line {python_pkg + 1})")
check("payload extraction exists", payload >= 0, f"(line {payload + 1})")
check("payload extracted after apk add", payload > apk_add, f"(apk {apk_add + 1}, payload {payload + 1})")
check("compileall runs chroot $TARGET", compile_line >= 0, "(no such line)")
if compile_line >= 0:
    l = lines[compile_line]
    check("compileall after payload extraction", compile_line > payload,
          f"(payload {payload + 1}, compileall {compile_line + 1})")
    check("compileall after python3 is installed", compile_line > apk_add, f"(line {compile_line + 1})")
    check("compileall cannot abort the script", "|| " in l and "echo" in l, f"(line {compile_line + 1})")
    check("compileall targets /usr/lib/llmos/llmos", "/usr/lib/llmos/llmos" in l, f"(line {compile_line + 1})")

r = subprocess.run(["sh", "-n", INSTALL], capture_output=True, text=True)
check("sh -n src/install.sh", r.returncode == 0, (r.stderr or "").strip())

if fails:
    print(f"FAILED {len(fails)} check(s)")
    sys.exit(1)
print("all good")
sys.exit(0)
