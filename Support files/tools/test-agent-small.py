#!/usr/bin/env python3
"""Host-side unit test for two small agent.py rules:
(a) delete_file of a path that does not exist answers at once and never asks the owner to confirm;
(b) a bare 'click X' that fails says "I can't see “X” on the screen." (no model fallback).
Run: python3 tools/test-agent-small.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, agent

failures = []


def check(label, got, want):
    if got == want:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


class FakeCtx:
    headless = False
    tainted = False

    def confirm_action(self, *a, **k):
        raise AssertionError("asked")


# (a) real agent.execute: a missing path must be refused without asking
missing = "/tmp/llmos-no-such-dir-xyz"
assert not os.path.lexists(missing), "test path unexpectedly exists"
res = agent.execute(FakeCtx(), "delete_file", {"path": missing})
check("delete of a missing path answers without asking",
      str(res).startswith("error: there's nothing called"), True)

# (b) faked execute: a failed bare click gives the new sentence
calls = []


def fake_execute(ctx, name, arguments):
    calls.append((name, arguments))
    return "error: nothing named File on the screen"


agent.execute = fake_execute
_saved_available = tools.REGISTRY["click"].available
tools.REGISTRY["click"].available = lambda: True
try:
    check("failed bare click -> can't-see sentence",
          agent._bare_click(None, "click File"), "I can't see “File” on the screen.")
    check("failed bare click was attempted once", calls, [("click", {"text": "File", "describe_miss": False})])
finally:
    tools.REGISTRY["click"].available = _saved_available

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
