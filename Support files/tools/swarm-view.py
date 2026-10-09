#!/usr/bin/env python3
"""Live view of the LLM OS orchestrator and its workers.

Reads the orchestrator's Claude Code transcript, its workers' transcripts and
docs/tasks/queue.md, and serves a page that refreshes every 2 seconds.

    python3 "Support files/tools/swarm-view.py"        # opens http://localhost:8777
    python3 "Support files/tools/swarm-view.py" --session <id> --port 8777 --no-open
"""
import argparse, glob, json, os, re, subprocess, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORT = os.path.dirname(HERE)
REPO = os.path.dirname(SUPPORT)
PROJ = os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", REPO))
QUEUE = os.path.join(SUPPORT, "docs/tasks/queue.md")
ACTIVE_SECS = 120


def find_session(arg):
    if arg:
        hits = glob.glob(os.path.join(PROJ, arg + "*.jsonl"))
        return hits[0] if hits else None
    best = None
    for f in sorted(glob.glob(os.path.join(PROJ, "*.jsonl")), key=os.path.getmtime, reverse=True):
        with open(f) as fh:
            head = fh.read(200000)
        if '"sessionKind":"bg"' in head and "llmos-orchestrator" in head:
            return f
        best = best or f
    return best


def ts(s):
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except Exception:
        return 0


def short(s, n=400):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


def tool_summary(name, inp):
    if name == "Bash":
        return inp.get("description") or short(inp.get("command", ""), 160), short(inp.get("command", ""), 600)
    if name == "Agent":
        return "Dispatch worker: " + inp.get("description", ""), short(inp.get("prompt", ""), 1500)
    if name in ("Read", "Edit", "Write", "Glob", "Grep"):
        p = inp.get("file_path") or inp.get("pattern") or inp.get("path") or ""
        return f"{name} {os.path.relpath(p, REPO) if p.startswith('/') else p}", ""
    return name, short(json.dumps(inp), 300)


def read_events(path, limit=80):
    """Return (events, meta) from one transcript."""
    events, meta = [], {"model": "", "last": 0, "stop": "", "prompt": "", "tools": 0, "pending": False}
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return events, meta
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t = ts(d.get("timestamp", "")) or meta["last"]
        meta["last"] = max(meta["last"], t)
        typ = d.get("type")
        if typ == "queue-operation" and "task-notification" in str(d.get("content", "")):
            m = re.search(r"<summary>(.*?)</summary>", d["content"])
            events.append({"t": t, "kind": "notify", "title": m.group(1) if m else "worker finished", "body": ""})
            continue
        m = d.get("message")
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if typ == "user":
            if isinstance(c, str):
                if not meta["prompt"]:
                    meta["prompt"] = c
                if "<cross-session-message" in c:
                    events.append({"t": t, "kind": "inbox", "title": "Message from another session", "body": short(re.sub(r"<[^>]+>", "", c), 1200)})
                elif "<task-notification>" in c:
                    mm = re.search(r"<summary>(.*?)</summary>", c)
                    events.append({"t": t, "kind": "notify", "title": mm.group(1) if mm else "worker finished", "body": ""})
                elif len(events) == 0 or not c.startswith("<"):
                    events.append({"t": t, "kind": "user", "title": "Instruction", "body": short(c, 1500)})
            elif isinstance(c, list):
                for b in c:
                    if b.get("type") == "tool_result":
                        meta["pending"] = False
                        out = b.get("content")
                        if isinstance(out, list):
                            out = " ".join(x.get("text", "") for x in out if isinstance(x, dict))
                        events.append({"t": t, "kind": "result", "title": "error" if b.get("is_error") else "result", "body": short(out, 600)})
            continue
        if typ == "assistant":
            meta["model"] = m.get("model") or meta["model"]
            meta["stop"] = m.get("stop_reason") or meta["stop"]
            for b in c or []:
                bt = b.get("type")
                if bt == "text" and b.get("text", "").strip():
                    events.append({"t": t, "kind": "say", "title": "Says", "body": short(b["text"], 1500)})
                elif bt == "tool_use":
                    meta["tools"] += 1
                    meta["pending"] = True
                    title, body = tool_summary(b.get("name", ""), b.get("input", {}))
                    events.append({"t": t, "kind": "agent" if b.get("name") == "Agent" else "tool", "title": title, "body": body, "tool": b.get("name")})
    return events[-limit:], meta


def queue():
    out = []
    try:
        for line in open(QUEUE):
            m = re.match(r"- \[(\w+)\]\s*(.*)", line)
            if m:
                goal = m.group(2).split("|")[0]
                out.append({"status": m.group(1), "goal": short(goal, 260)})
    except OSError:
        pass
    return out


def bg_state(session_id):
    try:
        rows = json.loads(subprocess.run(["claude", "agents", "--json", "--all"], capture_output=True, text=True, timeout=8).stdout)
        for r in rows:
            if r.get("sessionId") == session_id:
                return r.get("status") or r.get("state") or "?"
    except Exception:
        pass
    return "unknown"


_cache = {"t": 0, "bg": "unknown"}


def state(session_path):
    now = time.time()
    sid = os.path.basename(session_path)[:-6]
    if now - _cache["t"] > 10:
        _cache.update(t=now, bg=bg_state(sid))
    ev, meta = read_events(session_path, 120)
    workers = []
    for mf in glob.glob(os.path.join(session_path[:-6], "subagents", "*.meta.json")):
        try:
            mj = json.load(open(mf))
        except ValueError:
            continue
        jf = mf.replace(".meta.json", ".jsonl")
        wev, wm = read_events(jf, 60)
        age = now - wm["last"] if wm["last"] else 1e9
        if wm["stop"] == "end_turn" and not wm["pending"]:
            status = "done"
        elif age < ACTIVE_SECS:
            status = "working"
        else:
            status = "stalled"
        workers.append({
            "id": os.path.basename(jf)[6:-6], "desc": mj.get("description", ""), "branch": mj.get("worktreeBranch", ""),
            "model": wm["model"], "status": status, "last": wm["last"], "start": wev[0]["t"] if wev else wm["last"],
            "tools": wm["tools"], "spec": short(wm["prompt"], 3000), "events": wev,
        })
    workers.sort(key=lambda w: w["start"])
    now_doing = next((e for e in reversed(ev) if e["kind"] in ("tool", "agent", "say")), None)
    return {
        "now": now, "session": sid, "bg": _cache["bg"], "model": meta["model"], "last": meta["last"],
        "pending": meta["pending"], "doing": now_doing, "events": ev, "workers": workers, "queue": queue(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    sp = find_session(a.session)
    if not sp:
        raise SystemExit("no orchestrator transcript found in " + PROJ)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = json.dumps(state(sp)).encode()
                ctype = "application/json"
            else:
                body = open(os.path.join(HERE, "swarm-view.html"), "rb").read()
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = f"http://localhost:{a.port}/"
    print("swarm view:", url, "session", os.path.basename(sp)[:8])
    if not a.no_open:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
