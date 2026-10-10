#!/usr/bin/env python3
"""Host-side test: the three power/service callers go through system.power / system.service.
Console.shutdown calls system.power("poweroff"|"reboot") then sys.exit(0);
syspanels.sleep calls system.power("suspend") and returns None as before (errors stay silent);
models.use calls system.service("llmos-model", "restart", timeout=60) and returns the model as before.
system.power and system.service are patched in every case, so nothing powers off, reboots, suspends or restarts.
config.settings is replaced by a stub so models.use does not write the real settings file.
Run: python3 tools/test-power-callers.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
import tempfile
import types

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import console, config, models, syspanels, system, ui  # noqa: E402

real_power = system.power
real_service = system.service
real_settings = config.settings
real_line = ui.line
real_exit = sys.exit

calls = []          # (verb, args, kwargs)
scripted = []       # replies for power / service, in order
failures = []


class ExitCalled(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class StubSettings:
    def __init__(self):
        self.data = {}

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        self.data[k] = v

    def all(self):
        return dict(self.data)


def fake_power(action):
    calls.append(("power", action, {}))
    return scripted.pop(0)


def fake_service(name, action, timeout=60):
    calls.append(("service", (name, action), {"timeout": timeout}))
    return scripted.pop(0)


def fake_exit(code=0):
    raise ExitCalled(code)


def check(label, cond, detail=""):
    if cond:
        print("ok " + label)
    else:
        failures.append(label)
        print("FAIL " + label + (" -- " + detail if detail else ""))


def install():
    system.power = fake_power
    system.service = fake_service
    config.settings = StubSettings()
    ui.line = lambda *a, **k: None
    sys.exit = fake_exit


def uninstall():
    system.power = real_power
    system.service = real_service
    config.settings = real_settings
    ui.line = real_line
    sys.exit = real_exit


def run_shutdown(how, reply):
    calls.clear()
    scripted[:] = [reply]
    self_stub = types.SimpleNamespace(ctx=types.SimpleNamespace(after_turn=None))
    try:
        console.Console.shutdown(self_stub, how)
        return "returned"
    except ExitCalled as e:
        return ("exit", e.code)


def test_shutdown():
    try:
        for how, action in (("poweroff", "poweroff"), ("reboot", "reboot")):
            for reply in ((True, "powering off"), (False, "no permission")):
                outcome = run_shutdown(how, reply)
                check(f"shutdown {how} with {reply[0]}: power({action!r}) called once",
                      calls == [("power", action, {})], repr(calls))
                check(f"shutdown {how} with {reply[0]}: exits 0 after the call",
                      outcome == ("exit", 0), repr(outcome))
    finally:
        pass


def test_sleep():
    for reply in ((True, "suspended"), (False, "no suspend")):
        calls.clear()
        scripted[:] = [reply]
        out = syspanels.sleep()
        check(f"sleep with {reply[0]}: power('suspend') called once",
              calls == [("power", "suspend", {})], repr(calls))
        check(f"sleep with {reply[0]}: returns None as before",
              out is None, repr(out))


def test_use():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    model = {"id": "test-model", "name": "Test Model", "file": "x.gguf", "ram_gb": 1}
    real_by_id, real_host, real_ram, real_path = models.by_id, models.host_mode, models.ram_gb, models.path_of
    models.by_id = lambda mid: model if mid == "test-model" else None
    models.host_mode = lambda: False
    models.ram_gb = lambda: 8.0
    models.path_of = lambda m: tmp.name
    try:
        for reply in ((0, "restarted", ""), (1, "", "rc-service failed"), (124, "", "timed out after 60 s")):
            calls.clear()
            scripted[:] = [reply]
            out = models.use("test-model")
            check(f"use with rc {reply[0]}: service('llmos-model','restart', timeout=60) called once",
                  calls == [("service", ("llmos-model", "restart"), {"timeout": 60})], repr(calls))
            check(f"use with rc {reply[0]}: returns the model dict as before",
                  out is model, repr(out))
        check("use stored the model id in the stub settings",
              config.settings.get("model") == "test-model", repr(config.settings.get("model")))
    finally:
        models.by_id, models.host_mode, models.ram_gb, models.path_of = real_by_id, real_host, real_ram, real_path
        os.unlink(tmp.name)


def main():
    install()
    try:
        test_shutdown()
        test_sleep()
        test_use()
    finally:
        uninstall()
    if failures:
        print("FAILED: " + ", ".join(failures))
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
