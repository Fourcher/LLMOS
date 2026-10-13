#!/usr/bin/env python3
"""Check that `vmctl.py run --fast` is quick and returns the same output as the
default run. A fake console (UNIX socket thread) answers each received line by
appending output and a DONE_7 marker to a log file, the way QEMU's serial log
does; vmctl reads the log file, not the socket."""
import os, socket, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
VMCTL = os.path.join(HERE, "vmctl.py")
RESPONSE = "...output\nDONE_7\n"


def serve(sock_path, state, ready):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(4)
    ready.set()
    while True:
        conn, _ = srv.accept()
        buf = b""
        while not (b"\r" in buf or b"\n" in buf):
            chunk = conn.recv(256)
            if not chunk:
                break
            buf += chunk
        with open(state["log"], "ab") as f:
            f.write(RESPONSE.encode())
        conn.close()


def run_vmctl(sock_path, log, extra):
    args = [sys.executable, "-I", VMCTL, "run", sock_path, log,
            "echo hi; echo DONE_\"\"7", "^DONE_7", "10", "--quiet", "1"] + extra
    t0 = time.time()
    p = subprocess.run(args, capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(log)))
    dt = time.time() - t0
    assert p.returncode == 0, (extra, p.returncode, p.stdout, p.stderr)
    body = p.stdout.split("\n[vmctl:")[0]
    return body, dt


def main():
    tmp = tempfile.mkdtemp(prefix="vmctlfast")
    os.chdir(tmp)                      # a relative socket name: the project folder's path is longer than a socket path may be
    sock_path = "s.sock"
    ready = threading.Event()
    state = {"log": None}
    th = threading.Thread(target=serve, args=(sock_path, state, ready), daemon=True)
    th.start()
    ready.wait(5)
    results = {}
    for mode, extra in (("slow", []), ("fast", ["--fast"])):
        log = os.path.join(tmp, mode + ".log")
        open(log, "wb").close()
        state["log"] = log
        results[mode] = run_vmctl(sock_path, log, extra)
        print("ok %s %.2fs output=%r" % (mode, results[mode][1], results[mode][0]))
    slow_out, slow_dt = results["slow"]
    fast_out, fast_dt = results["fast"]
    assert fast_dt < 1.5,"fast run too slow: %.2fs" % fast_dt
    assert slow_dt > 2.0, "default run unexpectedly fast: %.2fs" % slow_dt
    assert slow_out == fast_out, (slow_out, fast_out)
    assert "DONE_7" in fast_out and "...output" in fast_out
    print("ok timing fast=%.2fs default=%.2fs same-output" % (fast_dt, slow_dt))
    print("all good")


if __name__ == "__main__":
    main()
