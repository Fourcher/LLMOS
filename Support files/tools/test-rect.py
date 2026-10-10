#!/usr/bin/env python3
"""Host test of the test-shell control command `rect <id> <css selector>` (desk.py): the page's answer for an element's
on-screen box, text and value comes back through Desk.handle("rect.result"). desk.py needs GTK, so the real `class Desk`
source is executed without GTK, and its real methods (_control_conn, handle) are bound to a fake object that carries only
what they use. Run: python3 tools/test-rect.py"""
import io
import json
import os
import re
import socket
import subprocess
import shutil
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py")
src = open(SRC, encoding="utf-8").read()

# the Desk class and nothing after it up to control(): a class body with no top-level code of its own
body = src[src.index("class Desk:"):src.index("\ndef control(argv):")]
flags = {"testshell": ""}
ns = {
    "__name__": "desk_test", "json": json, "os": os, "re": re, "socket": socket, "subprocess": subprocess,
    "shutil": shutil, "sys": sys, "threading": threading, "time": time,
    "SCREEN_MESSAGES": {"desk": set(), "boot": set()},
    "_fwcfg": lambda key: flags.get(key, ""),
}
exec(body, ns)
Desk = ns["Desk"]


class FakeConn:
    def __init__(self, line):
        self.line = line
        self.sent = b""

    def settimeout(self, t):
        pass

    def makefile(self, mode, encoding=None):
        return io.StringIO(self.line + "\n")

    def sendall(self, data):
        self.sent += data

    def close(self):
        pass


class FakeDesk:
    """Only what the rect code uses: the screen, the wait table, emit, and the methods it calls on itself."""
    def __init__(self, reply_for=None):
        self.screen = "desk"
        self._rect_wait = {}
        self.emitted = []
        self.reply_for = reply_for      # fn(rid) -> (delay, msg) makes the page answer; None = no answer
        self.lock = threading.Lock()

    def emit(self, msg):
        self.emitted.append(msg)
        if msg.get("t") != "eval" or self.reply_for is None:
            return
        rid = json.loads(re.search(r"id:(\"[^\"]*\")", msg["js"]).group(1))
        delay, reply = self.reply_for(rid)
        threading.Thread(target=lambda: (time.sleep(delay), Desk.handle.__get__(self)(reply)), daemon=True).start()

    def control(self, line):
        conn = FakeConn(line)
        Desk._control_conn.__get__(self)(conn)
        return json.loads(conn.sent.decode())


fails = 0


def check(cond, what):
    global fails
    if cond:
        print("ok " + what)
    else:
        print("FAIL " + what)
        fails += 1


def page_reply(rid, found=True, x=10, y=20):
    return {"t": "rect.result", "id": rid, "found": found, "x": x, "y": y, "w": 300, "h": 40,
            "text": "Type here", "value": "", "dpr": 2, "vw": 1280, "vh": 800}


# 1. a reply from the page comes back as the answer to `rect 1 #in`, and the selector reaches the page's JS
flags["testshell"] = "1"
single = FakeDesk(reply_for=lambda rid: (0.05, page_reply(rid)))
got = single.control("rect 1 #in")
check(got == page_reply("1"), f"rect 1 #in returns the page's reply: {got}")
check(len(single.emitted) == 1 and single.emitted[0]["t"] == "eval" and json.dumps("#in") in single.emitted[0]["js"],
      "rect emits one eval carrying the selector as a JSON string")
check(single._rect_wait == {}, "the wait entry is removed after the answer")

# 2. two concurrent ids each get their own reply (the second page answer arrives first)
both = FakeDesk(reply_for=lambda rid: ((0.3, page_reply(rid, x=111)) if rid == "1" else (0.0, page_reply(rid, x=222))))
results = {}


def ask(rid):
    results[rid] = both.control(f"rect {rid} #box{rid}")


threads = [threading.Thread(target=ask, args=(r,)) for r in ("1", "2")]
for t in threads:
    t.start()
for t in threads:
    t.join(10)
check(results.get("1", {}).get("x") == 111 and results.get("2", {}).get("x") == 222,
      f"concurrent ids get their own replies: 1->{results.get('1', {}).get('x')} 2->{results.get('2', {}).get('x')}")
check(results.get("1", {}).get("id") == "1" and results.get("2", {}).get("id") == "2", "each reply carries its own id")

# 3. without the test shell the command is refused like any unknown command, and nothing is sent to the page
flags["testshell"] = ""
off = FakeDesk(reply_for=lambda rid: (0.0, page_reply(rid)))
refused = off.control("rect 1 #in")
check(refused == {"error": "unknown command"}, f"testshell off: refused: {refused}")
check(off.emitted == [], "testshell off: nothing emitted to the page")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
