#!/usr/bin/env python3
"""Tests for tools/qmp.py against a fake QMP server on a temp UNIX socket."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qmp  # noqa: E402

SHIFT = {"type": "qcode", "data": "shift"}


def serve(srv, log):
    conn, _ = srv.accept()
    f = conn.makefile("rb")
    conn.sendall(b'{"QMP": {"version": {}, "capabilities": []}}\n')
    n = 0
    for line in f:
        log.append(json.loads(line))
        n += 1
        if n == 2:  # one event before a reply, to prove events are skipped
            conn.sendall(b'{"event": "RESUME", "data": {}, "timestamp": {"seconds": 0, "microseconds": 0}}\n')
        conn.sendall(b'{"return": {}}\n')
    conn.close()


def fail(msg):
    print("FAIL " + msg)
    sys.exit(1)


def check(cond, msg):
    if not cond:
        fail(msg)
    print("ok " + msg)


def abs_values(m):
    ev = m["arguments"]["events"]
    return {e["data"]["axis"]: e["data"]["value"] for e in ev}


def main():
    tmp = tempfile.mkdtemp(prefix="qmpt")
    path = os.path.join(tmp, "q.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)
    log = []
    t = threading.Thread(target=serve, args=(srv, log), daemon=True)
    t.start()
    c = qmp.QMP(path)

    # click at top-left
    i = len(log)
    c.click(0, 0, 800, 600)
    sent = log[i:]
    check(len(sent) == 3, "click sends three commands (move, down, up): got %d" % len(sent))
    vals = abs_values(sent[0])
    check(vals == {"x": 0, "y": 0}, "click(0,0,800,600) -> x 0, y 0: %r" % vals)

    # click at bottom-right
    i = len(log)
    c.click(799, 599, 800, 600)
    vals = abs_values(log[i])
    check(vals == {"x": 0x7fff, "y": 0x7fff}, "click(799,599,800,600) -> 0x7fff, 0x7fff: %r" % vals)

    # button down and up are separate commands
    down = log[i + 1]["arguments"]["events"]
    up = log[i + 2]["arguments"]["events"]
    check(len(down) == 1 and down[0] == {"type": "btn", "data": {"down": True, "button": "left"}},
          "click sends btn down as its own command")
    check(len(up) == 1 and up[0] == {"type": "btn", "data": {"down": False, "button": "left"}},
          "click sends btn up as its own command")

    # typing
    i = len(log)
    c.type("A", delay_ms=0)
    m = log[i]
    check(m["execute"] == "send-key" and m["arguments"]["keys"] == [SHIFT, {"type": "qcode", "data": "a"}],
          "type('A') sends shift + a in one send-key")

    i = len(log)
    c.type("?", delay_ms=0)
    m = log[i]
    check(m["execute"] == "send-key" and m["arguments"]["keys"] == [SHIFT, {"type": "qcode", "data": "slash"}],
          "type('?') sends shift + slash in one send-key")

    i = len(log)
    try:
        c.type("é", delay_ms=0)
        fail("type('é') did not raise")
    except ValueError as e:
        check(len(log) == i, "type('é') raises ValueError and sends nothing")
        print("ok message: %s" % e)

    i = len(log)
    try:
        c.type("pé", secret=True, delay_ms=0)
        fail("type('pé', secret=True) did not raise")
    except ValueError as e:
        msg = str(e)
        check("pé" not in msg and "é" not in msg,
              "secret type error does not include the text")
        check(len(log) == i, "secret type with unknown char sends nothing")

    c.close()
    t.join(timeout=5)
    srv.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("all good")


if __name__ == "__main__":
    main()
