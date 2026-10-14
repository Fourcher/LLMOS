#!/usr/bin/env python3
"""Host-side regression tests for the bugs the 2026-10-14 feature sweep found (docs/research/feature-sweep-2026-10-14).
Run: python3 tools/test-sweep-fixes.py  (exit status 0 = pass)"""
import os
import sys
import tempfile

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
HOME = tempfile.mkdtemp(prefix="sweep-home-")
os.environ["LLMOS_HOME"] = HOME
for d in ("Documents/Sweep Test", "Downloads", "Desktop"):
    os.makedirs(os.path.join(HOME, d), exist_ok=True)
open(os.path.join(HOME, "Documents", "my-notes.txt"), "w").write("x\n")

from llmos import agent, everyday, intent  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


# 1. delete: the model sends its arguments as JSON text; execute read .get on that text ("'str' object has no attribute 'get'")
from llmos import desk  # noqa: E402


class _Desk:
    windows = {}

    def emit(self, m):
        pass

    def describe_tool(self, *a, **k):
        return "x"

    def __getattr__(self, k):
        return lambda *a, **kw: None


class Ctx(desk.DeskCtx):
    def confirm_action(self, *a, **k):
        return True

    def confirm_network(self, *a, **k):
        return True


def ctx():
    c = Ctx(_Desk())
    c.current_request = "delete it"
    return c


target = os.path.join(HOME, "Documents", "gone.txt")
open(target, "w").write("x")
try:
    out = agent.execute(ctx(), "delete_file", '{"path": "%s"}' % target)
except Exception as e:
    out = f"EXCEPTION {type(e).__name__}: {e}"
check("delete with arguments as JSON text works", "moved" in out and not os.path.exists(target), out)
out = agent.execute(ctx(), "delete_file", '{"path": "%s"}' % os.path.join(HOME, "nothing-here.txt"))
check("delete of a missing file says so", "nothing called" in out, out)

# 2. a new file "in <a folder the owner made>" goes into that folder, not into the name
r = intent.match("make a new text file called notes.txt in Sweep Test")
check("new file in a named folder", r == ("write_file", {"path": "~/Documents/Sweep Test/notes.txt", "content": "", "append": True}), r)
r = intent.match("make a text file called todo on my desktop")
check("new file on the desktop unchanged", r and r[1]["path"] == "~/Desktop/todo.txt", r)

# 3. move a file into a folder the owner made (the model's own shell command split the path at the space)
for q in ("move my-notes.txt into Sweep Test", "put my-notes.txt inside the Sweep Test folder",
          "move the file my-notes.txt into the Sweep Test folder"):
    r = intent.match(q)
    check(f"move: {q!r}", r == ("move_files", {"what": "my-notes.txt", "from": "home", "to": "~/Documents/Sweep Test", "copy": False}), r)
r = intent.match("copy my-notes.txt to the Sweep Test folder")
check("copy into a named folder", r and r[0] == "move_files" and r[1]["copy"] is True, r)
r = intent.match("move my-notes.txt into Nowhere Special")
check("move into a folder that does not exist is left to the assistant", r is None or r[0] != "move_files", r)


# 4. "write a note to my neighbour and save it as thanks.txt" is not "append to a file called 'neighbour and save it as ...'"
class D:
    said = None

    def instant_reply(self, line, text):
        D.said = text


for q in ("write a short thank-you note to my neighbour and save it as thanks.txt",):
    D.said = None
    low = q.lower()
    try:
        handled = everyday.handle(D(), q)
    except Exception:
        handled = False
    check(f"compose request is not an append: {q!r}", not (D.said or "").startswith("Added"), D.said)
check("no file named after the request", not any("save it as" in f for f in os.listdir(os.path.join(HOME, "Documents"))))
D.said = None
everyday.handle(D(), "add call the bank to todo.txt")
check("a real append still works", (D.said or "").startswith("Added"), D.said)

print("all good" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
