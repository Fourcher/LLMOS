#!/usr/bin/env python3
"""Tests for system.apk_add / system.apk_del (root bodies, plus the rootd_client path for a non-root desk) and the
rootd verbs apk_add / apk_del that check their arguments. subprocess.run is patched to record argv; nothing runs apk.

Run: python3 tools/test-rootd-apk.py"""
import json
import os
import subprocess
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import rootd, rootd_client, system  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

real_geteuid = os.geteuid
real_run = subprocess.run
real_call = rootd_client.call

calls = []


def fake_run(argv, **kw):
    calls.append((list(argv), kw))
    return subprocess.CompletedProcess(argv, 0, stdout="OUT", stderr="ERR")


def restore():
    os.geteuid = real_geteuid
    subprocess.run = real_run
    rootd_client.call = real_call


def as_uid(uid):
    os.geteuid = lambda: uid


try:
    subprocess.run = fake_run
    as_uid(0)

    # ---- root path: exact argv
    rc, out, err = system.apk_add(["firefox", "py3-pip"])
    assert calls[-1][0] == ["apk", "add", "--no-progress", "firefox", "py3-pip"], calls[-1]
    assert calls[-1][1].get("capture_output") is True and calls[-1][1].get("text") is True
    assert calls[-1][1].get("timeout") == 900, calls[-1][1]
    assert (rc, out, err) == (0, "OUT", "ERR"), (rc, out, err)
    print("ok root apk_add normal argv:", calls[-1][0])

    system.apk_add(["wireguard-tools"], quiet=True)
    assert calls[-1][0] == ["apk", "add", "-q", "wireguard-tools"], calls[-1]
    print("ok root apk_add quiet argv:", calls[-1][0])

    rc, out, err = system.apk_del("libreoffice-writer")
    assert calls[-1][0] == ["apk", "del", "--no-progress", "libreoffice-writer"], calls[-1]
    assert calls[-1][1].get("timeout") == 600, calls[-1][1]
    assert (rc, out, err) == (0, "OUT", "ERR"), (rc, out, err)
    print("ok root apk_del normal argv:", calls[-1][0])

    system.apk_del("musl", force=True)
    assert calls[-1][0] == ["apk", "del", "--no-progress", "--force-broken-world", "musl"], calls[-1]
    print("ok root apk_del force argv:", calls[-1][0])

    # ---- non-root path: goes through rootd_client with _timeout, returns the tuple
    as_uid(1000)
    sent = []

    def fake_call(verb, _timeout=None, **args):
        sent.append((verb, _timeout, args))
        if verb == "apk_add":
            return json.dumps([0, "added", ""])
        return json.dumps([3, "", "busy"])

    rootd_client.call = fake_call
    n_before = len(calls)
    assert system.apk_add(["firefox"], quiet=True) == (0, "added", "")
    assert sent[-1] == ("apk_add", 960, {"names": ["firefox"], "quiet": True, "timeout": 900}), sent[-1]
    assert system.apk_del("firefox", force=True) == (3, "", "busy")
    assert sent[-1] == ("apk_del", 660, {"name": "firefox", "force": True, "timeout": 600}), sent[-1]
    assert len(calls) == n_before, "non-root path must not run apk itself"

    def failing_call(verb, _timeout=None, **args):
        raise RootdError("the system helper is not running")

    rootd_client.call = failing_call
    assert system.apk_add(["firefox"]) == (1, "", "the system helper is not running")
    assert system.apk_del("firefox") == (1, "", "the system helper is not running")
    print("ok non-root apk_add/apk_del send _timeout and return the tuple; RootdError -> (1, '', msg)")

    # ---- rootd verbs: bad names rejected
    rootd_client.call = real_call
    bad_names = ["--allow-untrusted", "foo;rm", "../x", "", "-x", "Firefox", "a" * 101, "firefox\n"]
    for bad in bad_names:
        try:
            rootd.VERBS["apk_add"]({"names": [bad], "quiet": False})
        except ValueError as e:
            assert "bad args" in str(e), e
        else:
            raise AssertionError(f"apk_add accepted {bad!r}")
        try:
            rootd.VERBS["apk_del"]({"name": bad, "force": False})
        except ValueError as e:
            assert "bad args" in str(e), e
        else:
            raise AssertionError(f"apk_del accepted {bad!r}")
    for bad_list in ([], ["firefox"] * 21, "firefox", ["firefox", 5]):
        try:
            rootd.VERBS["apk_add"]({"names": bad_list, "quiet": False})
        except ValueError:
            pass
        else:
            raise AssertionError(f"apk_add accepted names {bad_list!r}")
    for bad_flag in ("yes", 1):
        try:
            rootd.VERBS["apk_add"]({"names": ["firefox"], "quiet": bad_flag})
        except ValueError:
            pass
        else:
            raise AssertionError(f"apk_add accepted quiet {bad_flag!r}")
        try:
            rootd.VERBS["apk_del"]({"name": "firefox", "force": bad_flag})
        except ValueError:
            pass
        else:
            raise AssertionError(f"apk_del accepted force {bad_flag!r}")
    print("ok rootd apk verbs reject", ", ".join(repr(b) for b in bad_names))

    # ---- rootd verbs: good names accepted, output truncated to the last 20000 chars
    good = ["firefox", "py3-pip", "gst-plugins-good", "libreoffice-writer"]
    as_uid(0)
    rc, out, err = json.loads(rootd.VERBS["apk_add"]({"names": good, "quiet": False}))
    assert calls[-1][0] == ["apk", "add", "--no-progress", *good], calls[-1]
    assert (rc, out, err) == (0, "OUT", "ERR")
    rc, out, err = json.loads(rootd.VERBS["apk_del"]({"name": "py3-pip", "force": True}))
    assert calls[-1][0] == ["apk", "del", "--no-progress", "--force-broken-world", "py3-pip"], calls[-1]
    print("ok rootd apk verbs accept", ", ".join(good))

    def long_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout="x" * 25000 + "END", stderr="e" * 30000)

    subprocess.run = long_run
    rc, out, err = json.loads(rootd.VERBS["apk_add"]({"names": ["firefox"]}))
    assert len(out) == 20000 and out.endswith("END"), len(out)
    assert len(err) == 20000 and set(err) == {"e"}, len(err)
    print(f"ok rootd truncates output: stdout {len(out)} chars, stderr {len(err)} chars")

    # ---- custom timeout reaches subprocess.run (root path)
    as_uid(0)
    subprocess.run = fake_run
    system.apk_add(["firefox"], quiet=True, timeout=600)
    assert calls[-1][0] == ["apk", "add", "-q", "firefox"], calls[-1]
    assert calls[-1][1].get("timeout") == 600, calls[-1][1]
    system.apk_del("firefox", timeout=120)
    assert calls[-1][1].get("timeout") == 120, calls[-1][1]
    print("ok custom timeout=600 for add -q reaches subprocess.run")

    # ---- rootd verb: timeout must be an int in 30..1800 (bool, str, out-of-range rejected)
    subprocess.run = fake_run
    for bad_t in (5, 5000, "60", True, 29, 1801, 60.0):
        for verb, args in (("apk_add", {"names": ["firefox"], "timeout": bad_t}),
                           ("apk_del", {"name": "firefox", "timeout": bad_t})):
            try:
                rootd.VERBS[verb](args)
            except ValueError as e:
                assert "bad args: timeout" in str(e), e
            else:
                raise AssertionError(f"{verb} accepted timeout {bad_t!r}")
    ok_n = len(calls)
    rootd.VERBS["apk_add"]({"names": ["firefox"], "timeout": 600})
    assert calls[-1][1].get("timeout") == 600, calls[-1][1]
    assert len(calls) == ok_n + 1
    print("ok rootd verb rejects timeout=5, 5000, \"60\"; accepts 600")

    # ---- TimeoutExpired -> rc 124 with the message
    def timing_out(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

    subprocess.run = timing_out
    assert system.apk_add(["firefox"], timeout=30) == (124, "", "timed out after 30 s"), system.apk_add(["firefox"], timeout=30)
    rc, out, err = json.loads(rootd.VERBS["apk_del"]({"name": "firefox", "timeout": 45}))
    assert (rc, out, err) == (124, "", "timed out after 45 s"), (rc, out, err)
    print("ok TimeoutExpired -> rc 124 with message:", err)
finally:
    restore()

print("all good")
