#!/usr/bin/env python3
"""Host test of the test-shell control command `rects <id> <css selector>` (desk.py): the page's answer for every element
matching the selector (items with box, text, tag, id, class, visible, disabled) comes back through Desk.handle("rects.result").
desk.py needs GTK, so the real `class Desk` source is executed without GTK, and its real methods (_control_conn, handle)
are bound to a fake object that carries only what they use. Run: python3 tools/test-rects.py"""
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
    """Only what the rects code uses: the screen, the wait table, emit, and the methods it calls on itself."""
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


def items_reply(rid, items):
    return {"t": "rects.result", "id": rid, "items": items, "vw": 1280, "vh": 800, "dpr": 2}


ITEM = {"i": 0, "x": 10, "y": 20, "w": 300, "h": 40, "text": "Save", "tag": "button", "id": "save",
        "cls": "btn primary", "visible": True, "disabled": False}

# 1. a reply from the page comes back as the answer to `rects 1 .btn`, and the selector reaches the page's JS
flags["testshell"] = "1"
one = FakeDesk(reply_for=lambda rid: (0.05, items_reply(rid, [ITEM])))
got = one.control("rects 1 .btn")
check(got == items_reply("1", [ITEM]), f"rects 1 .btn returns the page's reply: {got}")
check(len(one.emitted) == 1 and one.emitted[0]["t"] == "eval" and "querySelectorAll" in one.emitted[0]["js"]
      and json.dumps(".btn") in one.emitted[0]["js"], "rects emits one eval using querySelectorAll with the selector as a JSON string")
check(one.emitted[0]["js"].count("rects.result") == 2 and "bad selector" in one.emitted[0]["js"],
      "the JS posts rects.result on success and on the bad-selector catch")
check(one._rect_wait == {}, "the wait entry is removed after the answer")

# 2. a selector with spaces and quotes (rejoined from the words after the id) reaches the page as one JSON string
quoted = FakeDesk(reply_for=lambda rid: (0.0, items_reply(rid, [])))
quoted.control("rects 7 a[title=\"Save all\"] > span.x 'q'")
sel = "a[title=\"Save all\"] > span.x 'q'"
check(json.dumps(sel) in quoted.emitted[0]["js"], "selector with spaces and quotes is json-encoded into the JS")

# 3. zero matches -> the page's empty items list comes back as-is
empty = FakeDesk(reply_for=lambda rid: (0.0, items_reply(rid, [])))
got = empty.control("rects 2 .nothing")
check(got == {"t": "rects.result", "id": "2", "items": [], "vw": 1280, "vh": 800, "dpr": 2} and got["items"] == [],
      f"zero matches: items []: {got}")

# 4. an invalid selector: the page's error payload comes back as-is
bad_payload = {"t": "rects.result", "id": "3", "error": "bad selector"}
bad = FakeDesk(reply_for=lambda rid: (0.0, bad_payload))
got = bad.control("rects 3 ][ bad")
check(got == {"t": "rects.result", "id": "3", "error": "bad selector"}, f"invalid selector: error payload returned as-is: {got}")

# 5. the two ids each get their own reply
both = FakeDesk(reply_for=lambda rid: ((0.3, items_reply(rid, [dict(ITEM, i=1)])) if rid == "1" else (0.0, items_reply(rid, [dict(ITEM, i=2)]))))
results = {}


def ask(rid):
    results[rid] = both.control(f"rects {rid} .b{rid}")


threads = [threading.Thread(target=ask, args=(r,)) for r in ("1", "2")]
for t in threads:
    t.start()
for t in threads:
    t.join(10)
check(results.get("1", {}).get("items", [{}])[0].get("i") == 1 and results.get("2", {}).get("items", [{}])[0].get("i") == 2,
      "concurrent ids get their own replies")

# 6. without the test shell the command is refused like any unknown command, and nothing is sent to the page
flags["testshell"] = ""
off = FakeDesk(reply_for=lambda rid: (0.0, items_reply(rid, [ITEM])))
refused = off.control("rects 1 .btn")
check(refused == {"error": "unknown command"}, f"testshell off: refused: {refused}")
check(off.emitted == [], "testshell off: nothing emitted to the page")

# 7. a page reply on the first-run wizard: delivered with the test shell on, ignored with it off
def wizard_reply(flag):
    flags["testshell"] = flag
    w = FakeDesk()
    w.screen = "wizard"
    slot = [threading.Event(), None]
    w._rect_wait["6"] = slot
    Desk.handle.__get__(w)(items_reply("6", [ITEM]))
    return slot


slot = wizard_reply("1")
check(slot[0].is_set() and slot[1] == items_reply("6", [ITEM]), "wizard, testshell on: rects.result for a waiting id is delivered")
slot = wizard_reply("")
check(not slot[0].is_set() and slot[1] is None, "wizard, testshell off: rects.result is ignored")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
