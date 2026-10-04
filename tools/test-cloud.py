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

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path == "/v1/messages":
            if self.headers.get("x-api-key") != "sk-ant-test":
                return self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
            ev = [{"type": "message_start"}, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello "}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "there."}},
                  {"type": "content_block_stop", "index": 0}]
            if body.get("tools"):
                ev += [{"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "calculate", "input": {}}},
                       {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"expression\": "}},
                       {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "\"2+2\"}"}},
                       {"type": "content_block_stop", "index": 1}]
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
ok, note = llm.cloud_setup({"provider": "Claude", "model": "claude-sonnet-5", "url": base, "key": "bad"})
check(not ok and "invalid x-api-key" in note, f"a wrong key is refused in plain words: {note}")
check(config.cloud() is None, "a refused key is not kept")
ok, note = llm.cloud_setup({"provider": "claude", "model": "claude-sonnet-5", "url": base, "key": "sk-ant-test"})
check(ok and "Claude Sonnet 5" in note, f"a working key is kept: {note}")
check(config.cloud()["key"] == "sk-ant-test" and config.cloud()["provider"] == "anthropic", "the account is stored in the vault dir")
check(config.settings.get("brain") == "ask", "adopting an account turns 'local' into 'ask'")
check(oct(os.stat(config.data("cloud.json")).st_mode)[-3:] == "600", "cloud.json is 0600")
check(llm.cloud_label() == "Claude Sonnet 5", "cloud_label() names the model")
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
check(body["max_tokens"] == 1200 and body["stream"] is True, "max_tokens and stream set")

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

print("failures are explained")
ok, note = llm.cloud_setup({"provider": "claude", "model": "claude-sonnet-5", "url": "http://127.0.0.1:1", "key": "sk-ant-test"})
check(not ok and ("could not connect" in note or "refused" in note), f"a closed port: {note}")
ok, note = llm.cloud_setup({"provider": "claude", "model": "", "url": base, "key": ""})
check(not ok and "no API key" in note, f"missing key: {note}")
ok, note = llm.cloud_setup({"provider": "claude", "model": "m", "url": "ftp://x", "key": "k"})
check(not ok and "http" in note, f"bad address: {note}")
check(not any("sk-ant-test" in a for a in sys.argv), "the key is not on this process's command line")

print("forgetting")
config.forget_cloud()
check(config.cloud() is None, "forget_cloud() removes the account")
srv.shutdown()
print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
