#!/usr/bin/env python3
"""Tests for the radio (rfkill) path: system.radio, rootd's radio verb, and desk.py's call sites.

rfkill is never run for real: subprocess.run and the rootd client are replaced with recorders.
"""
import ast
import json
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos")
PKG_DIR = os.path.abspath(PKG_DIR)

# Load the real package files under the name "llmos" so their relative imports work.
pkg = types.ModuleType("llmos")
pkg.__path__ = [PKG_DIR]
sys.modules["llmos"] = pkg
from llmos import rootd, rootd_client, system  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"ok {label}")
    else:
        failures.append(label)
        print(f"FAIL {label} {detail}")


# ---- fakes -------------------------------------------------------------------
run_calls = []
run_result = {"rc": 0, "out": "", "err": "", "raise": None}


class FakeProc:
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err


def fake_run(argv, **kw):
    run_calls.append((list(argv), kw))
    if run_result["raise"]:
        raise run_result["raise"]
    return FakeProc(run_result["rc"], run_result["out"], run_result["err"])


rootd_calls = []
rootd_reply = {"value": None, "raise": None}


def fake_rootd_call(verb, _timeout=None, **args):
    rootd_calls.append((verb, _timeout, args))
    if rootd_reply["raise"]:
        raise rootd_reply["raise"]
    return rootd_reply["value"]


real_run = subprocess.run
real_geteuid = os.geteuid
real_call = rootd_client.call
root_radio_calls = []
real_radio_root = system._radio_root


def as_uid(uid):
    os.geteuid = lambda: uid


def reset():
    del run_calls[:]
    del rootd_calls[:]
    del root_radio_calls[:]
    run_result.update({"rc": 0, "out": "", "err": "", "raise": None})


subprocess.run = fake_run
rootd_client.call = fake_rootd_call

try:
    # ---- 1. root path: argv and timeout ------------------------------------
    as_uid(0)
    reset()
    r = system.radio("wifi", True)
    check("root wifi on argv", run_calls[-1][0] == ["rfkill", "unblock", "wifi"], run_calls)
    check("root wifi on timeout 10", run_calls[-1][1].get("timeout") == 10, run_calls)
    check("root wifi on returns tuple", r == (0, "", ""), r)
    system.radio("all", False)
    check("root all off argv", run_calls[-1][0] == ["rfkill", "block", "all"], run_calls)
    system.radio("bluetooth", False)
    check("root bluetooth off argv", run_calls[-1][0] == ["rfkill", "block", "bluetooth"], run_calls)
    check("root path never calls rootd", rootd_calls == [], rootd_calls)

    run_result["raise"] = subprocess.TimeoutExpired(cmd="rfkill", timeout=10)
    r = system.radio("wifi", False)
    check("root timeout -> 124", r == (124, "", "timed out after 10 s"), r)
    run_result["raise"] = None

    run_result.update(rc=1, out="o", err="e")
    check("root nonzero rc passed through", system.radio("all", True) == (1, "o", "e"))
    run_result.update(rc=0, out="", err="")

    # ---- 2. non-root path: rootd call args ---------------------------------
    as_uid(1000)
    reset()
    rootd_reply.update(value=json.dumps([0, "x", "y"]), **{"raise": None})
    r = system.radio("all", False)
    check("non-root returns rootd tuple", r == (0, "x", "y"), r)
    check("non-root call verb and args",
          rootd_calls == [("radio", 40, {"kind": "all", "on": False})], rootd_calls)
    check("non-root never runs rfkill", run_calls == [], run_calls)

    system.radio("wifi", True)
    check("non-root wifi on args", rootd_calls[-1] == ("radio", 40, {"kind": "wifi", "on": True}), rootd_calls)

    rootd_reply.update(value=None, **{"raise": rootd_client.RootdError("boom")})
    r = system.radio("wifi", True)
    check("RootdError -> (1,'',msg)", r == (1, "", "boom"), r)
    rootd_reply.update(value=None, **{"raise": None})

    # ---- 3. system.radio rejects bad input before doing anything -----------
    reset()
    for kind in ("wifi; reboot", "", "WWAN", "WiFi", None, 5):
        try:
            system.radio(kind, True)
            check(f"radio kind {kind!r} rejected", False, "accepted")
        except ValueError:
            check(f"radio kind {kind!r} rejected", True)
    for on in ("yes", 1, 0, None, "on"):
        try:
            system.radio("wifi", on)
            check(f"radio on {on!r} rejected", False, "accepted")
        except ValueError:
            check(f"radio on {on!r} rejected", True)
    check("bad input never reaches rfkill or rootd", run_calls == [] and rootd_calls == [],
          (run_calls, rootd_calls))

    # ---- 4. rootd radio verb ----------------------------------------------
    # The verb calls system._radio_root; record that instead of running rfkill.
    def fake_radio_root(kind, on):
        root_radio_calls.append((kind, on))
        return 0, "out", "err"
    system._radio_root = fake_radio_root
    try:
        def verb(args):
            return json.loads(rootd.handle(json.dumps({"verb": "radio", "args": args}).encode()))

        reset()
        reply = verb({"kind": "wifi", "on": True})
        check("verb good call ok", reply.get("ok") is True, reply)
        check("verb good call reaches _radio_root", root_radio_calls == [("wifi", True)], root_radio_calls)
        check("verb good call reply is [rc,out,err]", json.loads(reply["out"]) == [0, "out", "err"], reply)

        bad = [
            {"kind": "wifi; reboot", "on": True},
            {"kind": "", "on": True},
            {"kind": "WWAN", "on": True},
            {"kind": None, "on": True},
            {"kind": "wifi", "on": "yes"},
            {"kind": "wifi", "on": 1},
            {"kind": "wifi", "on": None},
            {"kind": "wifi"},
            {"on": True},
            {"kind": "wifi", "on": True, "extra": 1},
            {"kind": "wifi", "on": True, "argv": ["sh"]},
        ]
        for args in bad:
            reply = verb(args)
            check(f"verb rejects {json.dumps(args)}", reply.get("ok") is False and "Traceback" not in reply.get("error", ""), reply)
        check("verb bad input never reaches _radio_root", root_radio_calls == [("wifi", True)], root_radio_calls)
    finally:
        system._radio_root = real_radio_root

    # ---- 5. desk.py call sites --------------------------------------------
    desk_path = os.path.join(PKG_DIR, "desk.py")
    src = open(desk_path, encoding="utf-8").read()
    tree = ast.parse(src)
    radio_calls = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "radio" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "system"):
            radio_calls.append([ast.literal_eval(a) if isinstance(a, ast.Constant) else ast.dump(a) for a in node.args])
    kinds = sorted(c[0] for c in radio_calls if c and isinstance(c[0], str))
    check("desk calls system.radio for wifi and all", kinds == ["all", "wifi"], radio_calls)
    check("desk.py has no direct rfkill block/unblock write",
          '"block"' not in src and '"unblock"' not in src)
    check("desk.py keeps rfkill read calls",
          '["rfkill", "list", "wifi"]' in src and '["rfkill", "-n", "-o", "SOFT"]' in src)
    # The verb-level validation also rejects every kind desk could never send.
    check("desk only sends allowed kinds", set(kinds) <= set(system.RADIO_KINDS), kinds)

    # The on/off boolean each desk call sends, checked by name in the AST.
    def arg_call_name(call, idx):
        a = call.args[idx] if len(call.args) > idx else None
        return a.func.id if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) else None
    desk_radio = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "radio" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "system" and node.args and isinstance(node.args[0], ast.Constant)):
            desk_radio[node.args[0].value] = arg_call_name(node, 1)
    check("wifi call passes _wifi_radio_on(v)", desk_radio.get("wifi") == "_wifi_radio_on", desk_radio)
    check("airplane call passes _airplane_radio_on(v)", desk_radio.get("all") == "_airplane_radio_on", desk_radio)

    # Pure helpers: pulled out of desk.py by AST and exec'd alone (desk.py itself is not imported).
    helpers = {n.name: n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name in ("_wifi_radio_on", "_airplane_radio_on")}
    ns = {}
    exec(compile(ast.Module(body=list(helpers.values()), type_ignores=[]), desk_path, "exec"), ns)
    wifi_on, airplane_on = ns["_wifi_radio_on"], ns["_airplane_radio_on"]
    check("airplane on -> radio flag False", airplane_on("on") is False, airplane_on("on"))
    check("airplane off -> radio flag True", airplane_on("off") is True, airplane_on("off"))
    check("wifi on -> radio flag True", wifi_on("on") is True, wifi_on("on"))
    check("wifi off -> radio flag False", wifi_on("off") is False, wifi_on("off"))
finally:
    subprocess.run = real_run
    rootd_client.call = real_call
    os.geteuid = real_geteuid

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
