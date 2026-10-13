#!/usr/bin/env python3
"""Static and simulated checks for the opt-in owner account block in src/install.sh.

The block runs only when LLMOS_OWNER is exactly 1. It is executed here in /tmp with
stub addgroup/adduser/rc-update/getent/chroot programs on PATH; the stubs keep state
so a second run sees the account as existing. Nothing touches the host's accounts or /etc.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "src", "install.sh")
START = 'if [ "${LLMOS_OWNER:-0}" = 1 ]; then'
WATCH = ("addgroup", "adduser", "rc-update add llmos-rootd", "owner-user")
GROUPS = ["video", "input", "audio", "seat", "netdev", "plugdev"]

STUBS = {
    "getent": '''#!/bin/sh
echo "getent $*" >> "$LOG"
case "$1" in
  group) [ -e "$STATE/group.$2" ] ;;
  passwd) [ -e "$STATE/passwd.$2" ] ;;
  *) exit 2 ;;
esac
''',
    "addgroup": '''#!/bin/sh
echo "addgroup $*" >> "$LOG"
if [ "$1" = -S ]; then
  if [ -e "$STATE/group.$2" ]; then echo "addgroup: group '$2' in use" >&2; exit 1; fi
  : > "$STATE/group.$2"; exit 0
fi
[ -e "$STATE/group.$2" ] || { echo "addgroup: unknown group $2" >&2; exit 1; }
if [ -e "$STATE/member.$1.$2" ]; then echo "addgroup: user '$1' already in group '$2'" >&2; exit 1; fi
: > "$STATE/member.$1.$2"; exit 0
''',
    "adduser": '''#!/bin/sh
echo "adduser $*" >> "$LOG"
[ -e "$STATE/group.owner" ] || { echo "adduser: no group owner" >&2; exit 1; }
if [ -e "$STATE/passwd.owner" ]; then echo "adduser: user 'owner' in use" >&2; exit 1; fi
: > "$STATE/passwd.owner"; exit 0
''',
    # id and rc-update show are queries: they reflect state and are not logged
    "id": '''#!/bin/sh
[ "$1" = -nG ] && [ "$2" = owner ] || exit 2
[ -e "$STATE/passwd.owner" ] || { echo "id: 'owner': no such user" >&2; exit 1; }
out=owner
for g in video input audio seat netdev plugdev; do
  [ -e "$STATE/member.owner.$g" ] && out="$out $g"
done
echo "$out"; exit 0
''',
    "rc-update": '''#!/bin/sh
if [ "$1" = show ]; then
  [ -e "$STATE/rc.llmos-rootd" ] && echo "llmos-rootd | $2"
  exit 0
fi
echo "rc-update $*" >> "$LOG"
if [ "$1" = add ]; then
  if [ -e "$STATE/rc.$2" ]; then echo "rc-update: $2 already added" >&2; exit 1; fi
  : > "$STATE/rc.$2"
fi
exit 0
''',
    # chroot stub: rewrites /etc/ to the test target, then runs the command (stdin passes through)
    "chroot": '''#!/bin/sh
echo "chroot $*" >> "$LOG"
root=$1; shift
sed "s#/etc/#$root/etc/#g" | "$@"
''',
}


def fail(msg):
    print("FAIL " + msg)
    sys.exit(1)


def check(cond, msg):
    if not cond:
        fail(msg)
    print("ok " + msg)


def static_checks():
    text = open(INSTALL).read()
    lines = text.split("\n")
    r = subprocess.run(["sh", "-n", INSTALL], capture_output=True, text=True)
    check(r.returncode == 0, "sh -n install.sh clean " + r.stderr.strip())

    starts = [i for i, l in enumerate(lines) if l == START]
    check(len(starts) == 1, "exactly one owner flag block")
    s = starts[0]
    e = next(j for j in range(s + 1, len(lines)) if lines[j] == "fi")
    block = lines[s:e + 1]
    body = lines[s + 1:e]
    check(body[0].startswith("chroot $TARGET sh -eu <<'EOF'"), "block body runs in target via quoted heredoc")
    check(body[-1] == "EOF", "heredoc closes at end of body")
    print("new block (inside the flag's if/fi):")
    for l in block:
        print("   | " + l)

    # every line that mentions a new command must sit inside the flagged block
    for w in WATCH:
        outside = [i + 1 for i, l in enumerate(lines) if w in l and not (s <= i <= e)]
        check(not outside, "no '%s' outside the flagged block (lines %s)" % (w, outside))

    # flag is read like PAYLOAD/DISK: env with default
    check('LLMOS_OWNER=${LLMOS_OWNER:-0}' in text or 'LLMOS_OWNER:-0' in text, "flag read with env default")
    return block


def run_block(block, env_flag, state, log, target):
    script = os.path.join(ROOT, "block-%d.sh" % RUNS.setdefault("n", 0))
    RUNS["n"] += 1
    with open(script, "w") as f:
        f.write("#!/bin/sh\nset -eu\n" + "\n".join(block) + "\n")
    env = {
        "PATH": os.path.join(ROOT, "bin") + ":/usr/bin:/bin",
        "STATE": state, "LOG": log, "TARGET": target,
    }
    if env_flag is not None:
        env["LLMOS_OWNER"] = env_flag
    r = subprocess.run(["sh", script], env=env, capture_output=True, text=True)
    return r


def read_log(log):
    if not os.path.exists(log):
        return []
    return [l for l in open(log).read().split("\n") if l and not l.startswith("chroot ")]


ROOT = ""
RUNS = {}


def main():
    global ROOT
    block = static_checks()

    root = tempfile.mkdtemp(prefix="owner-test-", dir="/tmp")
    ROOT = root
    try:
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        for name, src in STUBS.items():
            p = os.path.join(bindir, name)
            with open(p, "w") as f:
                f.write(src)
            os.chmod(p, 0o755)

        def fresh(name):
            st = os.path.join(root, name, "state")
            os.makedirs(st)
            return st, os.path.join(root, name, "log"), os.path.join(root, name, "target")

        # A: on, fresh host
        st, log, tg = fresh("on1")
        os.makedirs(tg)
        r = run_block(block, "1", st, log, tg)
        check(r.returncode == 0, "on: block runs OK (rc %d) %s" % (r.returncode, r.stderr.strip()))
        expect = ["getent group owner", "addgroup -S owner",
                  "getent passwd owner", "adduser -D -h /home/owner -s /bin/sh -G owner owner"]
        for g in GROUPS:
            expect += ["getent group %s" % g, "addgroup -S %s" % g, "addgroup owner %s" % g]
        expect += ["rc-update add llmos-rootd default"]
        check(read_log(log) == expect, "on: calls are exactly the expected sequence (%d calls)" % len(expect))
        marker = os.path.join(tg, "etc", "llmos", "owner-user")
        check(os.path.exists(marker) and open(marker).read() == "owner\n", "on: marker /etc/llmos/owner-user = owner")

        # B: on again, same state (rerun)
        open(log, "w").close()
        r = run_block(block, "1", st, log, tg)
        check(r.returncode == 0, "on-again: no failure under set -e (rc %d) %s" % (r.returncode, r.stderr.strip()))
        calls = read_log(log)
        check(not any(c.startswith("addgroup -S") or c.startswith("adduser") for c in calls),
              "on-again: no duplicate addgroup -S / adduser")
        check(not any(c.startswith("addgroup owner ") for c in calls), "on-again: no addgroup owner <g> (already members)")
        check(not any(c.startswith("rc-update add") for c in calls), "on-again: no rc-update add (already added)")
        check(os.path.exists(os.path.join(st, "rc.llmos-rootd")), "on-again: llmos-rootd still in default")
        check(open(marker).read() == "owner\n", "on-again: marker still owner")

        # C, D, E: off (0, empty, unset) on fresh hosts
        for label, flag in (("0", "0"), ("empty", ""), ("unset", None)):
            st, log, tg = fresh("off-" + label)
            os.makedirs(tg)
            r = run_block(block, flag, st, log, tg)
            check(r.returncode == 0, "off (%s): block skipped OK" % label)
            check(read_log(log) == [] and not os.listdir(st), "off (%s): no account, group or service calls" % label)
            check(not os.path.exists(os.path.join(tg, "etc")), "off (%s): no marker written" % label)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("all good")


if __name__ == "__main__":
    main()
