#!/usr/bin/env python3
"""Host-side test of replytr.translate (the replies the desk gives at once, in the owner's language). The on-device
model is replaced by a recorder (llm.complete_json), and the reply cache lives in a temporary home.
Run: python3 tools/test-reply-translate.py"""
import json
import os
import stat
import sys
import tempfile
import threading
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos")
sys.path.insert(0, os.path.abspath(ROOT))
HOME = tempfile.mkdtemp(prefix="replytr-home-")
os.environ["LLMOS_HOME"] = HOME

from llmos import llm, replytr  # noqa: E402

fails = 0
calls = []   # (keys, user prompt, max_tokens) for each model call


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


def keys_of(schema):
    return list(schema["properties"])


def fake(system, user, schema, max_tokens=3000):
    calls.append((keys_of(schema), user, max_tokens))
    return {k: "[es] " + k for k in keys_of(schema)}


def slow(system, user, schema, max_tokens=3000):
    calls.append((keys_of(schema), user, max_tokens))
    gate.wait(10)
    return {k: "[es] " + k for k in keys_of(schema)}


def cache_file(code="es"):
    return os.path.join(HOME, ".llmos", "cache", "replies-%s.json" % code)


def settle():
    """Wait until no translation holds the miss lock (an abandoned worker may still be running)."""
    got = replytr._miss.acquire(timeout=15)
    if got:
        replytr._miss.release()
    return got


gate = threading.Event()
llm.complete_json = fake

# English: returned unchanged, no model call, no cache file
check(replytr.translate("Done.", "English") == "Done." and calls == [], "English reply unchanged, no model call")
check(not os.path.exists(os.path.join(HOME, ".llmos")), "English touches no cache folder")

# Spanish: translated once, second time served from the cache
r1 = replytr.translate("Done.", "Spanish")
r2 = replytr.translate("Done.", "Spanish")
check(r1 == "[es] Done." and r2 == "[es] Done.", "Spanish reply translated: %r" % r1)
check(len(calls) == 1, "second Spanish reply served from cache (llm calls: %d)" % len(calls))
check(calls and "into Spanish" in calls[0][1], "model asked for Spanish")
check(calls and calls[0][2] == 64, "short reply bounded to max(64, 3*len//2) = 64 tokens (got %s)"
      % (calls[0][2] if calls else None))
check(calls and calls[0][0] == ["Done."], "schema asks for exactly the one key")

# cache file and folder modes
mode_f = stat.S_IMODE(os.stat(cache_file()).st_mode)
mode_d = stat.S_IMODE(os.stat(os.path.dirname(cache_file())).st_mode)
check(mode_f == 0o600, "cache file mode 0600 (got %o)" % mode_f)
check(mode_d == 0o700, "cache folder mode 0700 (got %o)" % mode_d)
check(json.load(open(cache_file(), encoding="utf-8")) == {"Done.": "[es] Done."}, "cache file holds the reply")

# slow model: English after about the timeout; the worker still holds the lock until its call ends
llm.complete_json = slow
replytr.TIMEOUT_S = 0.2
t0 = time.time()
r = replytr.translate("Slow one.", "Spanish")
took = time.time() - t0
check(r == "Slow one." and took < 2, "slow model -> English after %.2f s" % took)
calls.clear()
check(replytr.translate("Next one.", "Spanish") == "Next one." and calls == [],
      "abandoned slow request still running: next miss gets English, no second call")
gate.set()
check(settle(), "abandoned request ends and releases the miss lock")
gate.clear()
replytr.TIMEOUT_S = 4.0
llm.complete_json = fake

# errors: exception, None, empty dict -> English
def boom(system, user, schema, max_tokens=3000):
    raise RuntimeError("model down")


def none_back(system, user, schema, max_tokens=3000):
    return None


def empty_back(system, user, schema, max_tokens=3000):
    return {}


for name, fn in (("exception", boom), ("None", none_back), ("empty dict", empty_back)):
    llm.complete_json = fn
    check(replytr.translate("Error case " + name + ".", "Spanish") == "Error case " + name + ".",
          "model error (%s) -> English" % name)
    settle()
llm.complete_json = fake

# placeholders lost in translation -> English
llm.complete_json = lambda system, user, schema, max_tokens=3000: {k: "sin nada" for k in keys_of(schema)}
check(replytr.translate("Hello {name}.", "Spanish") == "Hello {name}.", "placeholder dropped -> English")
llm.complete_json = fake

# a translation that drops a number -> English
llm.complete_json = lambda system, user, schema, max_tokens=3000: {k: "Tienes 7 tareas" for k in keys_of(schema)}
check(replytr.translate("You have 42 tasks.", "Spanish") == "You have 42 tasks.", "translation dropping \"42\" -> English")
check(replytr.translate("You have 7 tasks.", "Spanish") == "Tienes 7 tareas", "translation keeping the number is accepted")
llm.complete_json = fake

# long text and number/emoji only: unchanged, no model call
calls.clear()
long_text = "x" * 2001
check(replytr.translate(long_text, "Spanish") == long_text and calls == [], "text over 2000 chars -> English, no call")
check(replytr.translate("42 🙂", "Spanish") == "42 🙂" and calls == [], "number/emoji only -> unchanged, no call")

# model busy (a chat request in progress): English at once, no request made, no cache written
calls.clear()
llm._INFLIGHT = 1
t0 = time.time()
r = replytr.translate("Busy turn.", "Spanish")
took_busy = time.time() - t0
llm._INFLIGHT = 0
check(r == "Busy turn." and took_busy < 0.05 and calls == [],
      "model busy -> English in %.1f ms, no request made" % (took_busy * 1000))
check(not os.path.exists(cache_file()) or "Busy turn." not in json.load(open(cache_file(), encoding="utf-8")),
      "busy miss is not cached")

# cache hit while busy: still translated
replytr.translate("Done.", "Spanish")  # already cached above
calls.clear()
llm._INFLIGHT = 1
r = replytr.translate("Done.", "Spanish")
llm._INFLIGHT = 0
check(r == "[es] Done." and calls == [], "cache hit while busy -> translated, no call")

# chat() keeps the counter honest: it is back to zero after a failed request
real_conn = llm._conn


class FailConn:
    def request(self, *a, **k):
        raise OSError("refused")

    def close(self):
        pass


llm._conn = lambda *a, **k: FailConn()
try:
    llm.chat([{"role": "user", "content": "hi"}])
except llm.ModelDown:
    pass
llm._conn = real_conn
check(llm.busy() is False, "chat() counter back to zero after a failed request")

# two concurrent misses: exactly one model call; the other gets English at once
calls.clear()
gate.clear()
llm.complete_json = slow
results = {}
first = threading.Thread(target=lambda: results.__setitem__("a", replytr.translate("Concurrent A.", "Spanish")))
first.start()
while not calls:
    time.sleep(0.01)
t0 = time.time()
b = replytr.translate("Concurrent B.", "Spanish")
took_b = time.time() - t0
check(b == "Concurrent B." and took_b < 0.5 and len(calls) == 1,
      "second concurrent miss -> English at once, exactly one llm call (calls: %d)" % len(calls))
gate.set()
first.join()
check(results.get("a") == "[es] Concurrent A.", "first concurrent miss translated")
gate.clear()
llm.complete_json = fake
settle()

# concurrent replies on many texts: the cache file stays valid JSON, each entry matches its own text
calls.clear()
threads = [threading.Thread(target=replytr.translate, args=("Concurrent %d." % i, "Spanish")) for i in range(20)]
for th in threads:
    th.start()
for th in threads:
    th.join()
try:
    data = json.load(open(cache_file(), encoding="utf-8"))
    check(all(data.get("Concurrent %d." % i) in (None, "[es] Concurrent %d." % i) for i in range(20))
          and len(data) >= 1, "concurrent replies: cache file valid JSON, entries match their text (%d kept)"
          % len(data))
except ValueError as e:
    check(False, "cache file corrupted: %s" % e)

# cache cap: oldest dropped
replytr.MAX_ENTRIES = 3
for i in range(5):
    replytr.translate("Cap %d." % i, "Spanish")
data = json.load(open(cache_file(), encoding="utf-8"))
check(len(data) == 3 and "Cap 4." in data and "Cap 0." not in data, "cache capped at 3, oldest dropped")
replytr.MAX_ENTRIES = 2000

print("\nall good" if not fails else "\n%d failure(s)" % fails)
sys.exit(1 if fails else 0)
