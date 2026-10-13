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

# updates_panel: asked=True under "ask" runs apk and returns the normal panel; default under "ask" returns the look-online text
def panel_run(internet, **kw):
    with mock.patch.object(config, "settings", Settings(internet)), \
            mock.patch.object(system, "apk_update", return_value=(0, "", "")) as upd, \
            mock.patch.object(system, "apk_upgrade", return_value=(0, UPG, "")) as upg:
        p = syspanels.updates_panel(**kw)
    return p, upd, upg


p, upd, upg = panel_run("ask", asked=True)
texts = [b.get("text", "") for b in p["blocks"] if b.get("type") == "text"]
check(upd.called and upg.called and p["id"] == "panel-updates" and "1 update(s) available." in texts,
      f"ask with updates_panel(asked=True): apk runs and the normal panel: {texts!r}")

p, upd, upg = panel_run("ask")
texts = [b.get("text", "") for b in p["blocks"] if b.get("type") == "text"]
check(not upd.called and not upg.called and texts == [ASK],
      f"ask with updates_panel(): no apk call and the look-online text: {texts!r}")

# desk route: the owner's explicit "check for updates" (desk.py _system_shortcut, the self._SYS loop) must call
# updates_panel(asked=True), so under "ask" it goes online. The loop is taken from desk.py by ast (desk needs GTK);
# syspanels, threading and the window call are stubs that record.
import ast  # noqa: E402
import re  # noqa: E402
import types  # noqa: E402

DESK = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
tree = ast.parse(open(DESK, encoding="utf-8").read())
desk_cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Desk")
sys_list = next(n for n in desk_cls.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_SYS" for t in n.targets))
shortcut = next(n for n in desk_cls.body if isinstance(n, ast.FunctionDef) and n.name == "_system_shortcut")
route = next(n for n in ast.walk(shortcut) if isinstance(n, ast.For) and ast.unparse(n.iter) == "self._SYS")
print("desk route")
calls = []


def updates_panel_rec(**kw):
    calls.append(kw)
    return syspanels.updates_panel(**kw)          # real panel: apk is still stubbed above


def stub(name):
    return lambda: name


stub_sys = types.SimpleNamespace(processes=stub("p"), drives=stub("d"), displays=stub("s"), bluetooth=stub("b"),
                                 printers=stub("pr"), about=stub("a"), input_panel=stub("i"), storage=stub("st"),
                                 updates_panel=lambda **kw: updates_panel_rec(**kw))


class FakeThread:                                  # runs the target at once, so the route's lambda is called here
    def __init__(self, target, daemon=False):
        self.target = target

    def start(self):
        self.target()


ns = {"re": re, "syspanels": stub_sys, "threading": types.SimpleNamespace(Thread=FakeThread), "os": os}
exec(compile(ast.Module(body=[sys_list], type_ignores=[]), DESK, "exec"), ns)


class Route:
    _SYS = ns["_SYS"]

    def __init__(self):
        self.opened = []
        self.last_reply = self._said = None

    def open_window(self, w):
        self.opened.append(w)


route_src = "def route_fn(self, low, line):\n    " + ast.unparse(route).replace("\n", "\n    ") + "\n    return False\n"


def run_route(low, internet):
    calls.clear()
    r = Route()
    ns_route = {"re": re, "syspanels": stub_sys, "threading": types.SimpleNamespace(Thread=FakeThread), "os": os}
    exec(route_src, ns_route)
    with mock.patch.object(config, "settings", Settings(internet)), \
            mock.patch.object(system, "apk_update", return_value=(0, "", "")) as upd, \
            mock.patch.object(system, "apk_upgrade", return_value=(0, UPG, "")) as upg:
        ns_route["route_fn"](r, low, low)
    return r, upd, upg


r, upd, upg = run_route("check for updates", "ask")
check(calls == [{"asked": True}], f"desk 'check for updates' under ask: updates_panel(asked=True): {calls!r}")
check(upd.called and upg.called, "desk 'check for updates' under ask: apk runs (goes online)")
check(r.opened and r.opened[0]["id"] == "panel-updates", "desk 'check for updates' under ask: the Updates panel opens")

r, upd, upg = run_route("updates", "no")
check(calls == [{"asked": True}] and not upd.called and r.opened and r.opened[0]["blocks"][0]["text"] == OFF,
      f"desk 'updates' under no: still no apk call, the switched-off text: {r.opened[0]['blocks'][0]['text'] if r.opened else None!r}")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
