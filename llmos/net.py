"""Network policy. Nothing leaves the machine until the user turns the
network on. Modes: off, direct, tor. Enforced by nftables, not by trust."""
import json
import os
import random
import shutil
import subprocess
import time

from . import config

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
TOR_SOCKS = "127.0.0.1:9050"
MODES = ("off", "direct", "tor")


def _nft(script):
    if config.DEV or not shutil.which("nft"):
        return True
    p = subprocess.run(["nft", "-f", "-"], input=script, text=True, capture_output=True)
    return p.returncode == 0


def rules(mode):
    """The egress chain contents for a mode (also used by tests)."""
    lines = ["flush chain inet llmos egress"]
    if mode == "direct":
        lines.append("add rule inet llmos egress accept")
    elif mode == "tor":
        lines.append('add rule inet llmos egress meta skuid "tor" tcp dport { 443, 9001, 9030, 80 } accept')
        lines.append("add rule inet llmos egress udp dport 53 drop")
    return "\n".join(lines) + "\n"


class Net:
    def __init__(self):
        self.mode = "off"
        self.state_path = None

    def load(self):
        try:
            with open(config.dpath("network.json")) as f:
                m = json.load(f).get("mode", "off")
                return m if m in MODES else "off"
        except (OSError, ValueError):
            return "off"

    def set_mode(self, mode, persist=True):
        if mode not in MODES:
            raise ValueError("mode must be off, direct or tor")
        if not _nft(rules(mode)):
            raise RuntimeError("could not apply firewall rules")
        self.mode = mode
        if mode != "off":
            self.bring_up()
        if mode == "tor":
            self.start_tor()
        else:
            self.stop_tor()
        if persist and config.data_ready():
            with open(config.dpath("network.json"), "w") as f:
                json.dump({"mode": mode}, f)
        return mode

    # links
    def interfaces(self):
        try:
            return [i for i in os.listdir("/sys/class/net") if i != "lo"]
        except OSError:
            return []

    def bring_up(self):
        if config.DEV:
            return
        for ifc in self.interfaces():
            wireless = os.path.isdir("/sys/class/net/%s/wireless" % ifc)
            if not wireless:
                self._random_mac(ifc)
                subprocess.run(["ip", "link", "set", ifc, "up"], capture_output=True)
                if not self._has_addr(ifc):
                    subprocess.run(["dhcpcd", "-b", "-q", ifc], capture_output=True)
        if any(os.path.isdir("/sys/class/net/%s/wireless" % i) for i in self.interfaces()):
            subprocess.run(["rc-service", "iwd", "start"], capture_output=True)

    def _has_addr(self, ifc):
        out = subprocess.run(["ip", "-4", "addr", "show", ifc], capture_output=True, text=True).stdout
        return "inet " in out

    def _random_mac(self, ifc):
        if self._has_addr(ifc):
            return
        mac = [0x02] + [random.randint(0, 255) for _ in range(5)]
        addr = ":".join("%02x" % b for b in mac)
        subprocess.run(["ip", "link", "set", ifc, "down"], capture_output=True)
        subprocess.run(["ip", "link", "set", ifc, "address", addr], capture_output=True)

    def start_tor(self):
        if config.DEV:
            return
        subprocess.run(["rc-service", "tor", "start"], capture_output=True)

    def stop_tor(self):
        if config.DEV:
            return
        subprocess.run(["rc-service", "tor", "stop"], capture_output=True)

    def status(self):
        lines = ["mode " + self.mode]
        if config.DEV:
            return lines[0]
        for ifc in self.interfaces():
            out = subprocess.run(["ip", "-br", "addr", "show", ifc], capture_output=True, text=True).stdout.strip()
            lines.append(out)
        return "\n".join(lines)

    # clients
    def env(self):
        if self.mode == "tor":
            p = "socks5h://" + TOR_SOCKS
            return {"ALL_PROXY": p, "all_proxy": p, "HTTPS_PROXY": p, "https_proxy": p, "HTTP_PROXY": p, "http_proxy": p}
        return {}

    def curl_args(self):
        a = ["curl", "-sSL", "--compressed", "-A", UA, "--max-redirs", "5"]
        if self.mode == "tor":
            a += ["--socks5-hostname", TOR_SOCKS]
        return a

    def get(self, url, timeout=25, data=None, headers=None, max_bytes=8_000_000, out_file=None):
        if self.mode == "off":
            raise PermissionError("network is off")
        args = self.curl_args() + ["--max-time", str(timeout), "--max-filesize", str(max_bytes)]
        for h in headers or []:
            args += ["-H", h]
        for k, v in (data or {}).items():
            args += ["--data-urlencode", "%s=%s" % (k, v)]
        if out_file:
            args += ["-o", out_file]
        args += ["-w", "\n%{http_code}", "--", url] if not out_file else ["--", url]
        env = dict(os.environ)
        for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            if self.mode == "tor":
                env.pop(k, None)
        p = subprocess.run(args, capture_output=True, timeout=timeout + 5, env=env)
        if p.returncode != 0:
            raise RuntimeError("fetch failed: " + p.stderr.decode(errors="replace").strip()[:300])
        if out_file:
            return b""
        body, _, code = p.stdout.rpartition(b"\n")
        if not code.strip().isdigit() or int(code) >= 400:
            raise RuntimeError("HTTP %s from %s" % (code.decode(errors="replace").strip(), url))
        return body


def wait_for_tor(net, seconds=60):
    t = time.time()
    while time.time() - t < seconds:
        try:
            net.get("https://check.torproject.org/api/ip", timeout=10)
            return True
        except Exception:
            time.sleep(2)
    return False
