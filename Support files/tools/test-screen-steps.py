#!/usr/bin/env python3
"""Host-side unit test for deterministic screen steps (calculator test case).
Verifies that "open the calculator, then press 7 then + then 2 then = and tell me the result"
works without the model. Run: python3 tools/test-screen-steps.py  (no VM needed)."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

# Set up minimal stubs before importing agent
from llmos import tools, llm, intent
from llmos import agent


# Fake calculator simulator
class FakeCalculatorCtx:
    def __init__(self):
        self.display = "0"
        self.new_stream_count = 0
        self.text_calls = []
        self.cancel = None
        self.current_request = ""

    def new_stream(self):
        self.new_stream_count += 1
        return f"stream_{self.new_stream_count}"

    def on_text(self, stream, text):
        self.text_calls.append((stream, text))

    def end_stream(self, stream):
        pass

    def status(self, msg):
        pass

    def app_press(self, key):
        """Simulate calculator key press."""
        if key == "7":
            self.display = "7"
        elif key == "+":
            self.display = "7 +"
        elif key == "2":
            self.display = "7 + 2"
        elif key == "=":
            self.display = "9"
        elif key == "C":
            self.display = "0"
        return {"ok": True, "page": self._get_page()}

    def _get_page(self):
        """Simulate calculator page with display and buttons."""
        return f"Display: {self.display} C 7 8 9 / 4 5 6 * 1 2 3 - . 0 ="


# Mock the execute function to intercept tool calls
def fake_execute(ctx, name, arguments):
    """Intercept execute to track calls and provide fake implementations."""

    if name == "open_app":
        # Open app just marks the app as open
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        return f"opened the {args.get('command', 'app')}. Done: if the request asked for more, do the next step now; otherwise tell the owner in one sentence."

    elif name == "click":
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        text = args.get("text", "")
        result = ctx.app_press(text)
        if result.get("ok"):
            page = result.get("page", "")
            return f"pressed {text!r} in the app. It now shows: {page}"
        else:
            return f"error: could not press {text}"

    return f"error: no such tool '{name}'"


# Create a mock registry
class MockRegistry(dict):
    def __contains__(self, key):
        if key == "look_at_screen":
            return True
        return super().__contains__(key)

    def __getitem__(self, key):
        if key == "look_at_screen":
            mock_tool = MagicMock()
            mock_tool.available.return_value = True
            return mock_tool
        return super().__getitem__(key)


# Test 1: _screen_steps should handle the calculator sequence
print("Test 1: _screen_steps on calculator sequence...")
ctx = FakeCalculatorCtx()

with patch.object(agent, "execute", side_effect=fake_execute):
    with patch.object(agent, "tools") as mock_tools:
        mock_tools.REGISTRY = MockRegistry()
        with patch.object(agent, "time") as mock_time:
            # Make time.sleep a no-op
            mock_time.sleep = MagicMock()

            text = "press 7 then + then 2 then = and tell me the result"
            rest, notes, page_text, result_value = agent._screen_steps(ctx, text)

            print(f"  Input: {text}")
            print(f"  Rest (for model): {rest!r}")
            print(f"  Notes: {notes}")
            print(f"  Page text: {page_text!r}")
            print(f"  Result value: {result_value!r}")

            # Verify results
            assert any("pressed" in n for n in notes), f"Notes should contain 'pressed', got: {notes}"
            assert result_value == "9", f"Result value should be '9', got: {result_value}"
            print("  ✓ Test 1 passed\n")


# Test 2: Bare "press 7" should return non-empty reply
print("Test 2: Bare 'press 7' returns non-empty reply...")
ctx = FakeCalculatorCtx()

with patch.object(agent, "execute", side_effect=fake_execute):
    with patch.object(agent, "tools") as mock_tools:
        mock_tools.REGISTRY = MockRegistry()
        with patch.object(agent, "time") as mock_time:
            # Make time.sleep a no-op
            mock_time.sleep = MagicMock()

            text = "press 7"
            rest, notes, page_text, result_value = agent._screen_steps(ctx, text)

            print(f"  Input: {text}")
            print(f"  Rest: {rest!r}")
            print(f"  Notes: {notes}")

            assert not rest, f"Rest should be empty for bare press, got: {rest}"
            assert notes, f"Notes should not be empty, got: {notes}"
            assert any("7" in str(n) for n in notes), f"Notes should mention '7', got: {notes}"
            print("  ✓ Test 2 passed\n")

print("All core tests passed!")
