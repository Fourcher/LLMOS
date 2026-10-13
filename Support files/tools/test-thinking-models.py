#!/usr/bin/env python3
"""Host-side test (no network, no model): thinking models. The Gemma 4 catalog entries switch their thinking off
at serve time (chat_kwargs -> --chat-template-kwargs), granite is unchanged, and a reply made only of thinking
(reasoning_content, no content) is never shown as the answer. Run: python3 tools/test-thinking-models.py"""
import contextlib
import io
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
from llmos import llm, models  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def sse(*chunks):
    """Fake SSE lines: one 'data:' event per delta dict, then [DONE]."""
    out = [("data: " + json.dumps({"choices": [{"delta": d}]})) for d in chunks]
    return out + ["data: [DONE]"]


CAT = os.path.join(_ROOT, "usr/share/llmos/catalog.json")
with open(CAT, encoding="utf-8") as f:
    catalog = json.load(f)
by_id = {m["id"]: m for m in catalog}
KW = {"enable_thinking": False}
KW_ARG = json.dumps(KW, separators=(",", ":"))

# 1. catalog: every gemma-4 entry turns thinking off; the file is valid JSON (json.load above)
gemma = [m for m in catalog if m["id"].startswith("gemma-4")]
check(len(gemma) == 3, f"three gemma-4 entries ({', '.join(m['id'] for m in gemma)})")
for m in gemma:
    check(m.get("chat_kwargs") == KW, f"{m['id']} chat_kwargs is {KW}")
check(by_id["granite-4.2-3b"].get("chat_kwargs") == KW, "granite-4.2-3b chat_kwargs unchanged")

# 2. serve_argv: a fake active model (the catalog entry), no draft file, fixed RAM
real_active, real_draft = models.active, models.draft_path
models.draft_path = lambda m: None
try:
    for mid in ("gemma-4-e4b", "gemma-4-e2b", "gemma-4-12b", "granite-4.2-3b"):
        models.active = lambda m=by_id[mid]: m
        argv = models.serve_argv() or []
        ok = "--chat-template-kwargs" in argv and argv[argv.index("--chat-template-kwargs") + 1] == KW_ARG
        check(ok, f"serve_argv({mid}) has --chat-template-kwargs {KW_ARG}")
    for mid in ("ministral-3-3b", "hermes-3-3b", "dolphin-3-8b"):
        models.active = lambda m=by_id[mid]: m
        check("--chat-template-kwargs" not in (models.serve_argv() or []), f"serve_argv({mid}) has no chat kwargs")
finally:
    models.active, models.draft_path = real_active, real_draft

# 3. _read_stream: reasoning-only, content-only, reasoning then content
rs = []
content, calls, _, _ = llm._read_stream(sse({"reasoning_content": "Let me think"}, {"reasoning_content": " more."}), None, rs)
check(content == "" and rs == ["Let me think", " more."] and calls == [], "reasoning-only: content empty, reasoning kept aside")
content, calls, _, _ = llm._read_stream(sse({"content": "Hello"}, {"content": " there"}), None, [])
check(content == "Hello there", "content-only: content returned")
spoken = []
rs = []
content, _, _, _ = llm._read_stream(sse({"reasoning_content": "hmm"}, {"content": "Answer"}), spoken.append, rs)
check(content == "Answer" and spoken == ["Answer"] and rs == ["hmm"], "reasoning then content: only content is answer or spoken")
check(llm._read_stream(sse({"reasoning_content": "x"}), None)[0] == "", "reasoning with no reasoning list still not content")


# 4. _chat_on: reasoning-only reply with thinking off -> empty content and one log line; with thinking on -> no log
class FakeConn:
    def __init__(self, lines):
        self.lines = lines

    def request(self, *a, **k):
        pass

    def getresponse(self):
        class R:
            status = 200

            def __iter__(self_inner):
                return iter(self.lines)
        return R()

    def close(self):
        pass


def run_chat(lines, think):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        r = llm._chat_on(FakeConn(lines), {"chat_template_kwargs": {"enable_thinking": think}}, None)
    return r, err.getvalue()


r, log = run_chat(sse({"reasoning_content": "thinking only"}), False)
check(r["content"] == "" and log.count("model spent its turn thinking") == 1, "think off, reasoning only: empty answer, logged once")
r, log = run_chat(sse({"reasoning_content": "thinking"}), True)
check(r["content"] == "" and "spent its turn" not in log, "think on, reasoning only: unchanged (no log, empty as before)")
r, log = run_chat(sse({"reasoning_content": "r"}, {"content": "final"}), True)
check(r["content"] == "final" and log == "", "think on, reasoning then content: content returned")
r, log = run_chat(sse({"content": "plain"}), False)
check(r["content"] == "plain" and log == "", "no reasoning: content returned, no log")

if fails:
    print(f"{fails} FAIL")
    sys.exit(1)
print("all good")
