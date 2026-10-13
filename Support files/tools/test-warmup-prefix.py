#!/usr/bin/env python3
"""Host-side test: the model warm-up sends exactly the prefix the first real turn sends (same tool list, same
order, same thinking flag), llm.context_size() keeps a failed (None) check only 5 s and a number 60 s, and
warm-up's retries are bounded (10 tries, 15 s).
Run: python3 "Support files/tools/test-warmup-prefix.py"  (no VM needed). Exit status 0 = pass."""
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"),
                  LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import llm, config, agent  # noqa: E402


def check(cond, what):
    if not cond:
        print(f"FAIL {what}")
        sys.exit(1)
    print(f"ok   {what}")


class Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self):
        return self._body


class FakeConn:
    """Stands in for the model server connection: /props answers from a script, everything else is unused."""
    props_script = []
    props_fetches = 0

    def request(self, method, path, *a, **k):
        self.path = path

    def getresponse(self):
        import json
        if self.path == "/props":
            FakeConn.props_fetches += 1
            n = FakeConn.props_script.pop(0) if FakeConn.props_script else None
            if n is None:
                return Resp(503, b"")
            return Resp(200, json.dumps({"default_generation_settings": {"n_ctx": n}}).encode())
        return Resp(404, b"")

    def close(self):
        pass


clock = [1000.0]                 # fake time, so the timing checks run instantly


class SlowConn(FakeConn):
    """A hung /props: every fetch takes 3 s and gets no answer."""
    def getresponse(self):
        FakeConn.props_fetches += 1
        clock[0] += 3
        return Resp(503, b"")


def fake_sleep(s):
    clock[0] += s


sent = []


def fake_chat_on(c, body, on_text):
    sent.append(body)
    return {"content": "", "tool_calls": [], "timings": {}}


def reset_ctx(script):
    llm._ctx_cache[:] = [0.0, None]
    FakeConn.props_script = list(script)
    FakeConn.props_fetches = 0


# 1. context_size: a None result is kept 5 s, a number 60 s; each fetch is one /props request
with patch.object(llm, "_conn", side_effect=lambda timeout=900: FakeConn()), \
     patch("time.time", side_effect=lambda: clock[0]):
    reset_ctx([None, 6144, 7168])
    a = llm.context_size()
    clock[0] += 2
    b = llm.context_size()
    check(a is None and b is None and FakeConn.props_fetches == 1,
          f"two None results within 5 s cause one fetch (fetches={FakeConn.props_fetches})")
    clock[0] += 4                      # 6 s after the failed check: the 5 s window is over
    c = llm.context_size()
    check(c == 6144 and FakeConn.props_fetches == 2,
          f"after the 5 s window a new fetch happens (value={c}, fetches={FakeConn.props_fetches})")
    clock[0] += 59
    d = llm.context_size()
    check(d == 6144 and FakeConn.props_fetches == 2,
          f"a real number is cached for 60 s (value={d}, fetches={FakeConn.props_fetches})")
    clock[0] += 2                      # 61 s after the number was fetched
    e = llm.context_size()
    check(e == 7168 and FakeConn.props_fetches == 3,
          f"a number is fetched again after 60 s (value={e}, fetches={FakeConn.props_fetches})")
    reset_ctx([None, 6144])
    llm.context_size()
    f = llm.context_size(fresh=True)
    check(f == 6144 and FakeConn.props_fetches == 2,
          f"fresh=True skips the None cache (value={f}, fetches={FakeConn.props_fetches})")

# 2. warm-up body matches the first real turn
config.settings.set("think", True)
ctx = SimpleNamespace()
with patch.object(llm, "_conn", side_effect=lambda timeout=900: FakeConn()), \
     patch.object(llm, "_chat_on", side_effect=fake_chat_on), \
     patch.object(llm, "_testshell", return_value=False), \
     patch.object(agent.time, "sleep", return_value=None):
    reset_ctx([None, None, 6144])
    sent.clear()
    agent.warm_up()
    check(len(sent) == 1, "warm-up sent one request")
    check(FakeConn.props_fetches == 3,
          f"warm-up looks up the context size fresh on each try (fetches={FakeConn.props_fetches})")
    warm = sent[0]

    reset_ctx([6144])
    turn_msgs = agent.build_messages(ctx, "hi", [], private=False)
    turn_tools = agent.tool_schemas("")
    turn = {"messages": turn_msgs, "tools": turn_tools,
            "think": bool(config.settings.get("think"))}

warm_names = [t["function"]["name"] for t in warm.get("tools", [])]
turn_names = [t["function"]["name"] for t in turn["tools"]]
check(warm_names == turn_names and len(turn_names) > 0,
      f"warm-up tools equal the turn's tools, same order ({len(turn_names)} tools)")
check(warm["messages"][0] == turn["messages"][0],
      "warm-up system prompt equals the turn's system prompt")
warm_think = warm["chat_template_kwargs"]["enable_thinking"]
check(warm_think is True and warm_think == turn["think"],
      f"thinking flag matches the setting (warm-up={warm_think}, turn={turn['think']})")

# 3. context_size raising is treated as None: warm-up still sends
sent.clear()
with patch.object(llm, "context_size", side_effect=RuntimeError("boom")), \
     patch.object(llm, "_chat_on", side_effect=fake_chat_on), \
     patch.object(llm, "_testshell", return_value=False), \
     patch.object(agent.time, "sleep", return_value=None):
    agent.warm_up()
check(len(sent) == 1, "warm-up still runs when context_size raises")

# 4. warm-up returns within 15 s when every /props fetch hangs for 3 s
clock[0] = 1000.0
sent.clear()
with patch.object(llm, "_conn", side_effect=lambda timeout=900: SlowConn()), \
     patch.object(llm, "_chat_on", side_effect=fake_chat_on), \
     patch("time.time", side_effect=lambda: clock[0]), \
     patch("time.sleep", side_effect=fake_sleep):
    reset_ctx([])
    t0 = clock[0]
    agent.warm_up()
    elapsed = clock[0] - t0
    check(elapsed <= 15 and FakeConn.props_fetches < 10 and len(sent) == 1,
          f"warm-up returns within 15 s with hung fetches (elapsed={elapsed:.0f} s, fetches={FakeConn.props_fetches})")

print("all good")
sys.exit(0)
