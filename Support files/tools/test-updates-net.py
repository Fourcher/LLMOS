#!/usr/bin/env python3
"""Host-side test of the internet gate in syspanels.updates_check: under "yes" apk runs; under "no" no apk runs and
the owner gets the switched-off text; under "ask" no apk runs unless the owner asked (asked=True). system.apk_update
and system.apk_upgrade are patched and record every call: no network, no apk, no VM.
Run: python3 tools/test-updates-net.py"""
import os
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import config, syspanels, system  # noqa: E402

fails = 0
OFF = "The internet is off in Settings, so I can't check for updates."
ASK = "Say “check for updates” to look online."
UPG = "Upgrading musl (1.2.4-r1 -> 1.2.5-r0)\n"


class Settings:
    def __init__(self, internet):
        self.values = {"internet": internet}

    def get(self, key, default=None):
        return self.values.get(key, default)


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


def run(internet, **kw):
    """Returns (result, apk_update mock, apk_upgrade mock) for one updates_check call under the given setting."""
    with mock.patch.object(config, "settings", Settings(internet)), \
            mock.patch.object(system, "apk_update", return_value=(0, "", "")) as upd, \
            mock.patch.object(system, "apk_upgrade", return_value=(0, UPG, "")) as upg:
        res = syspanels.updates_check(**kw)
    return res, upd, upg


# yes: apk runs, result unchanged
res, upd, upg = run("yes")
check(upd.called and upg.called and res == ([("musl", "1.2.4-r1", "1.2.5-r0")], ""),
      f"yes: apk runs and returns the list: {res!r}")

res, upd, upg = run("yes", asked=True)
check(upd.called and upg.called and res[1] == "", f"yes with asked=True: apk runs: {res!r}")

# no: no apk call, switched-off text, same (None, text) shape
res, upd, upg = run("no")
check(not upd.called and not upg.called and res == (None, OFF),
      f"no: no apk call and the switched-off text: {res!r}")

res, upd, upg = run("no", asked=True)
check(not upd.called and not upg.called and res == (None, OFF),
      f"no with asked=True: still no apk call: {res!r}")

# ask: no apk call unless asked
res, upd, upg = run("ask")
check(not upd.called and not upg.called and res == (None, ASK),
      f"ask (not asked): no apk call and the look-online text: {res!r}")

res, upd, upg = run("ask", asked=True)
check(upd.called and upg.called and res[1] == "" and res[0] == [("musl", "1.2.4-r1", "1.2.5-r0")],
      f"ask with asked=True: apk runs and returns the list: {res!r}")

# default parameter is asked=False
res, upd, upg = run("ask", asked=False)
check(not upd.called and res == (None, ASK), f"ask with asked=False explicit: no apk call: {res!r}")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
