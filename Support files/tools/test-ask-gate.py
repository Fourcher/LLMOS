#!/usr/bin/env python3
"""Host-side test for the keyword gate in agent.execute: a call the gate does not match ("you did not ask for X")
is no longer refused when an owner is there to ask. It goes through the confirmation (balanced), runs without
asking under hands-off, and is still refused for scheduled tasks (headless ctx) and when there is no confirm callback.
Run: python3 tools/test-ask-gate.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, agent, config

failures = []


def check(label, got, want):
    if got == want:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


class FakeSettings:
    """In-memory stand-in: the real Settings.set writes the owner's config file."""
    def __init__(self, autonomy):
        self.d = {"autonomy": autonomy}

    def get(self, key, default=None):
        return self.d.get(key, default)


class FakeCtx:
    headless = False
    tainted = False

    def __init__(self, request, answer=True):
        self.current_request = request
        self.answer = answer
        self.asked = []
        self.after_turn = None

    def confirm_action(self, tool, args, risk):
        self.asked.append(tool.name)
        return self.answer

    def begin_tool(self, tool, args, risk):
        pass

    def end_tool(self, tool, result):
        pass


ran = []


def probe_fn(a, ctx):
    ran.append(a)
    return "probe ran"


# a CHANGE-risk tool the gate knows (only when the request says 'save'): balanced does not ask for CHANGE
tools.REGISTRY["probe_tool"] = tools.Tool("probe_tool", "probe", {}, [], probe_fn, tools.CHANGE)
agent._ONLY_IF_ASKED["probe_tool"] = r"\bsave\b"

real_settings = config.settings
DECLINED = "you declined this (probe_tool)"


def run(autonomy, request, name="probe_tool", args=None, answer=True, headless=False, confirm=True):
    config.settings = FakeSettings(autonomy)
    ran.clear()
    ctx = FakeCtx(request, answer)
    ctx.headless = headless
    if not confirm:
        del FakeCtx.confirm_action            # no confirm callback at all
    try:
        res = agent.execute(ctx, name, args or {})
    finally:
        if not confirm:
            FakeCtx.confirm_action = _confirm
        config.settings = real_settings
    return res, ctx


def _confirm(self, tool, args, risk):
    self.asked.append(tool.name)
    return self.answer


FakeCtx.confirm_action = _confirm

try:
    # gate hit: keyword present, balanced does not confirm CHANGE -> runs, no question
    res, c = run("balanced", "save this for me")
    check("gate hit runs without asking", (res, c.asked, len(ran)), ("probe ran", [], 1))

    # gate miss, balanced: the owner is asked; approve -> runs
    res, c = run("balanced", "what's the weather", answer=True)
    check("gate miss balanced asks", c.asked, ["probe_tool"])
    check("gate miss balanced approved runs", (res, len(ran)), ("probe ran", 1))

    # gate miss, balanced: decline -> does not run, existing declined result
    res, c = run("balanced", "what's the weather", answer=False)
    check("gate miss balanced asks (declined)", c.asked, ["probe_tool"])
    check("gate miss balanced declined does not run", (res, len(ran)), (DECLINED + ". Do not retry it; continue or stop.", 0))

    # gate miss, hands-off (full trust): runs, no question
    res, c = run("hands-off", "what's the weather")
    check("gate miss hands-off runs without asking", (res, c.asked, len(ran)), ("probe ran", [], 1))

    # scheduled task (headless): gate miss still refused as before, nothing asked, nothing run
    res, c = run("balanced", "what's the weather", headless=True)
    check("scheduled gate miss refused", (str(res).startswith("not done: you did not ask for 'probe_tool'"), c.asked, len(ran)),
          (True, [], 0))

    # no confirm callback at all: refused as before
    res, c = run("balanced", "what's the weather", confirm=False)
    check("no confirm callback refused", (str(res).startswith("not done: you did not ask for 'probe_tool'"), len(ran)), (True, 0))

    # real system_power (DESTRUCTIVE): a weather question asks under balanced, declined -> not run
    res, c = run("balanced", "what's the weather", name="system_power", args={"action": "shutdown"}, answer=False)
    check("system_power weather balanced asks", c.asked, ["system_power"])
    check("system_power weather balanced declined does not shut down", c.after_turn, None)

    # German request under balanced: the English keyword gate misses it -> asked, not refused
    res, c = run("balanced", "apaga el ordenador", name="system_power", args={"action": "shutdown"}, answer=False)
    check("apaga el ordenador balanced asks", c.asked, ["system_power"])

    # hands-off: the same weather question runs without asking (the owner's choice)
    res, c = run("hands-off", "what's the weather", name="system_power", args={"action": "shutdown"})
    check("system_power weather hands-off runs", (c.asked, c.after_turn), ([], "poweroff"))
except AssertionError as e:
    print(f"FAIL {e}")
    failures.append(str(e))
finally:
    config.settings = real_settings
    tools.REGISTRY.pop("probe_tool", None)
    agent._ONLY_IF_ASKED.pop("probe_tool", None)

if failures:
    print(f"FAILED: {len(failures)}")
    sys.exit(1)
print("all good")
