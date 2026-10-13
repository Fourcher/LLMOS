#!/usr/bin/env python3
"""Host-side test of the internet gate in everyday.py (web.fetch and web.search are patched and record every call: no
network). Each network-using answer runs under: "yes", "ask" with the owner saying yes, "ask" with the owner saying no,
and "no". Run: python3 tools/test-everyday-net.py"""
import json
import os
import re
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import everyday, web  # noqa: E402

fails = 0
DECLINED = "Okay, no internet for that."
OFF_FORECAST = "The internet is switched off in settings, so I can't get the forecast."


def same(a, b):
    """Replies equal, but for the one timing in the network check ("answered in N ms")."""
    return re.sub(r"\(answered in \d+ ms\)", "", str(a)) == re.sub(r"\(answered in \d+ ms\)", "", str(b))


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Settings:
    def __init__(self, internet):
        self.internet = internet

    def get(self, key, default=None):
        return self.internet if key == "internet" else default


class Ctx:
    """The desk's context: confirm_network is the owner's answer to "may this use the internet?"."""
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def confirm_network(self, name, args):
        self.asked.append((name, args))
        return self.answer


class Desk:
    def __init__(self, answer=True, ctx=True):
        self.said = None
        self.windows = []
        if ctx:
            self.ctx = Ctx(answer)

    def instant_reply(self, line, text):
        self.said = text

    def open_window(self, spec):
        self.windows.append(spec)


FORECAST = {"current": {"temperature_2m": 65.4, "weather_code": 0},
            "daily": {"time": ["2026-10-12", "2026-10-13"], "weather_code": [0, 61],
                      "temperature_2m_max": [70.2, 58.0], "temperature_2m_min": [45.1, 40.0],
                      "precipitation_probability_max": [10, 80]}}
GEO = {"results": [{"name": "Denver", "latitude": 39.7, "longitude": -104.9, "country_code": "US", "admin1": "Colorado"}]}
STATUS = {"status": {"indicator": "none", "description": "All Systems Operational"}}
WIKT = {"en": [{"partOfSpeech": "Noun", "definitions": [{"definition": "<b>the state of being happy</b>"}]}]}
DATAMUSE = [{"word": "glad"}, {"word": "merry"}]
RSS = ("<rss><channel><item><title>Storm hits coast - Example News</title><source>Example News</source>"
       "<link>https://news.example/1</link></item></channel></rss>")
RESULTS = [{"title": "Mount Everest - Britannica", "url": "https://www.britannica.com/place/Mount-Everest",
            "snippet": "Mount Everest is 8,849 metres tall. Climbers attempt it every spring. The library opens 9am to 5pm."}]


def body_for(url):
    if "geocoding-api" in url:
        return json.dumps(GEO)
    if "api.open-meteo.com" in url:
        return json.dumps(FORECAST)
    if "status.json" in url:
        return json.dumps(STATUS)
    if "wiktionary" in url:
        return json.dumps(WIKT)
    if "datamuse" in url:
        return json.dumps(DATAMUSE)
    if "news.google" in url:
        return RSS
    return ""                                   # generate_204 and anything else: an empty answer


fetches, searches = [], []


def fake_fetch(url, max_bytes=0, timeout=0, **kw):
    fetches.append(url)
    return (200, {}, b"", body_for(url))


def fake_search(query, n=6):
    searches.append(query)
    return RESULTS


# (name, what the answer does, how many web calls it makes when allowed, the reply under "no")
CASES = [
    ("weather", lambda dk: everyday.weather(dk, "what's the weather in denver", "what's the weather in denver"), 2, OFF_FORECAST),
    ("net_and_dates", lambda dk: everyday.net_and_dates(dk, "am i online", "am i online"), 1,
     "The internet is switched off in settings (say “turn the internet on”)."),
    ("service_status", lambda dk: everyday.service_status(dk, "is github down", "is github down"), 1, OFF_FORECAST),
    ("who won", lambda dk: everyday.live_lookup(dk, "who won the cup final", "who won the cup final"), 1,
     "The internet is switched off in settings, so I can't look up results."),
    ("fact", lambda dk: everyday.live_lookup(dk, "how tall is mount everest", "how tall is mount everest"), 1,
     "The internet is switched off in settings, so I can't look up results."),
    ("status", lambda dk: everyday.live_lookup(dk, "is acme widgets down", "is acme widgets down"), 1,
     "The internet is switched off in settings, so I can't check that."),
    ("hours", lambda dk: everyday.live_lookup(dk, "what time does the library open", "what time does the library open"), 1,
     "The internet is switched off in settings, so I can't check that."),
    ("news", lambda dk: everyday.news(dk, "what's the news", "what's the news"), 1,
     "The internet is switched off in settings, so I can't get the news."),
    ("dictionary", lambda dk: everyday.quick(dk, "define serendipity", "define serendipity"), 1, OFF_FORECAST),
    ("synonyms", lambda dk: everyday.quick(dk, "synonyms for happy", "synonyms for happy"), 1, OFF_FORECAST),
]


def run(runner, internet, answer=True, ctx=True):
    """Runs one answer with the setting and the owner's answer; returns (reply, web calls, questions asked)."""
    dk = Desk(answer=answer, ctx=ctx)
    fetches.clear()
    searches.clear()
    with mock.patch.object(web, "fetch", fake_fetch), mock.patch.object(web, "search", fake_search), \
            mock.patch.object(everyday.config, "settings", Settings(internet)):
        got = runner(dk)
    asked = dk.ctx.asked if ctx else []
    return got, dk.said, len(fetches) + len(searches), asked


for name, runner, allowed_calls, off in CASES:
    print(name)
    got_y, said_y, calls_y, asked_y = run(runner, "yes")
    check(got_y is True and calls_y == allowed_calls and asked_y == [] and said_y not in (DECLINED, off),
          f"yes: answered with {calls_y} web call(s), nothing asked: {said_y!r}")

    got_ay, said_ay, calls_ay, asked_ay = run(runner, "ask", answer=True)
    check(got_ay is True and calls_ay == allowed_calls and asked_ay and same(said_ay, said_y),
          f"ask, owner says yes: same answer, {calls_ay} web call(s), asked {len(asked_ay)} time(s)")
    check(all(n in ("read_webpage", "web_search") for n, _ in asked_ay),
          f"ask, owner says yes: the question names the request kind: {[n for n, _ in asked_ay]}")

    got_an, said_an, calls_an, asked_an = run(runner, "ask", answer=False)
    check(got_an is True and calls_an == 0 and asked_an and said_an == DECLINED,
          f"ask, owner says no: no web call, asked {len(asked_an)} time(s), reply {said_an!r}")

    got_n, said_n, calls_n, asked_n = run(runner, "no", answer=True)
    check(got_n is True and calls_n == 0 and asked_n == [] and said_n == off,
          f"no: no web call, nothing asked, reply {said_n!r}")

    got_nc, said_nc, calls_nc, _ = run(runner, "ask", ctx=False)
    check(calls_nc == allowed_calls and same(said_nc, said_y),
          f"ask with no desk to ask through (tests, console): as today, {calls_nc} web call(s)")

print("service status and dictionary: the owner's switch is honoured before any page is contacted")
got, said, calls, asked = run(CASES[2][1], "no")
check(calls == 0 and said == OFF_FORECAST, "service status under no: no status page is contacted")
got, said, calls, asked = run(CASES[8][1], "no")
check(calls == 0 and said == OFF_FORECAST, "dictionary under no: no dictionary site is contacted")

print("a question the internet is not needed for is not gated")
got, said, calls, asked = run(lambda dk: everyday.live_lookup(dk, "is it down", "is it down"), "ask", answer=False)
check(asked == [] and calls == 0, "a status question with no service name asks nothing")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
