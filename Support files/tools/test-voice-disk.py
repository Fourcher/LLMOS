#!/usr/bin/env python3
"""Host-side test of the voice-model download's free-disk refusal (llmos/voice.py download_voice): low free disk
gives the exact message "not enough free disk: need X GB, have Y GB" and no download starts; enough free disk
starts the download. The disk is read only through a stub and the download call is a stub; no network.
Run: python3 tools/test-voice-disk.py"""
import os
import shutil
import sys
import tempfile
import types
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_SHARE = os.path.join(ROOT, "src/rootfs/usr/share/llmos")
tmp = tempfile.mkdtemp(prefix="llmos-voice-disk-")
share, lib = os.path.join(tmp, "share"), os.path.join(tmp, "lib")
os.makedirs(os.path.join(share, "voice"))
os.makedirs(lib)
shutil.copy(os.path.join(SRC_SHARE, "voice-catalog.json"), share)
open(os.path.join(share, "voice", "ggml-base.bin"), "wb").write(b"base")
os.environ.update({"LLMOS_SHARE": share, "LLMOS_LIB": lib, "LLMOS_HOME": tmp, "LLMOS_ETC": os.path.join(tmp, "etc")})
os.environ.pop("WAYLAND_DISPLAY", None)
sys.path.insert(0, os.path.join(ROOT, "src/rootfs/usr/lib/llmos"))
from llmos import voice  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Started(Exception):
    """Raised by the download stub: the download call was reached."""


def stub_disk(free_gb):
    # f_frsize 1 byte, f_bavail in bytes: free GB is then exactly f_bavail / 1024**3
    return types.SimpleNamespace(f_frsize=1, f_bavail=int(free_gb * 1024 ** 3))


def try_download(vid, free_gb):
    m = voice.voice_by_id(vid)
    started = []

    def fake_popen(*a, **k):
        started.append(a)
        raise Started()

    with mock.patch.object(voice.os, "statvfs", return_value=stub_disk(free_gb)), \
            mock.patch.object(voice.subprocess, "Popen", side_effect=fake_popen):
        try:
            voice.download_voice(vid)
            return m, None, started
        except Started:
            return m, None, started
        except ValueError as e:
            return m, str(e), started


m = voice.voice_by_id("small")
need = m["size"] / 1024 ** 3 + 0.3
low_free = need - 0.5
low_stub = stub_disk(low_free)
have = low_stub.f_bavail * low_stub.f_frsize / 1024 ** 3
expected = f"not enough free disk: need {need:.1f} GB, have {have:.1f} GB"

print("the free-disk refusal")
_, msg, started = try_download("small", low_free)
check(msg == expected, f"low disk message is exact: {msg!r}")
check(started == [], "low disk: no download call was made")

_, msg, started = try_download("small", need + 5)
check(msg is None and len(started) == 1, "enough disk: no refusal, the download call is reached")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
