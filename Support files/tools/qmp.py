#!/usr/bin/env python3
"""QMP client for the test VM monitor socket. Stdlib only.

Default socket: <Support files>/run/tqmp.sock (override with the path argument).
"""
import json
import os
import socket
import time

SUPPORT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(SUPPORT_DIR, "run", "tqmp.sock")

# character -> (qcode name, needs shift)
CHARS = {}
for _c in "abcdefghijklmnopqrstuvwxyz":
    CHARS[_c] = (_c, False)
    CHARS[_c.upper()] = (_c, True)
for _c in "0123456789":
    CHARS[_c] = (_c, False)
CHARS.update({
    " ": ("spc", False), "\n": ("ret", False), "\t": ("tab", False),
    "-": ("minus", False), "=": ("equal", False),
    "[": ("bracket_left", False), "]": ("bracket_right", False),
    "\\": ("backslash", False), ";": ("semicolon", False),
    "'": ("apostrophe", False), "`": ("grave_accent", False),
    ",": ("comma", False), ".": ("dot", False), "/": ("slash", False),
    "!": ("1", True), "@": ("2", True), "#": ("3", True), "$": ("4", True),
    "%": ("5", True), "^": ("6", True), "&": ("7", True), "*": ("8", True),
    "(": ("9", True), ")": ("0", True), "_": ("minus", True), "+": ("equal", True),
    "{": ("bracket_left", True), "}": ("bracket_right", True),
    "|": ("backslash", True), ":": ("semicolon", True),
    '"': ("apostrophe", True), "~": ("grave_accent", True),
    "<": ("comma", True), ">": ("dot", True), "?": ("slash", True),
})


def _axis(p, d):
    v = round(p * 0x7fff / (d - 1))
    return max(0, min(0x7fff, v))


class QMP:
    def __init__(self, path=DEFAULT_PATH):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self._f = self.sock.makefile("rb")
        greeting = self._read()
        if "QMP" not in greeting:
            raise RuntimeError("no QMP greeting")
        self.cmd("qmp_capabilities")

    def _read(self):
        line = self._f.readline()
        if not line:
            raise RuntimeError("QMP socket closed")
        return json.loads(line)

    def cmd(self, name, **args):
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        self.sock.sendall((json.dumps(msg) + "\n").encode())
        while True:
            obj = self._read()
            if "event" in obj:
                continue
            if "error" in obj:
                e = obj["error"]
                raise RuntimeError("QMP %s failed: %s: %s" % (name, e.get("class"), e.get("desc")))
            if "return" in obj:
                return obj["return"]

    def shot(self, path, fmt="ppm"):
        return self.cmd("screendump", filename=path, format=fmt)

    def click(self, px, py, w, h, button="left"):
        x = _axis(px, w)
        y = _axis(py, h)
        self.cmd("input-send-event", events=[
            {"type": "abs", "data": {"axis": "x", "value": x}},
            {"type": "abs", "data": {"axis": "y", "value": y}},
        ])
        self.cmd("input-send-event", events=[
            {"type": "btn", "data": {"down": True, "button": button}},
        ])
        time.sleep(0.03)
        self.cmd("input-send-event", events=[
            {"type": "btn", "data": {"down": False, "button": button}},
        ])

    def key(self, name):
        self.combo(name)

    def combo(self, *names):
        self.cmd("send-key", keys=[{"type": "qcode", "data": n} for n in names])

    def type(self, text, delay_ms=40, secret=False):
        # Map every character first so an unknown one sends nothing.
        # The error names only the code point, never the text (secret or not).
        plan = []
        for ch in text:
            if ch not in CHARS:
                raise ValueError("no key mapping for character U+%04X" % ord(ch))
            plan.append(CHARS[ch])
        for name, shift in plan:
            self.combo(*(["shift", name] if shift else [name]))
            time.sleep(delay_ms / 1000.0)

    def close(self):
        try:
            self._f.close()
        finally:
            self.sock.close()
