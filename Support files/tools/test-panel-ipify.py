#!/usr/bin/env python3
"""Host-side test of the 'what is my ip' reply (desk.py shortcut(): the nested ip() builder). The public address is
looked up online (api.ipify.org) only when the internet is set to "yes": under "ask" and "no" nothing goes online and
the line is left out. desk.py needs GTK, so ip() is pulled out of its source with ast and run with stubs.
Run: python3 tools/test-panel-ipify.py"""
import ast
import os
import re
import sys
import textwrap
import types

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
src = open(SRC, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


# find the nested def ip() inside Desk.shortcut
tree = ast.parse(src)
ip_node = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "shortcut":
        for sub in ast.walk(node):
            if isinstance(sub, ast.FunctionDef) and sub.name == "ip":
                ip_node = sub
assert ip_node is not None, "nested ip() not found in shortcut()"
ip_src = ast.get_source_segment(src, ip_node)
ip_src = textwrap.dedent(ip_src)


class Stub:
    def __init__(self, internet):
        self.replies = []
        self.internet = internet
        self.fetches = []

    def instant_reply(self, line, text):
        self.replies.append(text)


def run_case(internet, fetch_result):
    calls = []

    def fake_fetch(url, **kw):
        calls.append((url, kw))
        if isinstance(fetch_result, Exception):
            raise fetch_result
        return (200, "text/plain", url, fetch_result)

    web_stub = types.SimpleNamespace(fetch=fake_fetch)
    pkg = types.ModuleType("llmos")
    pkg.web = web_stub
    sys.modules["llmos"] = pkg
    config_stub = types.SimpleNamespace(settings=types.SimpleNamespace(get=lambda k, d=None: internet if k == "internet" else d))
    fake_sub = types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(stdout="    inet 192.168.1.5/24 brd 192.168.1.255 scope global\n"),
                                     SubprocessError=Exception)
    desk = Stub(internet)
    ns = {"re": re, "subprocess": fake_sub, "config": config_stub, "__package__": "llmos", "__name__": "llmos.desk",
          "line": "what is my ip", "self": desk}
    exec(ip_src, ns)
    ns["ip"]()
    return calls, desk.replies


ip_text = ""
for mode, expect_calls in (("ask", 0), ("yes", 1), ("no", 0)):
    calls, replies = run_case(mode, b"203.0.113.7")
    text = " ".join(replies)
    print(f"internet={mode}: fetch calls={len(calls)} reply={text!r}")
    check(len(calls) == expect_calls, f"internet={mode}: {expect_calls} web.fetch call(s)")
    check(len(replies) == 1, f"internet={mode}: one reply given")
    if mode == "ask":
        check("None" not in text and "error" not in text.lower(), "internet=ask: no 'None' or 'error' text in the reply")
        check("203.0.113.7" not in text and "To the internet" not in text, "internet=ask: public address line omitted")
        check(text.startswith("On your network: 192.168.1.5."), "internet=ask: local address still reported")
    if mode == "yes":
        check("To the internet: 203.0.113.7." in text, "internet=yes: public address shown")
        check(calls and calls[0][0] == "https://api.ipify.org", "internet=yes: fetches api.ipify.org")
    if mode == "no":
        check("To the internet" not in text, "internet=no: public address line omitted")

# a failing lookup under "yes" must still give a clean reply without 'None' or 'error'
calls, replies = run_case("yes", OSError("offline"))
text = " ".join(replies)
check(len(calls) == 1 and "None" not in text and "error" not in text.lower() and "To the internet" not in text,
      "internet=yes with lookup failure: one call, clean reply")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
