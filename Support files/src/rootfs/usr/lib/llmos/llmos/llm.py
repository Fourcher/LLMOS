"""Clients for the models that answer requests.

The on-device model: llama.cpp's llama-server on 127.0.0.1 (or, under a VM launcher in host-GPU mode,
the host's server over the VM's private link). Nothing in that path talks to any other machine.

The online model (optional; there is none unless the owner adds an account at set-up or later): Claude
through Anthropic's Messages API, or any service that speaks the OpenAI chat-completions API. It only
answers when the owner's "brain" setting sends a request there (see agent.route_for), every such request
is written to the audit log, and the account's key lives with the owner's data, inside the vault."""
import http.client
import json
import math
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse

from . import config

TOR_PROXY = "127.0.0.1:9050"


class ModelDown(Exception):
    """The model server is unreachable."""


class ModelError(ModelDown):
    """The server answered, but refused or failed the request (e.g. the
    request did not fit in the context window)."""


class CloudError(Exception):
    """The online model could not answer: no account, offline, key refused, service error."""


# ------------------------------------------------------------------ the on-device model

class Cancelled(Exception):
    """The owner pressed Stop while the model was working."""


_OPEN = set()                 # connections to the model in progress (abort() closes them)
_OPEN_LOCK = threading.Lock()


def _conn(timeout=900):
    u = urllib.parse.urlparse(config.llama_url())
    return http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)


def abort():
    """Stop: cut every request to the on-device model now. Reading a long request can take the model a minute
    before its first word; closing the connection makes llama-server drop the work at once."""
    with _OPEN_LOCK:
        conns = list(_OPEN)
    for c in conns:
        c._llmos_aborted = True
        try:
            if c.sock:
                c.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


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


_ctx_cache = [0.0, None]


def context_size():
    """The model server's context window in tokens (from llama-server's /props), or None if it cannot say.
    Checked at most once a minute: switching models restarts the server, possibly with another size."""
    if _ctx_cache[1] is not None and time.time() - _ctx_cache[0] < 60:
        return _ctx_cache[1]
    n = None
    try:
        c = _conn(3)
        c.request("GET", "/props")
        r = c.getresponse()
        d = json.loads(r.read() or b"{}") if r.status == 200 else {}
        c.close()
        n = int((d.get("default_generation_settings") or {}).get("n_ctx") or d.get("n_ctx") or 0) or None
    except (OSError, ValueError):
        n = None
    if n is not None:                 # a failed check is not cached: the server may not be ready yet
        _ctx_cache[:] = [time.time(), n]
    return n


def wait_ready(timeout=600, tick=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if health():
            return True
        if tick:
            tick(time.time() - t0)
        time.sleep(1)
    return False


def _read_stream(lines, on_text):
    """Accumulate an OpenAI-style chat-completions SSE stream (llama-server and every OpenAI-compatible
    service speak it). Returns (content, tool_calls, timings, non_sse_text)."""
    content, calls, timings, other = "", {}, {}, []
    for raw in lines:
        line = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw).strip()
        if not line.startswith("data:"):
            if line and not line.startswith(("event:", ":")) and len(other) < 40:
                other.append(line)          # an error body is plain JSON, not an event stream
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except ValueError:
            continue
        if not isinstance(chunk, dict):
            continue
        if chunk.get("timings"):
            timings = chunk["timings"]
        if chunk.get("error"):
            e = chunk["error"]
            raise ModelError(str(e.get("message", e) if isinstance(e, dict) else e)[:200])
        for ch in chunk.get("choices") or []:
            d = ch.get("delta") or {}
            if d.get("content"):
                content += d["content"]
                if on_text:
                    on_text(d["content"])
            if d.get("tool_calls") and on_text:
                on_text("")                 # (no words to show, but a Stop pressed while a tool call is written is seen at once)
            for tc in d.get("tool_calls") or []:
                e = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    e["id"] = tc["id"]
                f = tc.get("function") or {}
                if f.get("name"):
                    e["name"] += f["name"]
                if f.get("arguments"):
                    e["arguments"] += f["arguments"]
    return content, [calls[i] for i in sorted(calls)], timings, "\n".join(other)


_FWCFG = "/sys/firmware/qemu_fw_cfg/by_name/opt/llmos"


def _testshell():
    """The test VM (fw_cfg opt/llmos/testshell): model sampling is made repeatable there; owners never see this."""
    try:
        with open(os.path.join(_FWCFG, "testshell", "raw")) as f:
            return f.read().strip() not in ("", "0")
    except OSError:
        return False


def _plain(messages):
    """Messages without this OS's private bookkeeping keys (such as the online model's own blocks)."""
    return [{k: v for k, v in m.items() if not str(k).startswith("_")} for m in messages]


def chat(messages, tools=None, on_text=None, max_tokens=1200, temperature=0.3,
         json_schema=None, think=None):
    """Stream one completion from the on-device model. Returns {"content", "tool_calls", "timings"}.
    Tool calls are accumulated from streamed deltas."""
    if think is None:
        think = bool(config.settings.get("think"))
    body = {"messages": _plain(messages), "stream": True, "temperature": temperature,
            "top_p": 0.95, "max_tokens": max_tokens, "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": think}}
    if _testshell():
        body["temperature"] = 0
        body["seed"] = 42
    if tools:
        body["tools"] = tools
    if json_schema:
        body["response_format"] = {"type": "json_object", "schema": json_schema}
    c = _conn()
    with _OPEN_LOCK:
        _OPEN.add(c)
    try:
        return _chat_on(c, body, on_text)
    except (OSError, http.client.HTTPException, ValueError) as e:
        if getattr(c, "_llmos_aborted", False):
            raise Cancelled()
        if isinstance(e, OSError):
            raise ModelDown(str(e))
        raise ModelError(str(e)[:200])
    finally:
        with _OPEN_LOCK:
            _OPEN.discard(c)
        c.close()                     # closing mid-stream (Ctrl+C, Stop) makes llama-server stop generating


def _chat_on(c, body, on_text):
    c.request("POST", "/v1/chat/completions", json.dumps(body),
              {"Content-Type": "application/json"})
    r = c.getresponse()
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
    content, calls, timings, _ = _read_stream(r, on_text)
    return {"content": content, "tool_calls": calls, "timings": timings}


def decide(messages, labels, question=None, prefill="", tools=None, top=20):
    """One-pass decision ("decide, don't write"): the model's probabilities for a fixed set of one-token answers,
    read from a single forward step instead of a generated reply. Given the turn's own messages and tools, the
    prompt cache already holds everything up to the owner's words, so only the question is new, and the reply
    that follows reuses the cache. question is appended to the last user message; prefill starts the answer.
    Returns ({label: probability, renormalised over the labels}, timings), or (None, {}) when it cannot say."""
    msgs = [dict(m) for m in _plain(messages)]
    if question:
        msgs[-1]["content"] = (msgs[-1].get("content") or "") + "\n\n" + question
    if prefill:
        msgs.append({"role": "assistant", "content": prefill})
    body = {"messages": msgs, "max_tokens": 1, "temperature": 0, "cache_prompt": True, "logprobs": True,
            "top_logprobs": top, "chat_template_kwargs": {"enable_thinking": False}}
    if tools:
        body["tools"] = tools
    try:
        c = _conn(120)
        c.request("POST", "/v1/chat/completions", json.dumps(body), {"Content-Type": "application/json"})
        r = c.getresponse()
        raw = r.read()
        c.close()
        if r.status != 200:
            return None, {}
        d = json.loads(raw)
        lp = (d["choices"][0].get("logprobs") or {}).get("content") or []
        tops = (lp[0].get("top_logprobs") or []) if lp else []
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None, {}
    p = {}
    for t in tops:
        tok = str(t.get("token", "")).strip()
        for lab in labels:
            # one-letter labels must match exactly ("a" is a word); word labels ignore case
            if tok == lab or (len(lab) > 1 and tok.lower() == lab.lower()):
                p[lab] = p.get(lab, 0.0) + math.exp(t.get("logprob", -99.0))
    total = sum(p.values())
    if total <= 0:
        return None, d.get("timings") or {}
    return {lab: p.get(lab, 0.0) / total for lab in labels}, d.get("timings") or {}


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


# ------------------------------------------------------------------ the online model

# Online models the owner can point the OS at. Facts (speed, cost, strengths, drawbacks) are shown in the
# model manager next to the on-device ones. Every online model shares the same privacy fact: the request
# leaves this computer and is billed to the owner's account, so that is said once, in the manager.
CLOUD_PROVIDERS = {
    "anthropic": {
        "name": "Claude", "url": "https://api.anthropic.com", "key_hint": "sk-ant-…",
        "console": "platform.claude.com", "signin": "https://platform.claude.com/settings/keys",
        "key_re": r"sk-ant-[A-Za-z0-9_\-]{20,}",
        "models": [{"id": "claude-opus-5-5", "name": "Claude Opus 5.5", "note": "strong and thorough; the usual choice",
                    "speed": "moderate", "cost": "moderate", "good_at": ["hard reasoning, long code and writing", "the everyday online choice"],
                    "limits": ["thinks before answering, so a reply takes a little longer"]},
                   {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "note": "fast and capable; half the price of Opus",
                    "speed": "fast", "cost": "lower", "good_at": ["everyday coding, analysis and writing", "quick replies"],
                    "limits": ["not the strongest for the hardest problems"]},
                   {"id": "claude-fable-5-1", "name": "Claude Fable 5.1", "note": "the most capable",
                    "speed": "slower", "cost": "high", "good_at": ["the most capable model here", "the toughest, longest tasks"],
                    "limits": ["the most expensive; long requests can take minutes"]},
                   {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "note": "fastest and cheapest",
                    "speed": "fastest", "cost": "low", "good_at": ["quick answers", "cheapest per use"], "limits": ["least capable of the four"]}]},
    # OpenAI's API (the models behind ChatGPT). The model is not asked for: after the key, the newest general model
    # the account offers is chosen (_pick_openai_model), since OpenAI's line-up changes often.
    "chatgpt": {"name": "ChatGPT", "url": "https://api.openai.com/v1", "key_hint": "sk-…",
                "console": "platform.openai.com", "signin": "https://platform.openai.com/api-keys",
                "key_re": r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}", "auto_model": True,
                "note": "OpenAI's models through its API (billed by OpenAI, separately from a ChatGPT subscription)",
                "models": []},
    # any service speaking the chat-completions API: Mistral, Groq, OpenRouter, a bigger computer at home…
    "openai": {"name": "Other (OpenAI-compatible)", "url": "https://api.openai.com/v1", "key_hint": "sk-…", "console": "",
               "note": "OpenAI, Mistral, Groq, OpenRouter, or your own server — anything speaking the OpenAI API",
               "models": []},
}


def _get_json(url, headers, timeout=30):
    """GET a JSON document through curl with the headers (the key) in a 0600 file, Tor when that is on.
    Returns the parsed document; raises CloudError with the service's own message on failure."""
    d = tempfile.mkdtemp(prefix="llmos-cloud-")
    cfg = os.path.join(d, "h")
    try:
        with os.fdopen(os.open(cfg, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            for k, v in headers.items():
                f.write('header = "%s: %s"\n' % (k, str(v).replace('"', "").replace("\n", "")))
        cmd = ["curl", "-sS", "--fail-with-body", "--max-time", str(timeout), "--connect-timeout", "20",
               "--proto", "=http,https", "-K", cfg, url]
        if config.settings.get("tor"):
            cmd[1:1] = ["--socks5-hostname", TOR_PROXY]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    except (OSError, subprocess.SubprocessError) as e:
        raise CloudError(f"couldn't reach the service: {e}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    try:
        doc = json.loads(r.stdout or b"{}")
    except ValueError:
        doc = {}
    if r.returncode != 0:
        msg = (doc.get("error") or {}).get("message") if isinstance(doc.get("error"), dict) else doc.get("error")
        raise CloudError(msg or r.stderr.decode("utf-8", "replace").strip() or "the service refused the request")
    return doc


def _pick_openai_model(ids):
    """The newest general chat model in an OpenAI account's list: gpt-<version>, not a mini/nano or a special-purpose
    variant (audio, realtime, search, image, codex, pro…), the base name before a dated snapshot. ("pro" models are
    answered only through another API than the one used here.)"""
    skip = ("audio", "realtime", "search", "transcribe", "tts", "image", "codex", "instruct", "embedding",
            "moderation", "preview", "chat-latest", "mini", "nano", "oss", "-pro", "deep-research")
    best = None
    for mid in ids:
        m = re.match(r"^gpt-(\d+(?:\.\d+)?)(.*)$", mid)
        if not m or any(x in mid for x in skip):
            continue
        dated = bool(re.search(r"-\d{4}-\d{2}-\d{2}$", m.group(2)))
        rank = (float(m.group(1)), not dated, -len(mid))
        if best is None or rank > best[0]:
            best = (rank, mid)
    return best[1] if best else ""


def cloud_models(provider=None):
    """The known models for a provider (the active one by default), each with its facts."""
    p = CLOUD_PROVIDERS.get(provider or (config.cloud() or {}).get("provider") or "anthropic", {})
    return p.get("models", [])


def switch_cloud_model(mid):
    """Point the existing online account at another of its provider's models (keeps the key). (ok, note)."""
    c = config.cloud()
    if not c:
        return False, "no online model is set up yet"
    mid = str(mid or "").strip()
    known = {m["id"]: m for m in cloud_models(c.get("provider"))}
    pick = known.get(mid)
    if not pick:
        low = mid.lower().replace("-", " ")
        hits = [m for m in cloud_models(c.get("provider")) if low and (low in m["id"].replace("-", " ") or low in m["name"].lower())]
        pick = hits[0] if len(hits) == 1 else None
    if not pick and CLOUD_PROVIDERS.get(c.get("provider"), {}).get("models"):
        return False, f"'{mid}' is not one of {cloud_label(c)}'s models; say the model name shown in the list"
    model_id = pick["id"] if pick else mid       # a custom OpenAI-compatible service: accept any name
    c = dict(c, model=model_id)
    config.save_cloud(c)
    return True, f"the online model is now {cloud_label(c)}"


def cloud_label(c=None):
    """The online model's display name ('Claude Sonnet 5'), or '' when none is set up."""
    c = c or config.cloud()
    if not c:
        return ""
    prov = CLOUD_PROVIDERS.get(c.get("provider"), {})
    for m in prov.get("models", []):
        if m["id"] == c.get("model"):
            return m["name"]
    return c.get("model") or prov.get("name") or "online model"


class _Stream:
    """A streaming HTTP(S) POST through curl: TLS with the system CAs, Tor when that is on, and the key in a
    0600 file (never on the command line). Iterating yields the response's lines as they arrive."""

    def __init__(self, url, headers, body, timeout=300):
        self.dir = tempfile.mkdtemp(prefix="llmos-cloud-")
        cfg, dat = os.path.join(self.dir, "h"), os.path.join(self.dir, "b")
        with os.fdopen(os.open(cfg, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            for k, v in headers.items():
                f.write('header = "%s: %s"\n' % (k, str(v).replace('"', "").replace("\n", "")))
        with os.fdopen(os.open(dat, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(json.dumps(body).encode())
        cmd = ["curl", "-sS", "-N", "--fail-with-body", "--max-time", str(timeout), "--connect-timeout", "20",
               "--proto", "=http,https", "-K", cfg, "-H", "Content-Type: application/json",
               "-H", "Accept: text/event-stream", "--data-binary", "@" + dat, url]
        if config.settings.get("tor"):
            cmd[1:1] = ["--socks5-hostname", TOR_PROXY]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.done = None

    def __iter__(self):
        return iter(self.p.stdout)

    def finish(self):
        """(exit code, stderr); stops curl if it is still running, removes the key file."""
        if self.done is None:
            try:
                self.p.stdout.close()
            except OSError:
                pass
            try:
                rc = self.p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.p.kill()
                rc = self.p.wait()
            err = self.p.stderr.read().decode("utf-8", "replace")
            self.p.stderr.close()
            shutil.rmtree(self.dir, ignore_errors=True)
            self.done = (rc, err)
        return self.done


_CURL = {6: "the service's address could not be resolved (is the internet reachable?)", 7: "could not connect to the service",
         28: "the service took too long to answer", 35: "the secure connection could not be made",
         60: "the service's certificate could not be verified"}


def _explain(rc, err, body):
    msg = ""
    try:
        j = json.loads(body)
        e = j.get("error") if isinstance(j, dict) else None
        msg = str((e.get("message") if isinstance(e, dict) else e) or "")
    except ValueError:
        pass
    if not msg and rc == 22:
        msg = "the service refused the request" + (f" ({err.strip()})" if err.strip() else "")
    if not msg:
        msg = _CURL.get(rc) or err.strip() or f"curl exit {rc}"
    return msg[:200]


def _anthropic_messages(messages):
    """OpenAI-style history -> (system text, Anthropic messages). Tool results become tool_result blocks in a
    user turn, tool calls become tool_use blocks, consecutive same-role turns are merged, the first turn is
    always the user's and empty text blocks are dropped (the API rejects all of those)."""
    system, out = [], []

    def add(role, block):
        if out and out[-1]["role"] == role:
            out[-1]["content"].append(block)
        else:
            out.append({"role": role, "content": [block]})

    for m in messages:
        role, content = m.get("role"), m.get("content")
        if role == "system":
            if content:
                system.append(str(content))
        elif role == "tool":
            add("user", {"type": "tool_result", "tool_use_id": str(m.get("tool_call_id") or "call"), "content": str(content or "")})
        elif role == "assistant" and m.get("_anthropic"):
            # Claude's own blocks for this turn, sent back unchanged: current models think before answering, and
            # a tool-use turn replayed without its thinking blocks (or with them edited) is rejected
            for b in m["_anthropic"]:
                add("assistant", b)
        elif role == "assistant":
            text = str(content or "").strip()
            blocks = [{"type": "text", "text": text}] if text else []
            for tc in m.get("tool_calls") or []:
                f = tc.get("function") or {}
                try:
                    inp = json.loads(f.get("arguments") or "{}")
                except ValueError:
                    inp = {"input": f.get("arguments")}
                if not isinstance(inp, dict):
                    inp = {"value": inp}
                blocks.append({"type": "tool_use", "id": str(tc.get("id") or "call"), "name": str(f.get("name") or "unknown"), "input": inp})
            for b in blocks:
                add("assistant", b)
        else:
            text = str(content or "")
            if text.strip():
                add("user", {"type": "text", "text": text})
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"type": "text", "text": "(the conversation continues)"}]})
    return "\n\n".join(system), out


def _anthropic(c, messages, tools, on_text, max_tokens, temperature):
    # Current Claude models think before they answer (thinking is on by default and counts toward max_tokens) and
    # reject sampling settings (temperature/top_p/top_k), so none is sent and real requests get room to think.
    system, msgs = _anthropic_messages(messages)
    body = {"model": c["model"], "max_tokens": max_tokens if max_tokens < 256 else max(max_tokens, 16000),
            "messages": msgs, "stream": True}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                          "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}} for t in tools]
    url = (c.get("url") or CLOUD_PROVIDERS["anthropic"]["url"]).rstrip("/")
    if not url.endswith("/v1/messages"):
        url += "/v1/messages"
    s = _Stream(url, {"x-api-key": c["key"], "anthropic-version": "2023-06-01"}, body)
    content, calls, other, blocks, refused = "", {}, [], {}, False
    try:
        for raw in s:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                if line and not line.startswith(("event:", ":")) and len(other) < 40:
                    other.append(line)
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            typ = ev.get("type")
            if typ == "content_block_start":
                blk = dict(ev.get("content_block") or {})
                i = ev.get("index", 0)
                if blk.get("type") == "tool_use":
                    calls[i] = {"id": str(blk.get("id") or ""), "name": str(blk.get("name") or ""), "arguments": ""}
                blocks[i] = blk
            elif typ == "content_block_delta":
                d = ev.get("delta") or {}
                i = ev.get("index", 0)
                b = blocks.get(i)
                if d.get("type") == "text_delta" and d.get("text"):
                    content += d["text"]
                    if b is not None:
                        b["text"] = b.get("text", "") + d["text"]
                    if on_text:
                        on_text(d["text"])
                elif d.get("type") == "input_json_delta":
                    e = calls.get(i)
                    if e is not None:
                        e["arguments"] += d.get("partial_json", "")
                elif d.get("type") == "thinking_delta" and b is not None:
                    b["thinking"] = b.get("thinking", "") + d.get("thinking", "")
                elif d.get("type") == "signature_delta" and b is not None:
                    b["signature"] = b.get("signature", "") + d.get("signature", "")
            elif typ == "message_delta":
                if (ev.get("delta") or {}).get("stop_reason") == "refusal":
                    refused = True
            elif typ == "error":
                raise CloudError(str((ev.get("error") or {}).get("message") or ev)[:200])
    finally:
        rc, err = s.finish()
    if rc != 0 and not content and not calls:
        raise CloudError(_explain(rc, err, "\n".join(other)))
    if refused:
        # the service's own safety check declined: the request is answered on this computer instead
        raise CloudError("the online model declined this request")
    out, raw = [], []
    for i in sorted(calls):
        e = calls[i]
        e["arguments"] = e["arguments"].strip() or "{}"
        out.append(e)
    for i in sorted(blocks):
        b = blocks[i]
        if b.get("type") == "tool_use":
            try:
                b["input"] = json.loads(calls[i]["arguments"])
            except (ValueError, KeyError):
                b["input"] = {}
        if b.get("type") == "text" and not b.get("text"):
            continue                          # the API rejects empty text blocks
        raw.append(b)
    return {"content": content, "tool_calls": out, "timings": {}, "raw": raw}


def _openai(c, messages, tools, on_text, max_tokens, temperature):
    url = (c.get("url") or CLOUD_PROVIDERS["openai"]["url"]).rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    official = urllib.parse.urlparse(url).hostname == "api.openai.com"
    body = {"model": c["model"], "messages": _plain(messages), "stream": True}
    body["max_completion_tokens" if official else "max_tokens"] = max_tokens   # OpenAI's newer models reject the old name
    if not official:
        body["temperature"] = temperature
    if tools:
        body["tools"] = tools
    s = _Stream(url, {"Authorization": "Bearer " + c["key"]}, body)
    try:
        content, calls, _, other = _read_stream(s, on_text)
    except ModelError as e:
        s.finish()
        raise CloudError(str(e))
    finally:
        rc, err = s.finish()
    if rc != 0 and not content and not calls:
        raise CloudError(_explain(rc, err, other))
    for e in calls:
        e["arguments"] = e["arguments"].strip() or "{}"
    return {"content": content, "tool_calls": calls, "timings": {}}


def cloud_chat(messages, tools=None, on_text=None, max_tokens=1200, temperature=0.3, account=None):
    """One completion from the online model, streamed. Same return shape as chat()."""
    c = account or config.cloud()
    if not c:
        raise CloudError("no online model is set up")
    if (c.get("provider") or "anthropic") == "anthropic":
        return _anthropic(c, messages, tools, on_text, max_tokens, temperature)
    return _openai(c, messages, tools, on_text, max_tokens, temperature)


def cloud_check(c):
    """Try an account with the smallest possible request. (ok, note)"""
    try:
        r = cloud_chat([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=8, temperature=0, account=c)
        return True, (r["content"] or "").strip()[:40]
    except CloudError as e:
        return False, str(e)


def cloud_setup(fields, adopt=True):
    """Keep an online-model account after checking it with one tiny request. fields: provider, model, url,
    key. With adopt, a brain setting of 'local' becomes 'ask' (adding an account means wanting to use it).
    Returns (ok, note)."""
    pname = str(fields.get("provider") or "").strip().lower()
    pid = next((k for k, p in CLOUD_PROVIDERS.items() if pname in (k, p["name"].lower())), None)
    if pid is None:
        pid = "anthropic" if (not pname or "claude" in pname or "anthropic" in pname) else "openai"
    prov = CLOUD_PROVIDERS[pid]
    c = {"provider": pid, "url": str(fields.get("url") or "").strip() or prov["url"],
         "model": str(fields.get("model") or "").strip() or (prov["models"][0]["id"] if prov["models"] else ""),
         "key": str(fields.get("key") or "").strip()}
    if not c["key"]:
        return False, "no API key was given"
    if not c["model"] and prov.get("auto_model"):
        try:
            doc = _get_json(c["url"].rstrip("/") + "/models", {"Authorization": "Bearer " + c["key"]})
        except CloudError as e:
            return False, f"the account did not work: {e}"
        c["model"] = _pick_openai_model([str(m.get("id", "")) for m in doc.get("data", []) if isinstance(m, dict)])
        if not c["model"]:
            return False, "the account offers no chat model this can use"
    if not c["model"]:
        return False, "no model name was given"
    if not re.match(r"^https?://[^\s/]+", c["url"]):
        return False, "the service address must start with http:// or https://"
    ok, note = cloud_check(c)
    if not ok:
        return False, f"the account did not work: {note}"
    config.save_cloud(c)
    note = f"{cloud_label(c)} is set up as the online model"
    if adopt and config.settings.get("brain", "local") == "local":
        config.settings.set("brain", "ask")
        note += "; from now on you are asked before a big request goes to it"
    return True, note
