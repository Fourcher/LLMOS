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

# ---- Test 3: the calculator's own key logic (calculator.html run under node with a small DOM stand-in)
# A closed calculator must not keep its number: a reopened one starts at 0 (the desk's close emits window.close,
# the page is loaded again). Each session below is one opening of the app; tokens are its button labels or "key:<k>".
import json
import shutil
import subprocess

from llmos import desk, apps

CALC = os.path.join(_ROOT, "usr/share/llmos/apps/calculator.html")
NODE_DRIVER = r"""
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const sessions = JSON.parse(process.argv[2]);
function open() {
  const els = {}, listeners = {};
  const mk = () => ({ textContent: "", className: "", onclick: null, attrs: {}, kids: [],
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    append(...c) { this.kids.push(...c); } });
  const document = {
    getElementById(id) { return els[id] || (els[id] = mk()); },
    createElement() { return mk(); },
    addEventListener(type, fn) { listeners[type] = fn; } };
  vm.runInNewContext(script, { document });
  return {
    tap(label) { const b = els.keys.kids.find(x => x.textContent === label); if (!b) throw new Error("no key " + label); b.onclick(); },
    key(k) { listeners.keydown({ key: k, preventDefault() {} }); },
    state() { return { cur: els.cur.textContent, label: els.cur.getAttribute("aria-label") }; } };
}
const out = sessions.map(tokens => {
  const c = open();
  for (const t of tokens) { if (t.startsWith("key:")) c.key(t.slice(4)); else c.tap(t); }
  return c.state();
});
process.stdout.write(JSON.stringify(out));
"""


def run_calculator(sessions):
    """Each session is one opening of calculator.html; returns the display state at its end."""
    p = subprocess.run(["node", "-e", NODE_DRIVER, CALC, json.dumps(sessions)], capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise RuntimeError("node failed: " + p.stderr[-500:])
    return json.loads(p.stdout)


NODE = shutil.which("node")
if not NODE:
    print("Test 3: SKIPPED (node not found): the calculator key logic was not run; the desk logic still was.\n")
else:
    print("Test 3: calculator.html key logic under node...")
    cases = [
        # (sessions, expected display of the LAST session)
        ([["7", "+", "2", "="]], "9"),
        # the reported bug: 7 pressed, the app closed, reopened, 7 + 2 = -> a new opening must show 9, not 77 / 79
        ([["7"], ["7", "+", "2", "="]], "9"),
        # what a reused page would show: the same opening pressed twice (documents why close must really close)
        ([["7", "7", "+", "2", "="]], "79"),
        # after = a digit starts a new number
        ([["7", "+", "2", "=", "3"]], "3"),
        # after = an operator carries on with the result
        ([["7", "+", "2", "=", "+", "1", "="]], "10"),
        # C clears
        ([["7", "+", "2", "=", "C"]], "0"),
        # the keyboard does the same as the keys
        ([["key:7", "key:+", "key:2", "key:Enter"]], "9"),
    ]
    for sessions, want in cases:
        got = run_calculator(sessions)[-1]
        assert got["cur"] == want, f"{sessions}: display {got['cur']!r}, wanted {want!r}"
    # the label the app keeps for the OS is what the read reply quotes
    st = run_calculator([["7", "+", "2", "="]])[-1]
    assert st["label"] == "display value: 9", st
    print(f"  {len(cases)} key sequences as expected; display label {st['label']!r}")
    print("  ✓ Test 3 passed\n")

    # the readback the desk gives for that page: the calculator's number, from the label the page keeps
    from llmos import intent as _intent
    page = {"text": "7 + 2 =\n9\nC\n±\n%\n÷", "controls": [st["label"], "C", "±", "%", "÷", "9", "="]}
    assert _intent.app_reading(page, "Calculator") == "The calculator shows 9.", _intent.app_reading(page, "Calculator")

# ---- Test 4: the desk closes an open app of the OS's own, reads it, and leaves other words alone
print("Test 4: desk close and read of an open app...")


class FakeDesk:
    """The parts of desk.Desk that shortcut() uses for these requests."""

    def __init__(self, open_windows=(), page=None):
        self.windows = {w: {"kind": "app"} for w in open_windows}
        self.page = page
        self.closed, self.replies, self.reads = [], [], []

    def close_window(self, wid):
        self.windows.pop(wid, None)
        self.closed.append(wid)

    def instant_reply(self, request, text):
        self.replies.append(text)

    def app_call(self, what, text="", app_id=""):
        self.reads.append((what, app_id))
        return self.page

    _app_question = desk.Desk._app_question


INSTALLED = [{"id": "calculator", "title": "Calculator", "size": "s", "file": "/x/calculator.html", "made": 0}]
with patch.object(apps, "installed", return_value=INSTALLED):
    d = FakeDesk(["app-calculator"])
    assert desk.Desk.shortcut(d, "close the calculator") is True
    assert d.closed == ["app-calculator"] and d.replies == ["Closed Calculator."], (d.closed, d.replies)

    d = FakeDesk([])
    assert desk.Desk.shortcut(d, "close the calculator") is True
    assert d.closed == [] and d.replies == ["The calculator is not open."], d.replies

    d = FakeDesk(["app-calculator"], page={"llmos": "page", "text": "7 + 2 =\n79", "controls": ["display value: 79", "C", "7"]})
    assert desk.Desk.shortcut(d, "what does the calculator show") is True
    assert d.reads == [("read", "calculator")] and d.replies == ["The calculator shows 79."], (d.reads, d.replies)
    d = FakeDesk(["app-calculator"], page={"llmos": "page", "text": "", "controls": ["display value: 9"]})
    assert desk.Desk.shortcut(d, "What's on the calculator?") is True and d.replies == ["The calculator shows 9."], d.replies

    d = FakeDesk([])
    assert desk.Desk.shortcut(d, "read the calculator") is True and d.replies == ["The calculator is not open."], d.replies

    # not an app of the OS's own: the old paths (a program, a window, the model) decide, not this
    d = FakeDesk(["app-calculator"])
    assert d._app_question("close the browser") is None and d._app_question("close the window") is None
    assert d._app_question("what time is it") is None
with patch.object(apps, "installed", return_value=[]):
    d = FakeDesk(["app-calculator"])
    assert d._app_question("close the calculator") is None     # no installed app of that name
print("  ✓ Test 4 passed\n")

print("All core tests passed!")
