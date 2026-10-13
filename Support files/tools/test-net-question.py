#!/usr/bin/env python3
"""Host-side test of the internet question (confirm_network in desk.py and console.py). The question must name the
action in plain words, never the raw tool name: "find_by_meaning -> search model download" becomes
"Get the search model — search model download". desk.py and console.py need GTK/termios, so each confirm_network
method is read from its source with ast and run against a recorder. Run: python3 tools/test-net-question.py"""
import ast
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos")
fails = 0


def check(cond, what):
    global fails
    print(("ok " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


def method_from(path, cls):
    """Compile only the confirm_network method of class cls, so the module's imports are not needed."""
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef) and fn.name == "confirm_network":
                    mod = ast.Module(body=[fn], type_ignores=[])
                    ns = {"T": lambda key, **kw: {"s_internet": "Internet"}.get(key, key), "L": lambda key: key}
                    exec(compile(mod, path, "exec"), ns)
                    return ns["confirm_network"]
    raise SystemExit(f"FAIL no confirm_network in {cls} ({path})")


class Recorder:
    def __init__(self):
        self.texts = []

    def ask(self, spec, consent=False):
        self.texts.append(spec["text"])
        return True

    def ask_yes_no(self, text, danger=False):
        self.texts.append(text)
        return True


class FakeDeskCtx:
    def __init__(self):
        self._net_ok = set()
        self.d = Recorder()


class FakeConsoleCtx:
    def __init__(self):
        self._net_ok = set()
        self.c = Recorder()


CASES = [
    ("find_by_meaning", {"query": "search model download, 310 MB"}, "Get the search model", "search model download, 310 MB"),
    ("read_webpage", {"url": "https://example.com/page"}, "Open a web page", "https://example.com/page"),
    ("web_search", {"query": "weather in Lyon"}, "Search the web", "weather in Lyon"),
    ("foo_bar", {"query": "some detail"}, "Foo bar", "some detail"),
]

for label, ctx_cls, path, getter in (
    ("desk", FakeDeskCtx, os.path.join(ROOT, "desk.py"), lambda c: c.d.texts),
    ("console", FakeConsoleCtx, os.path.join(ROOT, "console.py"), lambda c: c.c.texts),
):
    fn = method_from(path, "DeskCtx" if label == "desk" else "ConsoleCtx")
    for name, args, want_label, want_detail in CASES:
        c = ctx_cls()
        ok = fn(c, name, args)
        texts = getter(c)
        text = texts[-1] if texts else ""
        plain = (not any(raw in text for raw in (name, "_", "→"))) and want_label in text and want_detail in text
        check(ok is True and len(texts) == 1 and plain, f"{label} {name}: {text!r}")

# a second call for the same tool is answered from the consent set, with no question
c = FakeDeskCtx()
fn = method_from(os.path.join(ROOT, "desk.py"), "DeskCtx")
fn(c, "web_search", {"query": "x"})
fn(c, "web_search", {"query": "y"})
check(len(c.d.texts) == 1, "desk: a repeat of an allowed tool asks nothing")

print("all good" if fails == 0 else f"{fails} failed")
sys.exit(1 if fails else 0)
