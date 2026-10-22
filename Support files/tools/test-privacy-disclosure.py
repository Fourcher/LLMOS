#!/usr/bin/env python3
"""Host-side test of the privacy disclosure for the "online model for everything" choice. Under brain = "cloud" every
request sends the system prompt, the last 8 messages, tool results, the owner's name and the saved memory facts.
Checks: (1) the q_brain_2 choice text (where it thinks: online for everything) carries the sentence
"Your name and saved memory go with each request." in all six language blocks; (2) the privacy answer in desk.py says
what goes under brain = "cloud" (name and memory included) and keeps today's wording under local and ask.
desk.py needs GTK, so the answer's code is read from its source and run with stub config and llm modules.
Run: python3 tools/test-privacy-disclosure.py"""
import os
import re
import sys
import textwrap
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTFS = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos")
LLMOS_DIR = os.path.join(ROOTFS, "llmos")
DESK = os.path.join(LLMOS_DIR, "desk.py")
sys.path.insert(0, ROOTFS)
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


import llmos.i18n as i18n  # noqa: E402

SENTENCES = {
    "EN": "Your name and saved memory go with each request.",
    "ZH": "你的名字和保存的记忆会随每个请求一起发送。",
    "ES": "Tu nombre y tu memoria guardada se envían con cada petición.",
    "FR": "Votre nom et votre mémoire enregistrée sont envoyés avec chaque demande.",
    "DE": "Dein Name und dein gespeichertes Gedächtnis werden mit jeder Anfrage gesendet.",
    "JA": "名前と保存されたメモリーはリクエストごとに送信されます。",
}
for b, sent in SENTENCES.items():
    block = getattr(i18n, b)
    check(sent in block.get("q_brain_2", ""), f"{b}: q_brain_2 (online for everything) contains the disclosure sentence")

# the privacy answer's brain expression, copied from desk.py and run with stubs
src = open(DESK, encoding="utf-8").read()
start = src.index("            svc_ = llm.cloud_label()")
end = src.index("that company; everything else stays here.\")", start) + len("that company; everything else stays here.\")")
snippet = textwrap.dedent(src[start:end])


def answer(brain, cloud, label="Claude"):
    cfg = types.SimpleNamespace(cloud=lambda: cloud)
    llm = types.SimpleNamespace(cloud_label=lambda c=None: label, cloud_is_home=lambda c=None: False)
    ns = {"config": cfg, "llm": llm, "s_": {"brain": brain} if brain else {}}
    exec(snippet, ns)
    return ns["brain"]


# the phrase the answer tells the owner to say must route to brain = "ask" through the intent matcher (intent.py _BRAIN)
intent_src = open(os.path.join(LLMOS_DIR, "intent.py"), encoding="utf-8").read()
brain_ns = {"re": re}
exec(intent_src[intent_src.index("_ONLINE = "):intent_src.index("_CLOUD_SETUP = re.compile")], brain_ns)
SAY = "ask me before going online"
m = brain_ns["_BRAIN"].match(SAY)
check(m is not None and m.group("ask") is not None and not m.group("local") and not m.group("cloud"),
      f"route: {SAY!r} matches _BRAIN ask group (regex {brain_ns['_BRAIN'].pattern[:60]}...)")
check(SAY in src and "Say “" + SAY + "” to keep things here unless you agree." in src, "answer: quoted phrase is the one the test routes")

OLD = "Requests you send to the online model (Claude/ChatGPT) go to that company; everything else stays here."
LOCAL = "Your requests are answered by the model on this computer."
CLOUD_ACC = {"provider": "anthropic", "model": "x", "key": "k"}

cloud_text = answer("cloud", CLOUD_ACC)
CLOUD_HEAD = ("With the online assistant on, each request goes to Claude with the recent chat, anything I look at to answer it "
              "(files, mail, web pages, the screen), and your name and saved memory. What I don't look at stays here. ")
check(cloud_text.startswith(CLOUD_HEAD), "cloud: answer names the recent chat, anything looked at (files, mail, web, screen), name and saved memory, and the service")
check("mail" in cloud_text and "your name and saved memory" in cloud_text, "cloud: answer says mail goes and name and memory go")
check("Everything else stays here" not in cloud_text and "Requests, the recent chat" not in cloud_text,
      "cloud: old 'Everything else stays here' and 'results from your files or the web' wording is gone")
check("Say “ask me before going online” to keep things here unless you agree." in cloud_text,
      "cloud: answer tells the owner how to keep things here")
chatgpt_text = answer("cloud", {"provider": "openai", "model": "gpt", "key": "k"}, label="ChatGPT")
check(chatgpt_text.startswith("With the online assistant on, each request goes to ChatGPT with the recent chat, ")
      and "Claude" not in chatgpt_text, "cloud with label ChatGPT: answer names ChatGPT, not Claude")
print("  text " + chatgpt_text[:120] + "...")
check(answer("ask", CLOUD_ACC) == OLD, "ask: answer keeps today's wording")
check(answer("local", CLOUD_ACC) == LOCAL, "local: answer keeps today's wording")
check(answer(None, CLOUD_ACC) == LOCAL, "no brain setting: answer keeps today's wording")
check(answer("cloud", None) == LOCAL, "cloud brain with no account set up: answer keeps today's wording")

print("all good" if fails == 0 else f"{fails} FAIL(S)")
sys.exit(1 if fails else 0)
