#!/usr/bin/env python3
"""Host-side test for three owner requests (2026-10-13):
  - the queue: a request made while another runs is shown as waiting (a toast and the queue strip), can be removed,
    and a removed one never runs;
  - Ask mode: "ask: ..." reaches the model with no tools offered and a note to answer in words only;
  - the live view: the model's reading progress, thinking and the action it is writing reach the desk as they happen.
Run: python3 tools/test-queue-ask-watch.py  (exit status 0 = pass)"""
import os
import queue
import sys
import threading

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent, desk, llm  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def make_desk():
    d = desk.Desk.__new__(desk.Desk)
    d.events = []
    d.emit = d.events.append
    d._pending_lock = threading.Lock()
    d._req_pending, d._req_done = 0, 0
    d.requests = queue.Queue()
    d._waiting, d._dropped = [], set()
    d.busy = True
    d.ctx = desk.DeskCtx(d)
    return d


# ---- the queue
d = make_desk()
d._enqueue("make a slideshow of my holiday photos", None, "main")
d._enqueue("what's the weather tomorrow", None, "main")
qs = [e for e in d.events if e.get("t") == "queue"]
check("each queued request is announced", any(e.get("t") == "toast" for e in d.events))
check("the queue strip lists both, in order",
      [i["text"] for i in qs[-1]["items"]] == ["make a slideshow of my holiday photos", "what's the weather tomorrow"],
      f"{qs[-1] if qs else None}")
first = qs[-1]["items"][0]["id"]
d.drop_queued(first)
qs = [e for e in d.events if e.get("t") == "queue"]
check("removing one updates the strip", [i["text"] for i in qs[-1]["items"]] == ["what's the weather tomorrow"])
ran = []
d.turn = lambda text, chat: ran.append(text)
d.turn_done = threading.Event()
worker = threading.Thread(target=d._worker, daemon=True)
worker.start()
deadline = threading.Event()
for _ in range(50):
    if d._req_done >= 2:
        break
    deadline.wait(0.05)
check("a removed request never runs; the other does", ran == ["what's the weather tomorrow"], f"ran={ran}")
check("the strip is empty once the queue has run", [e for e in d.events if e.get("t") == "queue"][-1]["items"] == [])

# ---- Ask mode: no tools, words only
seen = {}


def fake_chat(msgs, tools=None, on_text=None, **kw):
    seen["tools"], seen["last"] = tools, msgs[-1]["content"]
    return {"content": "Paris.", "tool_calls": [], "timings": {}}


llm.chat = fake_chat
agent._wait_warm = lambda: None
ctx = desk.DeskCtx(make_desk())
ctx.ask_only = True
try:
    out = agent.run(ctx, "what is the capital of France", [])
except Exception as e:                       # the rest of the turn may want a real desk; the model call is what counts
    out = f"({type(e).__name__}: {e})"
check("Ask mode offers the model no tools", "tools" in seen and seen["tools"] is None, f"seen={seen.get('tools')!r}")
check("Ask mode tells the model to answer in words only", "Ask mode" in seen.get("last", ""), f"last={seen.get('last', '')[-120:]!r}")

# ---- the live view
d = make_desk()
c = d.ctx
c.new_stream()
c.watch("reading", 0, 4000)
c.watch("reading", 4000, 4000)
c.watch("thinking", "The owner wants the settings window.")
c.watch("tool", "show_panel", '{"panel": "sett')
c._watch_t = 0
c.watch("tool", "show_panel", '{"panel": "settings"}')
prog = [e for e in d.events if e.get("t") == "progress"]
acts = [e for e in d.events if e.get("t") == "activity"]
check("reading progress reaches the desk", prog and prog[-1]["done"] == 4000 and prog[-1]["total"] == 4000, f"{prog}")
check("thinking is shown", any("settings window" in e["text"] for e in acts), f"{acts}")
check("the action being written is shown, then updated in place",
      acts and acts[-1]["replace"] is True and "show_panel" not in acts[-1]["text"], f"{acts}")

# the stream reader passes llama-server's progress, thinking and tool-call deltas to watch
got = []
lines = [b'data: {"prompt_progress": {"total": 100, "processed": 40}}',
         b'data: {"choices": [{"delta": {"reasoning_content": "hmm"}}]}',
         b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "show_panel", "arguments": "{}"}}]}}]}',
         b"data: [DONE]"]
llm._read_stream(lines, None, None, lambda *a: got.append(a))
check("the stream reader reports reading, thinking and the tool",
      got[:1] == [("reading", 40, 100)] and ("thinking", "hmm") in got and any(g[0] == "tool" for g in got), f"{got}")

print("all good" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
