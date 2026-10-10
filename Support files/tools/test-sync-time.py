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
from llmos import config, system  # noqa: E402

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
         mock.patch("subprocess.run", side_effect=fake_run):
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

with open(DESK, encoding="utf-8") as f:
    lines = f.read().splitlines()
boot = [i for i, l in enumerate(lines) if "GLib.timeout_add_seconds(20" in l and "sync_time" in l]
check(bool(boot) and "automatic=True" in lines[boot[0]],
      "desk.py boot timer line passes automatic=True")

print("all good" if fails == 0 else "%d FAILED" % fails)
sys.exit(1 if fails else 0)
