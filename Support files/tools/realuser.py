#!/usr/bin/env python3
"""Drive the desk like a real user: find elements by CSS selector in the VM,
then click or type at their screen position through QMP. Stdlib only.

RealUser(qmp, run_in_vm, grab=None)
  run_in_vm(cmd: str) -> str   injected; runs a command in the VM and returns stdout
  grab() -> bytes              current frame as binary PPM (default: qmp.shot + read file)
"""
import json
import os
import shlex

SUPPORT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SHOT = os.path.join(SUPPORT_DIR, "run", "realuser.ppm")

# Selectors from src/rootfs/usr/share/llmos/desk/desk.js
DIALOG_YES = '#overlay .dlg button[data-value="yes"]'  # desk.js:877-892
DIALOG_NO = '#overlay .dlg button[data-value="no"]'  # desk.js:877-892
WIZ_NEXT = "#wiz-nav > button.btn.primary"  # desk.js:247-435
WIZ_BACK = "#wiz-nav > button.btn.ghost"  # desk.js:247-435
WIZ_SIGNIN = "#wz-signin"  # desk.js:247-435
INPUT = "#in"  # desk.js:247-435


def _ppm_size(data):
    """Width and height from a binary P6 PPM header (body not required)."""
    i = 0
    n = len(data)
    tokens = []
    while len(tokens) < 4:
        while i < n and data[i:i + 1].isspace():
            i += 1
        if i < n and data[i:i + 1] == b"#":
            while i < n and data[i:i + 1] not in (b"\n", b"\r"):
                i += 1
            continue
        start = i
        while i < n and not data[i:i + 1].isspace():
            i += 1
        if start == i:
            raise ValueError("truncated PPM header")
        tokens.append(data[start:i])
    if tokens[0] != b"P6":
        raise ValueError("not a binary P6 PPM")
    return int(tokens[1]), int(tokens[2])


class RealUser:
    def __init__(self, qmp, run_in_vm, grab=None):
        self.qmp = qmp
        self.run_in_vm = run_in_vm
        self.grab = grab if grab is not None else self._default_grab
        self._n = 0

    def _default_grab(self):
        os.makedirs(os.path.dirname(DEFAULT_SHOT), exist_ok=True)
        self.qmp.shot(DEFAULT_SHOT, "ppm")
        with open(DEFAULT_SHOT, "rb") as f:
            return f.read()

    def rect(self, sel):
        self._n += 1
        out = self.run_in_vm(f"llmos desk-ctl rect {self._n} {shlex.quote(sel)}")
        obj = json.loads(out)
        if obj.get("ok") is False:
            raise RuntimeError("rect %s failed: %s" % (sel, obj.get("error")))
        return obj

    def click_sel(self, sel):
        r = self.rect(sel)
        W, H = _ppm_size(self.grab())
        s = W / r["vw"]
        cx = (r["x"] + r["w"] / 2) * s
        cy = (r["y"] + r["h"] / 2) * s
        self.qmp.click(cx, cy, W, H)

    def type_into(self, sel, text, secret=False):
        self.click_sel(sel)
        self.qmp.type(text, secret=secret)
        if self.rect(sel).get("value") == text:
            return True
        # mismatch: select all and retype once
        self.qmp.combo("ctrl", "a")
        self.qmp.type(text, secret=secret)
        return self.rect(sel).get("value") == text

    def press(self, key):
        self.qmp.key(key)

    def shot(self, path):
        self.qmp.shot(path, "png")

    def answer_dialog(self, yes):
        self.click_sel(DIALOG_YES if yes else DIALOG_NO)
