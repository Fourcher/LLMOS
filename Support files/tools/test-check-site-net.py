#!/usr/bin/env python3
"""Host-side test of check_site and the internet setting: with internet "no" the tool answers
in one plain line and makes zero socket calls; with "yes" it still checks (socket calls are faked
here, nothing leaves the host); and the tool is registered network=True so the agent's own
network gate (confirm_network under "ask", refusal under "no") applies to it.
Run: python3 tools/test-check-site-net.py  (no network, no VM needed)."""
import os
import socket
import ssl
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import config, tools  # noqa: E402

FAILS = []


def check(cond, what):
    if cond:
        print("ok " + what)
    else:
        print("FAIL " + what)
        FAILS.append(what)


class FakeSettings:
    def __init__(self, internet):
        self.internet = internet

    def get(self, key, default=None):
        return self.internet if key == "internet" else default


class FakeTLS:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def getpeercert(self):
        return {"issuer": ((("organizationName", "Test CA"),),)}


class FakeSock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeContext:
    def wrap_socket(self, sock, server_hostname=None):
        return FakeTLS()


CALLS = []


def fake_getaddrinfo(host, port, *a, **k):
    CALLS.append(("getaddrinfo", host, port))
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.1", port))]


def fake_create_connection(addr, *a, **k):
    CALLS.append(("create_connection", addr))
    return FakeSock()


def run_with(internet):
    CALLS.clear()
    real_settings = config.settings
    real_gai, real_cc = socket.getaddrinfo, socket.create_connection
    real_ctx = ssl.create_default_context
    config.settings = FakeSettings(internet)
    socket.getaddrinfo = fake_getaddrinfo
    socket.create_connection = fake_create_connection
    ssl.create_default_context = lambda *a, **k: FakeContext()
    try:
        return tools.check_site({"address": "example.com"}, None)
    finally:
        config.settings = real_settings
        socket.getaddrinfo, socket.create_connection = real_gai, real_cc
        ssl.create_default_context = real_ctx


# 1. internet "no": the plain message, and zero socket calls
out = run_with("no")
check(out == "The internet is off in Settings, so I can't check that site.", "no -> plain message")
check(CALLS == [], "no -> zero socket calls (saw %r)" % (CALLS,))

# 2. internet "yes": the check still runs and reports the fake success
out = run_with("yes")
check(any(c[0] == "getaddrinfo" for c in CALLS) and any(c[0] == "create_connection" for c in CALLS),
      "yes -> socket calls happen (saw %r)" % (CALLS,))
check(out.startswith("example.com: ") and "secure connection is valid" in out,
      "yes -> normal output format")

# 3. registry: check_site is network=True, so the agent's network gate applies
reg = tools.REGISTRY.get("check_site")
check(reg is not None and reg.network is True, "registry -> check_site network flag True")
check(reg is not None and reg.network_for({"address": "example.com"}) is True,
      "registry -> network_for(args) True")

print("all good" if not FAILS else "FAILED: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
