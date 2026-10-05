#!/usr/bin/env python3
"""Host-side test of the online-model client (llmos/llm.py), with no network: a fake Claude (the Messages
API) and a fake OpenAI-compatible service on 127.0.0.1 answer with canned streams. The client must stream
the text, collect the tool call, convert the conversation correctly, keep the key off the command line and
explain failures in plain words. Run: python3 tools/test-cloud.py"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, llm  # noqa: E402

SEEN = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def _sse(self, lines):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for ln in lines:
            self.wfile.write(ln.encode())
            self.wfile.flush()

    def do_GET(self):
        SEEN.append((self.path, {k.lower(): v for k, v in self.headers.items()}, {}))
        if self.path == "/v1/models":     # what an OpenAI account offers (the ChatGPT sign-in picks from it)
            if self.headers.get("Authorization") != "Bearer sk-test":
                return self._json(401, {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}})
            return self._json(200, {"object": "list", "data": [{"id": i, "object": "model"} for i in
                                    ("gpt-4o", "gpt-5.1-mini", "gpt-5.1-2026-03-01", "gpt-5.1", "gpt-5.1-pro", "gpt-realtime", "o3", "text-embedding-3-large")]})
        self._json(404, {"error": {"message": "no such path"}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path == "/v1/messages":
            if self.headers.get("x-api-key") != "sk-ant-test":
                return self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
            last = json.dumps(body.get("messages", [])[-1:])
            if "REFUSE" in last:            # the service's safety check declines (HTTP 200, stop_reason refusal)
                ev = [{"type": "message_start"}, {"type": "message_delta", "delta": {"stop_reason": "refusal"}}, {"type": "message_stop"}]
                return self._sse([f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in ev])
            k = 0
            ev = [{"type": "message_start"}]
            if "THINK" in last:             # current models think first: a thinking block with a signature
                ev += [{"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
                       {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Add them."}},
                       {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig-abc"}},
                       {"type": "content_block_stop", "index": 0}]
                k = 1
            ev += [{"type": "content_block_start", "index": k, "content_block": {"type": "text", "text": ""}},
                   {"type": "content_block_delta", "index": k, "delta": {"type": "text_delta", "text": "Hello "}},
                   {"type": "content_block_delta", "index": k, "delta": {"type": "text_delta", "text": "there."}},
                   {"type": "content_block_stop", "index": k}]
            if body.get("tools"):
                ev += [{"type": "content_block_start", "index": k + 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "calculate", "input": {}}},
                       {"type": "content_block_delta", "index": k + 1, "delta": {"type": "input_json_delta", "partial_json": "{\"expression\": "}},
                       {"type": "content_block_delta", "index": k + 1, "delta": {"type": "input_json_delta", "partial_json": "\"2+2\"}"}},
                       {"type": "content_block_stop", "index": k + 1}]
            ev += [{"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 9}}, {"type": "message_stop"}]
            return self._sse([f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in ev])
        if self.path.endswith("/chat/completions"):
            if self.headers.get("Authorization") != "Bearer sk-test":
                return self._json(401, {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}})
            ch = [{"choices": [{"delta": {"role": "assistant", "content": "Hi "}}]}, {"choices": [{"delta": {"content": "from openai-ish."}}]}]
            if body.get("tools"):
                ch += [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_9", "type": "function", "function": {"name": "calculate", "arguments": "{\"expr"}}]}}]},
                       {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ession\": \"3*3\"}"}}]}}]}]
            return self._sse([f"data: {json.dumps(c)}\n\n" for c in ch] + ["data: [DONE]\n\n"])
        self._json(404, {"error": {"message": "no such path"}})


srv = HTTPServer(("127.0.0.1", 0), Fake)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


TOOLS = [{"type": "function", "function": {"name": "calculate", "description": "sum", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}}]
HISTORY = [{"role": "system", "content": "You are the OS."},
           {"role": "assistant", "content": "earlier reply"},
           {"role": "user", "content": "what is 2+2"},
           {"role": "assistant", "content": "", "tool_calls": [{"id": "call_0_0", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"2+2\"}"}}]},
           {"role": "tool", "tool_call_id": "call_0_0", "content": "4"},
           {"role": "user", "content": "[context]\nNow: Monday.\n[/context]\n\nand 3+3?"}]

print("no account yet")
check(config.cloud() is None, "config.cloud() is None before set-up")
check(llm.cloud_label() == "", "cloud_label() is '' without an account")
try:
    llm.cloud_chat([{"role": "user", "content": "hi"}])
    check(False, "cloud_chat without an account raises")
except llm.CloudError as e:
    check("no online model" in str(e), f"cloud_chat without an account raises: {e}")

print("Claude: the Messages API")
ok, note = llm.cloud_setup({"provider": "Claude", "model": "claude-opus-5-5", "url": base, "key": "bad"})
check(not ok and "invalid x-api-key" in note, f"a wrong key is refused in plain words: {note}")
check(config.cloud() is None, "a refused key is not kept")
ok, note = llm.cloud_setup({"provider": "claude", "model": "claude-opus-5-5", "url": base, "key": "sk-ant-test"})
check(ok and "Claude Opus 5.5" in note, f"a working key is kept: {note}")
check(config.cloud()["key"] == "sk-ant-test" and config.cloud()["provider"] == "anthropic", "the account is stored in the vault dir")
check(config.settings.get("brain") == "ask", "adopting an account turns 'local' into 'ask'")
check(oct(os.stat(config.data("cloud.json")).st_mode)[-3:] == "600", "cloud.json is 0600")
check(llm.cloud_label() == "Claude Opus 5.5", "cloud_label() names the model")
pieces = []
r = llm.cloud_chat(HISTORY, tools=TOOLS, on_text=pieces.append)
check(r["content"] == "Hello there." and pieces == ["Hello ", "there."], f"text streams in pieces: {pieces}")
check(r["tool_calls"] == [{"id": "toolu_1", "name": "calculate", "arguments": "{\"expression\": \"2+2\"}"}], f"the tool call is assembled from input_json_delta: {r['tool_calls']}")
path, hdr, body = SEEN[-1]
check(hdr.get("anthropic-version") == "2023-06-01" and hdr.get("x-api-key") == "sk-ant-test", "headers: version + key")
check(body["system"] == "You are the OS." and "system" not in [m["role"] for m in body["messages"]], "the system prompt becomes the system field")
roles = [m["role"] for m in body["messages"]]
check(roles[0] == "user" and all(a != b for a, b in zip(roles, roles[1:])), f"turns alternate and start with the user: {roles}")
tr = [b for m in body["messages"] for b in m["content"] if b["type"] == "tool_result"]
tu = [b for m in body["messages"] for b in m["content"] if b["type"] == "tool_use"]
check(tr == [{"type": "tool_result", "tool_use_id": "call_0_0", "content": "4"}], f"tool results become tool_result blocks: {tr}")
check(tu == [{"type": "tool_use", "id": "call_0_0", "name": "calculate", "input": {"expression": "2+2"}}], f"tool calls become tool_use blocks: {tu}")
check(not any(b.get("type") == "text" and not b.get("text", "").strip() for m in body["messages"] for b in m["content"]), "no empty text blocks")
check(body["tools"][0]["input_schema"]["type"] == "object" and body["tools"][0]["name"] == "calculate", "tools carry input_schema")
check(body["max_tokens"] >= 16000 and body["stream"] is True, f"room to think (max_tokens {body['max_tokens']}) and streamed")
check(not {"temperature", "top_p", "top_k"} & set(body), "no sampling settings (current Claude models reject them with a 400)")

print("Claude thinks before answering: its blocks go back unchanged")
think = HISTORY[:-1] + [{"role": "user", "content": "THINK: what is 2+2"}]
r = llm.cloud_chat(think, tools=TOOLS)
raw = r.get("raw") or []
check([b.get("type") for b in raw] == ["thinking", "text", "tool_use"], f"the response's own blocks are kept in order: {[b.get('type') for b in raw]}")
check(raw and raw[0].get("signature") == "sig-abc" and raw[0].get("thinking") == "Add them.", "the thinking block keeps its text and signature")
nxt = think + [{"role": "assistant", "content": r["content"], "_anthropic": raw,
                "tool_calls": [{"id": "toolu_1", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"2+2\"}"}}]},
               {"role": "tool", "tool_call_id": "toolu_1", "content": "4"}]
llm.cloud_chat(nxt, tools=TOOLS)
sent = SEEN[-1][2]["messages"]
check(sent[-2]["role"] == "assistant" and sent[-2]["content"] == raw, "the next step replays that assistant turn exactly as received")
check(sent[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "toolu_1", "content": "4"}, "followed by the tool's result")

print("a refusal from the service is answered on this computer instead")
try:
    llm.cloud_chat([{"role": "user", "content": "REFUSE this"}])
    check(False, "a refusal raises CloudError (the agent then answers locally)")
except llm.CloudError as e:
    check("declined" in str(e), f"a refusal raises CloudError (the agent then answers locally): {e}")

print("an OpenAI-compatible service")
ok, note = llm.cloud_setup({"provider": "OpenAI-compatible", "model": "some-model", "url": base + "/v1", "key": "sk-test"})
check(ok and "some-model" in note, f"set up: {note}")
pieces = []
r = llm.cloud_chat(HISTORY, tools=TOOLS, on_text=pieces.append)
check(r["content"] == "Hi from openai-ish." and pieces == ["Hi ", "from openai-ish."], f"text streams: {pieces}")
check(r["tool_calls"] == [{"id": "call_9", "name": "calculate", "arguments": "{\"expression\": \"3*3\"}"}], f"tool call assembled: {r['tool_calls']}")
path, hdr, body = SEEN[-1]
check(path == "/v1/chat/completions" and hdr.get("authorization") == "Bearer sk-test", "bearer key, chat-completions path")
check("max_tokens" in body and "max_completion_tokens" not in body and body["messages"] == HISTORY, "plain chat-completions body for a non-OpenAI host")
ok, note = llm.cloud_setup({"provider": "openai", "model": "x", "url": base + "/v1", "key": "wrong"})
check(not ok and "Incorrect API key" in note, f"a refused key is explained: {note}")
llm.cloud_chat([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "x", "_anthropic": [{"type": "text", "text": "x"}]},
                {"role": "user", "content": "again"}])
check(not any(k.startswith("_") for m in SEEN[-1][2]["messages"] for k in m), "this OS's private keys never reach another service")

print("failures are explained")
ok, note = llm.cloud_setup({"provider": "claude", "model": "claude-opus-5-5", "url": "http://127.0.0.1:1", "key": "sk-ant-test"})
check(not ok and ("could not connect" in note or "refused" in note), f"a closed port: {note}")
ok, note = llm.cloud_setup({"provider": "claude", "model": "", "url": base, "key": ""})
check(not ok and "no API key" in note, f"missing key: {note}")
ok, note = llm.cloud_setup({"provider": "claude", "model": "m", "url": "ftp://x", "key": "k"})
check(not ok and "http" in note, f"bad address: {note}")
check(not any("sk-ant-test" in a for a in sys.argv), "the key is not on this process's command line")

print("ChatGPT: the model is not asked for; the newest general one the account offers is picked")
P = llm._pick_openai_model
check(P(["gpt-4o", "gpt-5", "gpt-5-mini", "gpt-5.1", "gpt-5.1-2026-03-01", "gpt-5.1-codex", "gpt-realtime", "o3", "gpt-image-1"]) == "gpt-5.1",
      "the newest gpt-<version>, not a mini, codex, realtime, image or dated snapshot")
check(P(["gpt-5.5-pro", "gpt-5.5", "gpt-5"]) == "gpt-5.5" and P(["gpt-5.5-pro", "gpt-5"]) == "gpt-5", "never a -pro model (another API)")
check(P(["gpt-5-2025-08-07"]) == "gpt-5-2025-08-07", "a dated snapshot when it is all there is")
check(P(["gpt-4.1", "gpt-4.1-mini", "gpt-4o"]) == "gpt-4.1", "4.1 over 4o")
check(P([]) == "" and P(["o3", "o4-mini", "dall-e-3"]) == "", "nothing usable: ''")
ok, note = llm.cloud_setup({"provider": "chatgpt", "url": base + "/v1", "key": "sk-wrong"}, adopt=False)
check(not ok and "Incorrect API key" in note, f"a wrong ChatGPT key is refused when the models are listed: {note}")
ok, note = llm.cloud_setup({"provider": "chatgpt", "url": base + "/v1", "key": "sk-test"}, adopt=False)
check(ok and config.cloud()["model"] == "gpt-5.1" and config.cloud()["provider"] == "chatgpt", f"a ChatGPT key alone sets up gpt-5.1: {note}")
path, hdr, _ = [x for x in SEEN if x[0] == "/v1/models"][-1]
check(hdr.get("authorization") == "Bearer sk-test", "the models list is asked for with the key")
check(not any("sk-test" in a for a in sys.argv), "the key is not on this process's command line")
import re  # noqa: E402
for pid, good, bad in (("anthropic", "sk-ant-api03-" + "A" * 80 + "-xyzAA", "sk-proj-" + "B" * 60),
                       ("chatgpt", "sk-proj-" + "B" * 60, "hello world")):
    pat = llm.CLOUD_PROVIDERS[pid]["key_re"]
    check(re.search(pat, "copied: " + good + "\n") and re.search(pat, "copied: " + good + "\n").group(0) == good and not re.search(pat, bad),
          f"{pid}: a copied key is recognised in the clipboard text, other text is not")
check(llm.CLOUD_PROVIDERS["anthropic"]["signin"].startswith("https://platform.claude.com/") and
      llm.CLOUD_PROVIDERS["chatgpt"]["signin"].startswith("https://platform.openai.com/"), "sign-in pages are the services' own key pages")

print("forgetting")
config.forget_cloud()
check(config.cloud() is None, "forget_cloud() removes the account")
srv.shutdown()
print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
