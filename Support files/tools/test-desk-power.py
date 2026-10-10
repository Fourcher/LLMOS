#!/usr/bin/env python3
"""Host-side test: desk.py powers off / reboots through system.power and restarts the model
through system.service (never os.system or rc-service directly). Reads the source with ast,
so it needs no GTK and boots no VM. Run: python3 tools/test-desk-power.py. Exit 0 = pass."""
import ast
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
DESK = os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py")

failures = []


def check(name, ok, detail=""):
    if ok:
        print("ok", name)
    else:
        print("FAIL", name, detail)
        failures.append(name)


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def str_args(call):
    return [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


with open(DESK, encoding="utf-8") as f:
    src = f.read()
tree = ast.parse(src, DESK)

# 1. Desk.shutdown: system.power("poweroff"|"reboot"), no os.system anywhere in its body.
shutdown = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "shutdown":
        shutdown = node
        break
check("shutdown() found", shutdown is not None)
if shutdown is not None:
    calls = [dotted(c.func) for c in ast.walk(shutdown) if isinstance(c, ast.Call)]
    check("shutdown() has no os.system call", "os.system" not in calls, str(calls))
    power_calls = [c for c in ast.walk(shutdown) if isinstance(c, ast.Call) and dotted(c.func) == "system.power"]
    check("shutdown() calls system.power", len(power_calls) == 1, str(calls))
    # the power action is chosen from how == "poweroff" and is one of the two words
    consts = {n.value for n in ast.walk(shutdown) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    check("shutdown() passes poweroff/reboot only", {"poweroff", "reboot"} <= consts, str(consts))
    check("shutdown() keeps the bye screen and vault lock",
          "set_screen" in " ".join(dotted(c.func) for c in ast.walk(shutdown) if isinstance(c, ast.Call))
          and any(dotted(c.func) == "vault.lock" for c in ast.walk(shutdown) if isinstance(c, ast.Call)))

# 2. The model-restart check() inside Desk.shortcut: system.service("llmos-model", "restart", timeout=60).
svc_calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and dotted(c.func) == "system.service"
             and str_args(c)[:2] == ["llmos-model", "restart"]]
check("system.service('llmos-model','restart') present", len(svc_calls) == 1, str(len(svc_calls)))
if svc_calls:
    kw = {k.arg: k.value for k in svc_calls[0].keywords}
    check("system.service restart uses timeout=60",
          isinstance(kw.get("timeout"), ast.Constant) and kw["timeout"].value == 60)
    owner = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and any(n is svc_calls[0] for n in ast.walk(node)):
            owner = node.name
    check("restart call is inside check()", owner == "check", str(owner))

# 3. No direct rc-service or os.system calls left anywhere in desk.py.
direct = []
for c in ast.walk(tree):
    if isinstance(c, ast.Call):
        if dotted(c.func) == "os.system":
            direct.append(("os.system", c.lineno))
        if dotted(c.func).startswith("subprocess.") and "rc-service" in str_args(c):
            direct.append(("rc-service", c.lineno))
check("no os.system or rc-service subprocess call in desk.py", not direct, str(direct))

if failures:
    print("FAILED:", ", ".join(failures))
    sys.exit(1)
print("all good")
