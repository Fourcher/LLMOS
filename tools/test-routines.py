#!/usr/bin/env python3
"""Host-side test of routines (llmos/agent.py + store.py): what the model did for a short request is kept
only when it is safe to repeat as-is, and a replay runs the same calls under the same policy, answers
without the model when the tool's own words suffice, and forgets a routine that stops working.
Run: python3 tools/test-routines.py (no model, no VM)"""
import json
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import agent, store, tools  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Ctx:
    headless = False
    after_turn = None
    current_request = ""

    def __init__(self):
        self.status_lines, self.text, self.ran = [], "", []

    def new_stream(self):
        return None

    def on_text(self, s, t):
        self.text += t

    def end_stream(self, s):
        pass

    def status(self, t):
        self.status_lines.append(t)


# the agent's execute() is replaced by a fake: no tool really runs on this host
OUT = {}


def fake_execute(ctx, name, arguments):
    ctx.ran.append((name, json.loads(arguments)))
    return OUT.get(name, "done")


agent.execute = fake_execute

print("what is kept")
agent._maybe_save_routine("Open the settings!", [("show_panel", '{"panel": "settings"}', "opened the settings panel")])
check(store.routine("open the settings") is not None, "a one-step panel request is kept (case and punctuation aside)")
agent._maybe_save_routine("delete everything in downloads", [("delete_file", '{"path": "/root/Downloads"}', "deleted")])
check(store.routine("delete everything in downloads") is None, "a destructive call is never kept")
agent._maybe_save_routine("show me the newest photo", [("show_image", '{"path": "/root/Pictures/IMG_20260101_123456.jpg"}', "shown")])
check(store.routine("show me the newest photo") is None, "a long value taken from context (not from the request) is not kept")
agent._maybe_save_routine("remember that I like tea", [("remember", '{"fact": "likes tea"}', "saved")])
check(store.routine("remember that I like tea") is None, "memory writes are never kept")
agent._maybe_save_routine("what's the weather", [("web_search", '{"query": "weather"}', "error: internet off")])
check(store.routine("what's the weather") is None, "a failed call is not kept")
agent._maybe_save_routine("x" * 130, [("show_panel", '{"panel": "settings"}', "ok")])
check(store.routine("x" * 130) is None, "long requests are not kept")
agent._maybe_save_routine("open the file /root/notes/plan.txt", [("open_file", '{"path": "/root/notes/plan.txt"}', "opened")])
check(store.routine("open the file /root/notes/plan.txt") is not None, "a long value quoted from the request is kept")
check(tools.REGISTRY["show_panel"].risk_for({"panel": "settings"}) not in (tools.DESTRUCTIVE, tools.SECURITY), "show_panel is harmless")

print("replay")
ctx = Ctx()
OUT["show_panel"] = "opened the settings panel"
reply = agent._replay(ctx, "open the settings", store.routine("open the settings"))
check(ctx.ran == [("show_panel", {"panel": "settings"})], f"the same call runs again: {ctx.ran}")
check(reply is not None and "settings" in reply.lower(), f"the answer comes from the tool's own words, no model: {reply!r}")
check(store.routine("open the settings")["used"] == 1, "use is counted")
check(any("last time" in s for s in ctx.status_lines), "the owner is told it is a replay")
tail = store.audit_tail(3)
check(any(a.get("tool") == "routine" for a in tail), "the replay is in the audit log")

print("a routine that stops working is forgotten")
ctx = Ctx()
OUT["show_panel"] = "error: no such panel"
reply = agent._replay(ctx, "open the settings", store.routine("open the settings"))
check(reply is None, "replay reports failure (the model decides afresh)")
check(store.routine("open the settings") is None, "the routine is gone")

print("the request's route prefixes")
m = agent._ROUTE_RE.match("ask claude: write me a poem")
check(m and m.group("cloud") and m.group("rest") == "write me a poem", "'ask claude:' forces the online model")
m = agent._ROUTE_RE.match("here: what time is it")
check(m and m.group("local") and m.group("rest") == "what time is it", "'here:' keeps it local")
check(agent._ROUTE_RE.match("online shopping is fun") is None, "no false prefix without a colon")
check(agent.looks_hard("Write me a cover letter for a nursing job") and not agent.looks_hard("what time is it"), "looks_hard() separates big requests from small ones")
check(agent.about_time(5) == "this usually takes about 5 seconds" and agent.about_time(130) == "this usually takes about 2 minutes" and agent.about_time(90, left=True) == "about 2 minutes left", "about_time() words")
agent._learn_speed({"prompt_per_second": 200.0, "predicted_per_second": 20.0, "predicted_n": 40}, 3.0, "local")
check(agent.expect_seconds("local", 400) == 2.5, f"expect_seconds from measured speeds: {agent.expect_seconds('local', 400)}")
check(agent.expect_seconds("cloud", 0) is None, "no cloud figure until one round trip was measured")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
