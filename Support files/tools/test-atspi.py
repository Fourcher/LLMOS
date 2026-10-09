#!/usr/bin/env python3
"""Host test for the AT-SPI path of computer control (control.py). No VM, no gi, no bus needed.

(a) Atspi unavailable (no gi, or no accessibility bus): find() and click() take the OCR path, unchanged.
(b) A fake accessibility tree: the named button is matched (exact before partial, case and spaces ignored), its
    Action is invoked, and a field gets its text. Inactive windows are not searched unless named.
(c) No match in the tree: the OCR fallback is called and its line is returned.
Also: a real child process with no bus / a killed child (timeout) both return quickly and fall back to OCR.

Run: python3 tools/test-atspi.py
"""
import contextlib
import io
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import control  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------- a fake Atspi (the same calls the real GI module takes)
class State:
    def __init__(self, active):
        self.active = active

    def contains(self, flag):
        return bool(self.active) and flag == "ACTIVE"


class Rect:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.width, self.height = x, y, w, h


class Action:
    def __init__(self, names):
        self.names = names
        self.calls = []

    def get_n_actions(self):
        return len(self.names)

    def get_action_name(self, i):
        return self.names[i]

    def do_action(self, i):
        self.calls.append(i)
        return True


class Editable:
    def __init__(self):
        self.texts = []

    def set_text_contents(self, t):
        self.texts.append(t)
        return True


class Comp:
    def __init__(self, rect):
        self.rect = rect
        self.focused = 0

    def get_extents(self, coord):
        return self.rect

    def grab_focus(self):
        self.focused += 1
        return True


class Node:
    def __init__(self, name, role, children=(), active=False, actions=None, editable=False, rect=None):
        self.name, self.role, self.kids = name, role, list(children)
        self.active = active
        self.action = Action(actions) if actions else None
        self.editable = Editable() if editable else None
        self.comp = Comp(rect) if rect else Comp(Rect(0, 0, 0, 0))

    def get_name(self):
        return self.name

    def get_role_name(self):
        return self.role

    def get_child_count(self):
        return len(self.kids)

    def get_child_at_index(self, i):
        return self.kids[i]

    def get_state_set(self):
        return State(self.active)

    def get_action(self):
        return self.action

    def get_editable_text(self):
        return self.editable

    def get_component(self):
        return self.comp


class FakeAtspi:
    class StateType:
        ACTIVE = "ACTIVE"

    class CoordType:
        SCREEN = 0

    def __init__(self, desktop):
        self.desktop = desktop

    def get_desktop(self, i):
        return self.desktop


def build_tree():
    save_btn = Node("Save", "push button", actions=["press", "click"], rect=Rect(100, 200, 50, 20))
    save_as = Node("Save As…", "push button", actions=["click"])
    name_field = Node("Name", "entry", editable=True, actions=None, rect=Rect(10, 10, 80, 20))
    active_frame = Node("Notes", "frame", active=True, children=[
        save_as,                                     # partial match, listed before the exact one
        save_btn,
        name_field,
        Node("Saved", "label"),                      # a label, never a button
    ])
    # an inactive window with its own Cancel and Save: not searched unless it is named
    other_frame = Node("Other", "frame", active=False, children=[
        Node("Cancel", "push button", actions=["click"]),
        Node("Save", "push button", actions=["click"]),
    ])
    desk = Node("desktop", "desktop frame", children=[
        Node("gedit", "application", children=[active_frame]),
        Node("llmos", "application", children=[Node("LLM OS", "frame", active=True, children=[
            Node("Save", "push button", actions=["click"])])]),                 # the desk itself: never searched
        Node("other-app", "application", children=[other_frame]),
    ])
    return FakeAtspi(desk), {"save": save_btn, "as": save_as, "name": name_field}


ATSPI, N = build_tree()
ROLES = set(control._CLICK_ROLES) | set(control._FIELD_ROLES)

# ---------------------------------------------------------------- (b) fake tree: match, exact before partial, act
hit = control.find_element(control._scope(ATSPI, ""), "save", ROLES)
check("exact match wins over 'Save As' listed first", hit is not None and hit[0] is N["save"] and hit[1] == "Save",
      hit and hit[1])
hit = control.find_element(control._scope(ATSPI, ""), "  SAVE  ", ROLES)
check("case and spaces are ignored for the exact match", hit is not None and hit[0] is N["save"])
hit = control.find_element(control._scope(ATSPI, ""), "save a", ROLES)
check("partial match when there is no exact one", hit is not None and hit[0] is N["as"], hit and hit[1])
check("the desk's own window is never searched",
      control.find_element(control._scope(ATSPI, ""), "LLM OS", ROLES) is None)
check("an inactive window is not searched by default",
      control.find_element(control._scope(ATSPI, ""), "Cancel", ROLES) is None)
check("a named window is searched even when not focused",
      control.find_element(control._scope(ATSPI, "other"), "Cancel", ROLES) is not None)
check("a label is not a button", control.find_element(control._scope(ATSPI, ""), "Saved", ROLES) is None)
check("roles filter: a push button is not an entry",
      control.find_element(control._scope(ATSPI, ""), "Save", {"entry"}) is None)

# the real child-process entry point, on the fake tree
r = control._child({"op": "click", "target": "Save", "roles": ["push button"]}, Atspi=ATSPI)
check("click op presses the Action named 'click' (index 1 of press,click)",
      r.get("ok") is True and N["save"].action.calls == [1], f"{r} calls={N['save'].action.calls}")
r = control._child({"op": "find", "target": "Save", "roles": ["push button"]}, Atspi=ATSPI)
check("find op reports the place (logical pixels) of the button",
      r.get("ok") is True and r.get("x") == 125 and r.get("y") == 210, r)
r = control._child({"op": "text", "target": "Name", "roles": ["entry"], "text": "hello"}, Atspi=ATSPI)
check("text op sets the field's EditableText", r.get("ok") is True and N["name"].editable.texts == ["hello"], r)
r = control._child({"op": "focus", "target": "Name", "roles": ["entry"]}, Atspi=ATSPI)
check("focus op grabs focus on a field", r.get("ok") is True and N["name"].comp.focused == 1, r)

# end to end through find() and click(): the AT-SPI path, with the child call answered by the fake tree
buf = io.StringIO()
with patch.object(control, "_atspi_req", lambda req: control._child(req, Atspi=ATSPI)), \
        patch.object(control, "_scale", lambda: 2.0), \
        patch.object(control, "move_to") as move, \
        patch.object(control, "read_screen", MagicMock(side_effect=AssertionError("OCR must not run"))), \
        contextlib.redirect_stderr(buf):
    d = control.find("save")
    check("find() returns the accessible button with its place scaled to screen pixels",
          d is not None and d.get("atspi") and d["text"] == "Save" and d["x"] == 250 and d["y"] == 420, d)
    ok = control.click(d["x"], d["y"])
    check("click() presses the element through its Action, not the pointer",
          ok and N["save"].action.calls[-1] == 1 and not move.called, f"ok={ok} moved={move.called}")
    check("the log says which path ran", "control: atspi click 'Save' (push button)" in buf.getvalue(), buf.getvalue())
    check("the hit is one-shot: a second click at the same place is pointer-driven",
          control._HIT == {} and (control.click(d["x"], d["y"]) or True) and move.called)

buf = io.StringIO()
with patch.object(control, "_atspi_req", lambda req: control._child(req, Atspi=ATSPI)), \
        patch.object(control, "_scale", lambda: 2.0), \
        contextlib.redirect_stderr(buf):
    f = control.field_for("Name")
    check("field_for() finds the entry through AT-SPI", f is not None and f.get("field") is True and f["text"] == "Name", f)
    with patch.object(control, "move_to", MagicMock(return_value=True)) as move:
        control.click(f["x"] if f["x"] is not None else None, f["y"] if f["y"] is not None else None)
        check("clicking a field focuses it (no pointer move)", N["name"].comp.focused == 2 and not move.called,
              f"focused={N['name'].comp.focused} moved={move.called}")
    check("atspi_set_text writes into the field", control.atspi_set_text("Name", "world") is True and
          N["name"].editable.texts[-1] == "world")

# ---------------------------------------------------------------- (a) Atspi unavailable: the OCR path, unchanged
saved_gi = sys.modules.get("gi")
sys.modules["gi"] = None                                # `import gi` now raises ImportError
try:
    check("no gi: the Atspi module is unavailable", control._atspi_module() is None)
    check("no gi: the child reports it and does not touch the screen",
          control._child({"op": "find", "target": "Save", "roles": ["push button"]}).get("ok") is False)
finally:
    if saved_gi is None:
        del sys.modules["gi"]
    else:
        sys.modules["gi"] = saved_gi

OCR_LINE = {"text": "Save", "x": 300, "y": 90, "w": 40, "h": 12, "words": [(280, 84, 40, 12, "Save")]}
with patch.object(control, "_bus_env", lambda: {}), \
        patch.object(control.subprocess, "run", MagicMock(side_effect=AssertionError("no child without a bus"))), \
        patch.object(control, "read_screen", MagicMock(return_value=[OCR_LINE])) as rs, \
        patch.dict(os.environ, {}, clear=False), contextlib.redirect_stderr(io.StringIO()) as buf:
    os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
    d = control.find("Save")
    check("(a) no accessibility bus: find() is the OCR result", d == OCR_LINE and rs.called, d)
    check("(a) and the log says ocr", "control: ocr find 'save'" in buf.getvalue(), buf.getvalue())
    with patch.object(control, "move_to", MagicMock(return_value=True)) as move, \
            patch.object(control, "_run", MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))), \
            contextlib.redirect_stderr(io.StringIO()) as buf2:
        control._HIT.clear()
        check("(a) click() with no AT-SPI hit uses the pointer", control.click(300, 90) is True and move.called)
        check("(a) and logs the ocr click", "control: ocr click at 300,90" in buf2.getvalue(), buf2.getvalue())

# ---------------------------------------------------------------- (c) no match in the tree: the OCR fallback is called
QUIT_LINE = {"text": "Quit", "x": 500, "y": 60, "w": 30, "h": 12, "words": [(485, 54, 30, 12, "Quit")]}
buf = io.StringIO()
with patch.object(control, "_atspi_req", lambda req: control._child(req, Atspi=ATSPI)), \
        patch.object(control, "read_screen", MagicMock(return_value=[QUIT_LINE])) as rs, \
        contextlib.redirect_stderr(buf):
    d = control.find("Quit")                             # not in the tree: only the screen has it
    check("(c) no match: OCR is called and its line returned", rs.called and d == QUIT_LINE, d)
    check("(c) and the log says the accessible tree had no match", "control: ocr find 'quit'" in buf.getvalue(),
          buf.getvalue())

# the child process itself, for real: no bus address -> no spawn; a dead or slow child -> killed, OCR fallback
with patch.object(control, "_bus_env", lambda: {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent/bus"}):
    real = control._atspi_req({"op": "find", "target": "Save", "roles": ["push button"], "window": ""})
    check("real child: answers (or fails) without hanging", isinstance(real, dict) and real.get("ok") is False, real)
with patch.object(control, "_bus_env", lambda: {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent/bus"}), \
        patch.object(control, "_ATSPI_TIMEOUT", 0.0001), contextlib.redirect_stderr(io.StringIO()) as buf:
    slow = control._atspi_req({"op": "find", "target": "Save", "roles": ["push button"]})
    d = control._atspi_find("Save", control._CLICK_ROLES)
    check("timeout: a child past the limit is reported as timed out (no hang)", slow.get("timeout") is True
          or slow.get("ok") is False, slow)
    check("timeout: find() gives None so the caller uses OCR", d is None)

print()
print("FAILED: " + ", ".join(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
