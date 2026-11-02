#!/usr/bin/env python3
"""A goal that hits the 8-step cap is stored as a background task instead of stopping.

hands-off continues with no question. balanced and hands-on use the same confirmation as any other
action. A SECURITY tool is not stored. A goal that finishes inside one tool call (including a triage)
does not schedule a follow-up. The owner is notified when a background run finishes, not at the cap.

Run: python3 tools/test-goal-continue.py"""
import os, sys, tempfile
from unittest import mock
_ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","src/rootfs")
sys.path.insert(0,os.path.join(_ROOT,"usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME",tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC",tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"]=os.path.join(_ROOT,"usr/share/llmos")
from llmos import agent, config, llm, mail, scheduler, store, tools
fails=0
def check(c,w):
    global fails
    print(("  ok   " if c else "  FAIL ")+w)
    if not c: fails+=1

def clear_tasks():
    config.save_json(config.data("tasks.json"), [])

def clear_inbox():
    config.save_json(config.data("inbox.json"), [])

class Harness:
    headless = False
    ask_only = False
    after_turn = None
    approved = False
    tainted = False
    def __init__(self, allow_continue=True):
        self.notes = []
        self.asked = []
        self.allow_continue = allow_continue
    def status(self, t):
        self.notes.append(t)
    def new_stream(self):
        return object()
    def on_text(self, *a):
        pass
    def end_stream(self, *a):
        pass
    def begin_tool(self, *a):
        pass
    def end_tool(self, *a):
        pass
    def confirm_action(self, tool, args, risk):
        self.asked.append(tool.name)
        if tool.name == "schedule_task":
            return self.allow_continue
        return True
    def confirm_network(self, name, args):
        return True

def tool_call(name, arguments, cid="c1"):
    return {"content": "", "tool_calls": [{"id": cid, "name": name, "arguments": arguments}], "timings": {}}

def run_turn(user, replies, autonomy="hands-off", allow_continue=True, headless=False, approved=False):
    seq = list(replies)
    seen = {"n": 0}
    def fake_chat(msgs, tools=None, on_text=None, **kw):
        seen["n"] += 1
        if not seq:
            return tool_call("calculate", {"expression": "2+2"}, cid=f"c{seen['n']}")
        return seq.pop(0)
    config.settings.set("autonomy", autonomy)
    config.settings.set("brain", "local")
    config.settings.set("internet", "yes")
    config.settings.set("auto_escalate", True)
    clear_tasks()
    clear_inbox()
    ctx = Harness(allow_continue)
    ctx.headless = headless
    ctx.approved = approved
    with mock.patch.object(llm, "chat", fake_chat):
        out = agent.run(ctx, user, [])
    return out, ctx, store.tasks(), seen["n"]

CALC = tool_call("calculate", {"expression": "2+2"})

# a goal that uses the whole cap is stored, approved, and the reply says it is continuing
for phrase in ["sort the downloads today", "sort these until it's done", "keep going until the folder is empty"]:
    out, ctx, tasks, n = run_turn(phrase, [CALC] * 8)
    check(n == 8 and len(tasks) == 1 and tasks[0].get("approved") is True and phrase in tasks[0]["task"]
          and tasks[0]["when"] == "in 1 minute" and out == agent._GOAL_CONTINUE and ctx.asked == []
          and store.unseen() == [],
          f"hands-off goal continues with no question and no notification: {phrase!r} n={n} tasks={len(tasks)} "
          f"asked={ctx.asked} out={out!r}")

# balanced does not ask before a harmless continuation (a change is not destructive)
out, ctx, tasks, n = run_turn("sort the downloads today", [CALC] * 8, autonomy="balanced")
check(n == 8 and len(tasks) == 1 and tasks[0].get("approved") is True and ctx.asked == []
      and out == agent._GOAL_CONTINUE,
      f"balanced harmless goal continues without a question: asked={ctx.asked} tasks={len(tasks)} out={out!r}")

# hands-on asks, the way any change asks; a yes stores it
out, ctx, tasks, n = run_turn("sort the downloads today", [CALC] * 8, autonomy="hands-on", allow_continue=True)
check(n == 8 and ctx.asked == ["schedule_task"] and len(tasks) == 1 and tasks[0].get("approved") is True
      and out == agent._GOAL_CONTINUE,
      f"hands-on asks once, then continues: asked={ctx.asked} tasks={len(tasks)} out={out!r}")

# hands-on, declined: nothing stored, the old stop message
out, ctx, tasks, n = run_turn("sort the downloads today", [CALC] * 8, autonomy="hands-on", allow_continue=False)
check(n == 9 and ctx.asked == ["schedule_task"] and tasks == [] and "couldn't finish" in out,
      f"hands-on decline does not store the goal: asked={ctx.asked} tasks={tasks} n={n} out={out[:60]!r}")

# balanced asks when the steps were destructive, and a no leaves nothing scheduled
RM = tool_call("run_command", {"command": "rm -rf /tmp/llmos-goal-test"})
real_run = tools.REGISTRY["run_command"].fn
tools.REGISTRY["run_command"].fn = lambda a, ctx: "ok"
try:
    out, ctx, tasks, n = run_turn("empty the old folder today", [RM] * 8, autonomy="balanced", allow_continue=False)
    check("schedule_task" in ctx.asked and tasks == [] and "couldn't finish" in out,
          f"balanced destructive continuation asks, and a no stores nothing: asked={ctx.asked} out={out[:40]!r}")
    out, ctx, tasks, n = run_turn("empty the old folder today", [RM] * 8, autonomy="hands-off")
    check(ctx.asked == [] and len(tasks) == 1 and tasks[0].get("approved") is True and out == agent._GOAL_CONTINUE,
          f"hands-off destructive goal continues silently: asked={ctx.asked} tasks={len(tasks)}")
    # a security tool is not stored, on any profile
    FW = tool_call("run_command", {"command": "iptables -F"})
    for auto in ("hands-off", "balanced", "hands-on"):
        out, ctx, tasks, n = run_turn("turn the firewall off today", [FW] * 8, autonomy=auto)
        check(tasks == [] and out != agent._GOAL_CONTINUE,
              f"a security tool is not stored ({auto}): tasks={len(tasks)} out={out[:50]!r}")
finally:
    tools.REGISTRY["run_command"].fn = real_run

# not a goal: the cap still stops, and nothing is scheduled
out, ctx, tasks, n = run_turn("add up these numbers", [CALC] * 8)
check(tasks == [] and "couldn't finish" in out and n == 9,
      f"a request that is not a goal still stops at the cap: n={n} tasks={len(tasks)} out={out[:50]!r}")

# a goal that finishes inside one tool call never schedules a follow-up
out, ctx, tasks, n = run_turn("sort the downloads today",
                              [CALC, {"content": "Sorted four files.", "tool_calls": [], "timings": {}}])
check(tasks == [] and n == 2 and "Sorted four" in out and "keep going" not in out.lower(),
      f"one tool call then an answer does not schedule: n={n} tasks={len(tasks)} out={out[:50]!r}")

# the inbox sentence is a goal, but intent runs mail_triage itself. One tool call, no follow-up task.
triage = tools.REGISTRY["mail_triage"]
old_av, old_fn = triage.available, triage.fn
triage.available = lambda: True
triage.fn = lambda a, ctx: "Archived the newsletter. Kept the note from Sam."
try:
    with mock.patch.object(mail, "account", return_value={"address": "owner@example.com"}):
        out, ctx, tasks, n = run_turn("I need to get to inbox zero today", [CALC] * 8)
finally:
    triage.available, triage.fn = old_av, old_fn
check(n == 0 and tasks == [] and "Sam" in out and "keep going" not in out.lower(),
      f"a triage that finishes in one call does not schedule: tasks={len(tasks)} n={n} out={out[:60]!r}")

# already in the background: another cap chains one more task and does not notify
out, ctx, tasks, n = run_turn("sort the downloads today", [CALC] * 8, headless=True, approved=True)
check(len(tasks) == 1 and tasks[0].get("approved") is True and store.unseen() == [],
      f"a headless approved goal chains without a notification: tasks={len(tasks)} approved={tasks[0].get('approved') if tasks else None}")
out, ctx, tasks, n = run_turn("sort the downloads today", [CALC] * 8, autonomy="balanced", headless=True, approved=False)
check(len(tasks) == 1 and tasks[0].get("approved") is False,
      f"a headless balanced goal stays unapproved, so later steps still follow that profile: {tasks[0].get('approved') if tasks else None}")

# the scheduler tells the owner when a run finishes, and stays quiet when the cap hands it onward
clear_inbox()
clear_tasks()
done = store.add_task("in 1 minute", "sort the downloads today", "agent", approved=True)
with mock.patch.object(agent, "run", lambda ctx, text, history: "Sorted 4 files."):
    scheduler.run_task(done)
notes = store.unseen()
check(len(notes) == 1 and "Sorted 4 files." in notes[0]["text"],
      f"a finished background task notifies: {notes!r}")
clear_tasks()
again = store.add_task("in 1 minute", "sort the downloads today", "agent", approved=True)
def still_going(ctx, text, history):
    ctx._goal_continued = True
    return agent._GOAL_CONTINUE
with mock.patch.object(agent, "run", still_going):
    scheduler.run_task(again)
check(len(store.unseen()) == 1, f"a step-cap handoff does not notify again: {store.unseen()!r}")

if fails:
    print(f"{fails} FAILED"); sys.exit(1)
print("all good")
