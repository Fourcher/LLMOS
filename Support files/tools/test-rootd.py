#!/usr/bin/env python3
"""Tests for rootd.py: the root service verbs, adversarial inputs, and one request over a real socket.

ZONEINFO, ETC_ROOT and LOG_PATH point at temp dirs, so nothing outside them is touched.
"""
import importlib.util
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "rootd.py")
spec = importlib.util.spec_from_file_location("rootd", SRC)
rootd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rootd)

tmp = tempfile.mkdtemp(prefix="rootd-test-")
zoneinfo = os.path.join(tmp, "zoneinfo")
etc = os.path.join(tmp, "root")
os.makedirs(os.path.join(zoneinfo, "Europe"))
with open(os.path.join(zoneinfo, "Europe", "Paris"), "wb") as f:
    f.write(b"TZif-fake")
os.makedirs(os.path.join(etc, "etc"))
rootd.ZONEINFO = zoneinfo
rootd.ETC_ROOT = etc
rootd.LOG_PATH = os.path.join(tmp, "log", "rootd.log")


def call(verb, args):
    return json.loads(rootd.handle(json.dumps({"verb": verb, "args": args}).encode()))


def expect_ok(label, reply):
    assert reply == {"ok": True, "out": "ok"}, f"{label}: {reply}"
    print(f"ok {label}")


def expect_err(label, reply, must=None):
    assert reply["ok"] is False, f"{label}: accepted {reply}"
    if must:
        assert must in reply["error"], f"{label}: {reply}"
    assert "Traceback" not in reply["error"], label
    print(f"ok {label}: {reply['error']}")


def snapshot(root):
    found = []
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            p = os.path.join(d, n)
            found.append(os.path.relpath(p, root))
    return sorted(found)


# --- set_timezone
expect_ok("set_timezone Europe/Paris", call("set_timezone", {"zone": "Europe/Paris"}))
assert os.readlink(os.path.join(etc, "etc", "localtime")) == os.path.realpath(os.path.join(zoneinfo, "Europe", "Paris"))
assert open(os.path.join(etc, "etc", "timezone")).read() == "Europe/Paris\n"
assert open(os.path.join(etc, "etc", "llmos", "timezone")).read() == "Europe/Paris\n"
expect_err("zone traversal", call("set_timezone", {"zone": "../../etc/passwd"}), "bad args")
expect_err("zone unknown", call("set_timezone", {"zone": "Europe/Atlantis"}), "bad args")
expect_err("zone directory", call("set_timezone", {"zone": "Europe"}), "bad args")
expect_err("zone not str", call("set_timezone", {"zone": 5}), "bad args")
expect_err("zone args not dict", json.loads(rootd.handle(b'{"verb":"set_timezone","args":["Europe/Paris"]}')), "bad args")
expect_err("zone trailing newline", call("set_timezone", {"zone": "Europe/Paris\n"}), "bad args")

# symlink inside zoneinfo that points outside it must be refused
outside = os.path.join(tmp, "outside-secret")
with open(outside, "w") as f:
    f.write("not a zone")
os.symlink(outside, os.path.join(zoneinfo, "Europe", "Escape"))
expect_err("symlink outside zoneinfo", call("set_timezone", {"zone": "Europe/Escape"}), "bad args")
os.unlink(os.path.join(zoneinfo, "Europe", "Escape"))

# --- set_hostname
expect_ok("set_hostname kitchen-pc", call("set_hostname", {"name": "kitchen-pc"}))
assert open(os.path.join(etc, "etc", "hostname")).read() == "kitchen-pc\n"
expect_err("hostname uppercase", call("set_hostname", {"name": "Kitchen"}), "bad args")
expect_err("hostname space", call("set_hostname", {"name": "kitchen pc"}), "bad args")
expect_err("hostname leading dash", call("set_hostname", {"name": "-pc"}), "bad args")
expect_err("hostname too long", call("set_hostname", {"name": "a" * 64}), "bad args")
expect_err("hostname trailing newline", call("set_hostname", {"name": "kitchen\n"}), "bad args")

# --- write_setting_file
expect_ok("write settings.json", call("write_setting_file", {"name": "settings.json", "text": "{\"a\": 1}"}))
assert open(os.path.join(etc, "etc", "llmos", "settings.json")).read() == "{\"a\": 1}"
expect_ok("write conduct.txt", call("write_setting_file", {"name": "conduct.txt", "text": "be kind\n"}))
assert open(os.path.join(etc, "etc", "llmos", "conduct.txt")).read() == "be kind\n"
expect_err("setting traversal", call("write_setting_file", {"name": "../x", "text": "x"}), "bad args")
expect_err("setting other name", call("write_setting_file", {"name": "shadow", "text": "x"}), "bad args")
expect_err("setting too big", call("write_setting_file", {"name": "conduct.txt", "text": "x" * (256 * 1024 + 1)}), "bad args")
expect_err("setting text not str", call("write_setting_file", {"name": "conduct.txt", "text": ["x"]}), "bad args")

# --- handle-level
expect_err("unknown verb", call("reboot", {}), "unknown verb")
expect_err("args not dict", json.loads(rootd.handle(b'{"verb":"set_hostname","args":"kitchen"}')), "bad args")
expect_err("oversized request", json.loads(rootd.handle(b"x" * (512 * 1024 + 1))), "too large")
expect_err("not json", json.loads(rootd.handle(b"{nope")), "bad args")
expect_err("not object", json.loads(rootd.handle(b"[1,2]")), "bad args")

# --- nothing written anywhere else
written = snapshot(etc)
expected = sorted([
    "etc", "etc/localtime", "etc/timezone", "etc/hostname", "etc/llmos", "etc/llmos/timezone",
    "etc/llmos/settings.json", "etc/llmos/conduct.txt",
])
assert written == expected, f"unexpected files: {written}"
assert not os.path.exists(os.path.join(etc, "etc", "localtime.tmp"))
assert not any(n.startswith(".") for n in written), "temp files left behind"
assert snapshot(zoneinfo) == ["Europe", "Europe/Paris"], "zoneinfo was modified"
print("ok files written exactly where expected")

# --- serve over a real socket, in a thread
sock_dir = tempfile.mkdtemp(prefix="rs-", dir="/tmp")
sock_path = os.path.join(sock_dir, "root.sock")
t = threading.Thread(target=rootd.serve, args=(sock_path, "no-such-group-xyz"), daemon=True)
t.start()
for _ in range(100):
    if os.path.exists(sock_path):
        break
    time.sleep(0.05)
assert os.path.exists(sock_path), "socket not created"
assert oct(os.stat(sock_path).st_mode & 0o777) == "0o660", oct(os.stat(sock_path).st_mode)
c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
c.connect(sock_path)
c.sendall(json.dumps({"verb": "set_hostname", "args": {"name": "socket-pc"}}).encode())
c.shutdown(socket.SHUT_WR)
reply = json.loads(c.makefile("rb").read().decode())
c.close()
assert reply == {"ok": True, "out": "ok"}, reply
assert open(os.path.join(etc, "etc", "hostname")).read() == "socket-pc\n"
time.sleep(0.2)
log = open(rootd.LOG_PATH).read().splitlines()
assert log and log[-1].endswith(" set_hostname ok"), log
print(f"ok socket request: {reply}; log: {log[-1]}")

# a silent client must not block a second client
silent = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
silent.connect(sock_path)
c2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
c2.settimeout(2)
c2.connect(sock_path)
started = time.time()
c2.sendall(json.dumps({"verb": "set_hostname", "args": {"name": "second-pc"}}).encode())
c2.shutdown(socket.SHUT_WR)
chunks = []
while True:
    part = c2.recv(65536)
    if not part:
        break
    chunks.append(part)
elapsed = time.time() - started
c2.close()
silent.close()
reply2 = json.loads(b"".join(chunks).decode())
assert reply2 == {"ok": True, "out": "ok"}, reply2
assert elapsed < 2, f"second client waited {elapsed:.2f}s"
print(f"ok silent client does not block: reply in {elapsed:.2f}s")

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(sock_dir, ignore_errors=True)
print("all good")
