#!/usr/bin/env python3
"""Host-side test: web.search() asks DuckDuckGo and Brave at the same time.
The first non-empty list wins; empty or failed engines do not stop the other;
the wait is capped at 10 s x LLMOS_SLOW.
Run: python3 tools/test-web-search.py  (no network needed). Exit status 0 = pass."""
import os
import sys
import time

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import web

HIT = [{"title": "t", "url": "https://example.com/a", "snippet": "s"}]
HIT2 = [{"title": "u", "url": "https://example.com/b", "snippet": "s"}]


def fake(delay, result=None, exc=None):
    def engine(query):
        time.sleep(delay)
        if exc is not None:
            raise exc
        return result
    return engine


def run_search(ddg, brave):
    web._search_ddg = ddg
    web._search_brave = brave
    t0 = time.monotonic()
    try:
        out = web.search("q")
        err = None
    except web.WebError as e:
        out, err = None, e
    return out, err, time.monotonic() - t0


os.environ.pop("LLMOS_SLOW", None)

# 1. fast DDG wins without waiting for a slow Brave
out, err, dt = run_search(fake(0.1, HIT), fake(2, HIT2))
assert err is None and out == HIT, (out, err)
assert dt < 0.5, f"fast DDG took {dt:.2f}s"
print(f"ok fast DDG wins in {dt:.2f}s")

# 2. DDG raises, Brave returns -> Brave's list
out, err, dt = run_search(fake(0.05, exc=web.WebError("DuckDuckGo returned 503")), fake(0.2, HIT2))
assert err is None and out == HIT2, (out, err)
print(f"ok DDG error, Brave list returned in {dt:.2f}s")

# 3. DDG empty fast, Brave later -> Brave's list
out, err, dt = run_search(fake(0.05, []), fake(0.3, HIT2))
assert err is None and out == HIT2, (out, err)
print(f"ok DDG empty, Brave list returned in {dt:.2f}s")

# 4. both slow -> failure value, without waiting for the threads
os.environ["LLMOS_SLOW"] = "0.1"
out, err, dt = run_search(fake(3, HIT), fake(3, HIT2))
assert out is None and isinstance(err, web.WebError), (out, err)
assert dt < 1.5, f"both slow took {dt:.2f}s, limit is 1s"
assert str(err) == "the search took too long", str(err)
print(f"ok both slow -> WebError({str(err)!r}) in {dt:.2f}s")

# 5. both engines raise a non-WebError at once -> WebError naming ValueError, fast
os.environ.pop("LLMOS_SLOW", None)
out, err, dt = run_search(fake(0.01, exc=ValueError("bad page")), fake(0.01, exc=ValueError("bad json")))
assert out is None and isinstance(err, web.WebError), (out, err)
assert "ValueError" in str(err), str(err)
assert dt < 0.5, f"both ValueError took {dt:.2f}s, limit is 0.5s"
print(f"ok both ValueError -> WebError({str(err)!r}) in {dt:.2f}s")

# 6. one engine raises KeyError fast, the other returns a list after 0.2 s -> the list
out, err, dt = run_search(fake(0.01, exc=KeyError("uddg")), fake(0.2, HIT2))
assert err is None and out == HIT2, (out, err)
assert dt < 1.0, f"KeyError + list took {dt:.2f}s, limit is 1s"
print(f"ok KeyError, Brave list returned in {dt:.2f}s")

# 7. both engines WebError -> the plain sentence for both services failing, no "WebError:" prefix
out, err, dt = run_search(fake(0.01, exc=web.WebError("X 503")), fake(0.01, exc=web.WebError("Y 429")))
assert out is None and str(err) == "the search services aren't answering right now; try again in a minute", (out, str(err))
print(f"ok both WebError -> {str(err)!r} in {dt:.2f}s")

# 8. both ValueError -> type-prefixed messages joined
out, err, dt = run_search(fake(0.01, exc=ValueError("a")), fake(0.01, exc=ValueError("b")))
assert out is None and str(err) == "ValueError: a; ValueError: b", (out, str(err))
print(f"ok both ValueError -> {str(err)!r} in {dt:.2f}s")

# 9. both engines finish with empty lists -> "no results"
out, err, dt = run_search(fake(0.01, []), fake(0.01, []))
assert out is None and str(err) == "no results", (out, str(err))
print(f"ok both empty -> {str(err)!r} in {dt:.2f}s")

# 10. both slow -> "the search took too long" in about 1 s
os.environ["LLMOS_SLOW"] = "0.1"
out, err, dt = run_search(fake(3, HIT), fake(3, HIT2))
assert out is None and str(err) == "the search took too long", (out, str(err))
assert dt < 1.5, f"both slow took {dt:.2f}s, limit is 1s"
os.environ.pop("LLMOS_SLOW", None)
print(f"ok both slow -> {str(err)!r} in {dt:.2f}s")

print("all good")
