"""Name lookups (DNS) on real hardware.

Images up to 1.8.9 shipped /etc/resolv.conf pointing at 10.0.2.3 (the test VM's resolver, left by the build) and told
Wi-Fi (iwd) never to write the DNS servers its DHCP got. On a real computer every web address then failed to resolve
while the network itself worked: "the browser doesn't work". Run as root by the update service at start:
  - Wi-Fi hands its DNS servers to /usr/libexec/llmos-resolvconf (as /sbin/resolvconf) from now on;
  - a resolver that can't be reached on this network (the VM's) is replaced by the router at once.
"""
import os
import re
import shutil
import subprocess

SHIM = "/usr/libexec/llmos-resolvconf"
IWD = "/etc/iwd/main.conf"
RESOLV = "/etc/resolv.conf"


def _gateway():
    try:
        out = subprocess.run(["ip", "-4", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else ""


def ensure(log=print):
    changed_iwd = False
    try:
        if os.path.exists(SHIM) and not os.access(SHIM, os.X_OK):
            os.chmod(SHIM, 0o755)              # iwd will not start when its resolvconf can't run
    except OSError as e:
        log(f"netfix: resolvconf not made runnable: {e}")
    if os.path.exists(SHIM) and not os.path.lexists("/sbin/resolvconf") and not shutil.which("resolvconf"):
        try:
            os.symlink(SHIM, "/sbin/resolvconf")
        except OSError as e:
            log(f"netfix: resolvconf not linked: {e}")
    try:
        conf = open(IWD).read() if os.path.exists(IWD) else ""
        if "NameResolvingService=none" in conf and os.path.lexists("/sbin/resolvconf") and os.access("/sbin/resolvconf", os.X_OK):
            with open(IWD, "w") as f:
                f.write(conf.replace("NameResolvingService=none", "NameResolvingService=resolvconf"))
            changed_iwd = True
    except OSError as e:
        log(f"netfix: iwd settings not changed: {e}")
    gw = _gateway()
    try:
        cur = open(RESOLV).read() if os.path.exists(RESOLV) else ""
    except OSError:
        cur = ""
    servers = re.findall(r"^nameserver\s+(\S+)", cur, re.M)
    # the VM resolver on a network that isn't the VM's (its gateway is 10.0.2.2), or no resolver at all
    if gw and gw != "10.0.2.2" and (not servers or servers == ["10.0.2.3"]):
        try:
            with open(RESOLV + ".llmos", "w") as f:
                f.write(f"nameserver {gw}\nnameserver 1.1.1.1\n")
            os.replace(RESOLV + ".llmos", RESOLV)
            log(f"netfix: name lookups now go to {gw} (the old resolver was the test VM's)")
        except OSError as e:
            log(f"netfix: resolv.conf not written: {e}")
    if changed_iwd:
        # iwd reads this at its next start (the next boot). It is never restarted from here: the update service
        # depends on the network, so restarting Wi-Fi stopped this very service halfway and left Wi-Fi off
        # (1.8.9.2 on the spare computer, 2026-10-14). The resolver written above works until then.
        log("netfix: Wi-Fi will write the DNS servers it is given from the next start")
    return changed_iwd
