#!/usr/bin/env python3
"""Host-side test of system.sync_time(): the boot timer (automatic=True) obeys internet == "yes" only;
the owner's own ask (automatic=False) keeps the old rule (skip only on "no"). No clock is touched.
Run: python3 tools/test-sync-time.py"""
import os
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import config, rootd, rootd_client, system  # noqa: E402

DESK = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


def run(internet, automatic):
    """Return (result, list of subprocess argv calls) for one sync_time call with the given setting."""
    calls = []

    def fake_run(argv, **kw):
        calls.append(list(argv))
        return mock.Mock(returncode=0)

    with mock.patch.object(config.settings, "get", side_effect=lambda k, d=None: internet if k == "internet" else d), \
         mock.patch("shutil.which", return_value="/sbin/ntpd"), \
         mock.patch("subprocess.run", side_effect=fake_run), \
         mock.patch("os.geteuid", return_value=0):
        result = system.sync_time(automatic=automatic)
    return result, calls


r, calls = run("ask", True)
check(r is False and calls == [], 'automatic=True, internet "ask": no subprocess call, returns False')
r, calls = run("no", True)
check(r is False and calls == [], 'automatic=True, internet "no": no subprocess call, returns False')
r, calls = run("yes", True)
check(any(c[:1] == ["ntpd"] and "pool.ntp.org" in c for c in calls),
      'automatic=True, internet "yes": ntpd argv recorded %s' % calls[:1])
r, calls = run("ask", False)
check(any(c[:1] == ["ntpd"] for c in calls), 'automatic=False, internet "ask": ntpd runs')
r, calls = run("no", False)
check(r is False and calls == [], 'automatic=False, internet "no": no subprocess call')

def run_as(uid, internet, automatic=False, rootd_reply=None, rootd_error=None):
    """Run sync_time as uid. Return (result, subprocess argv calls, rootd call mock)."""
    calls = []

    def fake_run(argv, **kw):
        calls.append(list(argv))
        return mock.Mock(returncode=0)

    with mock.patch.object(config.settings, "get", side_effect=lambda k, d=None: internet if k == "internet" else d), \
         mock.patch("shutil.which", return_value="/sbin/ntpd"), \
         mock.patch("subprocess.run", side_effect=fake_run), \
         mock.patch("os.geteuid", return_value=uid), \
         mock.patch.object(rootd_client, "call", side_effect=rootd_error if rootd_error else None,
                           return_value=rootd_reply) as rc:
        result = system.sync_time(automatic=automatic)
    return result, calls, rc


# root path: the two commands run in-process, no rootd call
r, calls, rc = run_as(0, "yes")
check(r is True and calls == [["ntpd", "-q", "-n", "-p", "pool.ntp.org"], ["hwclock", "-w", "-u"]] and not rc.called,
      "root: ntpd then hwclock run in-process, no rootd call, returns True")

# non-root path: rootd call with _timeout=60, returns its bool
r, calls, rc = run_as(1000, "yes", rootd_reply="true")
check(r is True and calls == [] and rc.call_args == mock.call("sync_time", _timeout=60),
      "non-root: rootd sync_time called with _timeout=60, no local subprocess, returns True")
r, calls, rc = run_as(1000, "yes", rootd_reply="false")
check(r is False and rc.called, "non-root: rootd reply false returns False")

# RootdError -> False
r, calls, rc = run_as(1000, "yes", rootd_error=rootd_client.RootdError("busy"))
check(r is False and calls == [], "non-root: RootdError returns False")

# caller-side internet rules still apply before rootd is called
r, calls, rc = run_as(1000, "no")
check(r is False and not rc.called, 'non-root, internet "no": rootd not called, returns False')

# rootd verb: rejects arguments
for bad in ({"server": "evil.example"}, {"x": 1}):
    try:
        rootd.VERBS["sync_time"](bad)
        check(False, "verb rejects args %s" % bad)
    except ValueError as e:
        check("bad args" in str(e), "verb rejects args %s: %s" % (bad, e))

# rootd verb: internet "no" -> false, ntpd never runs
calls = []
with mock.patch.object(config.settings, "get", side_effect=lambda k, d=None: "no" if k == "internet" else d), \
     mock.patch("subprocess.run", side_effect=lambda argv, **kw: calls.append(list(argv)) or mock.Mock(returncode=0)):
    out = rootd.VERBS["sync_time"]({})
check(out == "false" and calls == [], 'verb with internet "no": returns "false", no ntpd run')

# rootd verb: internet "yes" -> runs the root helper and returns its bool
with mock.patch.object(config.settings, "get", side_effect=lambda k, d=None: "yes" if k == "internet" else d), \
     mock.patch("subprocess.run", side_effect=lambda argv, **kw: mock.Mock(returncode=0)), \
     mock.patch("shutil.which", return_value="/sbin/ntpd"):
    out = rootd.VERBS["sync_time"]({})
check(out == "true", 'verb with internet "yes": returns "true" when ntpd succeeds')

with open(DESK, encoding="utf-8") as f:
    lines = f.read().splitlines()
boot = [i for i, l in enumerate(lines) if "GLib.timeout_add_seconds(20" in l and "sync_time" in l]
check(bool(boot) and "automatic=True" in lines[boot[0]],
      "desk.py boot timer line passes automatic=True")

print("all good" if fails == 0 else "%d FAILED" % fails)
sys.exit(1 if fails else 0)
