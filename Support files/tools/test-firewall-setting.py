#!/usr/bin/env python3
"""Host-side test of change_setting "firewall" (tools.py): the owner can switch the firewall off (inbound open) and on.
- settings are kept in a temp LLMOS_HOME; the write goes to config.settings (checked in the file on disk).
- the apply path is rootd_client.call("firewall_apply", ...), patched to record the firewall value; nothing runs nft.
- aliases: off/disable/disabled/no -> off; on/enable/enabled/yes -> on; anything else ("banana") is an error and
  stores nothing and applies nothing.
- the risk class: off while on is SECURITY (asked under balanced); on, or off while already off, is SAFE.
- internet stays as it was.
Run: python3 tools/test-firewall-setting.py  (no VM, no nft). Exit status 0 = pass."""
import json
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import config, rootd_client, tools  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

fails = 0
OFF_MSG = ("The firewall is off: other computers can now connect to this one. "
           "Say “turn the firewall on” to put it back.")
ON_MSG = "The firewall is on again."


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


class Ctx:
    current_request = "turn the firewall off"
    is_desk = True


sent = []


def record(verb, _timeout=None, **kw):
    sent.append((verb, kw))
    return json.dumps([True, ""])


real_call = rootd_client.call
rootd_client.call = record
real_undo = tools._undo_push
tools._undo_push = lambda *a, **k: None
try:
    config.settings.set("internet", "ask")
    config.settings.set("firewall", "on")
    check(os.path.exists(config.settings.path) and config.settings.path.startswith(home),
          f"settings live in the temp home: {config.settings.path}")

    got = tools.change_setting({"setting": "firewall", "value": "off"}, Ctx())
    check(got == OFF_MSG, f"off -> exact reply: {got!r}")
    check(config.settings.get("firewall") == "off", "off is saved to the settings file")
    check(sent == [("firewall_apply", {"internet": "ask", "firewall": "off"})], f"off applies with firewall off: {sent}")
    check(config.settings.get("internet") == "ask", "internet is unchanged by the firewall change")

    sent.clear()
    got = tools.change_setting({"setting": "firewall", "value": "on"}, Ctx())
    check(got == ON_MSG, f"on -> exact reply: {got!r}")
    check(config.settings.get("firewall") == "on", "on is saved")
    check(sent == [("firewall_apply", {"internet": "ask", "firewall": "on"})], f"on applies with firewall on: {sent}")

    for alias in ("off", "disable", "disabled", "no", "OFF", " Disable "):
        sent.clear()
        tools.change_setting({"setting": "firewall", "value": alias}, Ctx())
        check(config.settings.get("firewall") == "off" and sent[-1][1]["firewall"] == "off", f"alias {alias!r} -> off")
    for alias in ("on", "enable", "enabled", "yes", "ON"):
        sent.clear()
        tools.change_setting({"setting": "firewall", "value": alias}, Ctx())
        check(config.settings.get("firewall") == "on" and sent[-1][1]["firewall"] == "on", f"alias {alias!r} -> on")

    config.settings.set("firewall", "on")
    sent.clear()
    got = tools.change_setting({"setting": "firewall", "value": "banana"}, Ctx())
    check(got.startswith("error:") and "firewall" in got, f"banana -> error: {got!r}")
    check(config.settings.get("firewall") == "on", "banana stores nothing")
    check(sent == [], f"banana applies nothing: {sent}")

    def boom(verb, _timeout=None, **kw):
        raise RootdError("the system helper is not running")
    rootd_client.call = boom
    got = tools.change_setting({"setting": "firewall", "value": "off"}, Ctx())
    check(got == OFF_MSG + " (couldn't change it: the system helper is not running)", f"failure wording: {got!r}")
    rootd_client.call = record

    # risk class: loosening (off while on) is SECURITY; everything else SAFE
    config.settings.set("firewall", "on")
    check(tools._policy_risk("firewall", "off") == tools.SECURITY, "off while on -> SECURITY")
    check(tools._policy_risk("firewall", "disable") == tools.SECURITY, "disable while on -> SECURITY")
    check(tools._policy_risk("firewall", "on") == tools.SAFE, "on while on -> SAFE")
    config.settings.set("firewall", "off")
    check(tools._policy_risk("firewall", "off") == tools.SAFE, "off while already off -> SAFE")
    check(tools._policy_risk("firewall", "on") == tools.SAFE, "on while off -> SAFE")

    # the request must mention the firewall (same guard as the other settings)
    class Other(Ctx):
        current_request = "what time is it"
    config.settings.set("firewall", "on")
    got = tools.change_setting({"setting": "firewall", "value": "off"}, Other())
    check(got.startswith("not done") and config.settings.get("firewall") == "on", f"unrelated request is refused: {got!r}")

    # undo: the real undo push is used from here on
    tools._undo_push = real_undo
    rootd_client.call = record

    class FwOff(Ctx):
        current_request = "turn the firewall off"

    class NetOff(Ctx):
        current_request = "turn the internet off"

    # firewall off -> undo: back to on, and the firewall is re-applied as on
    config.settings.set("internet", "ask")
    config.settings.set("firewall", "on")
    tools._UNDO.clear()
    tools.change_setting({"setting": "firewall", "value": "off"}, FwOff())
    check(config.settings.get("firewall") == "off", "setup: firewall is off before undo")
    sent.clear()
    got = tools.undo({}, Ctx())
    check(got == "undone: the settings are back to how they were", f"undo reply: {got!r}")
    check(config.settings.get("firewall") == "on", f"undo puts firewall back to on: {config.settings.get('firewall')!r}")
    check(sent == [("firewall_apply", {"internet": "ask", "firewall": "on"})], f"undo applies firewall on: {sent}")

    # firewall never set (absent -> default on): undo puts it back to on and applies on
    config.settings.set("firewall", "off")
    tools._UNDO.clear()
    tools._UNDO.append(("settings", {"firewall": None, "internet": "ask"}, 0))
    sent.clear()
    tools.undo({}, Ctx())
    check(config.settings.get("firewall") == "on", "absent firewall -> undo sets on")
    check(sent == [("firewall_apply", {"internet": "ask", "firewall": "on"})], f"absent firewall -> apply on: {sent}")

    # internet change -> undo: internet back, apply carries the current firewall value (off)
    config.settings.set("firewall", "off")
    tools._UNDO.clear()
    tools.change_setting({"setting": "internet", "value": "no"}, NetOff())
    check(config.settings.get("internet") == "no", "setup: internet is no before undo")
    sent.clear()
    tools.undo({}, Ctx())
    check(config.settings.get("internet") == "ask", "undo puts internet back to ask")
    check(config.settings.get("firewall") == "off", "internet undo keeps firewall off")
    check(sent == [("firewall_apply", {"internet": "ask", "firewall": "off"})], f"internet undo applies with firewall off: {sent}")

    # unrelated setting -> undo: restored, but no firewall apply
    config.settings.set("firewall", "on")
    config.settings.set("speak_replies", False)
    tools._UNDO.clear()
    tools._UNDO.append(("settings", tools._settings_snapshot(), 0))
    config.settings.set("speak_replies", True)
    sent.clear()
    tools.undo({}, Ctx())
    check(config.settings.get("speak_replies") is False, "unrelated undo restores its setting")
    check(sent == [], f"unrelated undo applies nothing: {sent}")

    print("all good" if not fails else f"{fails} FAILED")
finally:
    rootd_client.call = real_call
    tools._undo_push = real_undo
sys.exit(1 if fails else 0)
