#!/usr/bin/env python3
"""Drive a QEMU guest's serial console for testing.

QEMU is started with:
  -chardev socket,id=ser0,path=SOCK,server=on,wait=off,logfile=LOG,logappend=on
  -serial chardev:ser0
so every byte the guest prints lands in LOG even when no client is attached.

Subcommands:
  mark LOG                         print current LOG size (use as --from offset)
  send SOCK TEXT [--raw]           type TEXT into the console (adds CR unless --raw)
  wait LOG REGEX TIMEOUT [--from N] block until REGEX appears after offset N; print new output
  run  SOCK LOG TEXT REGEX TIMEOUT send TEXT, then wait for REGEX; print output
"""
import os, re, socket, sys, time


def mark(log):
    return os.path.getsize(log) if os.path.exists(log) else 0


def send(sock_path, text, raw=False):
    data = text if raw else text + "\r"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    # type slowly-ish: serial getty/readline can drop bytes on big bursts under TCG
    for i in range(0, len(data), 16):
        s.sendall(data[i:i + 16].encode())
        time.sleep(0.02)
    time.sleep(0.2)
    s.close()


ESC_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|\r")


def read_from(log, off):
    with open(log, "rb") as f:
        f.seek(off)
        return ESC_RE.sub("", f.read().decode("utf-8", "replace"))


def wait(log, pattern, timeout, off=0, quiet=0.0):
    """Wait until PATTERN appears after OFF; with QUIET, also require that
    nothing more is printed for that many seconds (so a prompt-looking
    fragment inside streamed output does not count)."""
    rx = re.compile(pattern, re.M)
    t0 = time.time()
    while True:
        out = read_from(log, off) if os.path.exists(log) else ""
        if rx.search(out):
            if quiet:
                size = mark(log)
                time.sleep(quiet)
                if mark(log) != size:
                    continue
                out = read_from(log, off)
            return True, out, time.time() - t0
        if time.time() - t0 > timeout:
            return False, out, time.time() - t0
        time.sleep(0.5)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(2)
    cmd = a[0]
    if cmd == "mark":
        print(mark(a[1]))
    elif cmd == "send":
        send(a[1], a[2], raw="--raw" in a)
    elif cmd in ("wait", "run"):
        if cmd == "run":
            sock, log, text, pattern, timeout = a[1], a[2], a[3], a[4], float(a[5])
            off = mark(log)
            time.sleep(1.2)   # the console flushes input while it re-arms its line editor
            send(sock, text, raw="--raw" in a)
        else:
            log, pattern, timeout = a[1], a[2], float(a[3])
            off = int(a[a.index("--from") + 1]) if "--from" in a else 0
        quiet = float(a[a.index("--quiet") + 1]) if "--quiet" in a else 0.0
        ok, out, dt = wait(log, pattern, timeout, off, quiet)
        sys.stdout.write(out)
        sys.stdout.write("\n[vmctl: %s after %.1fs]\n" % ("matched" if ok else "TIMEOUT", dt))
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
