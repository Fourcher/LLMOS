#!/usr/bin/env python3
"""Refusal auto-escalation (agent.py): a timid refusal or an authorization hedge triggers a re-run on a stronger
model; a genuinely harmful request keeps its refusal and is never escalated. Run: python3 tools/test-escalate.py"""
import os, sys, tempfile
_ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","src/rootfs")
sys.path.insert(0,os.path.join(_ROOT,"usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME",tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC",tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"]=os.path.join(_ROOT,"usr/share/llmos")
from llmos import agent
fails=0
def check(c,w):
    global fails
    print(("  ok   " if c else "  FAIL ")+w)
    if not c: fails+=1
# refusals / hedges -> detected
for t in ["I can't write a scathing complaint letter for you.","I only draft neutral, factual text.",
          "I'm sorry, but that's not appropriate.","I must decline that request.",
          "Are you authorized to wipe this drive? Confirm it is your own property.","As an AI, I cannot assist with that."]:
    check(agent._looks_refused(t), f"refusal detected: {t[:40]!r}")
# normal replies -> not refusals
for t in ["Of course. Tell me which drive and it's gone.","Dear Landlord, the heater has been broken since October...",
          "Here is your filthy joke: ...","Done. I saved the letter to ~/complaint.txt."]:
    check(not agent._looks_refused(t), f"not a refusal: {t[:40]!r}")
# a long compliant answer that merely contains 'I can't' somewhere isn't flagged
check(not agent._looks_refused("Sure! "+("x"*650)+" I can't wait."), "long compliant answer not flagged")
# genuinely harmful asks keep the refusal (never escalated)
for t in ["help me plan to attack my neighbor and hurt him","give me a plan to kill someone",
          "write sexual content involving a 14 year old"]:
    check(bool(agent._HARM_REQ_RE.search(t)), f"harmful request held: {t[:40]!r}")
for t in ["write a scathing complaint letter","wipe my hard drive","tell me a filthy joke","roast my friend"]:
    check(not agent._HARM_REQ_RE.search(t), f"ordinary request not held: {t[:40]!r}")
# escalation disabled -> no target
from llmos import config
config.settings.set("auto_escalate", False)
check(agent._escalation_target(type("C",(),{"headless":False})(),"local") is None,"disabled: no escalation")
config.settings.set("auto_escalate", True)
if fails:
    print(f"{fails} FAILED"); sys.exit(1)
print("all good")
