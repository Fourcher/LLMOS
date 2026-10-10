#!/usr/bin/env python3
"""Host-side test: the four apk callers (tools.install_app, tools.remove_software, everyday.vpn's package install,
everyday.system_more's shell install) go through system.apk_add / system.apk_del with the same names, quiet flag,
force flag and timeout as before, and their replies keep the old success and failure wording.
system.apk_add / apk_del are patched to record calls; subprocess.run is patched so nothing runs apk.
Run: python3 tools/test-apk-callers.py  (no VM needed). Exit status 0 = pass."""
import os
import subprocess
import shutil
import sys
import tempfile
import types

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import everyday, system, tools  # noqa: E402

real_apk_add = system.apk_add
real_apk_del = system.apk_del
real_run = subprocess.run
real_which = shutil.which
real_open = everyday.__dict__.get("open")
real_glob = everyday.glob.glob

calls = []          # (verb, args, kwargs)
scripted = []       # replies for apk_add / apk_del, in order
ctx = types.SimpleNamespace()


def fake_apk_add(names, quiet=False, timeout=900):
    calls.append(("apk_add", list(names), {"quiet": quiet, "timeout": timeout}))
    return scripted.pop(0)


def fake_apk_del(name, force=False, timeout=600):
    calls.append(("apk_del", name, {"force": force, "timeout": timeout}))
    return scripted.pop(0)


def fake_run(argv, **kw):
    # the only subprocess use left on these paths is the 'apk search' hint after a failed install: answer empty
    calls.append(("subprocess", list(argv), {}))
    return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")


class Desk:
    def __init__(self):
        self.replies = []

    def emit(self, ev):
        pass

    def instant_reply(self, line, text):
        self.replies.append(text)


def restore():
    everyday.glob.glob = real_glob
    system.apk_add = real_apk_add
    system.apk_del = real_apk_del
    subprocess.run = real_run
    shutil.which = real_which
    if real_open is None:
        everyday.__dict__.pop("open", None)
    else:
        everyday.open = real_open


def check(label, cond, detail=""):
    assert cond, f"{label}: {detail}"
    print("ok", label)


OUT = {"ok": (0, "ok", ""), "boom": (1, "", "boom"), "timeout": (124, "", "timed out after 900 s")}

try:
    system.apk_add = fake_apk_add
    system.apk_del = fake_apk_del
    subprocess.run = fake_run
    shutil.which = lambda name, *a, **k: None          # no flatpak fallback on any host

    # ---- tools.install_app: names, quiet=False, timeout=900; success / failure / timeout replies
    for key, want_reply_prefix in (("ok", "installed: htop nano -- open it by name."),
                                   ("boom", "install failed: boom"),
                                   ("timeout", "install failed: timed out after 900 s")):
        del calls[:]
        scripted.append(OUT[key])
        got = tools.install_app({"packages": "Htop, NANO"}, ctx)
        check(f"install_app {key} call", calls[0] == ("apk_add", ["htop", "nano"], {"quiet": False, "timeout": 900}), calls)
        check(f"install_app {key} reply", got == want_reply_prefix, repr(got))

    # ---- tools.remove_software: name, force=False for an ordinary program, timeout=600
    for key, want in (("ok", "removed htop"), ("boom", "could not remove it: boom"),
                      ("timeout", "could not remove it: timed out after 900 s")):
        del calls[:]
        scripted.append(OUT[key])
        got = tools.remove_software({"name": "htop"}, ctx)
        check(f"remove_software {key} call", calls[0] == ("apk_del", "htop", {"force": False, "timeout": 600}), calls)
        check(f"remove_software {key} reply", got == want, repr(got))

    # ---- tools.remove_software on a core package: force=True, owner is told what it means
    del calls[:]
    scripted.append(OUT["ok"])
    got = tools.remove_software({"name": "python3"}, ctx)
    check("remove_software core call", calls[0] == ("apk_del", "python3", {"force": True, "timeout": 600}), calls)
    check("remove_software core reply", got.startswith("removed python3 -- it was part of LLM OS itself"), repr(got))

    # ---- everyday.vpn: a WireGuard file is found, the program install fails: reply text unchanged
    conf = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
    conf.write("[Interface]\nPrivateKey = test\n")
    conf.close()
    everyday.glob.glob = lambda pattern: [conf.name] if pattern.endswith("*.conf") else []
    shutil.which = lambda name, *a, **k: None
    try:
        for key, want in (("boom", "Couldn't get the VPN program (wireguard-tools): boom"),
                          ("timeout", "Couldn't get the VPN program (wireguard-tools): timed out after 900 s")):
            del calls[:]
            desk = Desk()
            scripted.append(OUT[key])
            everyday.vpn(desk, "line", "connect to my vpn")
            check(f"vpn {key} call", calls[0] == ("apk_add", ["wireguard-tools"], {"quiet": True, "timeout": 600}), calls)
            check(f"vpn {key} reply", desk.replies == [want], desk.replies)
    finally:
        os.unlink(conf.name)

    # ---- everyday.system_more: shell install. Writing /etc/passwd is stubbed out (open raises OSError).
    def denied_open(*a, **k):
        raise OSError("denied")

    everyday.open = denied_open

    # install failed: zsh is still not found afterwards
    shutil.which = lambda name, *a, **k: None
    del calls[:]
    desk = Desk()
    scripted.append(OUT["timeout"])
    everyday.system_more(desk, "line", "change my shell to zsh")
    check("shell timeout call", calls[0] == ("apk_add", ["zsh"], {"quiet": True, "timeout": 600}), calls)
    check("shell timeout reply", desk.replies == ["Couldn't install zsh: timed out after 900 s"], desk.replies)

    # install succeeded: zsh is found on the second lookup, so the shell step runs (its write is stubbed)
    which_seq = [None]          # first lookup: not installed; afterwards: installed

    def which_then(name, *a, **k):
        if which_seq[0] is None:
            which_seq[0] = "done"
            return None
        return "/bin/zsh"

    shutil.which = which_then
    del calls[:]
    desk = Desk()
    scripted.append(OUT["ok"])
    everyday.system_more(desk, "line", "change my shell to zsh")
    check("shell ok call", calls[0] == ("apk_add", ["zsh"], {"quiet": True, "timeout": 600}), calls)
    check("shell ok reached the shell step", desk.replies == ["Couldn't change it: something went wrong."], desk.replies)
finally:
    restore()

print("all good")
