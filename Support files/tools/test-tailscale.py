#!/usr/bin/env python3
"""Host tests for Tailscale remote access: the image package list, the runlevel and the 15-minute
watchdog, the update paths that must be left alone, and the phrases that open Remote access.

No `tailscale up` runs here. Run: python3 tools/test-tailscale.py
"""
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "src")
ROOTFS = os.path.join(ROOT, "rootfs")
HOME = tempfile.mkdtemp(prefix="llmos-tailscale-")
os.environ.update(LLMOS_HOME=HOME, LLMOS_ETC=os.path.join(HOME, "etc"),
                  LLMOS_SHARE=os.path.join(ROOTFS, "usr/share/llmos"),
                  LLMOS_OTA_ROOT=os.path.join(HOME, "ota-root"),
                  LLMOS_OTA_DIR=os.path.join(HOME, "ota-state"))
sys.path.insert(0, os.path.join(ROOTFS, "usr/lib/llmos"))

from llmos import intent, ota, rootd, syspanels, system, tailscale, tools, uispec, watchdog  # noqa: E402

spec = importlib.util.spec_from_file_location("hostota", os.path.join(HERE, "ota.py"))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)

fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


# ---- image: package, runlevel, crond, watchdog file

install = open(os.path.join(ROOT, "install.sh")).read()
check("\n  tailscale\n" in install, "install.sh lists the tailscale package")
check("rc-update add tailscale default" in install, "install.sh puts tailscale in the default runlevel")
check("rc-update add crond default" in install, "install.sh enables crond")
check("rc-update del crond" not in install, "install.sh does not remove crond from the default runlevel")
sh = subprocess.run(["sh", "-n", os.path.join(ROOT, "install.sh")], capture_output=True, text=True)
check(sh.returncode == 0, "install.sh passes sh -n" + (": " + sh.stderr.strip() if sh.returncode else ""))

watch = os.path.join(ROOTFS, "etc/periodic/15min/tailscale-watchdog")
mode = os.stat(watch).st_mode
body = open(watch).read()
check(stat.S_ISREG(mode) and mode & stat.S_IXUSR, "tailscale-watchdog is executable")
wsh = subprocess.run(["sh", "-n", watch], capture_output=True, text=True)
check(wsh.returncode == 0, "tailscale-watchdog passes sh -n")
check("rc-update show default | grep -q tailscale || rc-update add tailscale default" in body,
      "watchdog puts tailscale back in the default runlevel")
check("tailscale status" in body and "rc-service tailscale restart" in body and "rc-service tailscale start" in body,
      "watchdog restarts tailscale when status fails, and starts it if restart fails")
check('"RunSSH": true' in body and "tailscale set --ssh" in body,
      "watchdog turns RunSSH back on")

pkg = os.path.join(ROOTFS, "usr/share/llmos/packages.txt")
names = [ln.split("#", 1)[0].strip() for ln in open(pkg).read().splitlines()]
names = [n for n in names if n]
check(names == ["tailscale"], f"packages.txt lists tailscale and nothing else: {names}")

# ---- OTA leaves state, config and the runlevel link alone, and installs missing packages

PRESERVE = ("var/lib/tailscale", "etc/conf.d/tailscale", "etc/runlevels/default/tailscale")
check(host.PRESERVE == ota.PRESERVE == PRESERVE, f"host and device preserve the same paths: {host.PRESERVE} {ota.PRESERVE}")
check(ota.preserved("./var/lib/tailscale/tailscaled.state") and host.preserved("/etc/conf.d/tailscale")
      and ota.preserved("etc/runlevels/default/tailscale"), "preserved() matches the three paths and children")
check(not ota.preserved("var/lib/tailscale-backup") and not host.preserved("etc/conf.d/tailscale.bak"),
      "a nearby path is not preserved")

for bad in ("var/lib/tailscale/tailscaled.state", "etc/conf.d/tailscale", "etc/runlevels/default/tailscale"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        ti = tarfile.TarInfo(bad)
        ti.size = 1
        tf.addfile(ti, io.BytesIO(b"x"))
    path = os.path.join(HOME, "bad.tar")
    open(path, "wb").write(buf.getvalue())
    try:
        ota.check_payload(path)
        check(False, f"refuses {bad}")
    except ValueError:
        check(True, f"refuses {bad}")

data, n = host.build_payload("9.9.9")
payload = os.path.join(HOME, "payload.tar")
open(payload, "wb").write(data)
shipped = ota.check_payload(payload)
check("etc/periodic/15min/tailscale-watchdog" in shipped, "an update ships the watchdog")
check("usr/share/llmos/packages.txt" in shipped, "an update ships packages.txt")
check(not any(ota.preserved(p) for p in shipped), "an update does not ship preserved Tailscale paths")
with tarfile.open(payload) as tf:
    member = tf.getmember("etc/periodic/15min/tailscale-watchdog")
check(bool(member.mode & 0o111), f"shipped watchdog is executable ({oct(member.mode)})")
check(host.merge_apk([]) == ["tailscale"], f"publish adds tailscale from packages.txt: {host.merge_apk([])}")
check(host.merge_apk(["htop", "tailscale", "htop", "Not A Package"]) == ["htop", "tailscale"],
      "merge_apk keeps order, drops duplicates and bad names")
check(ota.missing_packages(["tailscale", "curl"], ["curl"]) == ["tailscale"], "missing_packages drops what is installed")
check(ota.missing_packages(["tailscale"], ["tailscale"]) == [], "missing_packages is empty when nothing is missing")

# ---- phrases

def routed(text):
    return intent.match(text)

check(routed("turn on remote access") == ("remote_access", {"action": "connect"}), "turn on remote access connects")
check(routed("enable remote access") == ("remote_access", {"action": "connect"}), "enable remote access connects")
check(routed("connect tailscale") == ("remote_access", {"action": "connect"}), "connect tailscale connects")
check(routed("connect to tailscale") == ("remote_access", {"action": "connect"}), "connect to tailscale connects")
check(routed("tailscale up") == ("remote_access", {"action": "connect"}), "tailscale up connects")
check(routed("log in to tailscale") == ("remote_access", {"action": "connect"}), "log in to tailscale connects")
check(routed("sign in to tailscale") == ("remote_access", {"action": "connect"}), "sign in to tailscale connects")
check(routed("remote access") == ("show_panel", {"panel": "remote"}), "remote access opens the panel")
check(routed("tailscale") == ("show_panel", {"panel": "remote"}), "tailscale opens the panel")
check(routed("show the remote access panel") == ("show_panel", {"panel": "remote"}), "show the remote access panel")
check(routed("turn on tailscale ssh") == ("remote_access", {"action": "ssh-on"}), "turn on tailscale ssh")
check(routed("turn off tailscale ssh") == ("remote_access", {"action": "ssh-off"}), "turn off tailscale ssh")
check(routed("tailscale ssh on") == ("remote_access", {"action": "ssh-on"}), "tailscale ssh on")
check(routed("disable tailscale ssh") == ("remote_access", {"action": "ssh-off"}), "disable tailscale ssh")
wifi = routed("connect to the wifi")
check(wifi is None or wifi[0] != "remote_access", f"connect to the wifi is not remote access: {wifi}")
inet = routed("turn on the internet")
check(inet is None or inet[0] != "remote_access", f"turn on the internet is not remote access: {inet}")
check(routed("show the settings") == ("show_panel", {"panel": "settings"}), "show the settings still opens settings")

desk = open(os.path.join(ROOTFS, "usr/lib/llmos/llmos/desk.py")).read()
check('"label": "Remote access"' in desk and '"say": "remote access"' in desk, "Settings has a Remote access button")
check("intent._remote" in desk, "the desk routes remote-access phrases itself")

# ---- watchdog recovers tailscaled and does not stop it

wsrc = open(os.path.join(ROOTFS, "usr/lib/llmos/llmos/watchdog.py")).read()
check('_rc("tailscale", "restart")' not in wsrc and '_rc("tailscale", "stop")' not in wsrc
      and '"tailscale", "restart"' not in wsrc and '"tailscale", "stop"' not in wsrc,
      "llmos-watchdog never stops or restarts tailscaled")
i = wsrc.find("no network for 5 minutes")
check(i >= 0 and "_ensure_tailscale()" in wsrc[i:i + 500],
      "after the 5-minute Wi-Fi restart, tailscale is started if it is down")


def exercise(has, running, in_default):
    calls = []
    saved = (watchdog._has_service, watchdog._running, watchdog._in_default, watchdog._rc, watchdog.subprocess.run)
    watchdog._has_service = lambda svc: bool(has) and svc == "tailscale"
    watchdog._running = lambda svc: bool(running)
    watchdog._in_default = lambda svc: bool(in_default)

    def fake_rc(*a, **k):
        calls.append(("rc", a))
        return None

    def fake_run(argv, **k):
        calls.append(("run", tuple(argv)))

        class P:
            returncode = 0
        return P()

    watchdog._rc = fake_rc
    watchdog.subprocess.run = fake_run
    try:
        watchdog._ensure_tailscale()
    finally:
        watchdog._has_service, watchdog._running, watchdog._in_default, watchdog._rc, watchdog.subprocess.run = saved
    return calls


calls = exercise(True, False, False)
check(("run", ("rc-update", "add", "tailscale", "default")) in calls and ("rc", ("tailscale", "start")) in calls,
      f"missing runlevel and stopped: add and start {calls}")
calls = exercise(True, True, True)
check(calls == [], f"already in the runlevel and running: leave it {calls}")
calls = exercise(True, False, True)
check(("rc", ("tailscale", "start")) in calls and not any(c[0] == "run" for c in calls),
      f"runlevel entry kept, service down: start only {calls}")
calls = exercise(False, False, False)
check(calls == [], f"no tailscale init script: do nothing {calls}")

on = system.firewall_rules("yes")
check('iifname "tailscale0" accept' in on and "udp dport 41641 accept" in on,
      "firewall accepts Tailscale SSH on tailscale0 and WireGuard UDP 41641")
off = system.firewall_rules("yes", firewall=False)
m = re.search(r"chain input \{(.*?)\n  \}", off, re.S)
chain = m.group(1).strip() if m else ""
check(chain == "type filter hook input priority 0; policy accept;",
      f"firewall off: input chain stays open and empty: {chain!r}")

check(tailscale.UP[:3] == ["tailscale", "up", "--ssh"], f"Connect runs tailscale up --ssh: {tailscale.UP[:3]}")
facts = tailscale.facts_from({"BackendState": "Running", "Self": {"TailscaleIPs": ["fd7a:115c:a1e0::1", "100.64.1.2"]}},
                             '{ "RunSSH": true }')
check(facts["status"] == "Connected" and facts["ip"] == "100.64.1.2" and facts["ssh"] is True,
      f"status facts: {facts}")
need = tailscale.facts_from({"BackendState": "NeedsLogin", "Self": {"TailscaleIPs": []}}, "")
check(need["status"] == "Not signed in" and need["ip"] == "—", f"logged out: {need}")
url, qr = tailscale.parse_login("To authenticate, visit:\n\nhttps://login.tailscale.com/a/abc\n█▀▄\n▄█▀\n")
check(url == "https://login.tailscale.com/a/abc" and "█▀▄" in qr, f"login url and qr parsed: {url!r} {qr!r}")

for bad in ({"action": "nope"}, {"action": "status", "extra": 1}, {"action": "up", "ssh": True}, {}, {"action": 1}):
    try:
        rootd.VERBS["tailscale"](bad)
        check(False, f"rootd rejects {bad}")
    except ValueError:
        check(True, f"rootd rejects {bad}")

# ---- the panel

tailscale.snapshot = lambda: {"installed": True, "status": "Connected", "ip": "100.64.0.2", "ssh": True}
tailscale.login_view = lambda: ("", "", False)
spec = syspanels.remote_access()
blob = json.dumps(spec)
check("Connected" in blob and "100.64.0.2" in blob, "panel shows status and the tailnet address")
tog = next(b for b in spec["blocks"] if b["type"] == "toggle")
check(tog["say_on"] == "turn on tailscale ssh" and tog["say_off"] == "turn off tailscale ssh" and tog["on"] is True,
      "SSH toggle says the phrases the desk routes")
check(any(it.get("say") == "connect tailscale" for b in spec["blocks"] if b["type"] == "buttons" for it in b["items"]),
      "Connect says connect tailscale")
norm = uispec.normalize(spec)
ntog = next(b for b in norm["blocks"] if b["type"] == "toggle")
check("15 minutes" in (ntog.get("hint") or ""), "the SSH hint survives the window normaliser")

tailscale.snapshot = lambda: {"installed": True, "status": "Not signed in", "ip": "—", "ssh": False}
tailscale.login_view = lambda: ("https://login.tailscale.com/a/abc", "█▀▄\n▄█▀", False)
spec = syspanels.remote_access()
texts = [b.get("text", "") for b in spec["blocks"]]
check(any("https://login.tailscale.com/a/abc" in t for t in texts) and any("█▀▄" in t for t in texts),
      "panel shows the login link and the QR")
norm = uispec.normalize(spec)
code = next(b for b in norm["blocks"] if b["type"] == "code")
check(code.get("lang") == "qr" and "█" in code["text"], "the QR stays a qr code block")

tailscale.snapshot = lambda: {"installed": False, "status": "Not installed", "ip": "—", "ssh": False}
tailscale.login_view = lambda: ("", "", False)
spec = syspanels.remote_access()
check("Tailscale is not on this computer yet" in json.dumps(spec), "panel says when Tailscale is not installed yet")

tool = tools.REGISTRY["remote_access"]
check(tool.risk_for({"action": "ssh-on"}) == "security", "turning SSH on is a security change")
check(tool.risk_for({"action": "connect"}) == "change" and tool.network_for({"action": "connect"}) is True,
      "connect is a change and uses the network")
check(tool.risk_for({"action": "ssh-off"}) == "change" and tool.risk_for({"action": "show"}) == "safe",
      "ssh-off is a change and show is safe")
check(tool.network_for({"action": "show"}) is False, "showing the panel does not use the network")

print("all good" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
