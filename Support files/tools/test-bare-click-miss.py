#!/usr/bin/env python3
"""Host-side unit test for the click tool's describe_miss flag: when a bare click's words are not on the screen,
describe_miss=False returns the not-found text without reading the screen; absent or True reads it (one call).
agent._bare_click passes describe_miss=False; the click schema does not expose describe_miss.
Run: python3 tools/test-bare-click-miss.py  (no VM needed). Exit status 0 = pass."""
import inspect
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, agent, control

failures = []


def check(label, got, want):
    if got == want:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


class Ctx:
    pass          # no app_press attribute: the click tool skips the app path


screen_calls = []


def fake_screen_after(limit=40):
    screen_calls.append(limit)
    return "SCREEN"


saved_find = control.find
saved_screen = tools._screen_after
tools._screen_after = fake_screen_after
control.find = lambda target, *a, **k: None      # the words are not on the screen
click = tools.REGISTRY["click"].fn

try:
    screen_calls.clear()
    out = click({"text": "File", "describe_miss": False}, Ctx())
    check("describe_miss False -> not-found text", out, "error: 'File' is not on the screen now.")
    check("describe_miss False -> no _screen_after call", screen_calls, [])

    screen_calls.clear()
    out = click({"text": "File"}, Ctx())
    check("describe_miss absent -> screen text appended", out,
          "error: 'File' is not on the screen now. The screen shows:\nSCREEN")
    check("describe_miss absent -> one _screen_after call", len(screen_calls), 1)

    screen_calls.clear()
    out = click({"text": "File", "describe_miss": True}, Ctx())
    check("describe_miss True -> one _screen_after call", len(screen_calls), 1)
finally:
    control.find = saved_find
    tools._screen_after = saved_screen

src = inspect.getsource(agent._bare_click)
check("_bare_click passes describe_miss False",
      'execute(ctx, "click", {"text": t, "describe_miss": False})' in src, True)

check("click schema has no describe_miss",
      "describe_miss" in tools.REGISTRY["click"].params, False)

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
