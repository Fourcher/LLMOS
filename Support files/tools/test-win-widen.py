#!/usr/bin/env python3
"""Host-side test of the widened window route in llmos/desk.py and the reopen-tab key in llmos/wm.py.
- desk.py is read with ast (it needs GTK): the _WIN regex and _window_shortcut are extracted and run
  against a stub self; wm.py is imported for real with its process calls (_run, windows, act, force_quit) recorded.
- "force quit" / "force quit it" / "force quit this" / "force quit this app" stop the last program (asks first);
  bare "kill" never matches; "kill time", "kill the lights", "how do I force quit", "reopen my last file" do not match.
- "reopen what I closed", "reopen the tab I closed", "reopen closed tab", "undo close tab" send Ctrl+Shift+T to Firefox;
  with the browser closed they say "The browser is not open."
- existing _WIN results are unchanged ("kill firefox", "force quit firefox", "new tab", "reload", "go back", "close firefox").
Run: python3 tools/test-win-widen.py"""
import ast
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos")
DESK = os.path.join(ROOT, "desk.py")
WM = os.path.join(ROOT, "wm.py")
failures = []


def check(cond, label):
    if cond:
        print("ok " + label)
    else:
        print("FAIL " + label)
        failures.append(label)


# --- wm.py: real module, process calls recorded -------------------------------------------------
spec = importlib.util.spec_from_file_location("wm_under_test", WM)
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)
check(wm.KEYS.get("reopen tab") == ["-M", "ctrl", "-M", "shift", "-k", "t", "-m", "shift", "-m", "ctrl"],
      "wm.KEYS has 'reopen tab' = Ctrl+Shift+T")
check(wm.KEYS.get("new tab") == ["-M", "ctrl", "-k", "t", "-m", "ctrl"], "existing 'new tab' key unchanged")

calls = []
state = {"windows": ["firefox"]}
wm._run = lambda argv, *a, **k: (calls.append(("run", list(argv))), (0, ""))[1]
wm.windows = lambda: list(state["windows"])
wm.act = lambda verb, target: (calls.append(("act", verb, target)), (True, ""))[1]
wm.force_quit = lambda target: (calls.append(("force_quit", target)), (True, "stopped " + str(target)))[1]
wm.time.sleep = lambda s: None

# --- desk.py: _WIN regex and _window_shortcut, extracted with ast ------------------------------
tree = ast.parse(open(DESK, encoding="utf-8").read())
win_src = None
fn_node = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_WIN" for t in node.targets):
        win_src = ast.literal_eval(node.value.args[0])
    if isinstance(node, ast.FunctionDef) and node.name == "_window_shortcut":
        fn_node = node
check(win_src is not None and "(?P<reopen>" in win_src, "desk _WIN has a (?P<reopen>) group")
check(fn_node is not None, "desk _window_shortcut found")
WIN = re.compile(win_src)
mod = ast.Module(body=[fn_node], type_ignores=[])
ast.fix_missing_locations(mod)


class FakeThread:
    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        self.target()


class FakeThreading:
    Thread = FakeThread


class Stub:
    _WIN = WIN
    _reloaded = False
    _said = None
    last_reply = None

    def instant_reply(self, low, text):
        calls.append(("reply", text))

    def ask(self, spec_):
        calls.append(("ask", spec_.get("title")))
        return state.get("answer", True)


ns = {"re": re, "threading": FakeThreading, "wm": wm, "PAGE": "/x", "__builtins__": __builtins__}
exec(compile(mod, DESK, "exec"), ns)
shortcut = ns["_window_shortcut"]


def run(text, windows=("firefox",), answer=True):
    """Run the desk's shortcut on text (lowercased and stripped, as the desk does). Returns (handled, calls)."""
    calls.clear()
    state["windows"] = list(windows)
    state["answer"] = answer
    handled = shortcut(Stub(), text.lower().strip())
    return handled, list(calls)


def replies(cs):
    return [c[1] for c in cs if c[0] == "reply"]


def stopped(cs):
    return [c[1] for c in cs if c[0] == "force_quit"]


# --- must NOT match: nothing runs --------------------------------------------------------------
for text in ("kill", "kill time", "kill the lights", "kill it", "this is killing me",
             "how do i force quit", "reopen my last file", "force quit the lights"):
    handled, cs = run(text)
    check(handled is False and not cs, "no match, nothing run: '" + text + "'")
    if not (handled is False and not cs):
        print("   got", handled, cs)

# --- force quit: bare, it/this/this app -> the last program (asked first) ------------------------
for text in ("force quit", "force quit it", "force quit this", "force quit this app"):
    handled, cs = run(text)
    check(handled is True and stopped(cs) == ["firefox"] and ("ask", "Stop the browser?") in cs,
          "'" + text + "' stops the last program after asking")
    if not (handled is True and stopped(cs) == ["firefox"]):
        print("   got", handled, cs)

handled, cs = run("force quit", windows=())
check(handled is True and replies(cs) == ["No program is open to stop."] and not stopped(cs),
      "'force quit' with no program open keeps the existing reply")
handled, cs = run("force quit it", answer=False)
check(handled is True and not stopped(cs), "'force quit it' that the user declines stops nothing")

# --- named force quit / kill: unchanged --------------------------------------------------------
handled, cs = run("kill firefox")
check(handled is True and stopped(cs) == ["firefox"], "'kill firefox' stops firefox (unchanged)")
handled, cs = run("force quit firefox")
check(handled is True and stopped(cs) == ["firefox"], "'force quit firefox' stops firefox (unchanged)")
handled, cs = run("force quit the firefox")
check(handled is True and stopped(cs) == ["firefox"], "'force quit the firefox' stops firefox")

# --- reopen closed tab: Ctrl+Shift+T to Firefox -------------------------------------------------
want_keys = ["-M", "ctrl", "-M", "shift", "-k", "t", "-m", "shift", "-m", "ctrl"]
for text in ("reopen what I closed", "reopen the tab I closed", "reopen closed tab",
             "undo close tab", "reopen the last closed tab", "Reopen what I closed?"):
    handled, cs = run(text)
    sent = [c[1] for c in cs if c[0] == "run" and c[1][:1] == ["wtype"]]
    check(handled is True and sent == [["wtype"] + want_keys] and replies(cs) == ["Reopened the last closed tab."],
          "'" + text + "' reopens the closed tab")
    if not (handled is True and sent == [["wtype"] + want_keys]):
        print("   got", handled, cs)

handled, cs = run("reopen closed tab", windows=())
check(handled is True and replies(cs) == ["The browser is not open."] and not any(c[0] == "run" for c in cs),
      "'reopen closed tab' with the browser closed says the browser is not open")

# --- existing browser keys unchanged ------------------------------------------------------------
for text, key in (("new tab", "new tab"), ("reload", "reload"), ("go back", "back")):
    handled, cs = run(text)
    sent = [c[1] for c in cs if c[0] == "run" and c[1][:1] == ["wtype"]]
    check(handled is True and sent == [["wtype"] + wm.KEYS[key]], "'" + text + "' still sends the " + key + " key")
handled, cs = run("close firefox")
check(handled is True and ("act", "close", "firefox") in cs and replies(cs) == ["Closed the browser."],
      "'close firefox' still closes the browser")

# --- the _WIN regex itself: names that must not be captured -----------------------------------
g = WIN.fullmatch("force quit").groupdict()
check(g["killw"] is None, "bare 'force quit' captures no name")
check(WIN.fullmatch("kill") is None, "bare 'kill' does not match _WIN")
check(WIN.fullmatch("how do i force quit") is None, "'how do i force quit' does not match _WIN (how-to route)")

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
