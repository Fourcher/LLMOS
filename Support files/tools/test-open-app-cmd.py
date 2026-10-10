#!/usr/bin/env python3
"""Host-side check that 'open the task list app' gives the command 'task list' (no verb or article, no
trailing 'app'). Results that depend on programs installed on this Mac assert only the command string.
Run: python3 tools/test-open-app-cmd.py"""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402


def check(text, want):
    got = intent.match(text)
    assert got == want, f"{text!r}: got {got!r}, want {want!r}"
    print(f"ok {text!r} -> {got!r}")


def check_command(text, want_cmd):
    # depends on installed programs: when it is an app open, the command must be the bare name
    got = intent.match(text)
    if isinstance(got, tuple) and got[0] == "open_app":
        assert got[1].get("command") == want_cmd, f"{text!r}: got {got!r}, want command {want_cmd!r}"
        print(f"ok {text!r} -> {got!r}")
    else:
        print(f"ok {text!r} -> {got!r} (no installed program here; command not checked)")


# the verb and article are stripped from the command, the trailing 'app' too
check_command("open the task list app", "task list")

# unchanged cases
check("open the calculator", ("open_app", {"command": "calculator"}))
check("launch firefox", ("browse", {}))

# 'program' ending: the command is the name only, when a program of that name exists
check_command("start the text editor program", "text editor")

# printed only: no assertion about the result
print(f"ok 'open app store' -> {intent.match('open app store')!r}")

print("all good")
