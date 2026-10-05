#!/usr/bin/env python3
"""A minimal Model Context Protocol server over stdio, for tests and demos. It advertises two tools (echo,
add) and answers JSON-RPC 2.0 on stdin/stdout. Used by tools/test-connectors.py and usable as a real
connector: add a connector whose command is 'python3 .../tools/fake-mcp-server.py'."""
import json
import sys
import time

TOOLS = [
    {"name": "echo", "description": "Echo the given text back.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
     "annotations": {"readOnlyHint": True}},
    {"name": "add", "description": "Add two numbers.",
     "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}},
]
if "--stall" in sys.argv:       # tests: a tool that writes half a line and then never answers
    TOOLS.append({"name": "stall", "description": "Stop responding (tests).", "inputSchema": {"type": "object", "properties": {}}})


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    while True:
        raw = sys.stdin.readline()        # readline, not "for line in stdin", to avoid pipe read-ahead buffering
        if raw == "":
            break
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2025-06-18",
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            p = msg.get("params", {})
            name, args = p.get("name"), p.get("arguments", {})
            if name == "echo":
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "echo: " + str(args.get("text", ""))}]}})
            elif name == "stall" and "--stall" in sys.argv:
                sys.stdout.write('{"jsonrpc": "2.0", "id": ' + json.dumps(mid))     # half a line, no newline
                sys.stdout.flush()
                time.sleep(3600)
            elif name == "add":
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": str((args.get("a") or 0) + (args.get("b") or 0))}]}})
            else:
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "no such tool"}], "isError": True}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
