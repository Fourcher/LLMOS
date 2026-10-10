#!/usr/bin/env python3
"""Tests for rootd_client.py: a non-root call over rootd's socket (served in a thread), the error paths, the
in-process path when the process is root (os.geteuid patched), and the reply checks (bad reply, oversized reply).

ZONEINFO, ETC_ROOT and LOG_PATH point at temp dirs, so nothing outside them is touched. Run as a non-root user.
Run: python3 tools/test-rootd-client.py"""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import rootd, rootd_client  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

tmp = tempfile.mkdtemp(prefix="rootd-client-test-")
zoneinfo = os.path.join(tmp, "zoneinfo")
etc = os.path.join(tmp, "root")
os.makedirs(os.path.join(zoneinfo, "Europe"))
os.makedirs(os.path.join(etc, "etc"))
rootd.ZONEINFO = zoneinfo
rootd.ETC_ROOT = etc
rootd.LOG_PATH = os.path.join(tmp, "log", "rootd.log")


def expect_raises(label, fn, must):
    try:
        fn()
    except RootdError as e:
        assert must in str(e), f"{label}: got {e!r}, wanted {must!r}"
        assert "Traceback" not in str(e), label
        print(f"ok {label}: {e}")
        return
    raise AssertionError(f"{label}: no RootdError raised")


def wait_for(path):
    for _ in range(100):
        if os.path.exists(path):
            return
        time.sleep(0.05)
    raise AssertionError(f"socket not created: {path}")


def fake_server(path, payload):
    """A one-shot server that reads the request to EOF, then sends payload as its whole reply."""
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)

    def run():
        conn, _ = srv.accept()
        with conn:
            while conn.recv(65536):
                pass
            conn.sendall(payload)
        srv.close()

    threading.Thread(target=run, daemon=True).start()


# --- (a) non-root user, over the socket
assert os.geteuid() != 0, "run this test as a non-root user"
sock_dir = tempfile.mkdtemp(prefix="rc-", dir="/tmp")
sock_path = os.path.join(sock_dir, "root.sock")
t = threading.Thread(target=rootd.serve, args=(sock_path, "no-such-group-xyz"), daemon=True)
t.start()
wait_for(sock_path)
rootd_client.SOCK = sock_path

out = rootd_client.call("set_hostname", name="kitchen")
assert out == "ok", out
assert open(os.path.join(etc, "etc", "hostname")).read() == "kitchen\n"
print(f"ok socket set_hostname kitchen -> {out!r}, hostname file written")

expect_raises("socket bad name", lambda: rootd_client.call("set_hostname", name="Kitchen"), "bad args")
expect_raises("socket unknown verb", lambda: rootd_client.call("reboot"), "unknown verb")
expect_raises("socket args not JSON-serialisable", lambda: rootd_client.call("set_hostname", name=object()),
              "not JSON-serialisable")
assert open(os.path.join(etc, "etc", "hostname")).read() == "kitchen\n", "a refused call changed the hostname"

rootd_client.SOCK = os.path.join(sock_dir, "missing.sock")
expect_raises("no socket", lambda: rootd_client.call("set_hostname", name="kitchen"), "the system helper is not running")

rootd_client.SOCK = os.path.join(sock_dir, "bad.sock")
fake_server(rootd_client.SOCK, b"{nope")
expect_raises("non-JSON reply", lambda: rootd_client.call("set_hostname", name="kitchen"), "bad reply")

rootd_client.SOCK = os.path.join(sock_dir, "big.sock")
fake_server(rootd_client.SOCK, b'{"ok": true, "out": "' + b"x" * (1024 * 1024 + 10) + b'"}')
expect_raises("reply over 1 MiB", lambda: rootd_client.call("set_hostname", name="kitchen"), "reply too large")

# --- (b) root: the verb runs in this process, no socket used
rootd_client.SOCK = os.path.join(sock_dir, "never-created.sock")
real_geteuid = os.geteuid
os.geteuid = lambda: 0
try:
    out = rootd_client.call("set_hostname", name="root-pc")
    assert out == "ok", out
    assert open(os.path.join(etc, "etc", "hostname")).read() == "root-pc\n"
    assert not os.path.exists(rootd_client.SOCK), "in-process call touched a socket"
    print(f"ok in-process (euid 0) set_hostname root-pc -> {out!r}, no socket used")
    expect_raises("in-process bad name", lambda: rootd_client.call("set_hostname", name="Root"), "bad args")
    expect_raises("in-process unknown verb", lambda: rootd_client.call("reboot"), "unknown verb")
finally:
    os.geteuid = real_geteuid

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(sock_dir, ignore_errors=True)
print("all good")
