#!/usr/bin/env python3
"""Host-side test of the web-page check's explanation. When an instruction from a web page, email or file leads to a
change that the owner is asked about, the dialog says why it asked. agent.execute sets ctx.confirm_tainted for that
call only (and resets it after); the desk (DeskCtx) and the console (ConsoleCtx) add the sentence when it is set.
No signature changes: a ctx whose confirm_action(tool, shown, risk) takes the old three arguments still works.
desk.py and console.py need GTK / a terminal, so their confirm_action methods are read from source and run with stubs.
Run: python3 tools/test-guard-explain.py (no model, no VM)"""
import os
import re
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
LLMOS = os.path.join(_ROOT, "usr/lib/llmos/llmos")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import agent, config, i18n, tools  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


KEY = i18n.t("d_guard_tainted")
check(bool(KEY) and KEY != "d_guard_tainted", "the explanation has text in the current language")

# ---- agent side: the flag is set on the taint path only, and reset afterwards
print("agent: the flag is set for the web-page check and reset after")


class OldStyleCtx:
    """An old-style ctx: confirm_action takes exactly (tool, shown, risk). Records the flag seen during the call."""
    headless = False
    current_request = ""

    def __init__(self):
        self.tainted = False
        self.seen = []
        self.asked = []

    def confirm_action(self, tool, shown, risk):
        self.seen.append(getattr(self, "confirm_tainted", None))
        self.asked.append(tool.name)
        return True

    def confirm_network(self, name, shown):
        return True

    def begin_tool(self, *a):
        pass

    def end_tool(self, *a):
        pass

    def status(self, *a):
        pass


ran = []
for name in ("empty_trash", "run_command"):
    t = tools.REGISTRY[name]
    t.fn = (lambda n: (lambda a, ctx: ran.append(n) or f"done {n}"))(name)
    t.network = None
    t.available = lambda: True
config.settings.set("internet", "yes")
config.settings.set("guard_untrusted", True)
config.settings.set("autonomy", "balanced")

ctx = OldStyleCtx()
ctx.current_request = "delete my old folder"
ctx.tainted = True
out = agent.execute(ctx, "run_command", {"command": "rm -rf ~/old"})
check(ctx.asked == ["run_command"], "tainted destructive call is asked (old-style confirm_action does not raise)")
check(ctx.seen == [True], f"flag is True during the taint confirm (saw {ctx.seen})")
check(getattr(ctx, "confirm_tainted", None) is False, "flag is reset to False after the taint confirm")
check(ran == ["run_command"], "the confirmed call ran")

ctx = OldStyleCtx()
ctx.current_request = "empty the trash"
ctx.tainted = False
out = agent.execute(ctx, "empty_trash", {})
check(ctx.asked == ["empty_trash"] and ctx.seen == [None], f"untainted always-confirm call: flag never set (saw {ctx.seen})")
check(not getattr(ctx, "confirm_tainted", False), "flag is not True after an untainted confirm")

# ---- desk and console: the sentence is added only when the flag is set
print("desk and console: the sentence is added only when the flag is set")


def method_source(path, start, end):
    src = open(path, encoding="utf-8").read()
    return src[src.index(start):src.index(end)]


def load_method(path):
    ns = {"re": re, "T": i18n.t, "__builtins__": __builtins__}
    ns["ui"] = type("UI", (), {"safe": staticmethod(lambda s: s)})
    exec("class X:\n" + method_source(path, "    def confirm_action(self, tool, args, risk):", "    def confirm_online("), ns)
    return ns["X"]


class Tool:
    name = "run_command"


class DeskStub:
    def __init__(self):
        self.recorded = []

    def ask(self, spec, consent=False):
        self.recorded.append(spec["text"])
        return True

    def describe_tool(self, tool, args, confirm=False):
        return "title"

    def describe_args(self, tool, args):
        return "args"


class ConsoleStub:
    def __init__(self):
        self.recorded = []

    def ask_yes_no(self, question, default=False, danger=False):
        self.recorded.append(question)
        return True

    def describe_tool(self, tool, args, confirm=False):
        return "tool line"


DeskX = load_method(os.path.join(LLMOS, "desk.py"))
ConsoleX = load_method(os.path.join(LLMOS, "console.py"))

for label, cls, stub_cls, attr in (("desk", DeskX, DeskStub, "d"), ("console", ConsoleX, ConsoleStub, "c")):
    obj = cls()
    stub = stub_cls()
    setattr(obj, attr, stub)            # the ctx's desk (self.d) or console (self.c) object
    # flag unset: no explanation
    obj.confirm_action(Tool(), {"command": "ls"}, tools.DESTRUCTIVE)
    rec = stub.recorded
    check(len(rec) == 1 and KEY not in rec[0], f"{label}: flag unset, no explanation shown")
    # flag set (agent.execute sets it on this same ctx object): explanation added
    obj.confirm_tainted = True
    obj.confirm_action(Tool(), {"command": "ls"}, tools.DESTRUCTIVE)
    check(len(rec) == 2 and rec[1].endswith(KEY), f"{label}: flag set, explanation added at the end")
    # flag reset: no explanation again
    obj.confirm_tainted = False
    obj.confirm_action(Tool(), {"command": "ls"}, tools.DESTRUCTIVE)
    check(len(rec) == 3 and KEY not in rec[2], f"{label}: flag reset, no explanation")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
