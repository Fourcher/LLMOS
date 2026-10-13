#!/usr/bin/env python3
"""Host-side test of the plain-words replies of everyday.py's port, local website and stop routes.

The subprocess, socket-free helpers and os.kill are patched, so nothing listens, starts or stops anything on this host.
Checks: the new wording shows up, the old technical words (web server, listening, process, server) don't, and the
stop phrases ("stop the local website", "stop the web server", "stop serving") reach the stop route, while
"stop the website from tracking me" does not stop the server.
Run: python3 tools/test-everyday-words.py"""
import os
import re
import sys
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", "/nonexistent-llmos-test-home")
from llmos import everyday, intent  # noqa: E402

fails = 0
TECH = re.compile(r"web ?server|listening|process|server", re.I)


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


class Desk:
    def __init__(self):
        self.said = None

    def instant_reply(self, line, text):
        self.said = text


class FakeProc:
    def poll(self):
        return None

    def terminate(self):
        self.terminated = True


# ---- patches: no real lsof, netstat, http.server, browser, kill or sleep
LISTENERS = {}          # port -> [(pid, name)]
POPENS = []             # every Popen call
KILLS = []              # every os.kill call
real = (everyday.subprocess, everyday._open, everyday.time.sleep, os.kill)


def fake_run(argv, **kw):
    port = None
    for a in argv:
        m = re.match(r"-iTCP:(\d+)$", a)
        if m:
            port = int(m.group(1))
    out = ""
    if port is not None:
        for pid, name in LISTENERS.get(port, []):
            out += f"p{pid}\nc{name}\n"
    return types.SimpleNamespace(stdout=out)


def fake_popen(argv, **kw):
    POPENS.append(argv)
    return FakeProc()


everyday.subprocess = types.SimpleNamespace(run=fake_run, Popen=fake_popen, DEVNULL=None,
                                            SubprocessError=Exception)
everyday._open = lambda desk, url: None
everyday.time.sleep = lambda s: None
os.kill = lambda pid, sig: KILLS.append((pid, sig))

try:
    # ---- ports: nothing running
    d = Desk()
    LISTENERS.clear()
    check(everyday.handle(d, "kill whatever's on 3000") and d.said == "Nothing is running on port 3000.",
          f"kill on an empty port: {d.said!r}")
    d = Desk()
    check(everyday.handle(d, "what's listening on port 8080") and d.said == "Nothing is running on port 8080.",
          f"who is on an empty port: {d.said!r}")

    # ---- ports: one program listening, no process number in the reply
    LISTENERS[8080] = [(4242, "node")]
    d = Desk()
    check(everyday.handle(d, "what's on port 8080") and d.said.startswith("Port 8080: node. Say"),
          f"who is on a busy port: {d.said!r}")
    check("4242" not in d.said and "process" not in d.said, "busy-port reply has no process number")
    check(not TECH.search(d.said), "busy-port reply has no technical words")

    # ---- local website: start, then the stop routes
    d = Desk()
    check(everyday.handle(d, "start a local web server here") and d.said.startswith("Showing ")
          and "Say “stop the local website” to end it." in d.said,
          f"start reply: {d.said!r}")
    check(not TECH.search(d.said), "start reply has no technical words")
    check(POPENS and POPENS[-1][:3] == ["python3", "-m", "http.server"], "start launches the local website (patched)")

    for phrase in ("stop the local website", "stop the web server", "stop serving"):
        everyday._SERVER["p"] = FakeProc()
        t = intent.plain(phrase).lower().strip()
        matched = everyday.MATCH.search(t) is not None
        d = Desk()
        handled = everyday.handle(d, phrase)
        check(matched and handled and d.said == "The local website is stopped." and "p" not in everyday._SERVER,
              f"{phrase!r}: MATCH={matched} handled={handled} reply={d.said!r}")
        check(not TECH.search(d.said), f"{phrase!r}: reply has no technical words")

    d = Desk()
    handled = everyday.handle(d, "stop the local website")
    check(handled and d.said == "No local website was running.", f"stop with nothing running: {d.said!r}")
    check(not TECH.search(d.said), "nothing-running reply has no technical words")

    # ---- must not stop the server
    everyday._SERVER["p"] = FakeProc()
    phrase = "stop the website from tracking me"
    matched = everyday.MATCH.search(intent.plain(phrase).lower().strip()) is not None
    d = Desk()
    handled = everyday.handle(d, phrase)
    check(not matched and "p" in everyday._SERVER and (d.said is None or "website" not in d.said or "stopped" not in d.said),
          f"{phrase!r}: MATCH={matched} handled={handled} server kept={'p' in everyday._SERVER} reply={d.said!r}")
    everyday._SERVER.pop("p", None)
finally:
    everyday.subprocess, everyday._open, everyday.time.sleep, os.kill = real

if fails:
    print(f"{fails} FAIL")
    sys.exit(1)
print("all good")
