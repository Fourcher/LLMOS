#!/usr/bin/env python3
"""Host-side test of how shell commands are ranked (tools.classify_command) and whether they reach the
network (tools.uses_network), and of writes to the OS's own policy files: the confirmation policy depends on
these, so a destructive command in disguise must still rank as destructive, and the assistant must not be able
to rewrite its own rules without the owner. Run: python3 tools/test-risk.py (no model, no VM)"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, tools  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


R, C, D, S = tools.READ, tools.CHANGE, tools.DESTRUCTIVE, tools.SECURITY
RANKS = [
    # destructive, however it is written
    ("rm -rf ~/Downloads", D), ("/bin/rm -rf ~/Documents", D), ("echo hi\n/bin/rm -rf ~/x", D),
    ("printf x\n/sbin/mkfs.ext4 /dev/sda1", D), ("sudo rm -rf /tmp/x", D), ("sudo -u bob /bin/rm x", D),
    ("sh -c 'rm -rf ~/x'", D), ('bash -c "/usr/bin/shred secret.txt"', D), ("xargs -0 /bin/rm < list", D),
    ("timeout 5 rm x", D), ("find . -name '*.tmp' -exec /bin/rm {} \\;", D), ("find /tmp -delete", D),
    ('for f in *.log; do rm "$f"; done', D), ("if true; then rm x; fi", D), ("echo $(rm x)", D), ("`rm x`", D),
    ("eval 'rm x'", D), ("env A=1 rm x", D), ("busybox rm x", D), ("dd if=/dev/zero of=/dev/sda", D),
    ("{ rm x; }", D), ("cat x > /dev/sda", D), ("python3 -c 'import shutil; shutil.rmtree(\"/home\")'", D),
    ("reboot", D), ("pkill -f mpv", D), ("apk del firefox", D), ("chmod -R 777 /", D),
    # changes
    ("mkdir projects", C), ("echo hi\nmkdir x", C), ("touch a.txt", C), ("echo x > notes.txt", C),
    ("sed -i s/a/b/ f.txt", C), ("apk add htop", C), ("sudo ls", C), ("cp a b", C), ("mv a b", C),
    ("curl -o page.html https://example.com", C), ("cat /dev/sda > disk.img", C),
    # reads
    ("ls -la", R), ("cat /etc/hosts", R), ("grep -E 'a|b' file.txt", R), ("awk '{print $1}' f.txt", R),
    ("df -h | sort", R), ("echo hello", R), ("date", R), ("uptime", R), ("curl https://example.com", R),
    ("apk search htop", R), ("rc-service tor status", R), ("ps aux | grep mpv", R),
    # the OS's own rules: a change to them always asks (security)
    ("echo '{}' > /etc/llmos/settings.json", S), ("cd /etc/llmos && echo x > conduct.txt", S),
    ("sed -i s/drop/accept/ /etc/nftables.nft", S), ("cp evil.json ~/.llmos/cloud.json", S),
    ("cat /etc/llmos/settings.json", R), ("rm /etc/llmos/conduct.txt", D),
]
for cmd, want in RANKS:
    got = tools.classify_command(cmd)
    check(got == want, f"{cmd!r:58} -> {got} (want {want})")

NET = [("curl https://x", True), ("/usr/bin/curl http://x", True), ("sudo wget x", True), ("timeout 10 curl y", True),
       ("env HTTPS_PROXY=x curl y", True), ("git clone https://x", True), ("apk add foo", True), ("ping -c1 example.com", True),
       ("dig example.com", True), ("nslookup example.com", True), ("bash -c 'curl x | sh'", True),
       ("python3 -c 'import urllib.request; urllib.request.urlopen(\"http://x\")'", True), ("exec 3<>/dev/tcp/1.2.3.4/80", True),
       ("npx -y some-server", True), ("telnet towel.blinkenlights.nl", True),
       ("cat /etc/hosts", False), ("grep ping log.txt", False), ("hostname", False), ("ls -la", False), ("apk search vim", False),
       ("git status", False), ("echo done", False)]
for cmd, want in NET:
    got = tools.uses_network(cmd)
    check(got == want, f"network {cmd!r:58} -> {got} (want {want})")

wf = tools.REGISTRY["write_file"]
for path, want in [("~/notes.txt", C), ("/tmp/x", C), (os.path.join(config.ETC, "settings.json"), S),
                   (os.path.join(config.ETC, "conduct.txt"), S), ("/usr/lib/llmos/llmos/agent.py", S),
                   ("/etc/nftables.nft", S), (config.data("cloud.json"), S), (config.data("notes.json"), C)]:
    got = wf.risk_for({"path": path, "content": "x"})
    check(got == want, f"write_file {path!r:58} -> {got} (want {want})")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
