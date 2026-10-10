#!/usr/bin/env python3
"""Tests for the power and service paths: system.power / system.service (root and non-root), and rootd's power and
service verbs (input checks). os.system, subprocess.run and builtins.open are patched to record calls, so nothing
powers off, reboots, suspends or restarts anything. rootd_client.call is patched for the non-root path.
Run: python3 tools/test-rootd-power.py"""
import builtins
import json
import os
import subprocess
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import rootd, rootd_client, system  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

calls = {"system": [], "run": [], "write": [], "rpc": []}
euid = {"value": 0}
fake = {"system_rc": 0, "open_error": None, "run_error": None, "run_rc": 0, "rpc_reply": None, "rpc_error": None}

_real_geteuid = os.geteuid
_real_system = os.system
_real_run = subprocess.run
_real_open = builtins.open
_real_call = rootd_client.call


class FakeFile:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, text):
        calls["write"].append((self.path, text))
        return len(text)


def fake_open(path, mode="r", *a, **kw):
    if fake["open_error"] is not None:
        raise fake["open_error"]
    if "w" in mode:
        return FakeFile(path)
    return _real_open(path, mode, *a, **kw)


def fake_system(cmd):
    calls["system"].append(cmd)
    return fake["system_rc"]


def fake_run(argv, **kw):
    calls["run"].append((argv, kw))
    if fake["run_error"] is not None:
        raise fake["run_error"]
    return subprocess.CompletedProcess(argv, fake["run_rc"], stdout="out", stderr="err")


def fake_call(verb, _timeout=None, **args):
    calls["rpc"].append((verb, args, _timeout))
    if fake["rpc_error"] is not None:
        raise fake["rpc_error"]
    return fake["rpc_reply"]


def reset():
    for v in calls.values():
        v.clear()
    fake.update(system_rc=0, open_error=None, run_error=None, run_rc=0, rpc_reply=None, rpc_error=None)


def install():
    os.geteuid = lambda: euid["value"]
    os.system = fake_system
    subprocess.run = fake_run
    builtins.open = fake_open
    rootd_client.call = fake_call


def uninstall():
    os.geteuid = _real_geteuid
    os.system = _real_system
    subprocess.run = _real_run
    builtins.open = _real_open
    rootd_client.call = _real_call


def check(label, cond, detail=""):
    assert cond, f"{label}: {detail}"
    print(f"ok {label}")


def expect_value_error(label, fn):
    try:
        fn()
    except ValueError as e:
        assert "Traceback" not in str(e), label
        print(f"ok {label}: {e}")
        return
    raise AssertionError(f"{label}: no ValueError raised")


install()
try:
    # 1. Root path: each action runs exactly its literal command or write.
    euid["value"] = 0
    reset()
    check("root poweroff returns ok", system.power("poweroff") == (True, ""))
    check("root poweroff is os.system('poweroff') only", calls["system"] == ["poweroff"] and calls["run"] == []
          and calls["write"] == [], f"{calls}")

    reset()
    check("root reboot returns ok", system.power("reboot") == (True, ""))
    check("root reboot is os.system('reboot') only", calls["system"] == ["reboot"] and calls["run"] == []
          and calls["write"] == [], f"{calls}")

    reset()
    fake["system_rc"] = 256
    ok, msg = system.power("reboot")
    check("root reboot nonzero exit is not ok", ok is False and "256" in msg, f"{ok!r} {msg!r}")

    reset()
    check("root suspend returns ok", system.power("suspend") == (True, ""))
    check("root suspend runs sync(timeout 30) then writes mem",
          calls["run"] == [(["sync"], {"timeout": 30})] and calls["write"] == [("/sys/power/state", "mem")]
          and calls["system"] == [], f"{calls}")

    reset()
    fake["open_error"] = OSError("no suspend here")
    check("root suspend OSError -> (False, msg)", system.power("suspend") == (False, "no suspend here"))

    # 2. Bad power actions never reach os.system, subprocess or open.
    for bad in ("shutdown", "halt", "", "Poweroff", "poweroff; rm -rf /"):
        reset()
        expect_value_error(f"power rejects {bad!r}", lambda b=bad: system.power(b))
        assert calls["system"] == [] and calls["run"] == [] and calls["write"] == [] and calls["rpc"] == [], calls
    print("ok power rejects: no command or write for any bad action")

    # 3. Non-root path: the rootd call, with the reply parsed and RootdError turned into (False, msg).
    euid["value"] = 1000
    reset()
    fake["rpc_reply"] = json.dumps([True, ""])
    check("non-root power returns rootd reply", system.power("reboot") == (True, ""))
    check("non-root power sends rootd verb power", calls["rpc"] == [("power", {"action": "reboot"}, 60)], f"{calls}")
    check("non-root power runs no command here", calls["system"] == [] and calls["run"] == [] and calls["write"] == [])

    reset()
    fake["rpc_error"] = RootdError("the system helper is not running")
    check("non-root power RootdError -> (False, msg)",
          system.power("suspend") == (False, "the system helper is not running"))

    # 4. service: root argv and timeout; non-root rootd call.
    euid["value"] = 0
    reset()
    check("root service returns rc/out/err", system.service("llmos-model", "restart") == (0, "out", "err"))
    check("root service argv is rc-service name action, timeout 60",
          calls["run"] == [(["rc-service", "llmos-model", "restart"],
                            {"capture_output": True, "text": True, "timeout": 60})], f"{calls}")

    reset()
    system.service("llmos-model", "stop", timeout=120)
    check("root service timeout is passed through", calls["run"][0][1]["timeout"] == 120, f"{calls}")

    reset()
    fake["run_error"] = subprocess.TimeoutExpired(["rc-service"], 60)
    check("root service timeout -> (124, '', msg)",
          system.service("llmos-model", "start") == (124, "", "timed out after 60 s"))

    reset()
    fake["run_error"] = OSError("no rc-service")
    check("root service OSError -> (1, '', msg)", system.service("llmos-model", "start") == (1, "", "no rc-service"))

    euid["value"] = 1000
    reset()
    fake["rpc_reply"] = json.dumps([0, "done", ""])
    check("non-root service returns rootd reply", system.service("llmos-model", "restart") == (0, "done", ""))
    check("non-root service sends rootd verb service with timeout+30 wait",
          calls["rpc"] == [("service", {"name": "llmos-model", "action": "restart", "timeout": 60}, 90)],
          f"{calls}")
    check("non-root service runs no command here", calls["run"] == [] and calls["system"] == [])

    reset()
    fake["rpc_error"] = RootdError("busy")
    check("non-root service RootdError -> (1, '', msg)", system.service("llmos-model", "stop") == (1, "", "busy"))

    # 5. rootd verbs: good input reaches the system helper; bad input is refused before anything runs.
    euid["value"] = 0
    seen = []
    real_power_root, real_service_root = system._power_root, system._service_root
    system._power_root = lambda action: (seen.append(("power", action)) or (True, ""))
    system._service_root = lambda name, action, timeout=60: (seen.append(("service", name, action, timeout))
                                                             or (0, "o", "e"))
    try:
        reset()
        check("rootd power verb poweroff", json.loads(rootd.VERBS["power"]({"action": "poweroff"})) == [True, ""])
        check("rootd power verb reboot", json.loads(rootd.VERBS["power"]({"action": "reboot"})) == [True, ""])
        check("rootd power verb suspend", json.loads(rootd.VERBS["power"]({"action": "suspend"})) == [True, ""])
        check("rootd power verb calls _power_root only with the three literals",
              seen == [("power", "poweroff"), ("power", "reboot"), ("power", "suspend")], f"{seen}")

        for bad in ("shutdown", "halt", "", None, 1, ["reboot"]):
            seen.clear()
            reply = rootd._run(json.dumps({"verb": "power", "args": {"action": bad}}).encode())[1]
            check(f"rootd power refuses {bad!r}", reply["ok"] is False and reply["error"] == "bad args: action"
                  and seen == [], f"{reply} {seen}")
        seen.clear()
        reply = rootd._run(json.dumps({"verb": "power", "args": {}}).encode())[1]
        check("rootd power refuses missing action", reply["ok"] is False and seen == [], f"{reply}")

        seen.clear()
        check("rootd service verb default timeout 60",
              json.loads(rootd.VERBS["service"]({"name": "llmos-model", "action": "restart"})) == [0, "o", "e"]
              and seen == [("service", "llmos-model", "restart", 60)], f"{seen}")
        seen.clear()
        for action in ("start", "stop", "restart"):
            rootd.VERBS["service"]({"name": "llmos-model", "action": action, "timeout": 5})
        check("rootd service verb accepts start/stop/restart with timeout 5",
              seen == [("service", "llmos-model", a, 5) for a in ("start", "stop", "restart")], f"{seen}")

        for bad_name in ("tor", "sshd", "llmos-model;x", "llmos-model ", "", None):
            seen.clear()
            reply = rootd._run(json.dumps({"verb": "service", "args": {"name": bad_name, "action": "restart"}})
                               .encode())[1]
            check(f"rootd service refuses name {bad_name!r}", reply["ok"] is False and seen == [], f"{reply}")
        for bad_action in ("enable", "reload", "", "restart;x", None):
            seen.clear()
            reply = rootd._run(json.dumps({"verb": "service", "args": {"name": "llmos-model",
                                                                       "action": bad_action}}).encode())[1]
            check(f"rootd service refuses action {bad_action!r}", reply["ok"] is False and seen == [], f"{reply}")
        for bad_t in (4, 301, True, "60", 60.0, None):
            seen.clear()
            reply = rootd._run(json.dumps({"verb": "service", "args": {"name": "llmos-model", "action": "stop",
                                                                       "timeout": bad_t}}).encode())[1]
            check(f"rootd service refuses timeout {bad_t!r}", reply["ok"] is False and seen == [], f"{reply}")
    finally:
        system._power_root, system._service_root = real_power_root, real_service_root

    # 6. The real service argv (not patched): only a list, never a shell string, and only the validated name.
    euid["value"] = 0
    reset()
    rootd.VERBS["service"]({"name": "llmos-model", "action": "start", "timeout": 30})
    argv = calls["run"][0][0]
    check("rootd service argv is a list of three literals", isinstance(argv, list)
          and argv == ["rc-service", "llmos-model", "start"], f"{argv}")
    check("no os.system call anywhere in the service path", calls["system"] == [], f"{calls}")
finally:
    uninstall()

print("all good")
