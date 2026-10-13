#!/usr/bin/env python3
"""Tests for the llmos-rootd init script and rootd.serve()'s socket mode/group handling.

The init script is checked as a file (mode, shebang, reference to rootd.py, sh -n). serve() is run in a thread on a
temp socket: with the owner group missing the socket is 0600 and one stderr line is printed; with a group present
(getgrnam and os.chown patched) it is 0660 and chown is called with the group's gid.
"""
import importlib.util
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
INIT = os.path.join(ROOT, "src", "rootfs", "etc", "init.d", "llmos-rootd")
SRC = os.path.join(ROOT, "src", "rootfs", "usr", "lib", "llmos", "llmos", "rootd.py")

# --- the init script as a file
assert os.path.isfile(INIT), INIT
mode = os.stat(INIT).st_mode & 0o777
assert mode & 0o111 == 0o111, oct(mode)
print(f"ok init script exists, mode {oct(mode)}")

idx = subprocess.run(["git", "-C", ROOT, "ls-files", "-s", "--", "src/rootfs/etc/init.d/llmos-rootd"],
                     capture_output=True, text=True)
if idx.returncode == 0 and idx.stdout.strip():
    git_mode = idx.stdout.split()[0]
    assert git_mode == "100755", idx.stdout
    print(f"ok git index mode: {idx.stdout.split()[0]}")
else:
    print("skip git index mode (not in a git checkout)")

with open(INIT, encoding="utf-8") as f:
    script = f.read()
first = script.splitlines()[0]
assert first == "#!/sbin/openrc-run", first
print(f"ok shebang: {first}")
assert "/usr/lib/llmos/llmos/rootd.py" in script, "script does not reference rootd.py"
print("ok script references /usr/lib/llmos/llmos/rootd.py")
r = subprocess.run(["sh", "-n", INIT], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
print("ok sh -n")

# --- rootd.serve() socket mode
spec = importlib.util.spec_from_file_location("rootd", SRC)
rootd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rootd)

tmp = tempfile.mkdtemp(prefix="rootd-svc-", dir="/tmp")
rootd.LOG_PATH = os.path.join(tmp, "rootd.log")  # the probe connections log here, not to /run/llmos
try:
    def wait_listening(path):
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        for _ in range(100):
            try:
                c.connect(path)
                c.close()
                return
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.05)
        raise AssertionError("socket never listened")

    # 1. group missing: 0600 and one stderr line
    sock1 = os.path.join(tmp, "missing", "root.sock")
    err = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = err
    try:
        t1 = threading.Thread(target=rootd.serve, args=(sock1, "no-such-group-xyz-svc"), daemon=True)
        t1.start()
        wait_listening(sock1)
    finally:
        sys.stderr = real_stderr
    m1 = oct(os.stat(sock1).st_mode & 0o777)
    assert m1 == "0o600", m1
    d1 = oct(os.stat(os.path.dirname(sock1)).st_mode & 0o777)
    assert d1 == "0o700", d1
    lines = err.getvalue().splitlines()
    assert lines == ["rootd: group 'no-such-group-xyz-svc' missing; socket is root-only"], lines
    print(f"ok missing group: dir {d1}, socket {m1}, stderr: {lines[0]}")

    # 2. group present (patched): 0660 and chown called with the gid
    sock2 = os.path.join(tmp, "present", "root.sock")
    gid = os.getgid()
    fake_group = mock.Mock(gr_gid=gid)
    chown_calls = []

    def recorder(path, uid, g):
        chown_calls.append((path, uid, g))

    err2 = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = err2
    try:
        with mock.patch.object(rootd.grp, "getgrnam", return_value=fake_group) as gg, \
                mock.patch.object(rootd.os, "chown", side_effect=recorder):
            t2 = threading.Thread(target=rootd.serve, args=(sock2, "owner"), daemon=True)
            t2.start()
            wait_listening(sock2)
            gg.assert_called_with("owner")
    finally:
        sys.stderr = real_stderr
    m2 = oct(os.stat(sock2).st_mode & 0o777)
    assert m2 == "0o660", m2
    d2 = oct(os.stat(os.path.dirname(sock2)).st_mode & 0o777)
    assert d2 == "0o750", d2
    assert chown_calls == [(os.path.dirname(sock2), 0, gid), (sock2, -1, gid)], chown_calls
    assert err2.getvalue() == "", err2.getvalue()
    print(f"ok group present: dir {d2} owned root:owner, socket {m2}, no stderr")

    # 3. the default path is the new one, and the client points at the same place
    assert rootd.SOCK_PATH == "/run/llmos-rootd/root.sock", rootd.SOCK_PATH
    assert rootd.serve.__defaults__[0] == rootd.SOCK_PATH, rootd.serve.__defaults__
    spec_c = importlib.util.spec_from_file_location("rootd_client", os.path.join(
        ROOT, "src", "rootfs", "usr", "lib", "llmos", "llmos", "rootd_client.py"))
    client_src = open(spec_c.origin, encoding="utf-8").read()
    assert 'SOCK = "/run/llmos-rootd/root.sock"' in client_src, "client SOCK is not the new path"
    print("ok default path: /run/llmos-rootd/root.sock in rootd and rootd_client")

    # 4. a symlinked socket directory is refused: exit with a stderr line, nothing bound behind the link
    real_dir = os.path.join(tmp, "real-dir")
    os.mkdir(real_dir)
    link_dir = os.path.join(tmp, "link-dir")
    os.symlink(real_dir, link_dir)
    err3 = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = err3
    try:
        try:
            rootd.serve(os.path.join(link_dir, "root.sock"), "no-such-group-xyz-svc")
            raise AssertionError("serve did not refuse a symlinked directory")
        except SystemExit as e:
            code = e.code
    finally:
        sys.stderr = real_stderr
    assert code != 0, code
    assert err3.getvalue().splitlines() == [f"rootd: {link_dir} is a symlink or not a directory; refusing to start"], err3.getvalue()
    assert os.listdir(real_dir) == [], os.listdir(real_dir)
    print(f"ok symlinked dir refused: exit {code}, stderr: {err3.getvalue().strip()}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("all good")
