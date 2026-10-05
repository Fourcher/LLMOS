#!/usr/bin/env python3
"""Evaluate one-pass decisions ("decide, don't write") on the real on-device model.

A decision reads the model's probabilities for a fixed set of one-token answers after the OS's own prompt
(system prompt + tool schemas + the owner's request), so it shares llama-server's prompt cache with the
request itself and costs a few dozen tokens, not a generation. This scores the routing question used under
the 'ask' brain setting ("is this a big one for the online model?") on labelled requests, next to the
keyword rule it can replace, and reports accuracy, separation and cost.

usage: tools/decide-eval.py [PORT] [--variants]   (a llama-server with the OS's model must be listening;
       default port 8082). --variants also scores the alternative wordings that were tried.
No VM needed: the OS's real prompt and tools are built from src/rootfs."""
import json
import os
import sys
import tempfile
import time

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-eval-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
PORT = next((a for a in sys.argv[1:] if a.isdigit()), "8082")
os.environ["LLMOS_LLAMA_URL"] = f"http://127.0.0.1:{PORT}"
from llmos import agent, config, llm, tools  # noqa: E402

QUICK = [
    "what time is it?", "how much disk space do I have?", "set a timer for 10 minutes", "turn the volume down a bit",
    "open my files", "remember that my sister's birthday is March 3rd", "what's 12 times 34?", "lock the screen",
    "play some music", "write \"milk\" on my shopping list", "summarize my disk usage",
    "translate \"thank you\" into French", "is the internet on?", "take a screenshot", "what's the weather in Phoenix?",
    "remind me to call mom at 6pm", "make the screen brighter", "delete the file notes-old.txt",
    "what's the capital of Australia?", "show me my recent notes", "how do I say goodbye in Japanese?",
    "rename photo1.jpg to beach.jpg", "what's my IP address?", "who wrote Pride and Prejudice?",
]
BIG = [
    "Write a two-page cover letter for a senior nursing job at a children's hospital, emphasising my ICU years.",
    "Can you put together a heartfelt ten-minute speech for my sister's wedding? She loves hiking and terrible puns.",
    "Plan a two-week trip through Japan for a family of four in April, with a day-by-day itinerary and a budget.",
    "Explain the causes of the 2008 financial crisis in depth, with the main players and what regulators changed afterwards.",
    "My Python web scraper keeps getting a 403 after a few hundred pages. Figure out why and fix it.",
    "Compare the last five years of Tesla, BYD and Toyota's EV strategies and tell me which is best placed for 2030.",
    "Draft a business plan for a small bakery: market, costs, pricing, a 12-month cash flow and the risks.",
    "Read these three studies on intermittent fasting and tell me what the evidence really says, with the weaknesses of each.",
    "Turn my notes from today's meeting into a clear project proposal with milestones, owners and risks.",
    "Build me a small Flask app with user accounts, a SQLite database and a page that charts my spending.",
    "Create a 12-week marathon training plan for a beginner who can run 5 km, with rest days and nutrition advice.",
    "Rewrite my CV so it targets product management roles, and tell me what's missing.",
    "Analyse this year's household spending from the CSV in my documents and suggest where we can save 15%.",
    "Help me prepare for a Google interview for a senior SRE role: likely questions, model answers and a study plan.",
    "Write a short story of about 2,000 words about a lighthouse keeper who finds a message in a bottle.",
    "Teach me the basics of linear algebra step by step, with exercises and worked solutions.",
]
CASES = [(t, 0) for t in QUICK] + [(t, 1) for t in BIG]

# alternative wordings tried while designing agent.ROUTE_QUESTION: (name, appended question, prefill, labels)
VARIANTS = [
    ("prefill-AB", None, "(Routing note, not shown to the owner. Is this request (A) quick everyday help I can do well "
     "here, or (B) big open-ended work, such as long writing, deep analysis, research or programming, that a stronger "
     "online model would do much better? Answer: (", ("A", "B")),
    ("ask-AB", "[Routing question, answer with one letter: is this request (A) quick everyday help, or (B) big work "
     "(long writing, in-depth analysis, research, detailed planning or programming) that a stronger online model would "
     "do much better?]", "(", ("A", "B")),
    ("ask-yesno", "[Routing question: is this request big work (long writing, in-depth analysis, research, detailed "
     "planning or programming) that a stronger online model would do much better? Answer yes or no.]", "", ("no", "yes")),
]


def auc(scores):
    pos = [s for s, y in scores if y]
    neg = [s for s, y in scores if not y]
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / max(1, len(pos) * len(neg))


def best_threshold(scores):
    best = (0, 0.5)
    for t in sorted({s for s, _ in scores} | {0.5}):
        acc = sum((s >= t) == bool(y) for s, y in scores) / len(scores)
        best = max(best, (acc, t))
    return best


def report(name, scores, cost):
    acc5 = sum((s >= 0.5) == bool(y) for s, y in scores) / len(scores)
    bacc, bt = best_threshold(scores)
    fp = [t for (s, y), (t, _) in zip(scores, CASES) if s >= 0.5 and not y]
    fn = [t for (s, y), (t, _) in zip(scores, CASES) if s < 0.5 and y]
    print(f"{name:12s} accuracy@0.5 {acc5:.0%}  best {bacc:.0%} @ {bt:.2f}  AUC {auc(scores):.2f}  {cost}")
    for t in fp:
        print(f"    big?  but quick: {t[:90]}")
    for t in fn:
        print(f"    quick? but big:  {t[:90]}")


def main():
    if not llm.health():
        sys.exit(f"no model server on port {PORT}")
    agent.warm_up()
    # the keyword rule the decision replaces
    report("keywords", [(1.0 if agent.looks_hard(t) else 0.0, y) for t, y in CASES], "no model call")
    variants = [("shipped", None, None, None)] + (VARIANTS if "--variants" in sys.argv else [])
    for name, question, prefill, labels in variants:
        scores, toks, secs = [], [], []
        for text, y in CASES:
            msgs = agent.build_messages(None, text, [])
            t0 = time.time()
            if name == "shipped":
                p, info = agent.route_score(msgs)
            else:
                p, info = llm.decide(msgs, labels, question=question, prefill=prefill, tools=agent.tool_schemas())
                p = p.get(labels[1]) if p else None
            secs.append(time.time() - t0)
            toks.append((info or {}).get("prompt_n") or 0)
            scores.append((p if p is not None else 0.5, y))
        report(name, scores, f"{sum(toks) / len(toks):.0f} new prompt tokens, {sum(secs) / len(secs):.2f} s per decision")


if __name__ == "__main__":
    main()
