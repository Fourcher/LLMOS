#!/usr/bin/env python3
"""Host-side unit test: owner_text() turns 'error: ...' tool output into plain words for the owner.
Non-error output and non-strings pass through unchanged. Also checks the four error-branch call sites use owner_text.
Run: python3 tools/test-owner-text.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent


def _check(label, got, want):
    if got != want:
        print(f"FAIL {label}: got {got!r}, wanted {want!r}")
        sys.exit(1)
    print(f"ok   {label}: {got!r}")


def _check_true(label, cond, detail):
    if not cond:
        print(f"FAIL {label}: {detail}")
        sys.exit(1)
    print(f"ok   {label}")


errno_out = agent.owner_text("error: [Errno 2] No such file or directory: '/root/x'")
_check_true("errno: no 'error:'", "error:" not in errno_out, repr(errno_out))
_check_true("errno: no '[Errno'", "[Errno" not in errno_out, repr(errno_out))
_check("errno: plain words", errno_out, agent._plain_error("[Errno 2] No such file or directory: '/root/x'"))
_check("empty command", agent.owner_text("error: empty command"), "Empty command")
_check("bare error:", agent.owner_text("error:"), "Something went wrong.")
_check("errors plural unchanged", agent.owner_text("errors were found in 3 files"), "errors were found in 3 files")
_check("None unchanged", agent.owner_text(None), None)
_check("Done. unchanged", agent.owner_text("Done."), "Done.")

# source check: the four error-branch call sites use owner_text
here = os.path.join(_ROOT, "usr/lib/llmos/llmos")
with open(os.path.join(here, "agent.py"), encoding="utf-8") as f:
    agent_src = f.read()
with open(os.path.join(here, "desk.py"), encoding="utf-8") as f:
    desk_src = f.read()
sites = [
    (agent_src, 'if not out.startswith("error") else owner_text(out)\n            else:'),
    (agent_src, 'return _cap(out.split(". Say")[0]) + "." if not low.startswith("error") else owner_text(out)'),
    (agent_src, '("Done." if " is ticked off" in low else "Back on the list.") if not low.startswith("error") else owner_text(out)'),
    (desk_src, 'if not out.startswith("error") else agent.owner_text(out))'),
]
for i, (src, needle) in enumerate(sites, 1):
    _check_true(f"call site {i} uses owner_text", src.count(needle) == 1, needle)
print("ok   four call sites use owner_text")
print("all good")
