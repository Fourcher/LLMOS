#!/usr/bin/env python3
"""Host-side test: a desk button that restarts or shuts down (the installer's "Restart now", the power panel's
Restart / Shut down) really does it. Before the fix the button path ran system_power, which only marks the action
for "after this reply", and nothing ever carried it out: the screen said it would restart and nothing happened.
The desk is a Desk.__new__ stub; shutdown() is recorded instead of run.
Run: python3 tools/test-button-power.py  (exit status 0 = pass)"""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent, desk, intent  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


class Ctx(desk.DeskCtx):
    """The desk's real context; the owner answers yes when the power tool asks."""

    def confirm_action(self, *a, **k):
        return True

    def confirm_network(self, *a, **k):
        return True


def make_desk():
    d = desk.Desk.__new__(desk.Desk)
    d.events, d.shutdowns, d.queued = [], [], []
    d.ctx = Ctx(d)
    d.emit = d.events.append
    d.shutdown = d.shutdowns.append
    d._enqueue = lambda text, done, chat: d.queued.append(text)
    d.last_active = 0
    return d


for words, want in (("restart the computer", "reboot"), ("restart", "reboot"), ("shut down", "poweroff")):
    m = intent.match(words)
    if not m or m[0] != "system_power":
        check(f"'{words}' is the power tool", False, f"intent.match -> {m!r}")
        continue
    d = make_desk()
    d._instant = lambda text: True
    d.shortcut = lambda text: False
    real_execute = agent.execute
    try:
        d.act(words)
    finally:
        agent.execute = real_execute
    check(f"button '{words}' carries out {want}", d.shutdowns == [want], f"shutdowns={d.shutdowns} queued={d.queued} events={d.events}")
    check(f"button '{words}' leaves nothing pending", d.ctx.after_turn is None)

# a button that is not about power never powers anything off
d = make_desk()
d._instant = lambda text: True
d.shortcut = lambda text: True
d.__dict__["_said"] = "Done."
d.act("settings")
check("a non-power button does not power off", d.shutdowns == [])

print("all good" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
