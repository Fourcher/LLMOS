#!/usr/bin/env python3
"""Stop hook: the LLM OS orchestrator may not end its turn while no worker is running.

Only acts on sessions whose transcript records agentSetting llmos-orchestrator.
If background workers are still running, it may stop (it is woken when they finish).
"""
import glob, json, os, re, sys, time

try:
    inp = json.load(sys.stdin)
    lines = open(inp["transcript_path"]).read().splitlines()
except Exception:
    sys.exit(0)

is_orch, launched, finished = False, set(), set()
for line in lines:
    try:
        d = json.loads(line)
    except ValueError:
        continue
    if d.get("type") == "agent-setting" and d.get("agentSetting") == "llmos-orchestrator":
        is_orch = True
    m = d.get("message")
    if isinstance(m, dict) and d.get("type") == "assistant":
        for b in m.get("content") or []:
            if b.get("type") == "tool_use" and b.get("name") == "Agent":
                launched.add(b.get("id"))
    if "<task-notification>" in line and "<status>" in line:
        for tid in re.findall(r"<tool-use-id>(toolu_[A-Za-z0-9]+)</tool-use-id>", line.replace("\\n", "\n")):
            finished.add(tid)

def alive(tool_id):
    """A launch counts as running only if its transcript moved in the last 10 minutes."""
    sub = os.path.join(inp["transcript_path"][:-6], "subagents")
    for mf in glob.glob(os.path.join(sub, "*.meta.json")):
        try:
            if json.load(open(mf)).get("toolUseId") == tool_id:
                jf = mf[:-10] + ".jsonl"
                return os.path.exists(jf) and time.time() - os.path.getmtime(jf) < 600
        except Exception:
            pass
    return False

if not is_orch:
    sys.exit(0)

# Owner inbox: instructions the managing session writes for the orchestrator.
# Delivered once, at the next turn end, even while workers are running.
inbox = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orchestrator-inbox.md")
try:
    note = open(inbox).read().strip()
except OSError:
    note = ""
if note:
    with open(inbox + ".delivered", "a") as fh:
        fh.write(time.strftime("\n## %Y-%m-%d %H:%M:%S\n") + note + "\n")
    open(inbox, "w").close()
    print(json.dumps({"decision": "block", "reason": "Owner instruction (delivered by the managing session, which speaks for the owner):\n" + note}))
    sys.exit(0)

if any(alive(t) for t in launched - finished):
    sys.exit(0)

print(json.dumps({"decision": "block", "reason": (
    "Never stop (owner's rule). No worker is running. Re-read BRIEF.md and queue.md, then dispatch the next round now: "
    "fill every front (speed, capability, UI, owner freedom, reliability, process) with PROBE/FIX/VERIFY/RUN workers, "
    "all in one message, run in the background.")}))
