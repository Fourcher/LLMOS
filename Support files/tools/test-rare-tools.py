#!/usr/bin/env python3
"""Host-side test: agent.tool_schemas(request) leaves the 'rare' tools (security, network, wifi, drive format,
passphrase, program analysis) out of the list unless the request is about them or one was already used this turn,
and appends them at the END so the rest of the list keeps today's order. request_text None gives today's full list.
Run: python3 "Support files/tools/test-rare-tools.py"  (no VM needed). Exit status 0 = pass."""
import os
import sys
import tempfile
from unittest.mock import patch

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"),
                  LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import llm, tools, agent  # noqa: E402


def check(cond, what):
    if not cond:
        print(f"FAIL {what}")
        sys.exit(1)
    print(f"ok   {what}")


def names(lst):
    return [s["function"]["name"] for s in lst]


def rare(n):
    return agent._is_rare(n)


BIG = 12000          # a context at or above 12k: no budget
SMALL = 6144         # a 6k context: budgeted list
with patch.object(tools, "_has_wifi", return_value=True), \
     patch.object(tools, "_connectors_synced", True), \
     patch.object(llm, "context_size", return_value=BIG):
    full = names(tools.schemas(compact=True))            # today's list, all tools in PRIORITY order
    check(any(rare(n) for n in full) and any(n.startswith("wifi_") for n in full),
          f"full list has the rare group ({sum(rare(n) for n in full)} tools)")

    # None -> full list, identical to today
    check(names(agent.tool_schemas()) == full, "tool_schemas() with no request is today's full list, same order")
    check(names(agent.tool_schemas(None, sticky=True)) == full, "no request + sticky is still the full list")

    # 10 requests: rare group included or excluded as expected
    cases = [
        ("scan my network for devices", True),
        ("what's the weather", False),
        ("format this document nicely", False),         # 'format' only with a drive/disk/usb/stick/card/sd
        ("write a report", False),                      # 'port' only as a whole word
        ("contact support", False),
        ("this is important", False),
        ("scan my ports", True),
        ("format the usb stick", True),
        ("format my sd card", True),
        ("is my wifi secure", True),
        ("open the calculator", False),
        ("write a note to buy milk", False),
        ("install llm os on this system", True),
        ("encrypt my vault with a passphrase", True),
        ("play some music", False),
        ("what is the capital of France", False),
        # 1.7.1: natural wordings that used to miss the rare group
        ("is my computer safe", True),
        ("connect to my phone's hotspot", True),
        ("what does this program do", True),
        ("erase the sd card", True),
        ("is my network secure", True),
        ("are my files protected", True),
        ("how do I stop a hacker", True),
        ("is there spyware on my laptop", True),
        ("tether my phone", True),
        ("list open ports", True),
        ("who's on my wifi", True),
        ("devices on my network", True),
        ("make my files private", False),
    ]
    for req, want in cases:
        got = names(agent.tool_schemas(req))
        has = any(rare(n) for n in got)
        check(has == want, f"{req!r}: rare group {'included' if has else 'excluded'} (want {'included' if want else 'excluded'})")

    # order: the non-rare part is exactly today's order minus the rare group; rare tools come last
    for req in ["what's the weather", "scan my network for devices"]:
        got = names(agent.tool_schemas(req))
        plain = [n for n in got if not rare(n)]
        check(plain == [n for n in full if not rare(n)], f"{req!r}: non-rare part identical to today's order")
        check(got[:len(plain)] == plain, f"{req!r}: rare tools only after all the others")

    # sticky: a rare tool already used this turn keeps the group for a non-matching request
    got = names(agent.tool_schemas("what's the weather", sticky=True))
    check(any(rare(n) for n in got), "sticky + non-matching request: rare group kept")
    check(names(agent.tool_schemas("what's the weather", sticky=True)) ==
          [n for n in full if not rare(n)] + [n for n in full if rare(n)],
          "sticky keeps the exact order: non-rare as today, then the rare group in today's order")

    # token savings for a non-matching request (chars/3.6, as tools.schemas budgets it)
    import json
    sch = {s["function"]["name"]: s for s in tools.schemas(compact=True)}
    saved = sum(len(json.dumps(sch[n])) for n in full if rare(n)) / 3.6
    first_rare = next(i for i, n in enumerate(full) if rare(n))
    reprefill = sum(len(json.dumps(sch[n])) for n in full[first_rare:] if not rare(n)) / 3.6
    print(f"     rare group saves about {saved:.0f} tokens on a non-matching request")
    print(f"     non-rare tools after the first rare one ({full[first_rare]}) re-prefill once: about {reprefill:.0f} tokens")

# warm-up sends the same tool list, in the same order, as a normal non-rare turn (byte-for-byte JSON)
import json
with patch.object(tools, "_has_wifi", return_value=True), \
     patch.object(tools, "_connectors_synced", True), \
     patch.object(llm, "context_size", return_value=BIG), \
     patch.object(llm, "chat") as chat_mock, \
     patch.object(agent.time, "sleep", return_value=None):
    agent.warm_up()
    check(chat_mock.call_count == 1, "warm-up sent one request")
    warm_tools = chat_mock.call_args.kwargs["tools"]
    normal = agent.tool_schemas("what's the weather")
    check(json.dumps(warm_tools) == json.dumps(normal),
          f"warm-up tool list == non-rare turn's list, byte-for-byte ({len(normal)} tools)")
    check(not any(rare(n) for n in names(warm_tools)), "warm-up tool list has no rare tool")

# small context: budget kept, rare group only from what fits the budget
with patch.object(tools, "_has_wifi", return_value=True), \
     patch.object(tools, "_connectors_synced", True), \
     patch.object(llm, "context_size", return_value=SMALL):
    budget_full = names(tools.schemas(compact=True, budget=max(1500, SMALL - 3400)))
    plain_small = agent.tool_schemas("what's the weather")
    check(names(plain_small) == [n for n in budget_full if not rare(n)],
          "6k context: budgeted list minus the rare group, same order")
    check(not any(rare(n) for n in names(plain_small)), "6k context: no rare tool for a non-matching request")

print("all good")
