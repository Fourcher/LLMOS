#!/usr/bin/env python3
"""The Abliteration preset (llm.CLOUD_PROVIDERS["abliteration"]): uncensored online models as a named choice, so adding
one is "sign in to Abliteration" and a pasted key, not a typed URL and model name. And the "home" provider (a computer
of the owner's, set up by tools/brain.py) stays out of the lists a person picks from. Run: python3 tools/test-abliteration-preset.py"""
import os, re, sys, tempfile
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC", tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import intent, llm  # noqa: E402

fails = 0


def check(c, w):
    global fails
    print(("  ok   " if c else "  FAIL ") + w)
    if not c:
        fails += 1


p = llm.CLOUD_PROVIDERS.get("abliteration") or {}
check(p.get("url") == "https://api.abliteration.ai/v1", "OpenAI-compatible address")
check(p.get("signin", "").startswith("https://abliteration.ai/"), "a key page to sign in on (nothing to type)")
check(bool(re.fullmatch(p.get("key_re", "x"), "ak_" + "A1b2_-" * 6)) and not re.fullmatch(p.get("key_re", "x"), "sk-ant-abc"),
      "its keys (ak_…) are recognised when pasted, others' are not")
check([m["id"] for m in p.get("models", [])][:1] == ["abliterated-model-large-v2"], "the frontier GLM-5.3 model is the default")
check("billed" in p.get("note", ""), "says it is paid after the free try")
for q in ("sign in to abliteration", "connect abliteration", "use my abliteration account",
          "sign in to Abliteration (uncensored)"):              # the connect panel's button says the name in full
    check(intent.match(q) == ("online_model", {"action": "sign in", "provider": "abliteration"}), f"{q!r} opens its sign-in")
check(intent.match("sign in to claude")[1]["provider"] == "claude" and intent.match("log in to chatgpt")[1]["provider"] == "chatgpt",
      "Claude and ChatGPT sign-ins unchanged")
check(llm.CLOUD_PROVIDERS["home"].get("hidden") is True, "the home computer is not a manual choice")
dsk = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py"), encoding="utf-8").read()
check(dsk.count('if not p.get("hidden")') >= 2, "the provider form and the set-up list leave hidden providers out")
if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
