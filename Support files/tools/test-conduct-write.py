#!/usr/bin/env python3
"""Host-side test that desk.py and tools.py no longer open or unlink conduct.txt directly and go through
config.write_conduct / config.remove_conduct, and that those helpers create and remove the file under ETC.
Run: python3 tools/test-conduct-write.py"""
import os
import re
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
_LIB = os.path.join(_ROOT, "usr/lib/llmos")
sys.path.insert(0, _LIB)
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import config  # noqa: E402

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print(f"ok {name}")
    else:
        fails += 1
        print(f"FAIL {name} {detail}")


def read(name):
    with open(os.path.join(_LIB, "llmos", name), encoding="utf-8") as f:
        return f.read()


desk = read("desk.py")
tools = read("tools.py")

for label, src in (("desk.py", desk), ("tools.py", tools)):
    check(f"{label} has no direct open/unlink of conduct_path()",
          not re.search(r"(open|os\.unlink|os\.remove)\(\s*config\.conduct_path\(\)", src))
check("desk.py calls config.write_conduct", "config.write_conduct(" in desk)
check("desk.py calls config.remove_conduct", "config.remove_conduct()" in desk)
check("tools.py calls config.remove_conduct", "config.remove_conduct()" in tools)
check("conduct_path is ETC/conduct.txt",
      os.path.normpath(config.conduct_path()) == os.path.normpath(os.path.join(config.ETC, "conduct.txt")),
      config.conduct_path())

path = config.conduct_path()
try:
    config.write_conduct("x")
    check("write_conduct creates conduct.txt", os.path.isfile(path))
    with open(path, encoding="utf-8") as f:
        check("write_conduct writes the text as given", f.read() == "x")
    config.remove_conduct()
    check("remove_conduct removes conduct.txt", not os.path.exists(path))
    config.remove_conduct()
    check("remove_conduct is fine when the file is already absent", not os.path.exists(path))
finally:
    shutil.rmtree(home, ignore_errors=True)

for f in (os.path.join(_LIB, "llmos", "desk.py"), os.path.join(_LIB, "llmos", "tools.py")):
    import py_compile
    try:
        py_compile.compile(f, doraise=True)
        check(f"py_compile {os.path.basename(f)}", True)
    except py_compile.PyCompileError as e:
        check(f"py_compile {os.path.basename(f)}", False, str(e))

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
