#!/usr/bin/env python3
"""Grade a tools/usecase-run.py run for the things the owner cares about in everyday use, before reading each reply:
  REFUSED   the reply says it can't or won't do what was asked
  ASKED     the reply turns the request back into a question for the owner (when a sensible default existed)
  LECTURE   the reply moralises, warns or advises unasked
  EMPTY     nothing came back at all (no reply, no window)
  FAILED    the reply is the fallback for a failure, or says an error
  SLOW      longer than the time the kind of request should take (instant ones: 15 s; model ones: 120 s)
  TIMEOUT   the harness gave up on it
  PENDING   the reply is only a placeholder ("the result follows"); read the answer that follows it
Flags are a checklist, not a verdict: every reply is still read by hand.
usage: tools/ux-grade.py run/everyday [more run dirs]    (writes REPORT.md into the first dir)"""
import glob
import json
import os
import re
import sys

REFUSED = re.compile(r"\b(i (cannot|can't|can not|am unable|'m unable|am not able|'m not able|won't|will not)|i do not have (the )?"
                     r"(ability|access|permission)|i don'?t have (the )?(ability|access|permission)|not something i can|"
                     r"outside (of )?my|i'?m sorry,? but|not allowed to|unable to (do|help|complete|find|perform|set|change|open))\b", re.I)
ASKED_START = re.compile(r"^\s*(which|what|where|who|when|how|could you|can you|would you like|do you want|should i|shall i|"
                         r"please (tell|say|specify|provide|clarify|choose|pick|describe)|tell me)\b", re.I)
ASKED_INSIDE = re.compile(r"\bsay (its|the|a|your) (name|date|time)\b|\bpick (it|one)\b|\bwhich (file|folder|one|email|photo|"
                          r"program|app|printer|network|picture|document|song|video)\b|\bwhat would you like\b", re.I)
LECTURE = re.compile(r"\b(it'?s important|be careful|please be (careful|aware)|caution|safety|security (risk|concern)|make sure (you|to)|"
                     r"i (strongly )?(recommend|suggest|advise)|you should (consider|always|never|be)|be aware|keep in mind|"
                     r"it is (important|recommended|advisable)|i'?d (strongly )?(recommend|advise))\b", re.I)
FAILED = re.compile(r"couldn'?t finish that|could not finish|did not complete|something went wrong|that didn'?t work|"
                    r"\berror\b|no answer from the model|the model (is|was) (busy|unavailable)", re.I)
# an honest limit ("I can't read the status page here") is not a refusal
HONEST_LIMIT = re.compile(r"\bi (can'?t|cannot|can not|couldn'?t) (read|see|check|tell|reach|open|find|hear|measure|know)\b[^.]{0,80}\bhere\b", re.I)
# a placeholder is the first words while the real answer is still on its way: the harness read it too early
PENDING = re.compile(r"the result follows|checking (?:the |that |it |now)|one moment", re.I)
INSTANT, MODEL = 20, 120


_ROUTES = None


def is_instant(phrase):
    """Would the OS answer this without the model? (its own routes decide, so the time limit is the right one)"""
    global _ROUTES
    if _ROUTES is None:
        import tempfile
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(here, "..", "src/rootfs/usr/lib/llmos"))
        os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-grade-"))
        os.environ.setdefault("LLMOS_ETC", os.environ["LLMOS_HOME"] + "/etc")
        from llmos import intent, everyday
        _ROUTES = (intent, everyday)
    intent, everyday = _ROUTES
    try:
        if intent.match(phrase):
            return True
        return bool(everyday.MATCH.search(phrase.lower()))
    except Exception:
        return False


def grade(r):
    reply = (r.get("reply") or "").strip()
    wins = r.get("windows") or []
    flags = []
    if not reply and not wins:
        flags.append("EMPTY")
    if reply and REFUSED.search(reply) and not HONEST_LIMIT.search(reply):
        flags.append("REFUSED")
    body = reply.rstrip()
    if (body.endswith("?") or ASKED_START.match(reply) or ASKED_INSIDE.search(reply)) and not wins:
        flags.append("ASKED")
    if reply and LECTURE.search(reply):
        flags.append("LECTURE")
    if reply and FAILED.search(reply):
        flags.append("FAILED")
    if r.get("timed_out"):
        flags.append("TIMEOUT")
    if reply and PENDING.search(reply):
        flags.append("PENDING")
    limit = INSTANT if is_instant(r.get("phrase", "")) else MODEL
    if (r.get("seconds") or 0) > limit:
        flags.append(f"SLOW{int(r['seconds'])}s")
    return flags


def load(d):
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        if os.path.basename(f) == "summary.json":
            continue
        try:
            rows.append(json.load(open(f)))
        except ValueError:
            pass
    return rows


def report(d):
    rows = load(d)
    out = [f"# Everyday grade: {os.path.basename(d.rstrip('/'))}", "",
           f"{len(rows)} requests. Flags are a checklist; read every reply.", "",
           "| ID | sec | request | flags | reply |", "|---|---:|---|---|---|"]
    counts = {}
    for r in rows:
        fl = grade(r)
        for f in fl:
            counts[f.rstrip("0123456789s")] = counts.get(f.rstrip("0123456789s"), 0) + 1
        reply = (r.get("reply") or "").replace("\n", " ").replace("|", "/")[:150]
        out.append(f"| {r['id']} | {r.get('seconds', 0)} | {r.get('phrase', '')[:52]} | {' '.join(fl) or '-'} | {reply} |")
    clean = sum(1 for r in rows if not grade(r))
    out[2:2] = ["Flag counts: " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"),
                f"Clean (no flag at all): {clean} of {len(rows)}", ""]
    text = "\n".join(out) + "\n"
    open(os.path.join(d, "REPORT.md"), "w").write(text)
    return text


if __name__ == "__main__":
    dirs = sys.argv[1:] or ["run/everyday"]
    for d in dirs:
        print(report(d))
