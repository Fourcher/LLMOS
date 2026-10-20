#!/usr/bin/env python3
"""Host-side test of syspanels.py callers of system.apk_update / apk_upgrade / clear_apk_cache: updates_check,
updates_apply and clear_caches keep their return shapes and owner-facing texts. system.* is patched; no apk runs,
no VM, no real files (LLMOS_HOME points at a temp dir). Run: python3 tools/test-update-callers.py"""
import os
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos"))

from llmos import syspanels, system  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


home = tempfile.mkdtemp(prefix="llmos-test-home-")
os.environ["LLMOS_HOME"] = home
cache = os.path.join(home, ".cache")
os.makedirs(os.path.join(cache, "sub"))
with open(os.path.join(cache, "a.bin"), "wb") as f:
    f.write(b"x" * 10)
with open(os.path.join(cache, "sub", "b.bin"), "wb") as f:
    f.write(b"y" * 20)

UPG = "Upgrading musl (1.2.4-r1 -> 1.2.5-r0)\nUpgrading busybox (1.36.0 -> 1.37.0)\n"

# ---- updates_check
with mock.patch.object(system, "apk_update", return_value=(0, "", "")) as upd, \
        mock.patch.object(system, "apk_upgrade", return_value=(0, UPG, "")) as upg:
    pk, err = syspanels.updates_check()
    check(pk == [("musl", "1.2.4-r1", "1.2.5-r0"), ("busybox", "1.36.0", "1.37.0")] and err == "",
          f"updates_check success returns list and empty error: {pk!r}, {err!r}")
    check(upd.call_args == mock.call() and upg.call_args == mock.call(simulate=True),
          f"updates_check calls apk_update() then apk_upgrade(simulate=True): {upd.call_args}, {upg.call_args}")

with mock.patch.object(system, "apk_update", return_value=(0, "", "")), \
        mock.patch.object(system, "apk_upgrade", return_value=(0, "OK: 5 MiB\n", "")):
    pk, err = syspanels.updates_check()
    check(pk == [] and err == "", f"updates_check nothing to upgrade returns ([], ''): {pk!r}, {err!r}")

with mock.patch.object(system, "apk_update", return_value=(1, "", "bad gateway\n")), \
        mock.patch.object(system, "apk_upgrade") as upg:
    pk, err = syspanels.updates_check()
    check(pk is None and err == "bad gateway" and not upg.called,
          f"updates_check update failure returns (None, stripped err) and skips upgrade: {pk!r}, {err!r}")

with mock.patch.object(system, "apk_update", return_value=(1, "", "")):
    pk, err = syspanels.updates_check()
    check(pk is None and err == "could not reach the update server (is the internet on?)",
          f"updates_check failure with no stderr uses the owner text: {err!r}")

with mock.patch.object(system, "apk_update", return_value=(124, "", "timed out after 120 s")):
    pk, err = syspanels.updates_check()
    check(pk is None and err == "timed out after 120 s", f"updates_check timeout (rc 124) returns (None, err): {err!r}")

# ---- updates_panel still renders from updates_check
with mock.patch.object(system, "apk_update", return_value=(1, "", "")):
    p = syspanels.updates_panel()
    check([b["text"] for b in p["blocks"] if b.get("type") == "text"][0] == "could not reach the update server (is the internet on?)",
          "updates_panel shows the update-server text on failure")

# ---- updates_apply
with mock.patch.object(system, "apk_upgrade", return_value=(0, "Installing linux-lts (6.6)\n", "")) as upg:
    ok, note = syspanels.updates_apply()
    check(ok is True and note == "updates installed; restart to use the new system kernel",
          f"updates_apply success with kernel: {ok!r}, {note!r}")
    check(upg.call_args == mock.call(simulate=False), f"updates_apply calls apk_upgrade(simulate=False): {upg.call_args}")

with mock.patch.object(system, "apk_upgrade", return_value=(0, "Installing busybox\n", "")):
    ok, note = syspanels.updates_apply()
    check(ok is True and note == "updates installed", f"updates_apply success without kernel: {ok!r}, {note!r}")

with mock.patch.object(system, "apk_upgrade", return_value=(1, "", "ERROR: disk full\n")):
    ok, note = syspanels.updates_apply()
    check(ok is False and note == "ERROR: disk full", f"updates_apply failure uses stderr: {ok!r}, {note!r}")

with mock.patch.object(system, "apk_upgrade", return_value=(1, "partial output\n", "")):
    ok, note = syspanels.updates_apply()
    check(ok is False and note == "partial output", f"updates_apply failure with no stderr uses stdout: {ok!r}, {note!r}")

with mock.patch.object(system, "apk_upgrade", return_value=(124, "", "timed out after 1800 s")):
    ok, note = syspanels.updates_apply()
    check(ok is False and note == "timed out after 1800 s", f"updates_apply timeout returns (False, err): {note!r}")

# ---- clear_caches
with mock.patch.object(system, "clear_apk_cache", return_value=(100, "cleared 100 bytes of apk cache")) as clr:
    msg = syspanels.clear_caches()
    check(msg == "cleared " + syspanels._human(30 + 100) + " of caches" and msg == "cleared 130 B of caches",
          f"clear_caches adds apk freed bytes to ~/.cache total: {msg!r}")
    check(clr.call_count == 1 and clr.call_args == mock.call(), f"clear_caches calls clear_apk_cache() once: {clr.call_args}")
    check(not os.path.exists(os.path.join(cache, "a.bin")) and not os.path.exists(os.path.join(cache, "sub")),
          "clear_caches still empties ~/.cache")

with open(os.path.join(cache, "c.bin"), "wb") as f:
    f.write(b"z" * 5)
with mock.patch.object(system, "clear_apk_cache", return_value=(0, "it took too long")):
    msg = syspanels.clear_caches()
    check(msg == "cleared 5 B of caches", f"clear_caches with apk failure reports only ~/.cache: {msg!r}")

with mock.patch.object(system, "clear_apk_cache", return_value=(0, "cleared 0 bytes of apk cache")):
    msg = syspanels.clear_caches()
    check(msg == "cleared 0 B of caches", f"clear_caches with nothing to free: {msg!r}")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
