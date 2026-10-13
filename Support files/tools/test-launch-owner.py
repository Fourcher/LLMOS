#!/usr/bin/env python3
"""Owner-account prologue of llmos-desk. Host-only: stubs replace every system command, and every
absolute path the script uses is relocated into a temp root (identically for the base and new copies).

No marker: the script must behave exactly like the base (same log: argv, env, chown/chmod/mkdir calls).
Valid owner marker: /run/llmos is chowned to the owner and the desk re-execs as that owner with its home.
Bad markers and the inner re-exec (LLMOS_DESK_INNER=1): the root path, no su.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[2]
REL = "Support files/src/rootfs/usr/libexec/llmos-desk"
SCRIPT = REPO / REL

PASSWD = """root:x:0:0::/var/root:/bin/sh
toor:x:0:0::/home/owner:/bin/sh
owner:x:501:20::/home/owner:/bin/sh
relhome:x:502:20::relhome:/bin/sh
"""

STUBS = {
    "getent": r'''[ "$1" = passwd ] || exit 2
out=$(awk -F: -v u="$2" '$1==u' "$PASSWD_FILE")
[ -n "$out" ] || exit 2
printf '%s\n' "$out"
''',
    "chown": r'''printf '%s\n' "chown $*" >> "$LOG"
''',
    "chmod": r'''printf '%s\n' "chmod $*" >> "$LOG"
''',
    "mkdir": r'''printf '%s\n' "mkdir $*" >> "$LOG"
exec /bin/mkdir "$@"
''',
    "su": r'''printf '%s\n' "su $*" >> "$LOG"
env | sort | sed 's/^/su-env: /' >> "$LOG"
for last; do :; done
exec /bin/sh -c "$last"
''',
    "dbus-run-session": r'''DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/llmos-test-bus
export DBUS_SESSION_BUS_ADDRESS
shift
exec "$@"
''',
    "seatd-launch": r'''printf '%s\n' "seatd-launch $*" >> "$LOG"
env | sort | sed 's/^/env: /' >> "$LOG"
if [ -f "$XDG_RUNTIME_DIR/a11y.env" ]; then sed 's/^/a11y: /' "$XDG_RUNTIME_DIR/a11y.env" >> "$LOG"; fi
''',
    "labwc": "exit 0\n",
    "python3": "exit 0\n",
    "llmos": r'''printf '%s\n' "llmos $*" >> "$LOG"
''',
}


def relocate(text, root):
    pairs = [
        ("/etc/llmos/owner-user", f"{root}/etc/owner-user"),
        ("/usr/libexec/llmos-desk", f"{root}/libexec/llmos-desk"),
        ("/run/llmos", f"{root}/run/llmos"),
        ("/var/cache/llmos", f"{root}/cache"),
        ("/usr/bin/llmos", f"{root}/bin/llmos"),
        ("/run/seatd.sock", f"{root}/run/seatd.sock"),
    ]
    for a, b in pairs:
        text = text.replace(a, b)
    return text


def run(text, marker=None, inner=False):
    root = tempfile.mkdtemp(prefix="llmos-owner.")
    try:
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        for name, body in STUBS.items():
            path = os.path.join(bindir, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n" + body)
            os.chmod(path, 0o755)
        passwd = os.path.join(root, "passwd")
        with open(passwd, "w") as f:
            f.write(PASSWD)
        log = os.path.join(root, "log")
        open(log, "w").close()
        os.makedirs(os.path.join(root, "etc"))
        os.makedirs(os.path.join(root, "libexec"))
        if marker is not None:
            with open(os.path.join(root, "etc", "owner-user"), "wb") as f:
                f.write(marker)
        script = os.path.join(root, "libexec", "llmos-desk")
        with open(script, "w") as f:
            f.write(relocate(text, root))
        os.chmod(script, 0o755)
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "LOG": log, "PASSWD_FILE": passwd}
        if inner:
            env["LLMOS_DESK_INNER"] = "1"
        p = subprocess.run(["/bin/sh", script], env=env, cwd=root,
                           capture_output=True, text=True, timeout=60)
        with open(log) as f:
            logtext = f.read().replace(root, "@T@")
        return p.returncode, logtext, (p.stdout + p.stderr).replace(root, "@T@")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    fails = []

    def check(cond, label):
        if cond:
            print("ok " + label)
        else:
            fails.append(label)
            print("FAIL " + label)

    syn = subprocess.run(["/bin/sh", "-n", str(SCRIPT)], capture_output=True, text=True)
    check(syn.returncode == 0, "sh -n llmos-desk " + syn.stderr.strip())

    base = subprocess.run(["git", "-C", str(REPO), "show", f"llmos-1.5.0:{REL}"],
                          capture_output=True, text=True)
    check(base.returncode == 0, "base script readable from llmos-1.5.0")
    old = base.stdout
    new = SCRIPT.read_text()

    # (1) no marker: identical to the base script
    rc_o, log_o, _ = run(old)
    rc_n, log_n, out_n = run(new)
    check(rc_o == 0 and rc_n == 0, f"no marker: both exit 0 (base {rc_o}, new {rc_n}) {out_n.strip()}")
    check(log_n == log_o, "no marker: log (argv, env, chown/chmod/mkdir) identical to base")
    check("seatd-launch -- labwc" in log_n, "no marker: seatd-launch -- labwc reached")
    check("env: HOME=/root" in log_n, "no marker: HOME=/root")
    check("a11y: DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/llmos-test-bus" in log_n,
          "no marker: a11y.env written with bus address")
    check("su " not in log_n and "chown " not in log_n, "no marker: no su or chown")

    # (2) valid owner marker
    rc, log, out = run(new, marker=b"owner\n")
    lines = log.splitlines()

    def first(prefix):
        return next((i for i, l in enumerate(lines) if l.startswith(prefix)), None)

    i_chown = first("chown -R owner:owner @T@/run/llmos")
    i_chmod = first("chmod 700 @T@/run/llmos")
    i_su = first("su -p -s /bin/sh owner -c exec @T@/libexec/llmos-desk")
    check(rc == 0, f"owner: exit 0 {out.strip()}")
    check(i_chown is not None and i_su is not None and i_chown < i_su,
          "owner: chown -R owner:owner /run/llmos before su")
    check(i_chmod is not None and i_su is not None and i_chmod < i_su,
          "owner: chmod 700 /run/llmos before su")
    check(sum(1 for l in lines if l.startswith("su ")) == 1, "owner: exactly one su re-exec")
    check("su-env: LLMOS_DESK_INNER=1" in log and "su-env: LLMOS_DESK_HOME=/home/owner" in log
          and "su-env: USER=owner" in log and "su-env: LOGNAME=owner" in log,
          "owner: su receives INNER=1, LLMOS_DESK_HOME, USER, LOGNAME")
    check("env: HOME=/home/owner" in log, "owner: inner desk runs with HOME=/home/owner")
    check("a11y: DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/llmos-test-bus" in log,
          "owner: a11y.env written with bus address")

    # (3) adversarial markers: the root path (same log as no marker, no su, no chown)
    cases = [
        (b"", False, "empty"),
        (b"root\n", False, "root"),
        (b"nosuchuser\n", False, "nonexistent user"),
        (b"owner; rm -rf /\n", False, "rm -rf / injection"),
        (b"rm -rf /\n", False, "rm -rf /"),
        (b"$(id)\n", False, "$(id)"),
        (b"toor\n", False, "uid-0 alias"),
        (b"relhome\n", False, "relative home"),
    ]
    for marker, inner, label in cases:
        rc, log, _ = run(new, marker=marker, inner=inner)
        check(rc == 0 and log == log_o, f"marker {label}: root path, log identical to no-marker base")

    rc, log, _ = run(new, marker=b"owner\n", inner=True)
    check(rc == 0 and "su " not in log and "chown " not in log and "env: HOME=/root" in log,
          "LLMOS_DESK_INNER=1 with valid owner: prologue skipped, HOME=/root, no su")

    if fails:
        print("FAILED: " + "; ".join(fails))
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
