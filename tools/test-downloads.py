#!/usr/bin/env python3
"""Host-side test of model downloads (llmos/models.py): a file is used only when its SHA-256 matches the pinned
value -- a wrong download is deleted and refused, a file changed on disk later is fetched again, and a good one
is not re-downloaded. curl is stubbed: no network. Run: python3 tools/test-downloads.py (no VM)"""
import hashlib
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = tempfile.mkdtemp(prefix="llmos-etc-")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, models  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


GOOD = b"the real model weights" * 100
config.MODELS = tempfile.mkdtemp(prefix="llmos-models-")
ENTRY = {"id": "tiny-test", "name": "Tiny Test", "file": "tiny-test.gguf", "size": len(GOOD), "repo": "example/tiny",
         "sha256": hashlib.sha256(GOOD).hexdigest()}
models.by_id = lambda mid: ENTRY if mid == "tiny-test" else None
models.host_mode = lambda: False
models.free_disk_gb = lambda: 100.0
served, calls = [GOOD], []


class FakeCurl:
    """Stands in for curl: writes whatever 'served' holds to the -o path."""
    def __init__(self, cmd, **kw):
        calls.append(cmd)
        with open(cmd[cmd.index("-o") + 1], "wb") as f:
            f.write(served[0])
        self.returncode = 0
        self.stderr = None

    def poll(self):
        return 0


models.subprocess.Popen = FakeCurl
dest = models.path_of(ENTRY)

served[0] = b"something else entirely"
try:
    models.download("tiny-test")
    got = "accepted"
except RuntimeError as e:
    got = str(e)
check("checksum mismatch" in got, f"a download with the wrong SHA-256 is refused: {got}")
check(not os.path.exists(dest) and not os.path.exists(dest + ".part"), "nothing is left behind: no model file, no partial file")

served[0] = GOOD
models.download("tiny-test")
check(open(dest, "rb").read() == GOOD, "the right bytes are kept")
n = len(calls)
models.download("tiny-test")
check(len(calls) == n, "a good file already there is not downloaded again")

with open(dest, "ab") as f:
    f.write(b"tampered")
models.download("tiny-test")
check(len(calls) == n + 1 and open(dest, "rb").read() == GOOD, "a file changed on disk is never used: it is fetched again")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
