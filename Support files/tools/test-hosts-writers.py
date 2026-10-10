#!/usr/bin/env python3
"""Tests for the /etc/hosts writers in system.py (focus mode) and everyday.py (focus blocks, web blocks).

Every writer goes through system._write_hosts: a writable hosts file is written directly (as before), a
non-writable one goes through rootd_client.call("write_hosts", text=...). The hosts path is redirected to a temp
file (system.HOSTS), so the real /etc/hosts is never touched. Settings and the Firefox policy file are stubbed.
Run: python3 tools/test-hosts-writers.py"""
import os
import re
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import config, everyday, rootd_client, system  # noqa: E402

tmp = tempfile.mkdtemp(prefix="hosts-writers-test-")
hosts = os.path.join(tmp, "hosts")
ORIGINAL = "127.0.0.1 localhost\n::1 localhost\n127.0.1.1 oldname\n"
with open(hosts, "w") as f:
    f.write(ORIGINAL)

# --- redirects: the hosts path, the settings store, the Firefox policy file
real_hosts, real_settings, real_policy = system.HOSTS, config.settings, everyday._POLICY
real_call, real_access = rootd_client.call, os.access


class FakeSettings:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


calls = []
system.HOSTS = hosts
config.settings = FakeSettings()
everyday._POLICY = os.path.join(tmp, "no-policy.json")


def read():
    with open(hosts) as f:
        return f.read()


def old_without_focus(text):
    """The old system._hosts_without_focus logic, copied here as the reference."""
    return re.sub(rf"\n?{system.FOCUS_BEGIN}.*?{system.FOCUS_END}\n?", "\n", text, flags=re.S).rstrip("\n") + "\n"


def old_focus_on(text, sites):
    """The old system.focus(True) text: the hosts text without the focus block, then the block."""
    block = "\n".join(f"0.0.0.0 {s}" for s in sites)
    return old_without_focus(text) + f"{system.FOCUS_BEGIN}\n{block}\n{system.FOCUS_END}\n"


try:
    # 1. focus on writes exactly the old text (computed by the old logic, and a fixed string for the first lines)
    system.focus(True, minutes=30)
    got = read()
    assert got == old_focus_on(ORIGINAL, system.DISTRACTIONS), got[:200]
    assert got.startswith(ORIGINAL + system.FOCUS_BEGIN + "\n0.0.0.0 facebook.com\n"), got[:200]
    print(f"ok focus on: {len(system.DISTRACTIONS)} sites, text matches the old logic")

    # 2. focus off restores the original text exactly
    system.focus(False)
    assert read() == old_without_focus(old_focus_on(ORIGINAL, system.DISTRACTIONS)) == ORIGINAL, repr(read())
    print("ok focus off: original hosts text restored")

    # 3. invalid names are skipped (rootd would refuse the whole file); valid extras are kept
    system.focus(True, minutes=5, extra=["bad_name.com", "https://x.com", "Ok-Site.org"])
    got = read()
    assert "0.0.0.0 ok-site.org\n" in got and "bad_name" not in got and "https" not in got, got[-200:]
    print("ok focus extras: bad_name.com and https://x.com skipped, ok-site.org kept")
    system.focus(False)

    # 4. non-writable hosts file: the text goes to rootd's write_hosts verb, the file is left alone
    def fake_access(path, mode, *a, **k):
        if path == hosts:
            return False
        return real_access(path, mode, *a, **k)

    def fake_call(verb, **args):
        calls.append((verb, args))
        return "ok"

    os.access = fake_access
    rootd_client.call = fake_call
    system.focus(True, minutes=30)
    assert read() == ORIGINAL, "a non-writable hosts file was written directly"
    assert calls and calls[-1][0] == "write_hosts", calls
    assert calls[-1][1] == {"text": old_focus_on(ORIGINAL, system.DISTRACTIONS)}, calls[-1][1]["text"][:200]
    print(f"ok non-writable focus on: rootd_client.call('write_hosts') with {len(calls[-1][1]['text'])} chars")

    # 5. a rootd refusal comes back as OSError with rootd's message
    def refusing_call(verb, **args):
        raise rootd_client.RootdError("bad args: hosts line 2")

    rootd_client.call = refusing_call
    try:
        system._write_hosts("127.0.0.1 localhost\n")
        raise AssertionError("RootdError was not turned into OSError")
    except OSError as e:
        msg = str(e)
    assert msg == "bad args: hosts line 2", msg
    print(f"ok RootdError -> OSError: {msg}")
    rootd_client.call = fake_call

    # 6. everyday's focus/web block writer: same text, same routing, invalid names skipped
    everyday._hosts_block(["youtube.com", "bad_site.com"])
    expected = ORIGINAL.splitlines()
    expected += [f"0.0.0.0 {s} {everyday._MARK}" for s in ["youtube.com", "www.youtube.com"]]
    assert calls[-1] == ("write_hosts", {"text": "\n".join(expected) + "\n"}), calls[-1]
    print("ok everyday _hosts_block (non-writable): write_hosts text has youtube.com and www.youtube.com, not bad_site.com")

    # 7. everyday's block writer when the file is writable: written directly, same text, marker lines replaced
    os.access = real_access
    everyday._hosts_block(["youtube.com"])
    assert read() == "\n".join(ORIGINAL.splitlines() + [f"0.0.0.0 {s} {everyday._MARK}" for s in ["youtube.com", "www.youtube.com"]]) + "\n", repr(read())
    everyday._hosts_block([])
    assert read() == ORIGINAL, repr(read())
    print("ok everyday _hosts_block (writable): direct write, block lifted restores the original text")

    print("all good")
finally:
    system.HOSTS = real_hosts
    config.settings = real_settings
    everyday._POLICY = real_policy
    rootd_client.call = real_call
    os.access = real_access
    shutil.rmtree(tmp, ignore_errors=True)
