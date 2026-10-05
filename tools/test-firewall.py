#!/usr/bin/env python3
"""Host-side test of the firewall rules (llmos/system.py): the brief's privacy promise depends on them.
With the internet off, nothing may go out (not even connections opened before the switch); with Tor on, only
the Tor daemon may reach the network, so a program that does not use Tor fails instead of leaking; the
launcher's host services are reachable only when this boot was actually given them. Run: python3
tools/test-firewall.py (no VM — the generated nftables text is inspected)."""
import os
import re
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ["LLMOS_HOME"] = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_ETC"] = tempfile.mkdtemp(prefix="llmos-etc-")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import system  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def output_chain(rules):
    m = re.search(r"chain output \{(.*?)\n  \}", rules, re.S)
    return m.group(1) if m else ""


system._tor_uid = lambda: 101          # the Alpine 'tor' user, deterministically, for this host test
system.launcher_says = lambda key: False   # on real hardware nothing is provided by a launcher
system._host_ports = system._host_ports    # uses launcher_says + llama_url

print("internet on: ordinary traffic allowed")
out = output_chain(system.firewall_rules("yes"))
check("policy accept" in out, "output policy is accept")
check("ct state established,related accept" in out, "established connections pass")

print("internet off: everything out is dropped, including connections already open")
out = output_chain(system.firewall_rules("no"))
check("policy drop" in out, "output policy is drop")
check("established,related" not in out, "no established-connections exception (an in-flight download is cut)")
check("oif lo accept" in out, "loopback still allowed (the on-device model is local)")

print("Tor on: only the Tor daemon reaches the network (fail closed)")
out = output_chain(system.firewall_rules("yes", tor=True))
check("policy drop" in out, "output policy is drop so nothing bypasses Tor")
check("meta skuid 101 accept" in out, "the Tor daemon may go out")
check("established,related" not in out, "no blanket established exception that would let non-Tor flows out")

print("Tor off again: back to normal")
check("policy accept" in output_chain(system.firewall_rules("yes", tor=False)), "accept returns when Tor is off")

print("the launcher's host services are allowed only when this boot was given them")
check("10.0.2.2" not in system.firewall_rules("yes"), "no 10.0.2.2 rule on real hardware (no launcher)")
system.launcher_says = lambda key: key == "mic"
check("10.0.2.2 tcp dport { 8766 }" in system.firewall_rules("yes"), "the mic-bridge port opens only when the launcher provided it")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
