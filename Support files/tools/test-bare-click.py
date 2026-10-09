#!/usr/bin/env python3
"""Host-side unit test for _bare_click: 'click File' / 'click the Save button' is one click by the control's words,
decided without the model. Anything else (a single key, a chain with 'then', a failed click) returns None.
Run: python3 tools/test-bare-click.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, agent

calls = []
result = {"out": "clicked 'File'."}


def fake_execute(ctx, name, arguments):
    calls.append((name, arguments))
    return result["out"]


agent.execute = fake_execute
_saved_available = tools.REGISTRY["click"].available
tools.REGISTRY["click"].available = lambda: True

failures = []


def check(label, got, want):
    if got == want:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


try:
    calls.clear()
    check("click File -> Clicked File.", agent._bare_click(None, "click File"), "Clicked File.")
    check("click File calls execute(click, text=File)", calls, [("click", {"text": "File"})])

    calls.clear()
    check("click the Save button -> Clicked Save.", agent._bare_click(None, "click the Save button"), "Clicked Save.")

    calls.clear()
    check("click on the File menu -> Clicked File.", agent._bare_click(None, "click on the File menu"), "Clicked File.")

    calls.clear()
    check("press 7 -> None (single key)", agent._bare_click(None, "press 7"), None)
    check("press 7 makes no click", calls, [])

    calls.clear()
    check("click File then Save -> None", agent._bare_click(None, "click File then Save"), None)
    check("click File then Save makes no click", calls, [])

    result["out"] = "error: nothing named File"
    calls.clear()
    check("failed click -> None", agent._bare_click(None, "click File"), None)
    check("failed click was attempted once", calls, [("click", {"text": "File"})])
finally:
    tools.REGISTRY["click"].available = _saved_available

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
