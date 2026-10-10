#!/usr/bin/env python3
"""Host-side test that config.Settings.set writes settings.json under ETC directly while ETC is writable, and
through rootd's write_setting_file verb (rootd_client.call) when it is not; a RootdError becomes OSError.
Run: python3 tools/test-config-etc.py"""
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import config, rootd_client  # noqa: E402

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print(f"ok {name}")
    else:
        fails += 1
        print(f"FAIL {name} {detail}")


def point_etc(d):
    config.ETC = d
    config.settings.path = os.path.join(d, "settings.json")


real_call = rootd_client.call

# (a) writable ETC: direct write, rootd never called
a = tempfile.mkdtemp(prefix="llmos-etc-a-")
point_etc(a)


def no_rootd(*args, **kwargs):
    raise AssertionError("rootd_client.call must not be called for a writable ETC")


rootd_client.call = no_rootd
try:
    config.settings.set("language", "Français")
    got = json.load(open(os.path.join(a, "settings.json"), encoding="utf-8"))
    check("a writable ETC writes directly", got.get("language") == "Français", repr(got))
except Exception as e:
    check("a writable ETC writes directly", False, repr(e))
finally:
    rootd_client.call = real_call

# (b) and (c): ETC not writable. Root bypasses permissions, so these need a non-root process.
if os.geteuid() == 0:
    print("skip (b) (c): running as root, ETC is always writable here")
else:
    b = tempfile.mkdtemp(prefix="llmos-etc-b-")
    ro = os.path.join(b, "ro")
    os.makedirs(ro)
    os.chmod(ro, 0o500)
    point_etc(ro)
    calls = []

    def record(verb, **args):
        calls.append((verb, args))
        return "ok"

    rootd_client.call = record
    try:
        config.settings.set("autonomy", "hands-on")
        want = json.dumps({"autonomy": "hands-on"}, ensure_ascii=False, indent=1)
        check("b non-writable ETC goes through rootd",
              calls == [("write_setting_file", {"name": "settings.json", "text": want})], repr(calls))
    except Exception as e:
        check("b non-writable ETC goes through rootd", False, repr(e))
    finally:
        rootd_client.call = real_call

    def refuse(verb, **args):
        raise rootd_client.RootdError("the system helper refused")

    rootd_client.call = refuse
    try:
        config.settings.set("autonomy", "hands-off")
        check("c RootdError becomes OSError", False, "no exception raised")
    except OSError as e:
        check("c RootdError becomes OSError", "refused" in str(e), repr(e))
    except Exception as e:
        check("c RootdError becomes OSError", False, repr(e))
    finally:
        rootd_client.call = real_call
        os.chmod(ro, 0o700)
    shutil.rmtree(b, ignore_errors=True)

# (d) writable ETC: _remove_etc unlinks directly, missing file ok, rootd never called
rootd_client.call = no_rootd
try:
    point_etc(a)
    config.write_conduct("be kind\n")
    config.remove_conduct()
    check("d writable ETC removes conduct.txt directly", not os.path.exists(os.path.join(a, "conduct.txt")))
    config.remove_conduct()
    check("d removing a missing conduct.txt is fine", True)
except Exception as e:
    check("d writable ETC removes conduct.txt directly", False, repr(e))
finally:
    rootd_client.call = real_call

# (e) non-writable ETC: remove goes through rootd's remove_setting_file verb
if os.geteuid() != 0:
    e_dir = tempfile.mkdtemp(prefix="llmos-etc-e-")
    e_ro = os.path.join(e_dir, "ro")
    os.makedirs(e_ro)
    open(os.path.join(e_ro, "conduct.txt"), "w").write("x")
    os.chmod(e_ro, 0o500)
    point_etc(e_ro)
    rm_calls = []

    def record_rm(verb, **args):
        rm_calls.append((verb, args))
        return "ok"

    rootd_client.call = record_rm
    try:
        config.remove_conduct()
        check("e non-writable ETC removes through rootd",
              rm_calls == [("remove_setting_file", {"name": "conduct.txt"})], repr(rm_calls))
    except Exception as e:
        check("e non-writable ETC removes through rootd", False, repr(e))
    finally:
        rootd_client.call = real_call
        os.chmod(e_ro, 0o700)
    shutil.rmtree(e_dir, ignore_errors=True)

shutil.rmtree(a, ignore_errors=True)
shutil.rmtree(home, ignore_errors=True)
if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
