#!/usr/bin/env python3
"""Host-side unit test for the result of screen steps: which number an open app reports.
"7 + 2 =" (the calculator's history line) comes before its display "9", so the first number on the page is wrong.
The result is the app's display (the read bridge's 'display value: N' control) or else the LAST number of the page.
Run: python3 tools/test-screen-result.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
from unittest.mock import MagicMock, patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, agent


class NoBridgeCtx:
    """An agent context with no read bridge (no app_read attribute)."""
    def new_stream(self):
        return "s"

    def on_text(self, stream, text):
        pass

    def end_stream(self, stream):
        pass

    def status(self, msg):
        pass


class BridgeCtx(NoBridgeCtx):
    """An agent context whose open app reports its page through the read bridge."""
    def __init__(self, controls, text=""):
        self._reply = {"text": text, "controls": controls}

    def app_read(self):
        return self._reply


# The calculator's page as it reads after "=": history line, then display, then the keypad labels.
KEYPAD = ["C", "±", "%", "÷", "7", "8", "9", "×", "4", "5", "6", "−", "1", "2", "3", "+", "0", ".", "="]


def _check(label, got, want):
    if got != want:
        print(f"FAIL {label}: got {got!r}, wanted {want!r}")
        sys.exit(1)
    print(f"ok   {label}: {got!r}")


# 1. history line plus display, no bridge: the display (9), never the history's first number (7)
_check("history plus display (text)", agent._shown_result(NoBridgeCtx(), "7 + 2 =\n9"), "9")
_check("history plus display (collapsed)", agent._shown_result(NoBridgeCtx(), "7 + 2 = 9"), "9")
_check("negative result keeps its sign", agent._shown_result(NoBridgeCtx(), "2 - 5 = -3"), "-3")

# 2. plain display
_check("plain display", agent._shown_result(NoBridgeCtx(), "9"), "9")
_check("display before keypad digits", agent._shown_result(NoBridgeCtx(), "Display: 9 C 7 8 9 / 4 5 6 * 1 2 3 - . 0 ="), "9")

# 3. no number at all
_check("no number (text)", agent._shown_result(NoBridgeCtx(), "Calculator Clear"), None)
_check("no number (empty)", agent._shown_result(NoBridgeCtx(), ""), None)
_check("no number (None)", agent._shown_result(NoBridgeCtx(), None), None)

# 4. the read bridge's display control wins over whatever the page text says
_check("bridge display over page text",
       agent._shown_result(BridgeCtx(["display value: 9"] + KEYPAD, "7 + 2 = 9 C 7 8 9"), "7 + 2 = 0"), "9")
_check("bridge display non-numeric as shown", agent._shown_result(BridgeCtx(["display value: Error"]), "x 1"), "Error")
_check("bridge without display control falls back to the number after =",
       agent._shown_result(BridgeCtx(["C", "7"], "7 + 2 = 9"), "7 + 2 = 9"), "9")

# 5. end to end through _screen_steps: the owner's sentence, with the click reporting the page after each key
def _calc_execute(page_after_equals):
    """Fake execute(): each key press answers like the app does (history line plus display on the page)."""
    def fake(ctx, name, args):
        if name == "click":
            key = args.get("text")
            if key == "=":
                return f"pressed '=' in the app. It now shows: {page_after_equals}"
            return f"pressed {key!r} in the app. It now shows: {key}"
        return ""
    return fake


registry = {"look_at_screen": MagicMock(available=MagicMock(return_value=True))}
with patch.dict(tools.REGISTRY, registry, clear=False):
    sentence = "press 7 then + then 2 then = and tell me the result"
    with patch.object(agent, "execute", side_effect=_calc_execute("7 + 2 =\n9")):
        rest, notes, page_text, result = agent._screen_steps(NoBridgeCtx(), sentence)
    _check("end to end, no bridge: result is the display", result, "9")
    _check("end to end, no bridge: result is not the history's 7", result != "7", True)

    with patch.object(agent, "execute", side_effect=_calc_execute("7 + 2 = 0")):
        rest, notes, page_text, result = agent._screen_steps(BridgeCtx(["display value: 9"]), sentence)
    _check("end to end, bridge: result is the display", result, "9")

print("PASS test-screen-result.py")
sys.exit(0)
