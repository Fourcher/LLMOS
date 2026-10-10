#!/usr/bin/env python3
"""Host-side test of the plain-words web error messages in web.py. No network: the curl runner
(subprocess.run inside web.fetch) is replaced by a fake that answers with a fixed HTTP status.
Run: python3 tools/test-web-errors.py  (exit status 0 = pass)."""
import os
import subprocess
import sys
from unittest import mock

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import web  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


print("status messages")
cases = (
    (429, "DuckDuckGo is getting too many requests; try again in a minute"),
    (500, "DuckDuckGo isn't answering right now; try again in a minute"),
    (503, "DuckDuckGo isn't answering right now; try again in a minute"),
    (404, "that page doesn't exist"),
    (403, "DuckDuckGo refused the request"),
    (418, "DuckDuckGo didn't answer properly"),
)
for code, want in cases:
    got = web._status_msg("DuckDuckGo", code)
    check(got == want, f"_status_msg({code}) -> {got!r}")

print("search with a 503 from both engines")
SEARCH_MSG = "the search services aren't answering right now; try again in a minute"


def fake_curl(cmd, **kw):
    # fetch() writes the body to the -o file and prints "status\ncontent-type\nfinal-url" on stdout
    return subprocess.CompletedProcess(cmd, 0, stdout="503\ntext/html\nhttps://example.com/", stderr="")


with mock.patch("llmos.web.subprocess.run", side_effect=fake_curl) as run:
    try:
        web.search("weather denver")
        got = None
    except web.WebError as e:
        got = str(e)
    check(run.call_count == 2, f"curl was called for both engines ({run.call_count} calls)")
check(got == SEARCH_MSG, f"search raises the plain sentence -> {got!r}")

print("one engine down, the other answered nothing")
with mock.patch.object(web, "_search_ddg", side_effect=web.WebError(web._status_msg("DuckDuckGo", 503), 503)), \
        mock.patch.object(web, "_search_brave", return_value=[]):
    try:
        web.search("q")
        got = None
    except web.WebError as e:
        got = str(e)
check(got == "DuckDuckGo isn't answering right now; try again in a minute", f"one failed engine -> {got!r}")

print("code kept on the error")
with mock.patch("llmos.web.subprocess.run", side_effect=fake_curl):
    try:
        web._search_ddg("q")
        status = None
    except web.WebError as e:
        status = e.status
check(status == 503, f"DuckDuckGo 503 keeps WebError.status == 503 ({status!r})")
with mock.patch("llmos.web.subprocess.run", side_effect=lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, stdout="404\ntext/html\nhttps://example.com/x", stderr="")):
    try:
        web.read("https://example.com/x")
        got, code = None, None
    except web.WebError as e:
        got, code = str(e), e.status
check(got == "that page doesn't exist" and code == 404, f"read() 404 -> {got!r}, status {code!r}")

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
