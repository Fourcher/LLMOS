#!/usr/bin/env python3
"""Hand a long battery of real user requests to a surface's on-device AI, collect every reply, and flag the ones
worth my attention (refusals, errors, or claims of action). The device executes (slow, offloaded); I judge.

    tools/soak.py vm|laptop BATTERY_FILE [TAG]

BATTERY_FILE: one request per line (# comments and blank lines skipped). Results -> run/soak/<surface>-<tag>.jsonl
and a short flagged summary to stdout at the end. Destructive requests should not be in the battery.
"""
import json, os, re, subprocess, sys, time
HERE=os.path.dirname(os.path.abspath(__file__)); PROJECT=os.path.dirname(HERE)
OUT=os.path.join(PROJECT,"run","soak")
REFUSE=re.compile(r"\b(i can'?t|i cannot|i'?m not able|cannot assist|i must decline|i refuse|i'?m sorry,? but|"
                  r"not appropriate|as an ai|against my|i only (?:draft|write|provide)|authoriz)\b",re.I)
ERRISH=re.compile(r"\b(error|failed|could ?n'?t|couldn't finish|something went wrong|i didn'?t|no such|traceback)\b",re.I)

def run(surface,q,timeout=600):
    env=dict(os.environ)
    if surface=="vm":
        env["DEVLINK_TARGET"]="vm"
        cmd=[sys.executable,os.path.join(HERE,"devlink.py"),"ask",q]
    else:
        cmd=[sys.executable,os.path.join(HERE,"devssh.py"),
             "cd /usr/lib/llmos && timeout %d llmos say %s" % (timeout-30, json.dumps(q))]
    t0=time.time()
    try:
        out=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,env=env).stdout
    except subprocess.TimeoutExpired:
        return {"q":q,"reply":"(timeout)","secs":timeout,"flag":"timeout"}
    reply=""
    i=out.find("{")
    if i>=0:
        try: reply=json.loads(out[i:out.rfind("}")+1]).get("reply","")
        except ValueError: reply=out[:400]
    reply=reply or out.strip()[:400]
    flag="refusal" if REFUSE.search(reply) else ("error" if ERRISH.search(reply[:120]) else "")
    return {"q":q,"reply":reply[:600],"secs":round(time.time()-t0,1),"flag":flag}

def main():
    surface=sys.argv[1]; battery=sys.argv[2]; tag=sys.argv[3] if len(sys.argv)>3 else "soak"
    os.makedirs(OUT,exist_ok=True)
    qs=[l.strip() for l in open(battery) if l.strip() and not l.startswith("#")]
    path=os.path.join(OUT,f"{surface}-{tag}.jsonl"); f=open(path,"w")
    flagged=[]
    for n,q in enumerate(qs,1):
        r=run(surface,q); f.write(json.dumps(r)+"\n"); f.flush()
        mark=r["flag"].upper() or "ok"
        print(f"[{n}/{len(qs)}] {mark:8} {r['secs']:5}s  {q[:46]:46} | {r['reply'][:70].replace(chr(10),' ')}",flush=True)
        if r["flag"]: flagged.append(r)
    print(f"\n=== {surface}/{tag}: {len(qs)} run, {len(flagged)} flagged -> {os.path.relpath(path)}")
    for r in flagged:
        print(f"  [{r['flag']}] {r['q'][:50]} => {r['reply'][:90].replace(chr(10),' ')}")

if __name__=="__main__": main()
