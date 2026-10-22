#!/usr/bin/env python3
"""OpenRouter's free models as the online model (llm.CLOUD_PROVIDERS["openrouter"]): the strongest free model that can call
tools is picked at sign-in, the wording says what free costs (a daily cap; the serving companies may keep what is sent),
and a refusal that escalates online and is refused there too still falls through to a stronger uncensored model here.
Run: python3 tools/test-openrouter-free.py (no network)"""
import os, sys, tempfile
from unittest import mock
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC", tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import agent, config, intent, llm  # noqa: E402

fails = 0


def check(c, w):
    global fails
    print(("  ok   " if c else "  FAIL ") + w)
    if not c:
        fails += 1


LIST = [{"id": "liquid/lfm-2.5-2.6b:free", "name": "LFM (free)", "context_length": 65536, "supported_parameters": ["tools"]},
        {"id": "google/gemma-4-31b-it:free", "name": "Gemma 4 31B (free)", "context_length": 262144, "supported_parameters": ["tools"]},
        {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "name": "NVIDIA: Nemotron 3 Ultra (free)", "context_length": 1000000,
         "supported_parameters": ["tools", "temperature"]},
        {"id": "nvidia/nemotron-3-ultra-550b-a55b", "name": "paid twin", "context_length": 1000000, "supported_parameters": ["tools"]},
        {"id": "some/chat-only:free", "name": "no tools", "context_length": 2000000, "supported_parameters": ["temperature"]}]
check(llm._pick_openrouter_free(LIST) == ("nvidia/nemotron-3-ultra-550b-a55b:free", "NVIDIA: Nemotron 3 Ultra (free)"),
      "the strongest free model that calls tools (not the paid twin, not one without tools)")
check(llm._pick_openrouter_free([m for m in LIST if "nemotron" not in m["id"] and "gemma" not in m["id"]])[0] == "liquid/lfm-2.5-2.6b:free",
      "an unlisted free model with tools is taken when none of the preferred ones are offered")
check(llm._pick_openrouter_free([LIST[-1]]) == ("", ""), "no free model with tools: nothing is picked")

p = llm.CLOUD_PROVIDERS["openrouter"]
check(p["signin"] == "https://openrouter.ai/settings/keys" and p["url"] == "https://openrouter.ai/api/v1", "key page and address")
check("50 requests a day" in p["note"] and "may keep" in p["note"], "says what free costs: a daily cap, and what is sent may be kept")
for q in ("sign in to openrouter", "connect open router", "sign in to OpenRouter (free models)"):
    check(intent.match(q) == ("online_model", {"action": "sign in", "provider": "openrouter"}), f"{q!r} opens its sign-in")

with mock.patch.object(llm, "_get_json", return_value={"data": LIST}), mock.patch.object(llm, "cloud_check", return_value=(True, "ok")):
    ok, note = llm.cloud_setup({"provider": "openrouter", "key": "sk-or-v1-" + "a" * 64})
c = config.cloud() or {}
check(ok and c.get("model") == "nvidia/nemotron-3-ultra-550b-a55b:free" and c.get("label") == "NVIDIA: Nemotron 3 Ultra (free)",
      f"signing in keeps the account with the picked free model, named for people: {note!r}")

# a refusal online falls through to a stronger model here; nothing is asked twice
Ctx = type("C", (), {"headless": False})
config.settings.set("internet", "yes")
config.settings.set("auto_escalate", True)
from llmos import models  # noqa: E402
with mock.patch.object(models, "host_mode", return_value=False), \
        mock.patch.object(models, "active", return_value={"id": "dolphin-3-8b"}), \
        mock.patch.object(models, "installed", return_value=[{"id": "dolphin-3-8b"}, {"id": "huihui-ornith-1.5-9b"}]):
    check(agent._escalation_target(Ctx(), "local") == ("cloud", None), "first: the online model")
    check(agent._escalation_target(Ctx(), "cloud", {"cloud"}) == ("local", "huihui-ornith-1.5-9b"),
          "refused online too: the stronger uncensored model here")
    check(agent._escalation_target(Ctx(), "local", {"cloud", "huihui-ornith-1.5-9b"}) is None, "nothing tried twice")
src = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/agent.py"), encoding="utf-8").read()
check("len(tried) < 2" in src and 'tried.add("cloud")' in src, "a turn escalates at most twice, and a failed online call counts")
if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
