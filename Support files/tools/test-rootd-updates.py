#!/usr/bin/env python3
"""Tests for system.apk_update / apk_upgrade / clear_apk_cache (root bodies, plus the rootd_client path for a
non-root desk) and the rootd verbs apk_update / apk_upgrade / clear_apk_cache that check their arguments.
subprocess.run is patched to record argv; nothing runs apk, and the cache test uses a temp dir.

Run: python3 tools/test-rootd-updates.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import rootd, rootd_client, system  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

real_geteuid = os.geteuid
real_run = subprocess.run
real_call = rootd_client.call
real_cache = system.APK_CACHE

calls = []


def fake_run(argv, **kw):
    calls.append((list(argv), kw))
    return subprocess.CompletedProcess(argv, 0, stdout="OUT", stderr="ERR")


def restore():
    os.geteuid = real_geteuid
    subprocess.run = real_run
    rootd_client.call = real_call
    system.APK_CACHE = real_cache


def as_uid(uid):
    os.geteuid = lambda: uid


tmp = tempfile.mkdtemp(prefix="updates-test-")
try:
    subprocess.run = fake_run
    as_uid(0)

    # ---- root path: exact argv and timeouts
    assert system.apk_update() == (0, "OUT", "ERR")
    assert calls[-1][0] == ["apk", "update"], calls[-1]
    assert calls[-1][1].get("timeout") == 120, calls[-1][1]
    print("ok root apk_update argv:", calls[-1][0], "timeout 120")

    assert system.apk_upgrade(simulate=True) == (0, "OUT", "ERR")
    assert calls[-1][0] == ["apk", "upgrade", "--simulate"], calls[-1]
    assert calls[-1][1].get("timeout") == 120, calls[-1][1]
    print("ok root apk_upgrade simulate argv:", calls[-1][0], "timeout 120")

    assert system.apk_upgrade(simulate=False) == (0, "OUT", "ERR")
    assert calls[-1][0] == ["apk", "upgrade", "--no-interactive"], calls[-1]
    assert calls[-1][1].get("timeout") == 1800, calls[-1][1]
    print("ok root apk_upgrade install argv:", calls[-1][0], "timeout 1800")

    assert system.apk_upgrade() == (0, "OUT", "ERR")
    assert calls[-1][0] == ["apk", "upgrade", "--no-interactive"], calls[-1]
    print("ok root apk_upgrade default is install")

    def timing_out(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

    subprocess.run = timing_out
    assert system.apk_update() == (124, "", "timed out after 120 s"), system.apk_update()
    assert system.apk_upgrade(simulate=True) == (124, "", "timed out after 120 s")
    assert system.apk_upgrade(simulate=False) == (124, "", "timed out after 1800 s")
    print("ok TimeoutExpired -> rc 124: update 120 s, simulate 120 s, install 1800 s")
    subprocess.run = fake_run

    # ---- non-root path: goes through rootd_client with _timeout, returns the tuple, runs nothing itself
    as_uid(1000)
    sent = []

    def fake_call(verb, _timeout=None, **args):
        sent.append((verb, _timeout, args))
        if verb == "apk_update":
            return json.dumps([0, "updated", ""])
        if verb == "apk_upgrade":
            return json.dumps([0, "upgraded", ""])
        return json.dumps([4096, "cleared 4096 bytes of apk cache"])

    rootd_client.call = fake_call
    n_before = len(calls)
    assert system.apk_update() == (0, "updated", "")
    assert sent[-1] == ("apk_update", 180, {}), sent[-1]
    assert system.apk_upgrade(simulate=True) == (0, "upgraded", "")
    assert sent[-1] == ("apk_upgrade", 180, {"simulate": True}), sent[-1]
    assert system.apk_upgrade(simulate=False) == (0, "upgraded", "")
    assert sent[-1] == ("apk_upgrade", 1860, {"simulate": False}), sent[-1]
    assert system.clear_apk_cache() == (4096, "cleared 4096 bytes of apk cache")
    assert sent[-1][0] == "clear_apk_cache" and sent[-1][2] == {}, sent[-1]
    assert len(calls) == n_before, "non-root path must not run apk or delete anything itself"
    print("ok non-root updates send _timeout (180 / 180 / 1860) and return the tuple")

    def failing_call(verb, _timeout=None, **args):
        raise RootdError("the system helper is not running")

    rootd_client.call = failing_call
    assert system.apk_update() == (1, "", "the system helper is not running")
    assert system.apk_upgrade(simulate=True) == (1, "", "the system helper is not running")
    assert system.clear_apk_cache() == (0, "the system helper is not running")
    print("ok RootdError -> (1, '', msg) for update/upgrade, (0, msg) for cache clear")
    rootd_client.call = real_call

    # ---- rootd verbs: extra args and non-bool simulate rejected
    as_uid(0)
    bad_calls = [
        ("apk_update", {"x": 1}),
        ("apk_update", "yes"),
        ("apk_upgrade", {}),
        ("apk_upgrade", {"simulate": "yes"}),
        ("apk_upgrade", {"simulate": 1}),
        ("apk_upgrade", {"simulate": None}),
        ("apk_upgrade", {"simulate": True, "x": 1}),
        ("apk_upgrade", {"simulate": True, "timeout": 60}),
        ("apk_upgrade", "yes"),
        ("clear_apk_cache", {"path": "/"}),
        ("clear_apk_cache", ["x"]),
    ]
    n_before = len(calls)
    for verb, args in bad_calls:
        try:
            rootd.VERBS[verb](args)
        except ValueError as e:
            assert str(e).startswith("bad args"), e
        else:
            raise AssertionError(f"{verb} accepted {args!r}")
    assert len(calls) == n_before, "a rejected verb must not run apk"
    print(f"ok rootd verbs reject {len(bad_calls)} bad argument sets (extra args, simulate not a bool)")

    # ---- rootd verbs: good calls reach the right argv; output is the usual [rc, out, err]
    rc, out, err = json.loads(rootd.VERBS["apk_update"]({}))
    assert calls[-1][0] == ["apk", "update"] and (rc, out, err) == (0, "OUT", "ERR"), calls[-1]
    rc, out, err = json.loads(rootd.VERBS["apk_upgrade"]({"simulate": True}))
    assert calls[-1][0] == ["apk", "upgrade", "--simulate"], calls[-1]
    rc, out, err = json.loads(rootd.VERBS["apk_upgrade"]({"simulate": False}))
    assert calls[-1][0] == ["apk", "upgrade", "--no-interactive"], calls[-1]
    assert calls[-1][1].get("timeout") == 1800, calls[-1][1]
    print("ok rootd verbs run the right apk argv")

    def long_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout="x" * 25000 + "END", stderr="e" * 30000)

    subprocess.run = long_run
    rc, out, err = json.loads(rootd.VERBS["apk_upgrade"]({"simulate": True}))
    assert len(out) == 20000 and out.endswith("END"), len(out)
    assert len(err) == 20000 and set(err) == {"e"}, len(err)
    print(f"ok rootd truncates update output: stdout {len(out)} chars, stderr {len(err)} chars")
    subprocess.run = fake_run

    # ---- cache clear on a temp dir: symlinks are unlinked, never followed
    outside = os.path.join(tmp, "outside")
    cache = os.path.join(tmp, "apk")
    os.makedirs(outside)
    os.makedirs(os.path.join(cache, "sub", "nested"))
    with open(os.path.join(outside, "keep"), "wb") as f:
        f.write(b"KEEP-ME-7")
    with open(os.path.join(cache, "a.apk"), "wb") as f:
        f.write(b"A" * 10)
    with open(os.path.join(cache, "sub", "b"), "wb") as f:
        f.write(b"B" * 5)
    with open(os.path.join(cache, "sub", "nested", "c"), "wb") as f:
        f.write(b"C" * 3)
    os.symlink(outside, os.path.join(cache, "dirlink"))
    os.symlink(os.path.join(outside, "keep"), os.path.join(cache, "filelink"))
    os.symlink(outside, os.path.join(cache, "sub", "inner_dirlink"))
    link_sizes = sum(os.lstat(os.path.join(cache, n)).st_size for n in ("dirlink", "filelink"))
    link_sizes += os.lstat(os.path.join(cache, "sub", "inner_dirlink")).st_size

    system.APK_CACHE = cache
    freed, msg = system._clear_apk_cache_root()
    assert sorted(os.listdir(cache)) == [], os.listdir(cache)
    assert os.path.isdir(outside) and not os.path.islink(outside), "symlink target dir was removed"
    assert os.path.isfile(os.path.join(outside, "keep")), "symlink target file was removed"
    with open(os.path.join(outside, "keep"), "rb") as f:
        assert f.read() == b"KEEP-ME-7", "symlink target file was changed"
    assert freed == 18 + link_sizes, (freed, link_sizes)
    assert msg == f"cleared {freed} bytes of apk cache", msg
    print(f"ok cache clear deletes 3 files + 3 links, target untouched; freed {freed} bytes")

    # the public function, as root, reports the same tuple
    os.makedirs(os.path.join(cache, "d"))
    with open(os.path.join(cache, "d", "x"), "wb") as f:
        f.write(b"X" * 4)
    assert system.clear_apk_cache() == (4, "cleared 4 bytes of apk cache"), system.clear_apk_cache()
    assert os.listdir(cache) == []

    # the cache dir itself is a symlink: nothing is deleted
    system.APK_CACHE = os.path.join(tmp, "apk-link")
    os.symlink(outside, system.APK_CACHE)
    assert system._clear_apk_cache_root() == (0, "cleared 0 bytes of apk cache")
    assert os.path.isfile(os.path.join(outside, "keep")), "a symlinked cache root was followed"
    system.APK_CACHE = os.path.join(tmp, "missing")
    assert system._clear_apk_cache_root() == (0, "cleared 0 bytes of apk cache")
    print("ok cache clear does nothing when the cache dir is a symlink or missing")

    # the rootd verb end to end through handle()
    system.APK_CACHE = cache
    with open(os.path.join(cache, "z"), "wb") as f:
        f.write(b"Z" * 2)
    reply = json.loads(rootd.handle(json.dumps({"verb": "clear_apk_cache", "args": {}}).encode()))
    assert reply == {"ok": True, "out": json.dumps([2, "cleared 2 bytes of apk cache"])}, reply
    reply = json.loads(rootd.handle(json.dumps({"verb": "clear_apk_cache", "args": {"x": 1}}).encode()))
    assert reply["ok"] is False and reply["error"].startswith("bad args"), reply
    print("ok rootd handle: clear_apk_cache clears; extra args -> ok false")

    print("all good")
finally:
    restore()
    shutil.rmtree(tmp, ignore_errors=True)
