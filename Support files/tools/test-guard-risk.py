#!/usr/bin/env python3
"""Host-side test of the risk class for change_setting "guard_untrusted" (tools._policy_risk).
Switching the web-page / email / file check OFF is loosening, so it is SECURITY while the check is on: a turn that
read text the owner did not write then gets asked first. Turning it ON, or turning off an already-off check, is SAFE.
Under full trust (hands-off) the owner's own request is not asked about (agent.needs_confirm(SECURITY) is False).
Run: python3 tools/test-guard-risk.py (no model, no VM). Exit status 0 = pass."""
import os
import sys
import tempfile
from unittest import mock

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import agent, config, tools  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("ok " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


class Settings:
    """Stands in for config.settings: a plain dict."""

    def __init__(self, **values):
        self.values = dict(values)

    def all(self):
        return dict(self.values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def risk_with(values, setting, value):
    with mock.patch.object(config, "settings", Settings(**values)):
        return tools._policy_risk(setting, value)


check(risk_with({"guard_untrusted": True}, "guard_untrusted", "off") == tools.SECURITY,
      "guard_untrusted off while currently on -> SECURITY")
check(risk_with({"guard_untrusted": False}, "guard_untrusted", "off") == tools.SAFE,
      "guard_untrusted off while already off -> SAFE")
check(risk_with({"guard_untrusted": True}, "guard_untrusted", "on") == tools.SAFE,
      "guard_untrusted on while currently on -> SAFE")
check(risk_with({"guard_untrusted": False}, "guard_untrusted", "on") == tools.SAFE,
      "guard_untrusted on while currently off -> SAFE")
check(risk_with({}, "guard_untrusted", "off") == tools.SECURITY,
      "guard_untrusted off with no setting stored (default on) -> SECURITY")
check(risk_with({"guard_untrusted": True}, "guard_untrusted", "don't check web pages") == tools.SECURITY,
      "'don't check web pages' reads as off -> SECURITY")
check(risk_with({"guard_untrusted": True}, "guard_untrusted", "stop") == tools.SECURITY,
      "'stop' reads as off -> SECURITY")

# _guard_on reads the RAW value: False/0/"off" mean off, None/True/"on" mean on
for raw, want in ((False, "off"), (0, "off"), (None, "on"), (True, "on"), ("off", "off"), ("on", "on")):
    got = "on" if tools._guard_on(raw) else "off"
    check(got == want, f"_guard_on({raw!r}) -> {want}")
check(risk_with({"guard_untrusted": True}, "guard_untrusted", False) == tools.SECURITY,
      "_policy_risk guard_untrusted False (raw) with check on -> SECURITY")
check(risk_with({"autonomy": "hands-off"}, "autonomy", "hands-on") == tools.SAFE,
      "_policy_risk autonomy hands-on while currently hands-off -> SAFE (unchanged)")

# the gate: under full trust the owner's own request runs unasked; a tainted turn asks (the gate uses SECURITY)
with mock.patch.object(config, "settings", Settings(autonomy="hands-off")):
    check(agent.needs_confirm(tools.SECURITY) is False,
          "hands-off: needs_confirm(SECURITY) is False (owner's own turn is not asked)")
with mock.patch.object(config, "settings", Settings(autonomy="balanced")):
    check(agent.needs_confirm(tools.SECURITY) is True,
          "balanced: needs_confirm(SECURITY) is True (a tainted turn is asked via the taint check)")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
