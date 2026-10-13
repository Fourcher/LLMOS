#!/usr/bin/env python3
"""Host-side test of the internet disclosure for the "yes" choice. With internet = "yes" the desk syncs the clock
with pool.ntp.org about 20 s after every start (desk.py boot timer -> system.sync_time(automatic=True)), so the
wording must say the internet is also used to keep the clock right.
Checks: (1) w_net_yes_d in every language block mentions the clock (EN clock, ES reloj, FR horloge, DE Uhr,
JA 時計, ZH 时钟); (2) the privacy answer in desk.py mentions the clock; (3) system.sync_time(automatic=True)
returns early unless internet == "yes" (settings and subprocess patched, no real ntpd, no network).
Run: python3 tools/test-net-disclosure.py"""
import os
import re
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTFS = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos")
LLMOS_DIR = os.path.join(ROOTFS, "llmos")
DESK = os.path.join(LLMOS_DIR, "desk.py")
sys.path.insert(0, ROOTFS)
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


import llmos.i18n as i18n  # noqa: E402

CLOCK_WORDS = {
    "EN": "clock",
    "ZH": "时钟",
    "ES": "reloj",
    "FR": "horloge",
    "DE": "Uhr",
    "JA": "時計",
}
for b, word in CLOCK_WORDS.items():
    text = getattr(i18n, b).get("w_net_yes_d", "")
    check(word in text, f"{b}: w_net_yes_d mentions the clock ({word!r}): {text}")

src = open(DESK, encoding="utf-8").read()
m = re.search(r'"Something goes online only when a request needs it:[^"]*"', src)
check(m is not None and "clock" in m.group(0), "desk.py: the 'yes' privacy answer mentions the clock")

# system.sync_time(automatic=True): settings, subprocess and the root call are stubbed, so nothing touches ntpd
import llmos.config as config  # noqa: E402
import llmos.system as system  # noqa: E402

calls = []
real_run = subprocess.run
real_which = system.__dict__.get("shutil")
old_settings = config.settings
old_root = system._sync_time_root
old_geteuid = os.geteuid
import shutil as _shutil  # noqa: E402
old_which = _shutil.which


def fake_run(*a, **k):
    calls.append(("subprocess", a))
    return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")


def fake_root():
    calls.append(("root",))
    return True


subprocess.run = fake_run
system._sync_time_root = fake_root
os.geteuid = lambda: 0
_shutil.which = lambda name, *a, **k: "/bin/ntpd" if name == "ntpd" else old_which(name, *a, **k)
try:
    for setting, expect in (("yes", True), ("ask", False), ("no", False)):
        calls.clear()
        config.settings = {"internet": setting}
        result = system.sync_time(automatic=True)
        ran = len(calls) > 0
        check(ran == expect and (not expect or result is True),
              f'sync_time(automatic=True) with internet={setting!r}: ' + ("runs the sync" if ran else "returns early"))
finally:
    subprocess.run = real_run
    system._sync_time_root = old_root
    os.geteuid = old_geteuid
    _shutil.which = old_which
    config.settings = old_settings

print("all good" if fails == 0 else f"{fails} FAIL")
sys.exit(1 if fails else 0)
