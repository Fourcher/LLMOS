#!/usr/bin/env python3
"""Log in to the test laptop directly (development): no need for it to know where this Mac is.

    tools/devssh.py setup            send this Mac's development key to the laptop once (a signed remote-testing
                                     command; afterwards the laptop runs an SSH server that takes only this key)
    tools/devssh.py 'COMMAND'        run COMMAND on the laptop as root and print its output
    tools/devssh.py                  an interactive shell there
    tools/devssh.py where            the laptop's address now

The laptop is found by its name on the network (llmos.local), else at its last known address, else by its network
card's hardware address in this Mac's neighbour table (after a ping sweep of the local network). The key is in
Support files/ota-keys/ (never in git); the laptop's host key is remembered in run/devssh-known_hosts.
"""
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
KEY = os.path.join(PROJECT, "ota-keys", "devssh_ed25519")
KNOWN = os.path.join(PROJECT, "run", "devssh-known_hosts")
STATE = os.path.join(PROJECT, "run", "devssh-host.json")
NAME = "llmos.local"


def _state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def _save(**kw):
    st = _state()
    st.update(kw)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w"))


def _open(ip, port=22, t=1.5):
    try:
        with socket.create_connection((ip, port), timeout=t):
            return True
    except OSError:
        return False


def _arp():
    out = subprocess.run(["arp", "-an"], capture_output=True, text=True).stdout
    return {m.group(2).lower(): m.group(1) for m in re.finditer(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+)", out, re.I)}


def _norm_mac(m):
    return ":".join(p.zfill(2) for p in m.lower().split(":"))


def where():
    st = _state()
    cands = []
    try:
        cands.append(socket.gethostbyname(NAME))
    except OSError:
        pass
    if st.get("ip"):
        cands.append(st["ip"])
    for ip in dict.fromkeys(cands):
        if _open(ip):
            return ip
    mac = st.get("mac")
    if mac:
        hit = {_norm_mac(k): v for k, v in _arp().items()}.get(_norm_mac(mac))
        if hit and _open(hit):
            return hit
        # wake the neighbour table: one ping to every address of this Mac's local network
        out = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
        for a, m in re.findall(r"inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-f]+)", out):
            if a.startswith("127."):
                continue
            net = ipaddress.ip_network(f"{a}/{bin(int(m, 16)).count('1')}", strict=False)
            if net.num_addresses > 1024:
                continue
            procs = [subprocess.Popen(["ping", "-c", "1", "-t", "1", str(h)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                     for h in net.hosts()]
            for p in procs:
                p.wait()
        hit = {_norm_mac(k): v for k, v in _arp().items()}.get(_norm_mac(mac))
        if hit and _open(hit):
            return hit
    return None


def ssh(cmd=None, ip=None):
    ip = ip or where()
    if not ip:
        print("the laptop is not answering on the network (is it on? was direct access set up? tools/devssh.py setup)")
        return 255
    argv = ["ssh", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=15", "-o", "LogLevel=ERROR", f"root@{ip}"]
    if cmd is None:
        return subprocess.call(argv)
    p = subprocess.run(argv + [cmd], text=True, capture_output=True)
    sys.stdout.write(p.stdout + p.stderr)
    if p.returncode != 255 and not _state().get("mac"):
        m = re.search(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})", subprocess.run(argv + ["cat /sys/class/net/wl*/address 2>/dev/null | head -1"],
                                                                         text=True, capture_output=True).stdout)
        if m:
            _save(mac=m.group(1))
    if p.returncode != 255:
        _save(ip=ip)
    return p.returncode


def setup():
    pub = open(KEY + ".pub").read().strip()
    p = subprocess.run([sys.executable, os.path.join(HERE, "devlink.py"), "sshkey", pub], capture_output=True, text=True, timeout=600)
    print(p.stdout.strip()[-400:])


def main():
    a = sys.argv[1:]
    if a[:1] == ["setup"]:
        return setup()
    if a[:1] == ["where"]:
        print(where() or "not found")
        return 0
    sys.exit(ssh(" ".join(a)) if a else ssh())


if __name__ == "__main__":
    main()
