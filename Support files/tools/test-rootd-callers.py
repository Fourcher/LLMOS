#!/usr/bin/env python3
"""Tests for the first callers of rootd_client: system.set_timezone and everyday's hostname path.

The process is made to look like root (os.geteuid patched to 0), so rootd_client runs the verbs in-process.
rootd's ZONEINFO and ETC_ROOT point at temp dirs. /etc/hosts is redirected to a temp file, and the `hostname`
command is stubbed, so the real machine is not touched.
Run: python3 tools/test-rootd-callers.py"""
import builtins
import os
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import everyday, rootd, rootd_client, system  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

tmp = tempfile.mkdtemp(prefix="rootd-callers-test-")
zoneinfo = os.path.join(tmp, "zoneinfo")
paris = os.path.join(zoneinfo, "Europe", "Paris")
os.makedirs(os.path.dirname(paris))
with open(paris, "wb") as f:
    f.write(b"TZif-fake")
etc = os.path.join(tmp, "root")
os.makedirs(os.path.join(etc, "etc"))
hosts = os.path.join(tmp, "hosts")
with open(hosts, "w") as f:
    f.write(f"127.0.0.1 localhost\n127.0.0.1 {os.uname().nodename}\n")

rootd.ZONEINFO = zoneinfo
rootd.ETC_ROOT = etc
rootd.LOG_PATH = os.path.join(tmp, "log", "rootd.log")
system.ZONEINFO = zoneinfo

# --- stubs: root-looking process, no real TZ change, no real hostname command, /etc/hosts redirected
real_geteuid = os.geteuid
real_apply = system.apply_timezone_env
real_open = builtins.open
real_subprocess = everyday.subprocess
real_call = rootd_client.call
real_find = system.find_timezone
applied = []
ran = []


class FakeSubprocess:
    @staticmethod
    def run(args, **kw):
        ran.append(args)


def fake_open(path, *a, **k):
    if path == "/etc/hosts":
        path = hosts
    return real_open(path, *a, **k)


class Desk:
    def __init__(self):
        self.said = []

    def instant_reply(self, request, text):
        self.said.append(text)


def path(*parts):
    return os.path.join(etc, "etc", *parts)


os.geteuid = lambda: 0
system.apply_timezone_env = lambda: applied.append(True)
everyday.subprocess = FakeSubprocess
builtins.open = fake_open
try:
    # 1. system.set_timezone, chosen by the owner: all three files
    zone = system.set_timezone("Europe/Paris")
    assert zone == "Europe/Paris", zone
    assert os.readlink(path("localtime")) == os.path.realpath(paris), os.readlink(path("localtime"))
    assert real_open(path("timezone")).read() == "Europe/Paris\n"
    assert real_open(path("llmos", "timezone")).read() == "Europe/Paris\n"
    assert applied, "apply_timezone_env not called"
    print("ok system.set_timezone Europe/Paris: localtime, timezone, llmos/timezone written")

    # 2. chosen_by_user=False: /etc/llmos/timezone is skipped
    os.unlink(path("llmos", "timezone"))
    zone = system.set_timezone("Europe/Paris", chosen_by_user=False)
    assert zone == "Europe/Paris", zone
    assert os.readlink(path("localtime")) == os.path.realpath(paris)
    assert not os.path.exists(path("llmos", "timezone")), "chosen_by_user=False wrote the llmos timezone"
    print("ok system.set_timezone chosen_by_user=False: llmos/timezone skipped")

    # 3. unknown zone: the same ValueError as before
    msg = None
    try:
        system.set_timezone("Atlantis/Nowhere")
    except ValueError as e:
        msg = str(e)
    assert msg == "unknown time zone 'Atlantis/Nowhere'", msg
    print(f"ok unknown zone: {msg}")

    # 4. a RootdError from the verb becomes a ValueError with the same text
    system.find_timezone = lambda name: "Europe/Atlantis"
    msg = None
    try:
        system.set_timezone("whatever")
    except ValueError as e:
        msg = str(e)
    assert msg == "bad args: unknown zone", msg
    print(f"ok rootd error mapped to ValueError: {msg}")
    system.find_timezone = real_find

    # 5. everyday hostname: name is normalised, then written through rootd
    desk = Desk()
    assert everyday.hostname(desk, "call this computer kitchen_pc", "call this computer kitchen_pc")
    assert real_open(path("hostname")).read() == "kitchenpc\n", real_open(path("hostname")).read()
    assert ran and ran[-1] == ["hostname", "kitchenpc"], ran
    assert desk.said[-1].startswith("This computer is now called “kitchenpc”"), desk.said
    assert f"127.0.0.1 kitchenpc" in real_open(hosts).read()
    print(f"ok everyday hostname 'kitchen_pc' -> hostname file 'kitchenpc': {desk.said[-1]}")

    desk = Desk()
    assert everyday.hostname(desk, "call this computer kitchen-pc", "call this computer kitchen-pc")
    assert real_open(path("hostname")).read() == "kitchen-pc\n"
    print("ok everyday hostname 'kitchen-pc' written as given")

    # 6. everyday hostname: a RootdError is reported in plain words
    def failing_call(verb, **args):
        raise RootdError("bad args: name")
    rootd_client.call = failing_call
    desk = Desk()
    assert everyday.hostname(desk, "call this computer kitchen-pc", "call this computer kitchen-pc")
    assert desk.said[-1] == "Couldn't rename it: bad args: name.", desk.said
    assert real_open(path("hostname")).read() == "kitchen-pc\n", "a refused call changed the hostname"
    print(f"ok everyday hostname RootdError: {desk.said[-1]}")
finally:
    os.geteuid = real_geteuid
    system.apply_timezone_env = real_apply
    everyday.subprocess = real_subprocess
    builtins.open = real_open
    rootd_client.call = real_call
    system.find_timezone = real_find
    shutil.rmtree(tmp, ignore_errors=True)

print("all good")
