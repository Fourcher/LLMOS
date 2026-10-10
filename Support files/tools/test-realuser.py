#!/usr/bin/env python3
"""Offline test for tools/realuser.py with a fake QMP and a fake VM. Stdlib only."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import realuser  # noqa: E402
from realuser import RealUser  # noqa: E402

W, H = 1600, 1200
VW = 800  # CSS viewport width -> scale 2


class FakeQMP:
    def __init__(self, drop_first_char=False):
        self.calls = []
        self.value = ""  # value of the focused text field
        self.drop_first_char = drop_first_char
        self._types = 0

    def click(self, px, py, w, h, button="left"):
        self.calls.append(("click", px, py, w, h))

    def type(self, text, delay_ms=40, secret=False):
        self.calls.append(("type", secret))
        self._types += 1
        out = text
        if self.drop_first_char and self._types == 1:
            out = text[:-1]  # first typing loses its last character
        self.value += out

    def combo(self, *names):
        self.calls.append(("combo",) + names)
        if names == ("ctrl", "a"):
            self.value = ""  # select-all then type replaces the field

    def key(self, name):
        self.calls.append(("key", name))

    def shot(self, path, fmt="ppm"):
        self.calls.append(("shot", fmt))


def ppm_header(w, h):
    return b"P6\n%d %d\n255\n" % (w, h)


def make_vm(qmp, rects):
    cmds = []

    def run_in_vm(cmd):
        cmds.append(cmd)
        sel = cmd.split("'")[1]
        if sel not in rects:
            return json.dumps({"ok": False, "error": "no match"})
        r = dict(rects[sel])
        r.setdefault("vw", VW)
        if sel == "#field":
            r["value"] = qmp.value
        return json.dumps(r)

    return run_in_vm, cmds


def grab():
    return ppm_header(W, H)


RECTS = {
    "#field": {"x": 100, "y": 50, "w": 200, "h": 40},
    "#dlg-yes": {"x": 10, "y": 20, "w": 60, "h": 30},
    "#dlg-no": {"x": 90, "y": 20, "w": 60, "h": 30},
}


def check(cond, label):
    if not cond:
        print("FAIL %s" % label)
        sys.exit(1)
    print("ok %s" % label)


# 1. click_sel centre scaled to screen pixels
q = FakeQMP()
vm, cmds = make_vm(q, RECTS)
u = RealUser(q, vm, grab=grab)
u.click_sel("#field")
clicks = [c for c in q.calls if c[0] == "click"]
check(clicks == [("click", 400, 140, W, H)], "click_sel clicks (400,140) at 1600x1200")
check(cmds[0] == "llmos desk-ctl rect 1 '#field'", "rect command format and counter")

# 2. type_into retypes exactly once on mismatch and returns True
q = FakeQMP(drop_first_char=True)
vm, cmds = make_vm(q, RECTS)
u = RealUser(q, vm, grab=grab)
ok = u.type_into("#field", "hello")
types = [c for c in q.calls if c[0] == "type"]
check(ok is True and q.value == "hello", "type_into returns True after one retype")
check(len(types) == 2, "type_into typed exactly twice on mismatch")
check(sum(1 for c in q.calls if c == ("combo", "ctrl", "a")) == 1, "type_into selected all once before retype")

# 3. matching first try: no retype
q = FakeQMP()
vm, cmds = make_vm(q, RECTS)
u = RealUser(q, vm, grab=grab)
ok = u.type_into("#field", "hello", secret=True)
types = [c for c in q.calls if c[0] == "type"]
check(ok is True, "type_into returns True on first try")
check(len(types) == 1 and types[0] == ("type", True), "no retype when first try matches (secret passed through)")
check(not any(c[0] == "combo" for c in q.calls), "no select-all when first try matches")

# 4. answer_dialog(True) clicks centre of #dlg-yes
q = FakeQMP()
vm, cmds = make_vm(q, RECTS)
u = RealUser(q, vm, grab=grab)
u.answer_dialog(True)
clicks = [c for c in q.calls if c[0] == "click"]
# centre (10+30, 20+15) = (40, 35) CSS -> (80, 70) screen
check(clicks == [("click", 80, 70, W, H)], "answer_dialog(True) clicks centre of #dlg-yes")

# 5. rect error raises
q = FakeQMP()
vm, cmds = make_vm(q, RECTS)
u = RealUser(q, vm, grab=grab)
try:
    u.rect("#missing")
    check(False, "rect raises RuntimeError on ok:false")
except RuntimeError:
    check(True, "rect raises RuntimeError on ok:false")

print("all good")
