#!/usr/bin/env python3
"""Host-side check that "stop the music" wordings route to media_control
(action=stop) without the slow model, and that system-sound and
autostart wordings do not. Run: python3 tools/test-stop-music.py"""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402

STOP = ("media_control", {"action": "stop"})


def stop(text):
    got = intent._everyday2(text)
    assert got == STOP, f"{text!r}: got {got!r}, want {STOP!r}"
    print(f"ok {text!r} -> media_control stop")


stop("stop the music")
stop("turn off the music")
stop("stop playing")
stop("stop playing music")
stop("please stop the song.")
stop("kill the music")
stop("end the podcast")

# system sound effects must not stop media
r = intent._everyday2("turn off the sound effects")
assert r is None or r[0] != "media_control", r
print("ok 'turn off the sound effects' -> not media_control:", r)

# autostart wording is not a stop request
r = intent._everyday2("stop the music app from starting at login")
assert r is None or r[0] != "media_control", r
print("ok 'stop the music app from starting at login' -> not media_control:", r)

# contraction: print only
print("info \"can't you stop the music\" ->", intent._everyday2("can't you stop the music"))

print("all good")
