#!/usr/bin/env python3
"""Host test for the speed of computer control in tools.py (click, fill_in): AT-SPI first, OCR only on a miss.

(a) click and fill_in handled through AT-SPI (fake control module): ZERO OCR calls, no post-action screen read.
(b) AT-SPI miss: the OCR path runs exactly as before (the same number of screen reads, the same click place).
(c) The real control.py with a fake accessibility bus and a counting read_screen: the same two guarantees, so the
    "empty line list means AT-SPI only" use in tools.fill_in is checked against the real code.

No VM, no gi, no bus needed. Run: python3 tools/test-control-speed.py
"""
import os
import sys
import types
from unittest.mock import patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

import llmos  # noqa: E402
from llmos import control as REAL_CONTROL  # noqa: E402  (loaded before any fake is installed)
from llmos import tools  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILS.append(name)


CTX = types.SimpleNamespace()          # neither tool needs the desk's own app hooks here
FIELD_ROLES = ("entry", "text", "password text")


# ---------------------------------------------------------------- a fake control module (the API tools.py uses)
class FakeControl:
    """Same contract as control.py: find/field_for try AT-SPI first and read the screen (OCR) only on a miss; an
    empty line list passed in means 'do not read the screen'."""

    def __init__(self, atspi=None, screen=None):
        self.atspi = {k.lower(): v for k, v in (atspi or {}).items()}   # name -> {x, y, role}
        self.screen = screen or []                                       # the OCR lines the screen would show
        self.ocr = 0
        self.actions = []

    def available(self):
        return True

    def _atspi(self, target):
        d = self.atspi.get(str(target).strip().lower())
        if d is None:
            return None
        return {"text": target, "x": d["x"], "y": d["y"], "w": 0, "h": 0, "words": [], "atspi": True,
                "field": d["role"] in FIELD_ROLES}

    def read_screen(self):
        self.ocr += 1
        return [dict(d) for d in self.screen]

    def describe(self, lines=None, limit=120):
        lines = self.read_screen() if lines is None else lines
        return "screen 1x1\n" + "\n".join(f"[{d['x']},{d['y']}] {d['text']}" for d in lines[:limit])

    def find(self, target, lines=None):
        d = self._atspi(target)
        if d is not None:
            return d
        lines = self.read_screen() if lines is None else lines
        for d in lines:
            if d["text"] and str(target).lower() in d["text"].lower():
                return d
        return None

    def field_for(self, target, lines=None):
        d = self._atspi(target)
        if d is not None:
            return dict(d, field=True)
        lines = self.read_screen() if lines is None else lines
        fields = [d for d in lines if d.get("field")]
        return fields[0] if fields else None

    def click(self, x, y, button="left", double=False):
        self.actions.append(("click", x, y))
        return True

    def type_text(self, text):
        self.actions.append(("type", text))
        return True, ""

    def press(self, keys):
        self.actions.append(("press", keys))
        return True, ""


def run_with(fake, fn):
    """Run one tool with fake installed as llmos.control (and time.sleep made instant)."""
    saved = getattr(llmos, "control", None)
    llmos.control = fake
    sys.modules["llmos.control"] = fake
    try:
        with patch("time.sleep"):
            return fn()
    finally:
        llmos.control = saved if saved is not None else REAL_CONTROL
        sys.modules["llmos.control"] = llmos.control


CLICK = tools.REGISTRY["click"].fn
FILL = tools.REGISTRY["fill_in"].fn

# ---------------------------------------------------------------- (a) AT-SPI handles it: zero OCR
f = FakeControl(atspi={"Send": {"x": 100, "y": 200, "role": "push button"}},
                screen=[{"text": "Send", "x": 50, "y": 60, "w": 20, "h": 10, "words": [], "field": False}])
out = run_with(f, lambda: CLICK({"text": "Send"}, CTX))
check("(a) click via AT-SPI performs zero OCR calls", f.ocr == 0, f"ocr={f.ocr}")
check("(a) click via AT-SPI presses the AT-SPI place, not the OCR place", ("click", 100, 200) in f.actions, f.actions)
check("(a) click via AT-SPI returns no screen text", "Now on screen" not in out and out.startswith("clicked"), out)

f = FakeControl(atspi={"Message": {"x": 300, "y": 400, "role": "entry"}},
                screen=[{"text": "Other", "x": 1, "y": 1, "w": 5, "h": 5, "words": [], "field": True}])
out = run_with(f, lambda: FILL({"field": "message", "text": "hi", "submit": True}, CTX))
check("(a) fill_in via AT-SPI performs zero OCR calls", f.ocr == 0, f"ocr={f.ocr}")
check("(a) fill_in via AT-SPI clicks the field, types, then presses enter",
      f.actions == [("click", 300, 400), ("type", "hi"), ("press", "enter")], f.actions)
check("(a) fill_in via AT-SPI returns no screen text", "Now on screen" not in out and out.startswith("wrote it"), out)

# ---------------------------------------------------------------- (b) AT-SPI miss: OCR runs as before
f = FakeControl(atspi={}, screen=[{"text": "Send", "x": 50, "y": 60, "w": 20, "h": 10, "words": [], "field": False}])
out = run_with(f, lambda: CLICK({"text": "Send"}, CTX))
# before this change: find() read the screen once, then the post-action screen read read it once more
check("(b) click AT-SPI miss: OCR find + post-action read (2 reads, as before)", f.ocr == 2, f"ocr={f.ocr}")
check("(b) click AT-SPI miss: clicks the OCR place", ("click", 50, 60) in f.actions, f.actions)
check("(b) click AT-SPI miss: returns the screen after", "Now on screen" in out, out)

f = FakeControl(atspi={}, screen=[{"text": "Message", "x": 320, "y": 380, "w": 60, "h": 10, "words": [], "field": False},
                                 {"text": "", "x": 320, "y": 410, "w": 200, "h": 20, "words": [], "field": True}])
out = run_with(f, lambda: FILL({"field": "message", "text": "hi"}, CTX))
check("(b) fill_in AT-SPI miss: OCR field read + post-action read (2 reads, as before)", f.ocr == 2, f"ocr={f.ocr}")
check("(b) fill_in AT-SPI miss: clicks the OCR box, then types", f.actions == [("click", 320, 410), ("type", "hi")], f.actions)
check("(b) fill_in AT-SPI miss: returns the screen after", "Now on screen" in out, out)

f = FakeControl(atspi={}, screen=[])
out = run_with(f, lambda: CLICK({"text": "Nowhere"}, CTX))
check("(b) click not found anywhere: error with the screen shown (OCR path)", out.startswith("error:") and f.ocr >= 1, out)

# ---------------------------------------------------------------- (c) the real control.py, fake accessibility bus
ocr_count = {"n": 0}
bus = {"Message": {"x": 300, "y": 400, "role": "entry"}, "Send": {"x": 100, "y": 200, "role": "push button"}}
ocr_lines = [{"text": "Message", "x": 320, "y": 380, "w": 60, "h": 10, "words": [], "field": False},
             {"text": "", "x": 320, "y": 410, "w": 200, "h": 20, "words": [], "field": True}]


def fake_bus(req):
    t = str(req.get("target") or "").strip().lower()
    hit = next((v for k, v in bus.items() if k.lower() == t), None)
    if hit is None:
        return {"ok": False, "why": "no match"}
    return {"ok": True, "name": t, "role": hit["role"], "x": hit["x"], "y": hit["y"]}


def counting_read_screen():
    ocr_count["n"] += 1
    return [dict(d) for d in ocr_lines]


real_actions = []
with patch.object(REAL_CONTROL, "_atspi_req", side_effect=fake_bus), \
        patch.object(REAL_CONTROL, "read_screen", side_effect=counting_read_screen), \
        patch.object(REAL_CONTROL, "click", side_effect=lambda x, y, b="left", d=False: real_actions.append(("click", x, y)) or True), \
        patch.object(REAL_CONTROL, "type_text", side_effect=lambda t: real_actions.append(("type", t)) or (True, "")), \
        patch.object(REAL_CONTROL, "press", side_effect=lambda k: real_actions.append(("press", k)) or (True, "")), \
        patch.object(REAL_CONTROL, "_scale", return_value=1.0):
    ocr_count["n"] = 0
    real_actions.clear()
    out = run_with(REAL_CONTROL, lambda: CLICK({"text": "Send"}, CTX))
    check("(c) real control: click via AT-SPI, zero OCR", ocr_count["n"] == 0, f"ocr={ocr_count['n']} out={out!r}")
    check("(c) real control: click via AT-SPI, the AT-SPI place is pressed", ("click", 100, 200) in real_actions, real_actions)

    ocr_count["n"] = 0
    real_actions.clear()
    out = run_with(REAL_CONTROL, lambda: FILL({"field": "message", "text": "hi", "submit": True}, CTX))
    check("(c) real control: fill_in via AT-SPI, zero OCR", ocr_count["n"] == 0, f"ocr={ocr_count['n']} out={out!r}")
    check("(c) real control: fill_in via AT-SPI, field pressed, typed, enter",
          real_actions == [("click", 300, 400), ("type", "hi"), ("press", "enter")], real_actions)

    # AT-SPI misses on the words the screen shows: the OCR field is used (one OCR read in fill_in + one after)
    ocr_count["n"] = 0
    real_actions.clear()
    out = run_with(REAL_CONTROL, lambda: FILL({"field": "search box", "text": "hi"}, CTX))
    check("(c) real control: fill_in AT-SPI miss falls back to OCR (2 reads, as before)", ocr_count["n"] == 2,
          f"ocr={ocr_count['n']}")
    check("(c) real control: fill_in AT-SPI miss clicks the OCR box", ("click", 320, 410) in real_actions, real_actions)

print("OK" if not FAILS else f"FAILED: {len(FAILS)}")
sys.exit(1 if FAILS else 0)
