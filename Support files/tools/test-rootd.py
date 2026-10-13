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
# chosen=False: the zone is set, but /etc/llmos/timezone is left alone
os.unlink(os.path.join(etc, "etc", "llmos", "timezone"))
expect_ok("set_timezone not chosen", call("set_timezone", {"zone": "Europe/Paris", "chosen": False}))
assert os.readlink(os.path.join(etc, "etc", "localtime")) == os.path.realpath(os.path.join(zoneinfo, "Europe", "Paris"))
assert not os.path.exists(os.path.join(etc, "etc", "llmos", "timezone")), "chosen=False wrote /etc/llmos/timezone"
expect_err("chosen not bool", call("set_timezone", {"zone": "Europe/Paris", "chosen": "yes"}), "bad args")
expect_ok("set_timezone chosen again", call("set_timezone", {"zone": "Europe/Paris", "chosen": True}))
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
expect_err("oversized request", json.loads(rootd.handle(b"x" * (rootd.MAX_REQUEST + 1))), "too large")
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

# --- remove_setting_file (after the snapshot above, which expects conduct.txt to exist)
conduct_path = os.path.join(etc, "etc", "llmos", "conduct.txt")
settings_path = os.path.join(etc, "etc", "llmos", "settings.json")
expect_ok("remove conduct.txt", call("remove_setting_file", {"name": "conduct.txt"}))
assert not os.path.exists(conduct_path), "conduct.txt still exists"
expect_ok("remove conduct.txt again (missing ok)", call("remove_setting_file", {"name": "conduct.txt"}))
expect_err("remove traversal", call("remove_setting_file", {"name": "../settings.json"}), "bad args")
expect_err("remove other name", call("remove_setting_file", {"name": "shadow"}), "bad args")
expect_err("remove name not str", call("remove_setting_file", {"name": 5}), "bad args")
assert os.path.exists(settings_path), "a rejected remove touched settings.json"
print("ok remove_setting_file: removes, missing ok, bad names rejected")

# --- symlinked etc/llmos: every verb refuses, and nothing outside is touched
def expect_refused(label, reply):
    assert reply["ok"] is False, f"{label}: accepted {reply}"
    assert "not a plain folder" in reply["error"], f"{label}: {reply}"
    print(f"ok {label}: {reply['error']}")


link_root = os.path.join(tmp, "linkroot")
os.makedirs(os.path.join(link_root, "etc"))
outside_dir = os.path.join(tmp, "outside-dir")
os.makedirs(outside_dir)
with open(os.path.join(outside_dir, "conduct.txt"), "w") as f:
    f.write("outside conduct")
with open(os.path.join(outside_dir, "timezone"), "w") as f:
    f.write("outside tz\n")
os.symlink(outside_dir, os.path.join(link_root, "etc", "llmos"))
rootd.ETC_ROOT = link_root
try:
    expect_refused("symlinked etc/llmos: write refused", call("write_setting_file", {"name": "conduct.txt", "text": "pwned"}))
    expect_refused("symlinked etc/llmos: remove refused", call("remove_setting_file", {"name": "conduct.txt"}))
    expect_refused("symlinked etc/llmos: set_timezone refused", call("set_timezone", {"zone": "Europe/Paris"}))
    expect_refused("symlinked etc/llmos: set_timezone not chosen refused", call("set_timezone", {"zone": "Europe/Paris", "chosen": False}))
    assert open(os.path.join(outside_dir, "conduct.txt")).read() == "outside conduct", "outside conduct.txt changed"
    assert open(os.path.join(outside_dir, "timezone")).read() == "outside tz\n", "outside timezone changed"
    assert sorted(os.listdir(outside_dir)) == ["conduct.txt", "timezone"], "outside dir changed"
    assert not os.path.lexists(os.path.join(link_root, "etc", "localtime")), "set_timezone wrote localtime despite refusal"
    assert not os.path.lexists(os.path.join(link_root, "etc", "timezone")), "set_timezone wrote timezone despite refusal"
finally:
    rootd.ETC_ROOT = etc
print("ok symlinked etc/llmos: outside files untouched")

# symlinked etc itself: refused too
etc_link_root = os.path.join(tmp, "etclinkroot")
os.makedirs(etc_link_root)
outside_etc = os.path.join(tmp, "outside-etc")
os.makedirs(os.path.join(outside_etc, "llmos"))
with open(os.path.join(outside_etc, "llmos", "conduct.txt"), "w") as f:
    f.write("outside etc conduct")
os.symlink(outside_etc, os.path.join(etc_link_root, "etc"))
rootd.ETC_ROOT = etc_link_root
try:
    expect_refused("symlinked etc: write refused", call("write_setting_file", {"name": "conduct.txt", "text": "pwned"}))
    expect_refused("symlinked etc: remove refused", call("remove_setting_file", {"name": "conduct.txt"}))
    expect_refused("symlinked etc: set_timezone refused", call("set_timezone", {"zone": "Europe/Paris"}))
finally:
    rootd.ETC_ROOT = etc
assert open(os.path.join(outside_etc, "llmos", "conduct.txt")).read() == "outside etc conduct", "outside etc conduct changed"
print("ok symlinked etc: outside files untouched")

# etc/llmos missing: created as before
missing_root = os.path.join(tmp, "missingroot")
os.makedirs(os.path.join(missing_root, "etc"))
rootd.ETC_ROOT = missing_root
try:
    expect_ok("missing etc/llmos: write creates it", call("write_setting_file", {"name": "conduct.txt", "text": "fresh"}))
    assert open(os.path.join(missing_root, "etc", "llmos", "conduct.txt")).read() == "fresh"
    os.unlink(os.path.join(missing_root, "etc", "llmos", "conduct.txt"))
    os.rmdir(os.path.join(missing_root, "etc", "llmos"))
    expect_ok("missing etc/llmos: set_timezone creates it", call("set_timezone", {"zone": "Europe/Paris"}))
    assert open(os.path.join(missing_root, "etc", "llmos", "timezone")).read() == "Europe/Paris\n"
finally:
    rootd.ETC_ROOT = etc
print("ok missing etc/llmos: created")

# symlinked settings.json inside a plain etc/llmos: remove drops only the link, write replaces the link
outside_file = os.path.join(tmp, "outside-settings.json")
with open(outside_file, "w") as f:
    f.write("outside settings")
if os.path.lexists(settings_path):
    os.unlink(settings_path)
os.symlink(outside_file, settings_path)
expect_ok("remove symlinked settings.json", call("remove_setting_file", {"name": "settings.json"}))
assert not os.path.lexists(settings_path), "symlinked settings.json link still exists"
assert open(outside_file).read() == "outside settings", "remove followed the symlink"
os.symlink(outside_file, settings_path)
expect_ok("write over symlinked settings.json", call("write_setting_file", {"name": "settings.json", "text": "{\"b\": 2}"}))
assert not os.path.islink(settings_path), "write kept the symlink"
assert open(settings_path).read() == "{\"b\": 2}", "write did not replace the link"
assert open(outside_file).read() == "outside settings", "write followed the symlink"
print("ok symlinked settings.json: remove drops the link, write replaces it, outside file untouched")

# --- corrupt settings.json: the exact bytes are kept as settings.json.broken-<stamp> before the overwrite
broken_root = os.path.join(tmp, "brokenroot")
os.makedirs(os.path.join(broken_root, "etc", "llmos"))
broken_dir = os.path.join(broken_root, "etc", "llmos")
broken_settings = os.path.join(broken_dir, "settings.json")
rootd.ETC_ROOT = broken_root
real_datetime = rootd.datetime
frozen = real_datetime(2026, 10, 10, 12, 0, 0)


class FrozenDatetime:
    @staticmethod
    def now():
        return frozen


def copies():
    return sorted(n for n in os.listdir(broken_dir) if n.startswith("settings.json.broken-"))


try:
    rootd.datetime = FrozenDatetime
    cases = [
        ("corrupt text", b"{nope, the owner's words"),
        ("empty file", b""),
        ("json list", b"[]"),
    ]
    for label, raw in cases:
        with open(broken_settings, "wb") as f:
            f.write(raw)
        for old in copies():
            os.unlink(os.path.join(broken_dir, old))
        expect_ok(f"corrupt settings.json ({label}): write", call("write_setting_file", {"name": "settings.json", "text": "{\"c\": 3}"}))
        assert copies() == ["settings.json.broken-20261010-120000"], (label, copies())
        kept = os.path.join(broken_dir, copies()[0])
        assert open(kept, "rb").read() == raw, f"{label}: copy bytes differ"
        assert oct(os.stat(kept).st_mode & 0o777) == "0o600", oct(os.stat(kept).st_mode)
        assert open(broken_settings).read() == "{\"c\": 3}", f"{label}: new content not written"
        print(f"ok corrupt settings.json ({label}): copy kept with exact bytes, mode 0600, new content written")

    # good JSON object: no copy
    for old in copies():
        os.unlink(os.path.join(broken_dir, old))
    with open(broken_settings, "w") as f:
        f.write("{\"a\": 1}")
    expect_ok("good settings.json: write", call("write_setting_file", {"name": "settings.json", "text": "{\"d\": 4}"}))
    assert copies() == [], f"good file was copied: {copies()}"
    assert open(broken_settings).read() == "{\"d\": 4}"
    print("ok good settings.json: no copy")

    # two corrupt writes in the same (frozen) second: distinct copies, -1 suffix on collision
    with open(broken_settings, "w") as f:
        f.write("{bad one")
    expect_ok("corrupt twice (first)", call("write_setting_file", {"name": "settings.json", "text": "{\"e\": 5}"}))
    with open(broken_settings, "w") as f:
        f.write("{bad two")
    expect_ok("corrupt twice (second)", call("write_setting_file", {"name": "settings.json", "text": "{\"f\": 6}"}))
    assert copies() == ["settings.json.broken-20261010-120000", "settings.json.broken-20261010-120000-1"], copies()
    assert open(os.path.join(broken_dir, copies()[0]), "rb").read() == b"{bad one", "first copy changed"
    assert open(os.path.join(broken_dir, copies()[1]), "rb").read() == b"{bad two", "second copy wrong"
    assert open(broken_settings).read() == "{\"f\": 6}"
    print("ok two corrupt writes in one second: two distinct copies")

    # conduct.txt is never copied, even when corrupt
    with open(os.path.join(broken_dir, "conduct.txt"), "w") as f:
        f.write("{not json")
    before = copies()
    expect_ok("conduct.txt write: no copy", call("write_setting_file", {"name": "conduct.txt", "text": "kind\n"}))
    assert copies() == before, "conduct.txt write made a copy"
    print("ok conduct.txt: no copy")

    # symlinked settings.json: no copy, the link is replaced as before, outside file untouched
    for old in copies():
        os.unlink(os.path.join(broken_dir, old))
    outside_bad = os.path.join(tmp, "outside-bad.json")
    with open(outside_bad, "w") as f:
        f.write("{outside bad")
    os.unlink(broken_settings)
    os.symlink(outside_bad, broken_settings)
    expect_ok("symlinked settings.json: write", call("write_setting_file", {"name": "settings.json", "text": "{\"g\": 7}"}))
    assert copies() == [], f"symlink target was copied: {copies()}"
    assert not os.path.islink(broken_settings) and open(broken_settings).read() == "{\"g\": 7}"
    assert open(outside_bad).read() == "{outside bad", "symlink target changed"
    print("ok symlinked settings.json: no copy, outside file untouched")
finally:
    rootd.datetime = real_datetime
    rootd.ETC_ROOT = etc

# --- write_hosts
hosts_root = os.path.join(tmp, "hostsroot")
os.makedirs(os.path.join(hosts_root, "etc"))
rootd.ETC_ROOT = hosts_root
hosts_path = os.path.join(hosts_root, "etc", "hosts")
# The formats written by system.py (full-line markers) and everyday.py (inline "# llmos focus mode"), plus IPv6 and tabs.
realistic = (
    "# Host Database\n"
    "# localhost is used to configure the loopback interface\n"
    "127.0.0.1\tlocalhost\n"
    "127.0.1.1 kitchen-pc\n"
    "::1 localhost ip6-localhost ip6-loopback\n"
    "# llmos-focus begin\n"
    "0.0.0.0 youtube.com\n"
    "0.0.0.0 www.youtube.com\n"
    "# llmos-focus end\n"
    "0.0.0.0 reddit.com # llmos focus mode\n"
    "0.0.0.0\twikipedia.org\n"
)
expect_ok("write_hosts realistic file", call("write_hosts", {"text": realistic}))
assert open(hosts_path).read() == realistic, "hosts text was not written as sent"
assert oct(os.stat(hosts_path).st_mode & 0o777) == "0o644", oct(os.stat(hosts_path).st_mode)
assert sorted(os.listdir(os.path.join(hosts_root, "etc"))) == ["hosts"], os.listdir(os.path.join(hosts_root, "etc"))
expect_ok("write_hosts replaces the file", call("write_hosts", {"text": "127.0.0.1 localhost\n"}))
assert open(hosts_path).read() == "127.0.0.1 localhost\n"
rejected_hosts = {
    "shell metacharacters": "127.0.0.1 localhost; rm -rf /\n",
    "url instead of name": "127.0.0.1 localhost\n0.0.0.0 https://x.com\n",
    "bad ip": "127.0.0.1 localhost\n999.1.1.1 x.com\n",
    "ip only": "127.0.0.1 localhost\n0.0.0.0\n",
    "label too long": "127.0.0.1 localhost\n0.0.0.0 " + "a" * 64 + ".com\n",
    "name starts with dash": "127.0.0.1 localhost\n0.0.0.0 -x.com\n",
    "carriage return": "127.0.0.1 localhost\r\n",
    "nul byte": "127.0.0.1 localhost\n0.0.0.0 x.com\x00\n",
    "no localhost": "0.0.0.0 youtube.com\n",
    "localhost on other ip": "10.0.0.1 localhost\n",
    "zone id": "127.0.0.1 localhost\nfe80::1%eth0 x.com\n",
}
for label, text in rejected_hosts.items():
    expect_err(f"write_hosts rejects {label}", call("write_hosts", {"text": text}), "bad args")
assert open(hosts_path).read() == "127.0.0.1 localhost\n", "a rejected write changed /etc/hosts"
expect_err("write_hosts line number", call("write_hosts", {"text": "127.0.0.1 localhost\n0.0.0.0 https://x.com\n"}), "bad args: hosts line 2")
expect_err("write_hosts no localhost msg", call("write_hosts", {"text": "0.0.0.0 youtube.com\n"}), "must keep localhost")
expect_err("write_hosts text not str", call("write_hosts", {"text": ["127.0.0.1 localhost"]}), "bad args")
expect_err("write_hosts args not dict", json.loads(rootd.handle(b'{"verb":"write_hosts","args":"x"}')), "bad args")
try:
    rootd.write_hosts({"text": "127.0.0.1 localhost\n#" + "x" * (2 * 1024 * 1024)})
    raise AssertionError("2 MiB hosts accepted")
except ValueError as e:
    assert "too large" in str(e), e
    print(f"ok write_hosts 2 MiB rejected: {e}")
exact = "127.0.0.1 localhost\n"
exact += "#" + "x" * (rootd.MAX_HOSTS - len(exact.encode()) - 2) + "\n"
assert len(exact.encode()) == rootd.MAX_HOSTS, len(exact.encode())
assert rootd.write_hosts({"text": exact}) == "ok"
assert open(hosts_path).read() == exact
print("ok write_hosts 1 MiB accepted (direct call)")
# symlinked etc: refused, nothing outside touched
hosts_link_root = os.path.join(tmp, "hostslinkroot")
os.makedirs(hosts_link_root)
hosts_outside_etc = os.path.join(tmp, "hosts-outside-etc")
os.makedirs(hosts_outside_etc)
os.symlink(hosts_outside_etc, os.path.join(hosts_link_root, "etc"))
rootd.ETC_ROOT = hosts_link_root
try:
    expect_refused("symlinked etc: write_hosts refused", call("write_hosts", {"text": "127.0.0.1 localhost\n"}))
finally:
    rootd.ETC_ROOT = etc
assert os.listdir(hosts_outside_etc) == [], "write_hosts wrote through a symlinked etc"
print("ok write_hosts: symlinked etc refused, outside folder untouched")

# --- serve over a real socket, in a thread
sock_dir = tempfile.mkdtemp(prefix="rs-", dir="/tmp")
sock_path = os.path.join(sock_dir, "root.sock")
t = threading.Thread(target=rootd.serve, args=(sock_path, "no-such-group-xyz"), daemon=True)
t.start()
# bind() creates the path before listen(), so retry the connect until the server is really listening
c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
for _ in range(100):
    try:
        c.connect(sock_path)
        break
    except (FileNotFoundError, ConnectionRefusedError):
        time.sleep(0.05)
else:
    raise AssertionError("socket never listened")
assert oct(os.stat(sock_path).st_mode & 0o777) == "0o600", oct(os.stat(sock_path).st_mode)
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
