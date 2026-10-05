#!/usr/bin/env python3
"""A stand-in online model for tests: speaks Anthropic's Messages API (/v1/messages, key sk-ant-test) and the
OpenAI chat-completions API (/v1/chat/completions, key sk-test) on the host, reachable from a test VM at
10.0.2.2. The first turn of a request with tools answers with one tool call (calculate 2+2), the turn after a
tool result answers with text, so the agent loop completes. Nothing here touches the real services.
usage: tools/fake-cloud.py [--port 8099] [--slow SECONDS]"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8099)
ap.add_argument("--slow", type=float, default=0.0, help="seconds to wait before answering (to watch the orb)")
opts = ap.parse_args()


def _has_tool_result(msgs, anthropic):
    if not msgs:
        return False
    last = msgs[-1]
    if anthropic:
        return isinstance(last.get("content"), list) and any(b.get("type") == "tool_result" for b in last["content"])
    return last.get("role") == "tool"


class Fake(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        print(time.strftime("%H:%M:%S"), fmt % a, flush=True)

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
            time.sleep(0.05)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if opts.slow:
            time.sleep(opts.slow)
        if self.path == "/v1/messages":
            if self.headers.get("x-api-key") != "sk-ant-test":
                return self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
            want_tool = bool(body.get("tools")) and not _has_tool_result(body.get("messages"), True)
            text = "Checking that first." if want_tool else "Two and two make four, says the stand-in online model."
            if body.get("max_tokens", 0) <= 8:
                text = "ok"
            ev = [{"type": "message_start"}, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}]
            for w in text.split(" "):
                ev.append({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": w + " "}})
            ev.append({"type": "content_block_stop", "index": 0})
            if want_tool:
                ev += [{"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "calculate", "input": {}}},
                       {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"expression\": \"2+2\"}"}},
                       {"type": "content_block_stop", "index": 1}]
            ev += [{"type": "message_delta", "delta": {"stop_reason": "tool_use" if want_tool else "end_turn"}}, {"type": "message_stop"}]
            return self._sse([f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in ev])
        if self.path.endswith("/chat/completions"):
            if self.headers.get("Authorization") != "Bearer sk-test":
                return self._json(401, {"error": {"message": "Incorrect API key provided"}})
            want_tool = bool(body.get("tools")) and not _has_tool_result(body.get("messages"), False)
            text = "Checking that first." if want_tool else "Two and two make four, says the stand-in service."
            ch = [{"choices": [{"delta": {"role": "assistant", "content": w + " "}}]} for w in text.split(" ")]
            if want_tool:
                ch.append({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                                                   "function": {"name": "calculate", "arguments": "{\"expression\": \"2+2\"}"}}]}}]})
            return self._sse([f"data: {json.dumps(c)}\n\n" for c in ch] + ["data: [DONE]\n\n"])
        self._json(404, {"error": {"message": "no such path"}})


print(f"fake cloud on 127.0.0.1:{opts.port} (VM: http://10.0.2.2:{opts.port})", flush=True)
HTTPServer(("127.0.0.1", opts.port), Fake).serve_forever()
