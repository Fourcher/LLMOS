#!/usr/bin/env python3
"""Host-side test of replytr.translate (the replies the desk gives at once, in the owner's language). The on-device
model is replaced by a recorder, and the reply cache lives in a temporary home. Run: python3 tools/test-reply-translate.py"""
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
calls = []


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


def fake(strings, language):
    calls.append((list(strings), language))
    return {s: "[es] " + s for s in strings}


def slow(strings, language):
    calls.append((list(strings), language))
    time.sleep(10)
    return {s: "[es] " + s for s in strings}


def cache_file(code="es"):
    return os.path.join(HOME, ".llmos", "cache", "replies-%s.json" % code)


llm.translate_strings = fake

# English: returned unchanged, no model call, no cache file
check(replytr.translate("Done.", "English") == "Done." and calls == [], "English reply unchanged, no model call")
check(not os.path.exists(os.path.join(HOME, ".llmos")), "English touches no cache folder")

# Spanish: translated once, second time served from the cache
r1 = replytr.translate("Done.", "Spanish")
r2 = replytr.translate("Done.", "Spanish")
check(r1 == "[es] Done." and r2 == "[es] Done.", "Spanish reply translated: %r" % r1)
check(len(calls) == 1, "second Spanish reply served from cache (llm calls: %d)" % len(calls))
check(calls and calls[0][1] == "Spanish", "model asked for Spanish")

# cache file and folder modes
mode_f = stat.S_IMODE(os.stat(cache_file()).st_mode)
mode_d = stat.S_IMODE(os.stat(os.path.dirname(cache_file())).st_mode)
check(mode_f == 0o600, "cache file mode 0600 (got %o)" % mode_f)
check(mode_d == 0o700, "cache folder mode 0700 (got %o)" % mode_d)
check(json.load(open(cache_file(), encoding="utf-8")) == {"Done.": "[es] Done."}, "cache file holds the reply")

# slow model: English after about the timeout
llm.translate_strings = slow
replytr.TIMEOUT_S = 0.2
t0 = time.time()
r = replytr.translate("Slow one.", "Spanish")
took = time.time() - t0
check(r == "Slow one." and took < 2, "slow model -> English after %.2f s" % took)
replytr.TIMEOUT_S = 4.0

# errors: exception, None, empty dict, empty text -> English
def boom(strings, language):
    raise RuntimeError("model down")


def none_back(strings, language):
    return None


def empty_back(strings, language):
    return {}


for name, fn in (("exception", boom), ("None", none_back), ("empty dict", empty_back)):
    llm.translate_strings = fn
    check(replytr.translate("Error case " + name + ".", "Spanish") == "Error case " + name + ".",
          "model error (%s) -> English" % name)

# placeholders lost in translation -> English
llm.translate_strings = lambda s, l: {k: "sin nada" for k in s}
check(replytr.translate("Hello {name}.", "Spanish") == "Hello {name}.", "placeholder dropped -> English")

# long text and number/emoji only: unchanged, no model call
llm.translate_strings = fake
calls.clear()
long_text = "x" * 2001
check(replytr.translate(long_text, "Spanish") == long_text and calls == [], "text over 2000 chars -> English, no call")
check(replytr.translate("42 🙂", "Spanish") == "42 🙂" and calls == [], "number/emoji only -> unchanged, no call")

# concurrent replies: the cache file stays valid JSON with every entry
calls.clear()
threads = [threading.Thread(target=replytr.translate, args=("Concurrent %d." % i, "Spanish")) for i in range(20)]
for th in threads:
    th.start()
for th in threads:
    th.join()
try:
    data = json.load(open(cache_file(), encoding="utf-8"))
    check(all(data.get("Concurrent %d." % i) == "[es] Concurrent %d." % i for i in range(20)),
          "20 concurrent replies all cached, file valid JSON")
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
