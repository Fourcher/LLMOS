#!/usr/bin/env python3
"""Host-side test of the plain-words error replies in everyday.py (touches no files and no system: the system call
is replaced by a stub that raises). Run: python3 tools/test-everyday-errors.py"""
import errno
import os
import socket
import sys
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import everyday, rootd_client  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Desk:
    def __init__(self):
        self.said = None

    def instant_reply(self, line, text):
        self.said = text


print("plain words for each kind of error")
cases = (
    (PermissionError(13, "Permission denied", "/root/x"), "it isn't allowed here"),
    (FileNotFoundError(2, "No such file or directory", "/tmp/x"), "it isn't there"),
    (FileExistsError(17, "File exists", "/tmp/x"), "something with that name already exists"),
    (IsADirectoryError(21, "Is a directory", "/tmp/x"), "that's a folder"),
    (NotADirectoryError(20, "Not a directory", "/tmp/x"), "that isn't a folder"),
    (OSError(errno.ENOSPC, "No space left on device"), "the disk is full"),
    (socket.timeout("timed out"), "no answer from the internet"),
    (TimeoutError("timed out"), "no answer from the internet"),
    (urllib.error.URLError("unreachable"), "no answer from the internet"),
    (ValueError("odd"), "something went wrong"),
)
for exc, want in cases:
    got = everyday._plain_err(exc)
    check(got == want, f"{type(exc).__name__} -> {got!r}")
    check("Errno" not in got and "/" not in got, f"{type(exc).__name__} reply has no errno or path")

print("the rename reply never shows Python's error text")
dk = Desk()
with mock.patch.object(rootd_client, "call", side_effect=PermissionError(13, "Permission denied", "/root/x")):
    everyday.hostname(dk, "call this computer kitchen-pc", "call this computer kitchen-pc")
said = dk.said or ""
print("  reply:", said)
check("Couldn't rename it" in said, "the rename failure is reported")
check("Errno" not in said, "no Errno in the reply")
check("/root/" not in said, "no /root/ path in the reply")
check("isn't allowed" in said, "the reply says it isn't allowed")

print("the system helper's refusals in plain words")
check(everyday._plain_err(rootd_client.RootdError("the system helper is not running")) == "the system helper is not running",
      "RootdError('the system helper is not running') -> same text")
check(everyday._plain_err(rootd_client.RootdError("bad args: zone")) == "that name or value isn't allowed",
      "RootdError('bad args: zone') -> that name or value isn't allowed")
check(everyday._plain_err(ValueError("bad args: zone")) == "that name or value isn't allowed",
      "ValueError('bad args: zone') -> that name or value isn't allowed")
dk = Desk()
with mock.patch.object(rootd_client, "call", side_effect=rootd_client.RootdError("bad args: name")):
    everyday.hostname(dk, "call this computer kitchen-pc", "call this computer kitchen-pc")
check(dk.said == "Couldn't rename it: that name isn't allowed: use letters, numbers and dashes.", f"rename site bad args -> {dk.said!r}")
dk = Desk()
with mock.patch.object(rootd_client, "call", side_effect=rootd_client.RootdError("the system helper is not running")):
    everyday.hostname(dk, "call this computer kitchen-pc", "call this computer kitchen-pc")
check(dk.said == "Couldn't rename it: the system helper is not running.", f"rename site not running -> {dk.said!r}")

print()
print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
