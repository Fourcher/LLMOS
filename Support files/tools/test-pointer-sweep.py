#!/usr/bin/env python3
"""Offline test for tools/pointer-sweep.py with a fake desk, fake QMP and fake VM. Stdlib only."""
import importlib.util
import json
import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_spec = importlib.util.spec_from_file_location("pointer_sweep", os.path.join(HERE, "pointer-sweep.py"))
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

VW, VH = 200, 150  # CSS viewport
W, H = 400, 300    # PPM frame size -> scale 2


class FakeDesk:
    def __init__(self, items, error=None):
        self.items = items
        self.error = error
        self.clicked = []
        self.keys = []
        self.resets = 0
        self.state = {"screen": "desk", "reply": "", "windows": []}

    def run_in_vm(self, cmd):
        if cmd.startswith("llmos desk-ctl rects"):
            assert shlex.split(cmd)[-1] == ps.DEFAULT_SEL, cmd
            if self.error:
                return json.dumps({"error": self.error})
            items = []
            for i, it in enumerate(self.items):
                row = {"i": i, "visible": True, "disabled": False, "id": "", "cls": "", "tag": "button"}
                row.update(it)
                items.append(row)
            return json.dumps({"items": items, "vw": VW, "vh": VH, "dpr": 1})
        if cmd == "llmos desk-state":
            return json.dumps(self.state)
        if cmd == "llmos desk-ctl testreset-min":
            self.resets += 1
            self.state = {"screen": "desk", "reply": "", "windows": []}
            return ""
        raise AssertionError("unexpected VM command: " + cmd)

    def act(self, text):
        self.clicked.append(text)
        if text.startswith("Open"):
            self.state["windows"] = [{"id": 1, "title": "Notes"}]
        elif text.startswith("Say"):
            self.state["reply"] = "hi"
        # "Do nothing" changes nothing


class FakeQMP:
    def __init__(self, desk):
        self.desk = desk

    def click(self, px, py, w, h, button="left"):
        css_x = px * VW / w
        css_y = py * VH / h
        for it in self.desk.items:
            if it["x"] <= css_x < it["x"] + it["w"] and it["y"] <= css_y < it["y"] + it["h"]:
                self.desk.act(it["text"])
                return
        self.desk.clicked.append(None)  # click landed on nothing


class FakeUser:
    def __init__(self, desk):
        self.desk = desk
        self.qmp = FakeQMP(desk)

    def press(self, key):
        self.desk.keys.append(key)
        self.desk.state["windows"] = []


def grab_for(desk):
    def grab():
        rgb = bytearray(b"\x40" * (W * H * 3))
        if desk.state["windows"]:
            for y in range(80, 200):
                off = (y * W + 100) * 3
                rgb[off:off + 200 * 3] = b"\xff" * (200 * 3)
        return b"P6\n%d %d\n255\n" % (W, H) + bytes(rgb)
    return grab


def clock():
    return 0.0


ITEMS = [
    {"x": 10, "y": 10, "w": 40, "h": 20, "text": "Open notes"},
    {"x": 60, "y": 10, "w": 60, "h": 20, "text": 'Say "hi"'},
    {"x": 130, "y": 10, "w": 40, "h": 20, "text": "Do nothing"},
    {"x": 10, "y": 50, "w": 40, "h": 20, "text": "Restart"},
    {"x": 60, "y": 50, "w": 0, "h": 20, "text": "Ghost"},
    {"x": 130, "y": 50, "w": 40, "h": 20, "text": "Locked", "disabled": True},
]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok " + msg)


def main():
    # 1. list_buttons: skips Restart (regex), zero-size, disabled
    desk = FakeDesk(ITEMS)
    listed = ps.list_buttons(desk.run_in_vm)
    texts = [it["text"] for it in listed]
    check(texts == ["Open notes", 'Say "hi"', "Do nothing"], "list_buttons keeps three buttons: %r" % texts)
    check(all(it["vw"] == VW for it in listed), "list_buttons carries the viewport width")

    # 2. sweep: the one that changes nothing is the only noop; Restart and Ghost are never clicked
    desk = FakeDesk(ITEMS)
    user = FakeUser(desk)
    res = ps.sweep(user, desk.run_in_vm, grab_for(desk), ps.list_buttons(desk.run_in_vm), clock)
    noops = [r["text"] for r in res if r["noop"]]
    check(noops == ["Do nothing"], "only 'Do nothing' is reported noop: %r" % noops)
    by = {r["text"]: r for r in res}
    check(by["Open notes"]["changed_pixels"] > ps.NOOP_RATIO and by["Open notes"]["state_changed"],
          "'Open notes' changes pixels and state")
    check(by['Say "hi"']["state_changed"] and not by['Say "hi"']["noop"],
          'state-only change (reply) is not a noop')
    check("Restart" not in desk.clicked and "Ghost" not in desk.clicked,
          "Restart and zero-size Ghost were never clicked: %r" % desk.clicked)
    check(desk.keys == ["esc"] * 3 and desk.resets == 3, "esc and testreset-min after each of 3 clicks")
    check(set(by["Do nothing"]) == {"i", "text", "changed_pixels", "state_changed", "noop", "seconds"},
          "record has the expected fields")

    # 3. zero-size item passed straight to sweep is skipped
    desk = FakeDesk(ITEMS)
    res = ps.sweep(FakeUser(desk), desk.run_in_vm, grab_for(desk),
                   [{"i": 9, "x": 0, "y": 0, "w": 0, "h": 0, "text": "Zero", "vw": VW}], clock)
    check(res == [] and desk.clicked == [], "zero-size item is skipped by sweep")

    # 4. zero buttons
    desk = FakeDesk([])
    check(ps.list_buttons(desk.run_in_vm) == [], "zero buttons: list_buttons is empty")
    check(ps.sweep(FakeUser(desk), desk.run_in_vm, grab_for(desk), [], clock) == [], "zero buttons: sweep is empty")

    # 5. rects error is raised with its message
    desk = FakeDesk(ITEMS, error="no desk open")
    try:
        ps.list_buttons(desk.run_in_vm)
        check(False, "rects error raises")
    except RuntimeError as e:
        check("no desk open" in str(e), "rects error raises with its message")

    # 6. machine-changing and irreversible labels are skipped; harmless labels are not (case-insensitive)
    dangerous = ["Restart", "Shut down", "Power off", "Log out", "Sign out", "Reset everything", "Erase disk",
                 "Delete", "Remove", "Empty trash", "Uninstall", "Format", "Factory reset", "Turn off", "Wipe",
                 "Install update", "Send", "Buy", "Send feedback", "Share", "EMPTY TRASH"]
    for label in dangerous:
        check(ps.SKIP.search(label) is not None, "skipped label: %r" % label)
    harmless = ["Open", "Notes", "Settings", "Calculator", "Back", "Next"]
    for label in harmless:
        check(ps.SKIP.search(label) is None, "harmless label not skipped: %r" % label)
    items = [{"x": 10 * k, "y": 0, "w": 8, "h": 8, "text": t} for k, t in enumerate(dangerous + harmless)]
    desk = FakeDesk(items)
    listed = [it["text"] for it in ps.list_buttons(desk.run_in_vm)]
    check(listed == harmless, "list_buttons drops every dangerous label: %r" % listed)

    # 7. an esc press that raises must not stop testreset-min
    class EscRaises(FakeUser):
        def press(self, key):
            raise OSError("esc failed")

    desk = FakeDesk(ITEMS)
    res = ps.sweep(EscRaises(desk), desk.run_in_vm, grab_for(desk), ps.list_buttons(desk.run_in_vm), clock)
    check(desk.resets == len(res) == 3, "testreset-min still runs after esc raises (%d resets)" % desk.resets)

    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
