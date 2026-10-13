#!/usr/bin/env python3
"""Tests for the firewall and Tor entry points: system.apply_firewall and system.set_tor run in-process as root
(os.geteuid patched to 0), or through rootd_client.call as a non-root desk (patched). The rootd verbs firewall_apply
and set_tor reject bad arguments. Nothing runs nft, rc-service or curl: the root functions are patched to record.

Run: python3 tools/test-rootd-firewall.py"""
import json
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import rootd, rootd_client, system  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

real_geteuid = os.geteuid
real_apply_root = system._apply_firewall_root
real_set_tor_root = system._set_tor_root
real_call = rootd_client.call


def restore():
    os.geteuid = real_geteuid
    system._apply_firewall_root = real_apply_root
    system._set_tor_root = real_set_tor_root
    rootd_client.call = real_call


def as_uid(uid):
    os.geteuid = lambda: uid


def expect_raises(label, fn, must):
    try:
        fn()
    except ValueError as e:
        assert must in str(e), f"{label}: got {e!r}"
        print(f"ok {label}: {e}")
        return
    raise AssertionError(f"{label}: no ValueError raised")


try:
    # (a) root: apply_firewall calls _apply_firewall_root and returns its value
    calls = []
    system._apply_firewall_root = lambda internet=None: (calls.append(internet) or (True, "root-ok"))
    as_uid(0)
    got = system.apply_firewall("no")
    assert calls == ["no"], calls
    assert got == (True, "root-ok"), got
    print("ok apply_firewall as root calls _apply_firewall_root")

    # (b) non-root: apply_firewall goes through rootd_client.call("firewall_apply")
    sent = []
    rootd_client.call = lambda verb, **kw: (sent.append((verb, kw)) or "[true, \"\"]")
    as_uid(1000)
    got = system.apply_firewall(internet="no")
    assert sent == [("firewall_apply", {"internet": "no"})], sent
    assert got == (True, ""), got
    print("ok apply_firewall as desk sends firewall_apply and returns (True, \"\")")

    def boom(verb, **kw):
        raise RootdError("the system helper is not running")
    rootd_client.call = boom
    got = system.apply_firewall(internet="no")
    assert got == (False, "the system helper is not running"), got
    print(f"ok apply_firewall as desk RootdError -> {got}")

    # (c) set_tor: same three cases
    tor_calls = []
    system._set_tor_root = lambda on: (tor_calls.append(on) or (True, "tor-root"))
    as_uid(0)
    got = system.set_tor(True)
    assert tor_calls == [True], tor_calls
    assert got == (True, "tor-root"), got
    print("ok set_tor as root calls _set_tor_root")

    sent = []
    def record(verb, _timeout=None, **kw):
        sent.append((verb, _timeout, kw))
        return "[true, \"\"]"
    rootd_client.call = record
    as_uid(1000)
    got = system.set_tor(False)
    assert sent == [("set_tor", 120, {"on": False})], sent
    assert got == (True, ""), got
    print(f"ok set_tor as desk sends set_tor with _timeout=120 (not in args): {sent[0]}")

    rootd_client.call = boom
    got = system.set_tor(True)
    assert got == (False, "the system helper is not running"), got
    print(f"ok set_tor as desk RootdError -> {got}")

    # (d) rootd verbs reject bad arguments
    expect_raises("firewall_apply rejects internet=maybe",
                  lambda: rootd.firewall_apply({"internet": "maybe"}), "bad args: internet")
    expect_raises("set_tor rejects on=yes",
                  lambda: rootd.set_tor({"on": "yes"}), "bad args: on")
    # (e) firewall_apply's optional "firewall" field: on/off/absent pass firewall=True/False/None; garbage is rejected
    fw_calls = []
    system._apply_firewall_root = lambda internet=None, firewall=None: (fw_calls.append((internet, firewall)) or (True, ""))
    for args, expect in (({"firewall": "on"}, True), ({"firewall": "off"}, False), ({}, None),
                         ({"internet": "no", "firewall": "off"}, False)):
        fw_calls.clear()
        out = json.loads(rootd.firewall_apply(args))
        assert out == [True, ""], out
        assert fw_calls[0][1] is expect, (args, fw_calls)
        print(f"ok firewall_apply {args} -> firewall={expect!r}")
    assert fw_calls[-1][0] == "no", fw_calls
    for bad in ("banana", "", "ON", True, 0):
        expect_raises(f"firewall_apply rejects firewall={bad!r}",
                      lambda bad=bad: rootd.firewall_apply({"firewall": bad}), "bad args: firewall")
    assert "firewall_apply" in rootd.VERBS and "set_tor" in rootd.VERBS
    print("ok rootd VERBS has firewall_apply and set_tor")

    print("all good")
finally:
    restore()
