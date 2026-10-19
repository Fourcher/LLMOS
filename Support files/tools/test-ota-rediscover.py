#!/usr/bin/env python3
"""Host-side test of ota.rediscover: when the paired computer's address changes (its network gave it a new one after
it slept, 2026-10-19: .159 -> .206, and the laptop lost its updates and remote testing), the client follows the server
with the SAME key, never one with another key, and looks at most every 5 minutes. Run: python3 tools/test-ota-rediscover.py"""
import os
import sys
import tempfile
from unittest.mock import patch

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC", tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, ota, system  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


KEY = "ssh-ed25519 AAAAC3Nza-the-owners-key"
config.settings.set("ota", {"url": "http://192.168.86.159:8781", "key": KEY, "fp": "BCFE-BACB", "name": "mac"})
other = {"url": "http://192.168.86.50:8781", "key": "ssh-ed25519 AAAA-someone-else", "fp": "0000", "name": "x"}
moved = {"url": "http://192.168.86.206:8781", "key": KEY, "fp": "BCFE-BACB", "name": "mac"}
with patch.object(system, "apply_firewall", return_value=None):
    with patch.object(ota, "find_servers", return_value=[other]):
        ota._LAST_LOOK[0] = 0
        check(ota.rediscover(ota.paired()) is False and ota.paired()["url"].endswith(".159:8781"), "a server with another key is never followed")
    with patch.object(ota, "find_servers", return_value=[other, moved]) as fs:
        ota._LAST_LOOK[0] = 0
        check(ota.rediscover(ota.paired()) is True, "the same key at a new address is followed")
        check(ota.paired()["url"] == moved["url"] and ota.paired()["key"] == KEY and ota.paired()["fp"] == "BCFE-BACB",
              "the new address is kept; the key and its fingerprint stay as paired")
        n = fs.call_count
        ota.rediscover(ota.paired())
        check(fs.call_count == n, "no second look within 5 minutes")

# the network search itself runs (it once died on a missing import, so "get updates from my computer" always failed)
import ipaddress  # noqa: E402
with patch.object(ota, "_local_nets", return_value=[ipaddress.ip_network("127.0.0.0/30")]), patch.object(ota, "PORT", 9):
    try:
        got = ota.find_servers(timeout=0.2)
        check(got == [], "find_servers runs and finds nothing on a closed port")
    except Exception as e:
        check(False, f"find_servers raised {e!r}")

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
