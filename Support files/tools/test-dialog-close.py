#!/usr/bin/env python3
"""Host test of desk.py dialog cleanup and the Updates refresh after "install the updates".
(1) Desk.decline_dialogs answers every pending ask "no", sets its event, and emits {"t": "dialog.close", "id": did}
for each id, so a declined dialog leaves the screen. (2) Desk.stop_all (the Stop path) calls decline_dialogs.
(3) After "install the updates" the refreshed Updates panel is built with updates_panel(asked=True).
desk needs GTK, so the methods are taken from desk.py by ast and run on a stub object; syspanels, llm and the
threads are stubs that record. No network, no apk, no VM. Run: python3 tools/test-dialog-close.py"""
import ast
import os
import queue
import re
import sys
import threading
import types

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
tree = ast.parse(open(DESK, encoding="utf-8").read())
desk_cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Desk")
fails = 0


def check(cond, label):
    global fails
    if cond:
        print("ok " + label)
    else:
        fails += 1
        print("FAIL " + label)


def method(name):
    return next(n for n in desk_cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


# ---- (1) decline_dialogs on a Desk stub (object.__new__, no GTK) ----
class FakeLLM:
    def __init__(self):
        self.aborted = 0

    def abort(self):
        self.aborted += 1


def methods_from_desk(method_nodes, llm):
    """Compile the given Desk methods (from desk.py) inside a class body and return that class's namespace."""
    out = {}
    cls = ast.ClassDef(name="X", bases=[], keywords=[], body=method_nodes, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), DESK, "exec"),
         {"threading": threading, "queue": queue, "re": re, "llm": llm}, out)
    return out["X"]


class DeskStub:
    pass


def new_stub(llm_obj):
    d = object.__new__(DeskStub)
    d.emitted = []
    d.emit = lambda msg: d.emitted.append(msg)
    d.dialogs = {"d1": [threading.Event(), None, "Empty the trash?", "x"],
                 "d2": [threading.Event(), None, "Delete?", "y"]}
    d.ctx = types.SimpleNamespace(cancel=threading.Event())
    d.requests = queue.Queue()
    d._pending_lock = threading.Lock()
    d._req_pending = 0
    return d


llm_obj = FakeLLM()
DeskStub.decline_dialogs = methods_from_desk([method("decline_dialogs")], llm_obj).decline_dialogs

d = new_stub(llm_obj)
d.decline_dialogs()
check(all(v[1] == "no" for v in d.dialogs.values()) and len(d.dialogs) == 2,
      f"decline_dialogs answers both pending asks 'no' and removes nothing: {[v[1] for v in d.dialogs.values()]}")
check(d.dialogs["d1"][0].is_set() and d.dialogs["d2"][0].is_set(), "decline_dialogs sets both events")
closes = [m for m in d.emitted if m.get("t") == "dialog.close"]
check(closes == [{"t": "dialog.close", "id": "d1"}, {"t": "dialog.close", "id": "d2"}],
      f"decline_dialogs emits dialog.close for d1 and d2: {closes!r}")
check(len(d.emitted) == 2, f"decline_dialogs emits nothing else: {d.emitted!r}")

# ---- (2) stop_all (the Stop / cancel path) calls decline_dialogs ----
stop_fn = method("stop_all")
calls_in_stop = [ast.unparse(n) for n in ast.walk(stop_fn) if isinstance(n, ast.Call)]
check("self.decline_dialogs()" in calls_in_stop, f"stop_all calls self.decline_dialogs(): {calls_in_stop}")
DeskStub.stop_all = methods_from_desk([method("decline_dialogs"), stop_fn], llm_obj).stop_all
d2 = new_stub(llm_obj)
d2.requests.put(("queued request", None))
d2._req_pending = 1
d2.stop_all()
closes2 = [m["id"] for m in d2.emitted if m.get("t") == "dialog.close"]
check(d2.ctx.cancel.is_set() and llm_obj.aborted >= 1, "stop_all sets cancel and aborts the model")
check(closes2 == ["d1", "d2"] and all(v[1] == "no" for v in d2.dialogs.values()),
      f"stop_all declines and closes the pending dialogs: {closes2!r}")
check(d2.requests.empty() and d2._req_pending == 0, "stop_all drops the queued request and counts it off")

# ---- (3) "install the updates" refreshes the Updates panel with asked=True ----
install_if = None
for node in ast.walk(desk_cls):
    if isinstance(node, ast.If) and ast.unparse(node.test).startswith("_UPD_INSTALL.fullmatch("):
        install_if = node
        break
check(install_if is not None, "desk.py has the 'install the updates' route")
body_src = ast.unparse(install_if)
route_src = "def route_fn(self, low, line):\n    " + body_src.replace("\n", "\n    ") + "\n    return False\n"
calls = []
opened = []
upd_calls = []


def updates_apply():
    upd_calls.append(True)
    return True, "updates installed"


def updates_panel(**kw):
    calls.append(kw)
    return {"id": "panel-updates", "kw": kw}


class FakeThread:                       # runs the target at once so the refresh happens inside this test
    def __init__(self, target, daemon=False):
        self.target = target

    def start(self):
        self.target()


stub_sys = types.SimpleNamespace(updates_apply=updates_apply, updates_panel=updates_panel)
_dsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py"), encoding="utf-8").read()
_uns = {}
exec("import re\n" + _dsrc[_dsrc.index("_UPD_AUTO = "):_dsrc.index("_TIME_Q = re.compile(")], _uns)
ns_route = {"re": re, "syspanels": stub_sys, "threading": types.SimpleNamespace(Thread=FakeThread), "_UPD_INSTALL": _uns["_UPD_INSTALL"]}
exec(route_src, ns_route)


class Route:
    def __init__(self):
        self.emitted = []
        self.last_reply = self._said = None

    def emit(self, msg):
        self.emitted.append(msg)

    def open_window(self, w):
        opened.append(w)


r = Route()
hit = ns_route["route_fn"](r, "install the updates", "install the updates")
check(hit is True and upd_calls == [True], "install the updates runs updates_apply once")
check(calls == [{"asked": True}], f"refresh after install calls updates_panel(asked=True): {calls!r}")
check(opened and opened[0]["id"] == "panel-updates", "the refreshed Updates panel opens")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
