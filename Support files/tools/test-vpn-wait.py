#!/usr/bin/env python3
"""Host-side test of everyday.vpn()'s wait for the OpenVPN tunnel. No VM, no real openvpn or pgrep: subprocess,
time and the net directory are faked, so the timings are exact. Run: python3 tools/test-vpn-wait.py"""
import os
import shutil as _real_shutil
import subprocess as _real_subprocess
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
HOME = tempfile.mkdtemp(prefix="llmos-vpn-test-")
os.makedirs(os.path.join(HOME, "Downloads"))
with open(os.path.join(HOME, "Downloads", "work.ovpn"), "w") as fh:
    fh.write("client\nremote vpn.example.com 1194\n")
os.environ["LLMOS_HOME"] = HOME
from llmos import everyday  # noqa: E402

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

    def emit(self, _msg):
        pass


clock = [0.0]
sleeps = []
calls = []
state = {}


class FakeTime:
    @staticmethod
    def monotonic():
        return clock[0]

    @staticmethod
    def sleep(s):
        sleeps.append(s)
        clock[0] += s
        tun_at = state.get("tun_at")
        if tun_at is not None and not state.get("made") and clock[0] >= tun_at - 1e-9:
            os.makedirs(os.path.join(everyday.NET_DIR, "tun0"))
            state["made"] = True


def fake_run(argv, **kw):
    calls.append(list(argv))
    if argv[0] == "openvpn":
        return _real_subprocess.CompletedProcess(argv, state["rc"], "", state["err"])
    if argv[0] == "pgrep":
        if state["pgrep_raises"]:
            raise OSError("no pgrep here")
        return _real_subprocess.CompletedProcess(argv, 0 if clock[0] < state["alive_until"] else 1, b"", b"")
    raise AssertionError(f"unexpected command {argv}")


class FakeSub:
    run = staticmethod(fake_run)


class FakeShutil:
    which = staticmethod(lambda name: "/usr/sbin/" + name)


real_time, real_sub, real_shutil = everyday.time, everyday.subprocess, everyday.shutil
everyday.time = FakeTime
everyday.subprocess = FakeSub
everyday.shutil = FakeShutil
INF = float("inf")
NET_BASE = tempfile.mkdtemp(prefix="llmos-net-test-")

# name, openvpn rc, openvpn stderr, pgrep alive until (s), tun appears at (s), net dir missing, pgrep raises,
# expect ok, expect elapsed (s), expect reply starts with
CASES = [
    ("tun appears at 0.75 s", 0, "", INF, 0.75, False, False, True, 0.75,
     "Connected to the VPN from work.ovpn"),
    ("openvpn dies at 1 s, no tun", 0, "", 1.0, None, False, False, False, 1.25,
     "The VPN from work.ovpn didn't connect: no answer from its server."),
    ("alive, no tun for 6 s", 0, "", INF, None, False, False, True, 6.0,
     "Connected to the VPN from work.ovpn"),
    ("net dir missing, alive", 0, "", INF, None, True, False, True, 6.0,
     "Connected to the VPN from work.ovpn"),
    ("net dir missing, dies at 1 s", 0, "", 1.0, None, True, False, False, 1.25,
     "The VPN from work.ovpn didn't connect: no answer from its server."),
    ("openvpn exits 1 at once", 1, "AUTH_FAILED", INF, 0.25, False, False, False, 0.0,
     "The VPN from work.ovpn didn't connect: AUTH_FAILED."),
    ("pgrep check fails, tun present", 0, "", INF, 0.5, False, True, False, 6.0,
     "The VPN from work.ovpn didn't connect: no answer from its server."),
]

print("the openvpn wait")
for name, rc, err, alive_until, tun_at, missing, raises, want_ok, want_t, want_text in CASES:
    clock[0] = 0.0
    sleeps.clear()
    calls.clear()
    net = os.path.join(NET_BASE, name.replace(" ", "_").replace(",", ""))
    if not missing:
        os.makedirs(net)
    everyday.NET_DIR = os.path.join(net, "missing") if missing else net
    state.update({"rc": rc, "err": err, "alive_until": alive_until, "tun_at": tun_at, "made": False,
                  "pgrep_raises": raises})
    desk = Desk()
    result = everyday.vpn(desk, "connect to my vpn", "connect to my vpn")
    elapsed = clock[0]
    ov = [c for c in calls if c[0] == "openvpn"]
    check(result is True, f"{name}: answered")
    check(ov == [["openvpn", "--config", os.path.join(HOME, "Downloads", "work.ovpn"), "--daemon", "llmos-vpn"]],
          f"{name}: the openvpn command is unchanged")
    check(abs(elapsed - want_t) < 0.01, f"{name}: took {elapsed:.2f} s (want {want_t} s)")
    if rc != 0:
        check(sleeps == [], f"{name}: no waiting at all when openvpn itself failed")
    check((desk.said or "").startswith(want_text), f"{name}: reply {desk.said!r}")
    check((desk.said or "").startswith("Connected") == want_ok, f"{name}: ok is {want_ok}")

everyday.time, everyday.subprocess, everyday.shutil = real_time, real_sub, real_shutil
for d in (NET_BASE, HOME):
    _real_shutil.rmtree(d, ignore_errors=True)

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
