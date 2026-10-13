#!/usr/bin/env python3
"""Host-side test: the home folder the model is told about (and the reset's erase root) follows
config.home(), not a hard-coded /root. With HOME=/root every string is byte-identical to before;
with /home/owner none of them says /root. Stubs keep erase() from touching the host.
Run: python3 tools/test-home-paths.py  (no VM needed)."""
import importlib
import os
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import config, tools, console, reset, mcp  # noqa: E402

FAILS = []


def check(cond, label):
    if cond:
        print("ok " + label)
    else:
        print("FAIL " + label)
        FAILS.append(label)


def set_home(value, use_llmos_home=True):
    for k in ("LLMOS_HOME", "HOME"):
        os.environ.pop(k, None)
    if use_llmos_home:
        os.environ["LLMOS_HOME"] = value
    os.environ["HOME"] = value


class Ctx:
    is_desk = False

    def show_panel(self, name):
        pass


def model_strings():
    """Every model-visible string this change touches, computed now (decorators re-run on reload)."""
    importlib.reload(tools)
    importlib.reload(console)
    out = {}
    out["read_file"] = tools.REGISTRY["read_file"].desc
    out["write_file"] = tools.REGISTRY["write_file"].desc
    out["show_files"] = tools.REGISTRY["show_files"].desc
    mcp_connectors, mcp.connectors = mcp.connectors, (lambda: [])
    try:
        out["manage_connectors"] = tools.manage_connectors({"action": "list"}, Ctx())
    finally:
        mcp.connectors = mcp_connectors
    out["setup_connector"] = console.ConsoleCtx.setup_connector(None)
    return out


def erase_listdir_arg():
    """Run reset.erase() with every destructive call stubbed; return the path it would empty (or None)."""
    seen = {"listdir": None, "rmtree": 0, "unlink": 0}
    saved = (os.listdir, shutil.rmtree, os.unlink, reset.glob.glob, reset.subprocess.run, config.settings, config.ETC)
    tmp = tempfile.mkdtemp()
    try:
        def fake_listdir(p):
            seen["listdir"] = p
            return []

        def fake_rm(*a, **k):
            seen["rmtree"] += 1

        def fake_unlink(*a, **k):
            seen["unlink"] += 1

        os.listdir, shutil.rmtree, os.unlink = fake_listdir, fake_rm, fake_unlink
        reset.glob.glob = lambda p: []
        reset.subprocess.run = lambda *a, **k: None
        config.settings = {}
        config.ETC = tmp
        left = reset.erase()
        return seen, left
    finally:
        os.listdir, shutil.rmtree, os.unlink, reset.glob.glob, reset.subprocess.run, config.settings, config.ETC = saved
        shutil.rmtree(tmp, ignore_errors=True)


OLD_ROOT = {
    "read_file": "(The owner's home folder is /root, i.e. ~.)",
    "write_file": "The owner's home folder is /root (~). Letters, essays ",
    "show_files": "/root (~). Use for 'show my files', 'open my documents folder', 'what's in ~/projects'.",
    "manage_connectors": "npx -y @modelcontextprotocol/server-filesystem /root'.",
    "setup_connector": "@modelcontextprotocol/server-filesystem /root'\"",
}

# 1. HOME=/root (today's desk): every string equals the old literal
set_home("/root")
s = model_strings()
for key, literal in OLD_ROOT.items():
    check(literal in s[key], f"HOME=/root {key} contains old literal {literal!r}")
seen, left = erase_listdir_arg()
check(seen["listdir"] == "/root" and left == [], "HOME=/root erase() empties /root (stubbed)")

# 2. LLMOS_HOME unset, HOME=/root: config.home() falls back to HOME, same strings
set_home("/root", use_llmos_home=False)
s2 = model_strings()
check(all(s2[k] == s[k] for k in OLD_ROOT), "HOME only (LLMOS_HOME unset) gives identical strings")

# 3. HOME=/home/owner: the new folder is named and /root is gone
set_home("/home/owner")
s = model_strings()
for key in OLD_ROOT:
    check("/home/owner" in s[key] and "/root" not in s[key], f"HOME=/home/owner {key} says /home/owner, no /root")
seen, left = erase_listdir_arg()
check(seen["listdir"] == "/home/owner", "HOME=/home/owner erase() empties /home/owner (stubbed)")

# 4. trailing slash: /home/owner/ reads as /home/owner
set_home("/home/owner/")
s = model_strings()
check("/home/owner (~)" in s["show_files"] and "/home/owner/ (~)" not in s["show_files"],
      "trailing slash HOME=/home/owner/ -> '/home/owner (~)'")
seen, left = erase_listdir_arg()
check(seen["listdir"] == "/home/owner", "trailing slash erase() path has no trailing slash")

# 5. HOME=/ : the disk root is never named as an erase target (guard still refuses)
set_home("/")
seen, left = erase_listdir_arg()
check(seen["listdir"] is None and left == ["home folder (not erased: it is the root of the disk)"],
      "HOME=/ erase() refuses, lists nothing")

# 6. HOME unset (no LLMOS_HOME): config.home() uses the account's home, as expanduser does
for k in ("LLMOS_HOME", "HOME"):
    os.environ.pop(k, None)
expected = os.path.expanduser("~")
check(config.home() == expected, f"HOME unset -> config.home() = expanduser('~') = {expected!r}")

set_home("/root")   # leave the process as it was for the rest of the host run
if FAILS:
    print("FAILED: " + ", ".join(FAILS))
    sys.exit(1)
print("all good")
