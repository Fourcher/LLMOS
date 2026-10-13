#!/usr/bin/env python3
"""Host-side test of the quick fact answers in everyday.py (web.search is patched: no network).
Run: python3 tools/test-quick-facts.py"""
import os
import re
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import everyday, web  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Desk:
    def __init__(self):
        self.said = None

    def instant_reply(self, line, text):
        self.said = text


class Settings:
    def __init__(self, internet):
        self.internet = internet

    def get(self, key, default=None):
        return self.internet if key == "internet" else default


EVEREST = [{"title": "Mount Everest - Britannica", "url": "https://www.britannica.com/place/Mount-Everest",
            "snippet": "Mount Everest is 8,849 metres (29,032 feet) tall. It is the highest mountain above sea level. "
                       "Climbers from many countries attempt it every spring."}]
calls = []


def fake_search(results=None, error=None):
    def search(query, n=6):
        calls.append(query)
        if error is not None:
            raise error
        return results
    return search


def ask(q, results=None, error=None, internet="yes"):
    """Run live_lookup on a typed question with web.search patched; returns (answered, reply)."""
    dk = Desk()
    calls.clear()
    with mock.patch.object(web, "search", fake_search(results, error)), \
            mock.patch.object(everyday.config, "settings", Settings(internet)):
        got = everyday.live_lookup(dk, q, q.lower().strip().rstrip("?.!"))
    return got, dk.said


print("positives: the top snippet, one or two sentences, and its source")
got, said = ask("how tall is mount everest", EVEREST)
check(got is True and said == "Mount Everest is 8,849 metres (29,032 feet) tall. It is the highest mountain above sea level. "
                              "(source: britannica.com)", f"how tall is mount everest -> {said!r}")
check(calls == ["how tall is mount everest"], f"the question as typed is the query: {calls}")
for q, res in (("when was the eiffel tower built", [{"title": "Eiffel", "url": "https://en.wikipedia.org/wiki/Eiffel_Tower",
                                                      "snippet": "Built from 1887 to 1889. It was designed by Gustave Eiffel's company."}]),
               ("what is the population of france", [{"title": "France", "url": "https://www.worldometers.info/x",
                                                       "snippet": "France has about 68 million people."}]),
               ("what's the capital of australia", [{"title": "Canberra", "url": "https://www.example.org/c",
                                                      "snippet": "Canberra is the capital city of Australia."}]),
               ("who wrote hamlet", [{"title": "Hamlet", "url": "https://www.poetryfoundation.org/h",
                                      "snippet": "Shakespeare wrote Hamlet around 1600. The play is a tragedy."}]),
               ("how old is the earth", [{"title": "Earth", "url": "https://science.nasa.gov/earth", "snippet": "Earth is about 4.5 billion years old."}])):
    got, said = ask(q, res)
    check(got is True and "(source: " in said and said.endswith(")"), f"{q!r} -> {said!r}")
check(ask("who wrote hamlet", [{"title": "Hamlet", "url": "https://other.example/h", "snippet": "Shakespeare wrote Hamlet around 1600."}])[1]
      == "Shakespeare wrote Hamlet around 1600. (source: other.example)", "a snippet with no source page still gives its domain")
long_snip = [{"title": "x", "url": "https://a.example/", "snippet": "Word " * 200}]
check(len(ask("how tall is the big tower", long_snip)[1].split(" (source:")[0]) <= 303, "a long snippet is trimmed to 300 characters")

print("internet switched off: the same reply as who won")
who_off = ask("who won the cup final", EVEREST, internet="no")[1]
fact_off = ask("how tall is mount everest", EVEREST, internet="no")
check(fact_off[0] is True and fact_off[1] == who_off and calls == [], f"no -> {fact_off[1]!r}, search not called")
got, said = ask("how tall is mount everest", EVEREST, internet="ask")
check(got is True and "switched off" not in said and "(source: britannica.com)" in said, "internet 'ask' answers as who won does")

print("failures: the who-won replies")
who_err = ask("who won the cup final", error=RuntimeError("boom"))[1]
fact_err = ask("how tall is mount everest", error=RuntimeError("boom"))[1]
check(fact_err == who_err == "I couldn't search for the result just now. Try again in a minute.", f"search error -> {fact_err!r}")
who_none = ask("who won the cup final", [])[1]
fact_none = ask("how tall is mount everest", [])[1]
check(fact_none == who_none == "I couldn't find that result.", f"no results -> {fact_none!r}")
check(ask("how tall is mount everest", [{"title": "x", "url": "https://a.example/", "snippet": ""}])[1] == "I couldn't find that result.",
      "an empty snippet is no answer")

print("the words reach the fact branch")
for q in ("how tall is mount everest", "how high is the eiffel tower", "how big is the moon", "how old is the earth",
          "how far is the moon", "how long is the nile", "how deep is the ocean", "how heavy is an elephant", "how fast is a cheetah",
          "when was the eiffel tower built", "when was einstein born", "when was the pyramid founded", "when was the car made",
          "what is the population of france", "what's the capital of australia", "what is the capital of japan",
          "who wrote hamlet", "who painted the mona lisa", "who invented the telephone", "who founded google", "who discovered penicillin"):
    got, said = ask(q, EVEREST)
    check(everyday.MATCH.search(q) is not None and got is True and "(source: " in said, f"{q!r} is instant and answered")

print("questions about the owner, this or that, or a place needing a location are left to the model")
for q in ("how tall am i", "how old is my computer", "how far is it to the station from here", "how big is this file",
          "what is the population of my contacts", "who wrote this email", "how long is the video i'm watching"):
    check(re.fullmatch(everyday._FACT_MATCH, q) is None, f"{q!r} is not a fact question")
    got, said = ask(q, EVEREST)
    check(got is False and calls == [] and said is None, f"{q!r} is not answered by the fact branch")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
