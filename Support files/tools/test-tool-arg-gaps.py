#!/usr/bin/env python3
"""Bad tool arguments from real logs are tolerated: connector enums/ints, open_app flags, install_app paths,
cat on a folder, read_file on a missing file. Run: python3 tools/test-tool-arg-gaps.py"""
import os, shlex, sys, tempfile
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC", tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import mcp, tools
fails = 0
def check(c, w):
    global fails
    print(("ok   " if c else "FAIL ") + w)
    fails += 0 if c else 1
sch = {"properties": {"thread": {"type": "integer"}, "close": {"type": "string", "enum": ["archive", "keep"]},
                      "state": {"type": "string", "enum": ["open", "closed"]}, "read": {"type": "boolean"}}, "required": []}
n = mcp.normalize_args(sch, {"thread": "all", "close": "done", "read": "yes", "other": 1})
check("thread" not in n, f"thread='all' dropped: {n}")
check(n.get("close") == "archive", f"close='done' -> archive: {n}")
check(n.get("read") is True and n.get("other") == 1, f"bool string and extra key: {n}")
check(mcp.normalize_args(sch, {"thread": "12", "state": "Closed"}) == {"thread": 12, "state": "closed"}, "digits and case")
check(tools.split_open_command("--new ~/voice-interface.html") == ("file", os.path.expanduser("~/voice-interface.html")), "flags + file")
check(tools.split_open_command("-x")[0] == "error", "only flags")
check(tools.split_open_command("thunar /tmp") == ("app", "thunar /tmp"), "normal command untouched")
check(tools.package_candidates("aports/system/auto-updates") == ["auto-updates"], "aports path -> package name")
check(tools.package_candidates("community/htop, vim.apk htop") == ["htop", "vim"], "dedupe, .apk")
d = tempfile.mkdtemp(); open(os.path.join(d, "Handoff to next AI.md"), "w").write("x"); os.mkdir(os.path.join(d, "sub"))
c = tools.cat_directory("cat " + shlex.quote(d + "/"))
check(c and "is a folder" in c and "sub/" in c, f"cat on a folder lists it: {c}")
check(tools.cat_directory(f"cat {d}/x") is None and tools.cat_directory("ls /") is None, "other commands untouched")
m = tools.missing_file_message(os.path.join(d, "handoff_to_next_ai.md"))
check(m.startswith("not found") and "Handoff to next AI.md" in m, f"missing file suggests near name: {m}")
r = tools.REGISTRY["read_file"].fn({"path": os.path.join(d, "nope", "a.txt")}, None)
check(r.startswith("error: not found") and "does not exist" in r, f"read_file missing: {r}")
print("all good" if not fails else f"{fails} failed"); sys.exit(1 if fails else 0)
