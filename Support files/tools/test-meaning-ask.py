#!/usr/bin/env python3
"""Host-side test for meaning.fetch under the internet setting. yes: the search model downloads. ask: it does not
download unless the owner asked (allowed=True); it raises the plain one-time-download message with the 310 MB size.
no: unchanged message, no download. The downloader (subprocess.Popen in meaning) is replaced by a recorder, so no
network is used and nothing is written outside a temporary folder.
Run: python3 tools/test-meaning-ask.py  (no VM needed). Exit status 0 = pass."""
import os
import shutil
import sys
import tempfile
import types

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import meaning, config  # noqa: E402

failures = []
downloads = []
ASK_MSG = "Searching by meaning needs a one-time download of 310 MB. Say “download the search model” to get it."
NO_MSG = "the internet is switched off, so the search model can't be downloaded"


def check(label, cond):
    if cond:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}")
        failures.append(label)


class Stop(Exception):
    """Raised by the recording downloader so no real transfer runs."""


def fake_popen(cmd, **kw):
    downloads.append(cmd)
    raise Stop()


class FakeSettings:
    def __init__(self, internet):
        self.d = {"internet": internet}

    def get(self, key, default=None):
        return self.d.get(key, default)


def run_fetch(internet, **kw):
    """Returns (outcome, message). outcome: 'download' (downloader reached), 'raised' (fetch refused), 'other'."""
    del downloads[:]
    tmp = tempfile.mkdtemp(prefix="meaning-ask-")
    real_settings, real_dir = config.settings, meaning._dir
    real_popen, real_disk = meaning.subprocess, meaning.models.free_disk_gb
    config.settings = FakeSettings(internet)
    meaning._dir = lambda: tmp
    meaning.subprocess = types.SimpleNamespace(Popen=fake_popen, PIPE=None, DEVNULL=None)
    meaning.models.free_disk_gb = lambda path=None: 100.0
    try:
        meaning.fetch(**kw)
        return "other", ""
    except Stop:
        return "download", ""
    except RuntimeError as e:
        return "raised", str(e)
    finally:
        config.settings, meaning._dir = real_settings, real_dir
        meaning.subprocess, meaning.models.free_disk_gb = real_popen, real_disk
        shutil.rmtree(tmp, ignore_errors=True)


out, _ = run_fetch("yes")
check("yes -> download", out == "download" and len(downloads) == 1)

out, msg = run_fetch("ask")
check("ask -> no download", out == "raised" and downloads == [])
check("ask -> plain message with 310 MB", msg == ASK_MSG and "310 MB" in msg)

out, _ = run_fetch("ask", allowed=True)
check("ask + allowed=True -> download", out == "download" and len(downloads) == 1)

out, msg = run_fetch("no")
check("no -> unchanged message", out == "raised" and msg == NO_MSG and downloads == [])

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
