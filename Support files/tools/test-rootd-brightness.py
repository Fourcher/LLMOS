#!/usr/bin/env python3
"""Tests for the backlight write path: devices.brightness (root and non-root), devices._write_backlight_root, and
rootd's set_backlight verb (input checks). devices.BACKLIGHT_DIR points at a temp dir holding a fake backlight, and
rootd_client.call is patched for the non-root path, so no real sysfs is touched.
Run: python3 tools/test-rootd-brightness.py"""
import os
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import devices, rootd, rootd_client  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

tmp = tempfile.mkdtemp(prefix="backlight-test-")
bl = os.path.join(tmp, "backlight")
dev = os.path.join(bl, "intel_backlight")
os.makedirs(dev)
with open(os.path.join(dev, "max_brightness"), "w") as f:
    f.write("400\n")
with open(os.path.join(dev, "brightness"), "w") as f:
    f.write("100\n")

_real_geteuid = os.geteuid
_real_call = rootd_client.call
euid = {"value": 0}
rpc = []
fake = {"error": None}


def fake_call(verb, _timeout=None, **args):
    rpc.append((verb, args))
    if fake["error"] is not None:
        raise fake["error"]
    return "ok"


def read_level():
    with open(os.path.join(dev, "brightness")) as f:
        return int(f.read())


def check(cond, label):
    if not cond:
        print("FAIL", label)
        sys.exit(1)
    print("ok", label)


devices.BACKLIGHT_DIR = bl
os.geteuid = lambda: euid["value"]
rootd_client.call = fake_call
try:
    # root path: brightness() writes the target level directly
    euid["value"] = 0
    msg = devices.brightness(percent=50)
    check(read_level() == 200 and rpc == [] and msg == "Brightness set to 50%.", "root path writes 200 directly")

    # _write_backlight_root writes the raw value
    devices._write_backlight_root("intel_backlight", 321)
    check(read_level() == 321, "_write_backlight_root writes the value")
    with open(os.path.join(dev, "brightness"), "w") as f:
        f.write("100\n")

    # non-root path: brightness() sends the rootd call and leaves the file alone
    euid["value"] = 1000
    msg = devices.brightness(percent=25)
    check(rpc == [("set_backlight", {"device": "intel_backlight", "value": 100})] and read_level() == 100
          and msg == "Brightness set to 25%.", "non-root path sends set_backlight, file untouched")

    # a refused rootd call surfaces as OSError, as a failed direct write did
    rpc.clear()
    fake["error"] = RootdError("bad args: value")
    try:
        devices.brightness(percent=10)
        check(False, "RootdError becomes OSError")
    except OSError as e:
        check("bad args: value" in str(e), "RootdError becomes OSError")
    fake["error"] = None

    # rootd verb: good input writes through devices
    euid["value"] = 0
    check(rootd.set_backlight({"device": "intel_backlight", "value": 400}) == "ok" and read_level() == 400,
          "verb accepts value == max")
    check(rootd.set_backlight({"device": "intel_backlight", "value": 0}) == "ok" and read_level() == 0,
          "verb accepts 0")

    bad = [
        ("device '../../etc'", {"device": "../../etc", "value": 5}),
        ("device 'intel_backlight/../x'", {"device": "intel_backlight/../x", "value": 5}),
        ("device ''", {"device": "", "value": 5}),
        ("device '.'", {"device": ".", "value": 5}),
        ("device '..'", {"device": "..", "value": 5}),
        ("device 'missing'", {"device": "missing", "value": 5}),
        ("device not a string", {"device": 3, "value": 5}),
        ("value -1", {"device": "intel_backlight", "value": -1}),
        ("value 401", {"device": "intel_backlight", "value": 401}),
        ("value '50'", {"device": "intel_backlight", "value": "50"}),
        ("value True", {"device": "intel_backlight", "value": True}),
        ("value missing", {"device": "intel_backlight"}),
    ]
    before = read_level()
    for label, args in bad:
        try:
            rootd.set_backlight(args)
            check(False, f"verb rejects {label}")
        except ValueError as e:
            check(str(e).startswith("bad args:"), f"verb rejects {label}")
    check(read_level() == before, "rejected requests write nothing")

    # the verb is registered
    check(rootd.VERBS.get("set_backlight") is rootd.set_backlight, "set_backlight is in VERBS")
finally:
    os.geteuid = _real_geteuid
    rootd_client.call = _real_call
    shutil.rmtree(tmp, ignore_errors=True)

print("all good")
