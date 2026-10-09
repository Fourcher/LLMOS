#!/usr/bin/env python3
"""Host-side unit test: config.ensure_folders() makes the usual folders (Documents, Downloads, Pictures,
Music, Videos) in the home folder, is safe to call twice, and does not raise when a file already
holds one of the names.
Run: python3 tools/test-home-folders.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
import tempfile

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))

home_dir = tempfile.mkdtemp()
os.environ["LLMOS_HOME"] = home_dir

from llmos import config

FOLDERS = ("Documents", "Downloads", "Pictures", "Music", "Videos")


def _check(label, ok, detail=""):
    if not ok:
        print(f"FAIL {label} {detail}".rstrip())
        sys.exit(1)
    print(f"ok   {label}")


config.ensure_folders()
config.ensure_folders()
for name in FOLDERS:
    path = os.path.join(home_dir, name)
    _check(f"folder {name} exists", os.path.isdir(path), f"(missing {path})")

# A regular file named "Music" already in the home folder must not make ensure_folders raise.
clash_dir = tempfile.mkdtemp()
os.environ["LLMOS_HOME"] = clash_dir
with open(os.path.join(clash_dir, "Music"), "w") as f:
    f.write("not a folder")
try:
    config.ensure_folders()
    raised = None
except Exception as e:
    raised = e
_check("existing file named Music does not raise", raised is None, f"(raised {raised!r})")
_check("existing file named Music is left alone",
       os.path.isfile(os.path.join(clash_dir, "Music")))

print("all good")
