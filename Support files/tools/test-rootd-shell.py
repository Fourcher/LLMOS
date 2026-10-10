#!/usr/bin/env python3
"""Tests for the default-shell path: system.set_shell (root and non-root), the rootd set_shell verb (input checks),
and everyday's "change my shell to ..." reply. PASSWD and SHELLS point at temp files, rootd_client.call is patched
for the non-root path, and the shell-existence check is patched to a fake executable. Nothing real is written.
Run: python3 tools/test-rootd-shell.py"""
import os
import shutil
import stat
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import everyday, rootd, rootd_client, system  # noqa: E402
from llmos.rootd_client import RootdError  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    if cond:
        print("ok", name)
    else:
        fails += 1
        print("FAIL", name)


tmp = tempfile.mkdtemp(prefix="rootd-shell-")
etc = os.path.join(tmp, "etc")
os.makedirs(etc)
PASSWD_T = os.path.join(etc, "passwd")
SHELLS_T = os.path.join(etc, "shells")
PASSWD_BODY = ("root:x:0:0:root:/root:/bin/ash\n"
               "daemon:x:2:2:daemon:/sbin:/sbin/nologin\n"
               "alice:x:1000:1000::/home/alice:/bin/sh\n")
SHELLS_BODY = "/bin/sh\n/bin/ash\n"

# A real executable (the fake /bin/bash) and a non-executable file (the fake /bin/zsh).
FAKE_EXEC = os.path.join(tmp, "fake-bash")
FAKE_NOEXEC = os.path.join(tmp, "fake-zsh")
for p, mode in ((FAKE_EXEC, 0o755), (FAKE_NOEXEC, 0o644)):
    with open(p, "w") as f:
        f.write("#!/bin/sh\n")
    os.chmod(p, mode)

real_is_shell_file = rootd._is_shell_file


def fake_is_shell_file(path):
    # Route the allowed shell paths to the fake files, then use the real check on them.
    mapping = {"/bin/bash": FAKE_EXEC, "/bin/zsh": FAKE_NOEXEC}
    return real_is_shell_file(mapping.get(path, path))


rootd._is_shell_file = fake_is_shell_file


def reset():
    with open(PASSWD_T, "w") as f:
        f.write(PASSWD_BODY)
    os.chmod(PASSWD_T, 0o640)
    with open(SHELLS_T, "w") as f:
        f.write(SHELLS_BODY)
    os.chmod(SHELLS_T, 0o644)


def read(p):
    with open(p) as f:
        return f.read()


system.PASSWD = PASSWD_T
system.SHELLS = SHELLS_T

# ---- 1. root path: system.set_shell("root", ...) ----
reset()
system.set_shell("root", "/bin/bash")
lines = read(PASSWD_T).split("\n")
check("root: only the root line changed",
      lines[0] == "root:x:0:0:root:/root:/bin/bash" and lines[1:] == PASSWD_BODY.split("\n")[1:])
check("root: passwd mode kept (0640)", stat.S_IMODE(os.stat(PASSWD_T).st_mode) == 0o640)
check("root: shells mode kept (0644)", stat.S_IMODE(os.stat(SHELLS_T).st_mode) == 0o644)
check("root: shell appended to shells", read(SHELLS_T) == "/bin/sh\n/bin/ash\n/bin/bash\n")
system.set_shell("root", "/bin/bash")
check("root: repeat does not append twice", read(SHELLS_T) == "/bin/sh\n/bin/ash\n/bin/bash\n")
check("root: repeat keeps passwd line", read(PASSWD_T).split("\n")[0] == "root:x:0:0:root:/root:/bin/bash")
check("root: no temp files left behind", sorted(os.listdir(etc)) == ["passwd", "shells"])
os.chmod(PASSWD_T, 0o640)

# ---- 2. non-root path: rootd call ----
reset()
calls = []


def fake_call(verb, _timeout=None, **args):
    calls.append((verb, args))
    return reply["value"]


real_call = rootd_client.call
rootd_client.call = fake_call
reply = {"value": "ok"}
try:
    system.set_shell("alice", "/bin/sh")
    check("non-root: sends set_shell to rootd",
          calls == [("set_shell", {"user": "alice", "shell": "/bin/sh"})])
    check("non-root: passwd untouched by the caller", read(PASSWD_T) == PASSWD_BODY)
    calls.clear()

    def raising_call(verb, _timeout=None, **args):
        raise RootdError("bad args: shell")

    rootd_client.call = raising_call
    try:
        system.set_shell("alice", "/tmp/evil")
        check("non-root: RootdError becomes OSError", False)
    except OSError as e:
        check("non-root: RootdError becomes OSError with its text", "bad args: shell" in str(e))
    rootd_client.call = fake_call
    reply["value"] = "something else"
    try:
        system.set_shell("alice", "/bin/sh")
        check("non-root: a reply other than ok raises", False)
    except OSError:
        check("non-root: a reply other than ok raises", True)
finally:
    rootd_client.call = real_call

# ---- 3. rootd verb: good input, then every adversarial input ----
reset()
check("verb: accepts root + /bin/bash", rootd.VERBS["set_shell"]({"user": "root", "shell": "/bin/bash"}) == "ok")
check("verb: root line rewritten", read(PASSWD_T).split("\n")[0] == "root:x:0:0:root:/root:/bin/bash")
reset()


def rejected(args):
    try:
        rootd.VERBS["set_shell"](args)
    except ValueError:
        return True
    return False


bad_shells = [
    "/bin/bash\nroot2::0:0::/:/bin/sh",
    "/tmp/evil",
    "../bin/sh",
    "/bin/bash ",
    "/usr/bin/bash",
    "/bin/nologin",
    "/bin/zsh",  # listed, but not an executable file (patched check)
    "",
    None,
    5,
]
for sh in bad_shells:
    check(f"verb: rejects shell {sh!r}", rejected({"user": "root", "shell": sh}))
for user in ["nobody", "root:x", "Root", "root\n", "", "alice", None]:
    check(f"verb: rejects user {user!r}", rejected({"user": user, "shell": "/bin/bash"}))
check("verb: rejects non-object args", rejected("root"))
check("verb: rejects missing args", rejected({}))
rootd._is_shell_file = lambda p: False
check("verb: rejects a listed shell that is not installed (/bin/bash missing)",
      rejected({"user": "root", "shell": "/bin/bash"}))
rootd._is_shell_file = fake_is_shell_file
check("verb: adversarial inputs leave passwd untouched", read(PASSWD_T) == PASSWD_BODY)
check("verb: adversarial inputs leave shells untouched", read(SHELLS_T) == SHELLS_BODY)

# A symlinked PASSWD or SHELLS is refused, and the link target is not touched.
target = os.path.join(tmp, "target-passwd")
with open(target, "w") as f:
    f.write(PASSWD_BODY)
link = os.path.join(tmp, "passwd-link")
os.symlink(target, link)
system.PASSWD = link
check("verb: refuses a symlinked PASSWD", rejected({"user": "root", "shell": "/bin/bash"}))
system.PASSWD = PASSWD_T
check("verb: symlink target untouched", read(target) == PASSWD_BODY)
slink = os.path.join(tmp, "shells-link")
os.symlink(SHELLS_T, slink)
system.SHELLS = slink
check("verb: refuses a symlinked SHELLS", rejected({"user": "root", "shell": "/bin/bash"}))
system.SHELLS = SHELLS_T

# ---- 3b. system._set_shell_root called directly: shared check, missing user, adversarial inputs ----
reset()
system._set_shell_root("root", "/bin/bash")
check("direct: positive change writes the root line",
      read(PASSWD_T).split("\n")[0] == "root:x:0:0:root:/root:/bin/bash")
check("direct: positive change appends shell once", read(SHELLS_T) == "/bin/sh\n/bin/ash\n/bin/bash\n")
system._set_shell_root("root", "/bin/bash")
check("direct: idempotent, shells not doubled", read(SHELLS_T) == "/bin/sh\n/bin/ash\n/bin/bash\n")
check("direct: passwd mode kept (0640)", stat.S_IMODE(os.stat(PASSWD_T).st_mode) == 0o640)
reset()


def direct_rejects(user, shell):
    try:
        system._set_shell_root(user, shell)
    except ValueError as e:
        return str(e)
    return None


direct_cases = [
    ("root", "/bin/bash\nevil:x:0:0::/:/bin/sh", "bad shell", "newline in shell"),
    ("root", "/bin/ba:sh", "bad shell", "colon in shell"),
    ("root", "bin/bash", "bad shell", "relative shell path"),
    ("root", "/bin/../tmp/x", "bad shell", "dot-dot segment in shell"),
    ("root", FAKE_NOEXEC, "bad shell", "non-executable file as shell"),
    ("root", "/nonexistent/bash", "bad shell", "missing shell file"),
    ("root\n", "/bin/bash", "bad user", "user with trailing newline"),
    ("root:x", "/bin/bash", "bad user", "colon in user"),
    ("", "/bin/bash", "bad user", "empty user"),
    ("nobody", "/bin/bash", "no such user", "user missing from passwd"),
    ("alice", "/bin/bash", "no such user", "user with no uid-0 line"),
]
for user, shell, want, label in direct_cases:
    got = direct_rejects(user, shell)
    check(f"direct: rejects {label} ({got})", got == want)
    check(f"direct: {label} writes nothing", read(PASSWD_T) == PASSWD_BODY and read(SHELLS_T) == SHELLS_BODY)

# ---- 3c. system._set_shell_root: no trailing newline in SHELLS, and linked files via the direct path ----
reset()
with open(SHELLS_T, "w") as f:
    f.write("/bin/sh\n/bin/ash")
system._set_shell_root("root", "/bin/bash")
check("nonl: one clean appended line, no merge",
      read(SHELLS_T) == "/bin/sh\n/bin/ash\n/bin/bash\n")
system._set_shell_root("root", "/bin/bash")
check("nonl: second call adds nothing", read(SHELLS_T) == "/bin/sh\n/bin/ash\n/bin/bash\n")
reset()
with open(SHELLS_T, "w") as f:
    f.write("/bin/sh\n/bin/bash")
system._set_shell_root("root", "/bin/bash")
check("nonl: shell already on last line without newline -> no change",
      read(SHELLS_T) == "/bin/sh\n/bin/bash")
reset()

# direct path: a symlinked PASSWD or SHELLS raises ValueError before any write; the targets are untouched.
pw_target = os.path.join(tmp, "direct-target-passwd")
sh_target = os.path.join(tmp, "direct-target-shells")
with open(pw_target, "w") as f:
    f.write(PASSWD_BODY)
with open(sh_target, "w") as f:
    f.write(SHELLS_BODY)
pw_link = os.path.join(tmp, "direct-passwd-link")
sh_link = os.path.join(tmp, "direct-shells-link")
os.symlink(pw_target, pw_link)
os.symlink(sh_target, sh_link)
system.PASSWD = pw_link
system.SHELLS = SHELLS_T
try:
    system._set_shell_root("root", "/bin/bash")
    check("direct link: symlinked PASSWD refused", False)
except ValueError as e:
    check("direct link: symlinked PASSWD refused with 'refusing a linked file'", str(e) == "refusing a linked file")
check("direct link: PASSWD symlink target untouched", read(pw_target) == PASSWD_BODY)
check("direct link: SHELLS untouched when PASSWD is linked", read(SHELLS_T) == SHELLS_BODY)
system.PASSWD = PASSWD_T
system.SHELLS = sh_link
try:
    system._set_shell_root("root", "/bin/bash")
    check("direct link: symlinked SHELLS refused", False)
except ValueError as e:
    check("direct link: symlinked SHELLS refused with 'refusing a linked file'", str(e) == "refusing a linked file")
check("direct link: SHELLS symlink target untouched", read(sh_target) == SHELLS_BODY)
check("direct link: PASSWD untouched when SHELLS is linked", read(PASSWD_T) == PASSWD_BODY)
system.PASSWD = PASSWD_T
system.SHELLS = SHELLS_T
reset()

# ---- 4. everyday: calls system.set_shell and keeps its replies ----


class FakeDesk:
    def __init__(self):
        self.replies = []

    def emit(self, msg):
        pass

    def instant_reply(self, line, text):
        self.replies.append(text)


real_which = everyday.shutil.which
real_set_shell = system.set_shell
set_calls = []
everyday.shutil.which = lambda name: {"bash": "/bin/bash", "zsh": "/bin/zsh"}.get(name)
try:
    desk = FakeDesk()
    system.set_shell = lambda user, shell: set_calls.append((user, shell))
    got = everyday.system_more(desk, "LINE", "change my shell to bash")
    check("everyday: returns True", got is True)
    check("everyday: calls system.set_shell('root', path)", set_calls == [("root", "/bin/bash")])
    check("everyday: success reply kept",
          desk.replies == ["New terminals now use bash (/bin/bash)."])

    set_calls.clear()
    desk = FakeDesk()
    got = everyday.system_more(desk, "LINE", "change my shell to zsh")
    check("everyday: zsh reply keeps the oh-my-zsh line",
          desk.replies == ["New terminals now use zsh (/bin/zsh). For oh-my-zsh, say “run the oh-my-zsh installer”."])

    def failing(user, shell):
        raise OSError(13, "Permission denied")

    system.set_shell = failing
    desk = FakeDesk()
    everyday.system_more(desk, "LINE", "change my shell to bash")
    check("everyday: failure reply kept", len(desk.replies) == 1 and desk.replies[0].startswith("Couldn't change it: "))
finally:
    system.set_shell = real_set_shell
    everyday.shutil.which = real_which

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
