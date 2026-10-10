#!/usr/bin/env python3
"""Tests for the printer path: system.printer_add / printer_default, rootd's printer verbs, and syspanels' callers.

lpadmin is never run for real: subprocess.run and the rootd client are replaced with recorders.
Run: python3 tools/test-rootd-printer.py
"""
import json
import os
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.abspath(os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos"))

# Load the real package files under the name "llmos" so their relative imports work.
pkg = types.ModuleType("llmos")
pkg.__path__ = [PKG_DIR]
sys.modules["llmos"] = pkg
# version_line is generated at build time (not in the source tree); syspanels only needs it for about().
version_line = types.ModuleType("llmos.version_line")
version_line.version_line = lambda: "test"
sys.modules["llmos.version_line"] = version_line
pkg.version_line = version_line
from llmos import rootd, rootd_client, syspanels, system  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

rootd.LOG_PATH = os.path.join(tempfile.mkdtemp(prefix="rootd-printer-test-"), "rootd.log")

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
real_add_root = system._printer_add_root
real_default_root = system._printer_default_root
root_calls = []


def as_uid(uid):
    os.geteuid = lambda: uid


def reset():
    del run_calls[:]
    del rootd_calls[:]
    del root_calls[:]
    run_result.update({"rc": 0, "out": "", "err": "", "raise": None})
    rootd_reply.update({"value": None, "raise": None})


subprocess.run = fake_run
rootd_client.call = fake_rootd_call

try:
    # ---- 1. root path: argv and timeouts -----------------------------------
    as_uid(0)
    reset()
    r = system.printer_add("Office_1", "ipp://printer.local/ipp/print")
    check("root add argv", run_calls[-1][0] == ["lpadmin", "-p", "Office_1", "-E", "-v", "ipp://printer.local/ipp/print", "-m", "everywhere"], run_calls)
    check("root add timeout 60", run_calls[-1][1].get("timeout") == 60, run_calls)
    check("root add returns tuple", r == (0, "", ""), r)
    check("root add never calls rootd", rootd_calls == [], rootd_calls)

    r = system.printer_default("Office_1")
    check("root default argv", run_calls[-1][0] == ["lpadmin", "-d", "Office_1"], run_calls)
    check("root default timeout 20", run_calls[-1][1].get("timeout") == 20, run_calls)
    system.printer_default("Office_1", timeout=10)
    check("root default timeout 10", run_calls[-1][1].get("timeout") == 10, run_calls)
    check("root default returns tuple", r == (0, "", ""), r)

    run_result["raise"] = subprocess.TimeoutExpired(cmd="lpadmin", timeout=60)
    r = system.printer_add("Office_1", "ipp://printer.local/ipp/print")
    check("root add timeout -> 124", r[0] == 124 and r[2] == "it took too long to answer", r)
    r = system.printer_default("Office_1")
    check("root default timeout -> 124", r[0] == 124, r)
    run_result["raise"] = None

    run_result.update(rc=1, out="o", err="e")
    check("root nonzero rc passed through", system.printer_add("Office_1", "ipp://h/p") == (1, "o", "e"))
    run_result.update(rc=0, out="", err="")

    # ---- 2. non-root path: rootd call args ---------------------------------
    as_uid(1000)
    reset()
    rootd_reply.update(value=json.dumps([0, "x", "y"]))
    r = system.printer_add("Office_1", "ipp://printer.local/ipp/print")
    check("non-root add returns rootd tuple", r == (0, "x", "y"), r)
    check("non-root add verb and args", rootd_calls == [("printer_add", 120, {"name": "Office_1", "uri": "ipp://printer.local/ipp/print"})], rootd_calls)
    check("non-root add never runs lpadmin", run_calls == [], run_calls)

    system.printer_default("Office_1")
    check("non-root default verb and args", rootd_calls[-1] == ("printer_default", 50, {"name": "Office_1", "timeout": 20}), rootd_calls)
    system.printer_default("Office_1", timeout=10)
    check("non-root default timeout 10 args", rootd_calls[-1] == ("printer_default", 40, {"name": "Office_1", "timeout": 10}), rootd_calls)
    check("non-root default never runs lpadmin", run_calls == [], run_calls)

    rootd_reply.update(value=None, **{"raise": RootdError("boom")})
    check("RootdError add -> (1,'',msg)", system.printer_add("Office_1", "ipp://h/p") == (1, "", "boom"))
    check("RootdError default -> (1,'',msg)", system.printer_default("Office_1") == (1, "", "boom"))
    rootd_reply.update(value=None, **{"raise": None})

    # ---- 3. system rejects bad input before doing anything -----------------
    reset()
    bad_names = ["-x", "a b", "../p", "a" * 65, "", "p;rm", None, 5]
    bad_uris = ["file:///etc/shadow", "-E", "ipp://h/p q", "ipp://h/\n", "", "ipp://", "ipp://h/p\x00", None]
    for n in bad_names:
        check(f"system add name {n!r} rejected", system.printer_add(n, "ipp://h/p")[0] == 1)
        check(f"system default name {n!r} rejected", system.printer_default(n)[0] == 1)
    for u in bad_uris:
        check(f"system add uri {u!r} rejected", system.printer_add("p", u)[0] == 1)
    for t in (4, 121, True, "20", None):
        check(f"system default timeout {t!r} rejected", system.printer_default("p", timeout=t)[0] == 1)
    check("bad input never reaches lpadmin or rootd", run_calls == [] and rootd_calls == [], (run_calls, rootd_calls))

    # ---- 4. rootd printer verbs --------------------------------------------
    # The verbs call system._printer_*_root; record that instead of running lpadmin.
    def fake_add_root(name, uri):
        root_calls.append(("add", name, uri))
        return 0, "out", "err"

    def fake_default_root(name, timeout):
        root_calls.append(("default", name, timeout))
        return 0, "out", "err"

    system._printer_add_root = fake_add_root
    system._printer_default_root = fake_default_root
    try:
        def verb(verb_name, args):
            return json.loads(rootd.handle(json.dumps({"verb": verb_name, "args": args}).encode()))

        reset()
        reply = verb("printer_add", {"name": "Office_1", "uri": "ipp://printer.local/ipp/print"})
        check("verb add good ok", reply.get("ok") is True, reply)
        check("verb add reaches _printer_add_root", root_calls == [("add", "Office_1", "ipp://printer.local/ipp/print")], root_calls)
        check("verb add reply is [rc,out,err]", json.loads(reply["out"]) == [0, "out", "err"], reply)

        reply = verb("printer_default", {"name": "Office_1"})
        check("verb default good ok", reply.get("ok") is True, reply)
        check("verb default default timeout 20", root_calls[-1] == ("default", "Office_1", 20), root_calls)
        verb("printer_default", {"name": "Office_1", "timeout": 5})
        check("verb default timeout 5 accepted", root_calls[-1] == ("default", "Office_1", 5), root_calls)
        verb("printer_default", {"name": "Office_1", "timeout": 120})
        check("verb default timeout 120 accepted", root_calls[-1] == ("default", "Office_1", 120), root_calls)

        before = len(root_calls)
        bad = [
            ("printer_add", {"name": "-x", "uri": "ipp://h/p"}),
            ("printer_add", {"name": "a b", "uri": "ipp://h/p"}),
            ("printer_add", {"name": "../p", "uri": "ipp://h/p"}),
            ("printer_add", {"name": "a" * 65, "uri": "ipp://h/p"}),
            ("printer_add", {"name": "", "uri": "ipp://h/p"}),
            ("printer_add", {"name": None, "uri": "ipp://h/p"}),
            ("printer_add", {"name": "p"}),
            ("printer_add", {"uri": "ipp://h/p"}),
            ("printer_add", {"name": "p", "uri": "file:///etc/shadow"}),
            ("printer_add", {"name": "p", "uri": "-E"}),
            ("printer_add", {"name": "p", "uri": "ipp://h/p q"}),
            ("printer_add", {"name": "p", "uri": "ipp://h/\n"}),
            ("printer_add", {"name": "p", "uri": ""}),
            ("printer_add", {"name": "p", "uri": "ipp://h/p", "extra": 1}),
            ("printer_add", {"name": "p", "uri": "ipp://h/p", "argv": ["sh"]}),
            ("printer_default", {"name": "-x"}),
            ("printer_default", {"name": "a b"}),
            ("printer_default", {"name": "../p"}),
            ("printer_default", {"name": "a" * 65}),
            ("printer_default", {"name": "p", "timeout": 4}),
            ("printer_default", {"name": "p", "timeout": 121}),
            ("printer_default", {"name": "p", "timeout": "20"}),
            ("printer_default", {"name": "p", "timeout": True}),
            ("printer_default", {"name": "p", "extra": 1}),
            ("printer_default", {"name": "p", "argv": ["sh"]}),
        ]
        for verb_name, args in bad:
            reply = verb(verb_name, args)
            check(f"verb rejects {verb_name} {json.dumps(args)}", reply.get("ok") is False and "Traceback" not in reply.get("error", ""), reply)
        check("verb bad input never reaches _printer_*_root", len(root_calls) == before, root_calls[before:])
    finally:
        system._printer_add_root = real_add_root
        system._printer_default_root = real_default_root

    # ---- 5. syspanels callers: same names, same uris, same replies --------
    sys_calls = []
    sys_reply = {"add": (0, "", ""), "default": (0, "", "")}

    def fake_printer_add(name, uri):
        sys_calls.append(("add", name, uri))
        return sys_reply["add"]

    def fake_printer_default(name, timeout=20):
        sys_calls.append(("default", name, timeout))
        return sys_reply["default"]

    real_sys_add, real_sys_default = system.printer_add, system.printer_default
    system.printer_add = fake_printer_add
    system.printer_default = fake_printer_default
    try:
        reset()
        ok, msg = syspanels.add_printer("ipp://printer.local/ipp/print")
        check("syspanels add name and uri", sys_calls[0] == ("add", "printer", "ipp://printer.local/ipp/print"), sys_calls)
        check("syspanels add sets default with 10 s", sys_calls[1] == ("default", "printer", 10), sys_calls)
        check("syspanels add reply", (ok, msg) == (True, "printer is set up and is the default printer"), (ok, msg))

        del sys_calls[:]
        sys_reply["add"] = (1, "", "  no such device \n")
        ok, msg = syspanels.add_printer("ipp://printer.local/ipp/print")
        check("syspanels add failure stops before default", sys_calls == [("add", "printer", "ipp://printer.local/ipp/print")], sys_calls)
        check("syspanels add failure reply", (ok, msg) == (False, "no such device"), (ok, msg))
        sys_reply["add"] = (1, "", "")
        ok, msg = syspanels.add_printer("ipp://printer.local/ipp/print")
        check("syspanels add empty err reply", (ok, msg) == (False, "the printer could not be added"), (ok, msg))
        sys_reply["add"] = (0, "", "")

        del sys_calls[:]
        ok, msg = syspanels.default_printer("Office_1")
        check("syspanels default call", sys_calls == [("default", "Office_1", 20)], sys_calls)
        check("syspanels default reply", (ok, msg) == (True, "Office_1 is now the default printer."), (ok, msg))
        sys_reply["default"] = (1, "", "")
        ok, msg = syspanels.default_printer("Office_1")
        check("syspanels default failure reply", (ok, msg) == (False, "That did not work."), (ok, msg))
    finally:
        system.printer_add, system.printer_default = real_sys_add, real_sys_default

    # syspanels no longer runs lpadmin itself
    src = open(os.path.join(PKG_DIR, "syspanels.py"), encoding="utf-8").read()
    check("syspanels has no direct lpadmin argv", '"lpadmin"' not in src)
finally:
    subprocess.run = real_run
    rootd_client.call = real_call
    os.geteuid = real_geteuid

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
