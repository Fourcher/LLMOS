"""Client for the on-device model: llama.cpp's llama-server, listening on
127.0.0.1 only. Nothing here talks to any other machine."""
import http.client
import json
import time
import urllib.parse

from . import config


class ModelDown(Exception):
    """The model server is unreachable."""


class ModelError(ModelDown):
    """The server answered, but refused or failed the request (e.g. the
    request did not fit in the context window)."""


def _conn(timeout=900):
    u = urllib.parse.urlparse(config.llama_url())
    return http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)


def health():
    try:
        c = _conn(3)
        c.request("GET", "/health")
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status == 200 and b"ok" in body
    except OSError:
        return False


def wait_ready(timeout=600, tick=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if health():
            return True
        if tick:
            tick(time.time() - t0)
        time.sleep(1)
    return False


def chat(messages, tools=None, on_text=None, max_tokens=1200, temperature=0.3,
         json_schema=None, think=None):
    """Stream one completion. Returns {"content", "tool_calls", "timings"}.
    Tool calls are accumulated from streamed deltas."""
    if think is None:
        think = bool(config.settings.get("think"))
    body = {"messages": messages, "stream": True, "temperature": temperature,
            "top_p": 0.95, "max_tokens": max_tokens, "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": think}}
    if tools:
        body["tools"] = tools
    if json_schema:
        body["response_format"] = {"type": "json_object", "schema": json_schema}
    c = _conn()
    try:
        c.request("POST", "/v1/chat/completions", json.dumps(body),
                  {"Content-Type": "application/json"})
        r = c.getresponse()
    except OSError as e:
        c.close()
        raise ModelDown(str(e))
    if r.status != 200:
        raw = r.read()[:600].decode("utf-8", "replace")
        c.close()
        try:
            detail = json.loads(raw).get("error", {}).get("message", raw)
        except ValueError:
            detail = raw
        if "context" in detail.lower() or "exceed" in detail.lower() or "too long" in detail.lower():
            detail = "the request was too long for the model's memory; try a shorter one"
        raise ModelError(str(detail)[:200])
    content, calls, timings = "", {}, {}
    try:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if chunk.get("timings"):
                timings = chunk["timings"]
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    content += d["content"]
                    if on_text:
                        on_text(d["content"])
                for tc in d.get("tool_calls") or []:
                    e = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        e["id"] = tc["id"]
                    f = tc.get("function") or {}
                    if f.get("name"):
                        e["name"] += f["name"]
                    if f.get("arguments"):
                        e["arguments"] += f["arguments"]
    finally:
        # closing mid-stream (Ctrl+C) makes llama-server stop generating
        c.close()
    return {"content": content, "tool_calls": [calls[i] for i in sorted(calls)], "timings": timings}


def complete_json(system, user, schema, max_tokens=3000):
    r = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
             json_schema=schema, max_tokens=max_tokens, temperature=0.2, think=False)
    return json.loads(r["content"])


def translate_strings(strings, language):
    schema = {"type": "object", "properties": {k: {"type": "string"} for k in strings},
              "required": list(strings)}
    system = ("You translate user-interface text. Keep it short and natural. Keep "
              "placeholders like {name} unchanged. Keep these command words in English: "
              "settings, models, tasks, memory, audit, voice, shell, clear, lock, shutdown.")
    user = (f"Translate every value into {language}. Return JSON with exactly the same keys.\n\n"
            + json.dumps(strings, ensure_ascii=False))
    return complete_json(system, user, schema, max_tokens=6000)
