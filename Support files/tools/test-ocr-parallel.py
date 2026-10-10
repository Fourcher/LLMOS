#!/usr/bin/env python3
"""Host test for the parallel screen reading in control.read_screen() (no VM, no grim, no tesseract needed).

Every external call (magick, tesseract, grim) and the OCR step is faked with a 0.2 s sleep. read_screen() must
finish clearly faster than doing those calls one after another, and must leave no temporary crop files behind.

Run: python3 tools/test-ocr-parallel.py
"""
import glob
import os
import subprocess
import sys
import time
from unittest.mock import patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import control  # noqa: E402

FAILS = []
DELAY = 0.2
N_BOXES = 16
N_STRIPS = 11   # range(0, 1600, 150) at a 1600 px screen


def check(name, cond, detail=""):
    print(("ok " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILS.append(name)


def fake_run(argv, timeout=20, text=True):
    time.sleep(DELAY)
    if argv[0] == "magick" and "-connected-components" in argv:
        out = "Objects (id: size)\n" + "".join(
            f"  {i + 1}: 200x60+10+{40 + i * 90} gray(0)\n" for i in range(N_BOXES))
        return subprocess.CompletedProcess(argv, 0, out, "")
    if argv[0] == "magick" and "-crop" in argv:
        target = argv[-1][len("PNG24:"):]          # the crop is written to disk, as magick would do
        with open(target, "wb") as f:
            f.write(b"png")
    return subprocess.CompletedProcess(argv, 0, "", "")


def fake_ocr(psm, path=control.SHOT, dy=0):
    time.sleep(DELAY)
    return []


def main():
    for stale in glob.glob(control.BOX + ".*") + glob.glob(control.STRIP + ".*"):
        os.remove(stale)

    with patch.object(control, "_run", side_effect=fake_run), \
            patch.object(control, "_size", return_value=(1600, 1600)), \
            patch.object(control.shutil, "which", return_value="/usr/bin/x"), \
            patch.object(control, "_ocr", side_effect=fake_ocr):
        t0 = time.time()
        control.read_screen()
        elapsed = time.time() - t0

    serial_floor = DELAY * (N_BOXES + N_STRIPS + 3)
    limit = serial_floor / 2
    check(f"read_screen finishes in {elapsed:.2f}s (serial would take about {serial_floor:.1f}s, limit {limit:.1f}s)",
          elapsed < limit, f"{elapsed:.2f}s >= {limit:.2f}s")

    left = glob.glob(control.BOX + ".*") + glob.glob(control.STRIP + ".*")
    check("no temporary crop files left behind", not left, str(left))

    print("all good" if not FAILS else "FAILED: " + ", ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
