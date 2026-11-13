#!/usr/bin/env python3
"""The self-improvement loop: separate checkout, light gate, kill switch, rate limit, OTA only with &&.

Does not publish and does not edit this tree. Run: python3 tools/test-selfloop.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src/rootfs/usr/lib/llmos")
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
state = tempfile.mkdtemp(prefix="llmos-selfloop-")
os.environ["LLMOS_SELFLOOP_DIR"] = state
os.environ["LLMOS_HOME"] = state
os.environ["LLMOS_ETC"] = os.path.join(state, "etc")
os.environ["LLMOS_SELFLOOP_CONFIG"] = os.path.join(state, "no-such-config.json")

import selfloop  # noqa: E402
from llmos import selfloop_ctl  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


check("selfloop.py" in os.path.basename(selfloop.__file__), "this test reads selfloop.py")
check("selfloop_ctl.py" in os.path.basename(selfloop_ctl.__file__), "this test reads selfloop_ctl.py")

cfg = selfloop_ctl.load_config(os.path.join(state, "missing.json"))
check(cfg["require_approval"] is True and cfg["mode"] == "dev",
      "a missing config requires approval and names dev-machine mode")
off = os.path.join(state, "off.json")
json.dump({"require_approval": False, "mode": "dev", "max_per_day": 4, "min_interval_sec": 0}, open(off, "w"))
check(selfloop_ctl.load_config(off)["require_approval"] is False, "approval can be turned off on purpose")
bad = os.path.join(state, "bad.json")
open(bad, "w").write("{")
check(selfloop_ctl.load_config(bad)["require_approval"] is True, "a broken config does not turn approval off")

shell = selfloop_ctl.ship_shell(ROOT, ["tools/test-selfloop.py"], "1.8.7", "note", os.path.join(state, "gate.txt"))
check("&&" in shell and "|" not in shell, "publish is chained with && and not a pipe")
left, _, right = shell.partition("&&")
check("run-host-tests.sh" in left and ">" in left and "publish" in right and "publish" not in left,
      "the host tests run, their output goes to a file, and only then does ota publish")
try:
    selfloop_ctl.assert_gated("bash tools/run-host-tests.sh | tail && python3 tools/ota.py publish")
    check(False, "a pipe is refused")
except RuntimeError as e:
    check("pipe" in str(e), "a pipe is refused")

ideas = selfloop_ctl.ideas_from_text("ok\nFAIL tools/test-a.py\nFAIL tools/test-a.py\nFAIL tools/test-b.py\n")
check(len(ideas) == 2 and ideas[0]["status"] == "open" and "Do not edit the test" in ideas[0]["detail"],
      "a failure log becomes a backlog item that must not weaken the test")
item, rows = selfloop_ctl.pick_item([], "FAIL tools/test-a.py\n")
check(item and item["source"] == "test-failure" and len(rows) == 1, "an empty backlog takes the failure")
item2, _rows = selfloop_ctl.pick_item([{"id": "keep", "title": "do the open one", "status": "open"},
                                      {"id": "nope", "title": "done", "status": "queued"}])
check(item2["id"] == "keep", "an open backlog item wins over the log")

check("dev" in selfloop_ctl.summary().lower() and "approval" in selfloop_ctl.summary().lower(),
      "status tells the owner this runs on a dev machine and whether approval is required")
print(selfloop_ctl.set_killed(True))
check(selfloop_ctl.killed(), "the kill switch file stops the loop")
selfloop_ctl.set_killed(False)
check(not selfloop_ctl.killed(), "resume clears the kill switch")
os.environ["LLMOS_SELFLOOP"] = "off"
check(selfloop_ctl.killed(), "LLMOS_SELFLOOP=off is a kill switch")
del os.environ["LLMOS_SELFLOOP"]

# a tiny git repo. The loop must write the checkout and leave this file alone.
repo = os.path.join(state, "repo")
os.makedirs(os.path.join(repo, "tools"))
marker = os.path.join(repo, "marker.txt")
open(marker, "w", encoding="utf-8").write("original\n")
open(os.path.join(repo, "tools", "run-host-tests.sh"), "w", encoding="utf-8").write("#!/bin/bash\nexit 0\n")


def git(*args, cwd=repo):
    subprocess.run(["git", "-C", cwd, "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
                   check=True, stdout=subprocess.DEVNULL)


git("init", "-b", "main")
git("add", "-A")
git("commit", "-m", "init")
outs = os.path.join(state, "checkouts")
calls = []


def implement(support, item):
    open(os.path.join(support, "marker.txt"), "w", encoding="utf-8").write("changed\n")
    return {"changed": ["src/rootfs/usr/lib/llmos/llmos/selfloop_ctl.py"]}


def select(_paths):
    return ["tools/test-selfloop.py"], "one test"


def gate(_support, _tests):
    return True, "host suites: 1 run, 0 failed"


def ship(shell, _support):
    calls.append(shell)
    selfloop_ctl.assert_gated(shell)
    return 0


def kw(now, **over):
    d = dict(live=repo, repo=repo, dest_parent=outs, implement=implement, select=select, gate=gate, ship=ship,
             log_text="", now=now)
    d.update(over)
    return d


selfloop_ctl.set_killed(True)
killed = selfloop.run_once(backlog=[{"id": "k", "title": "should not run", "status": "open"}],
                           cfg={"mode": "dev", "require_approval": True, "max_per_day": 4, "min_interval_sec": 0},
                           **kw(1_000_000))
check(killed["action"] == "refused" and "kill switch" in killed["detail"], "the kill switch refuses before any edit")
check(open(marker, encoding="utf-8").read() == "original\n", "a refused run leaves the tree as it was")
check(calls == [], "a refused run does not publish")
selfloop_ctl.set_killed(False)

selfloop.selfdev._is_live_install = lambda: True
live = selfloop.run_once(backlog=[{"id": "live", "title": "no", "status": "open"}],
                         cfg={"mode": "dev", "require_approval": True, "max_per_day": 4, "min_interval_sec": 0},
                         **kw(2_000_000))
check(live["action"] == "refused" and "running install" in live["detail"],
      "a live install is refused; dev-machine mode ships by OTA")
check(open(marker, encoding="utf-8").read() == "original\n", "a live install is not edited")
selfloop.selfdev._is_live_install = lambda: False

def gate_fail(_support, _tests):
    return False, "FAIL tools/test-selfloop.py"


failed = selfloop.run_once(backlog=[{"id": "bad", "title": "breaks tests", "status": "open"}],
                           cfg={"mode": "dev", "require_approval": False, "max_per_day": 8, "min_interval_sec": 0},
                           **kw(3_000_000, gate=gate_fail))
check(failed["action"] == "discarded" and calls == [], "a failed light gate discards the change and does not publish")
check(open(marker, encoding="utf-8").read() == "original\n", "a discarded run puts nothing into the running tree")
check(not os.path.isdir(outs) or not os.listdir(outs), "a failed checkout is removed")

queued = selfloop.run_once(backlog=[{"id": "good", "title": "a small fix", "status": "open"}],
                           cfg={"mode": "dev", "require_approval": True, "max_per_day": 8, "min_interval_sec": 0},
                           **kw(4_000_000))
check(queued["action"] == "queued" and calls == [], "a passing gate is queued and not published when approval is required")
check("&&" in queued.get("ship", "") and "|" not in queued.get("ship", ""), "the queued command is the && gate")
check(open(marker, encoding="utf-8").read() == "original\n", "the running tree stays original while the checkout has the change")
check(selfloop_ctl.load_queue() and selfloop_ctl.load_queue()[-1]["id"] == "good", "the queue remembers the change")
found = []
for dirpath, _dirs, files in os.walk(outs):
    if "marker.txt" in files:
        found.append(open(os.path.join(dirpath, "marker.txt"), encoding="utf-8").read())
check(found == ["changed\n"], "the change exists only in the separate checkout")

shipped = selfloop.run_once(backlog=[{"id": "ship", "title": "ship it", "status": "open"}],
                            cfg={"mode": "dev", "require_approval": False, "max_per_day": 8, "min_interval_sec": 0},
                            **kw(5_000_000))
check(shipped["action"] == "shipped" and len(calls) == 1, "with approval off, publish runs only after the gate")
check(selfloop_ctl.assert_gated(calls[0]) and "ota.py" in calls[0], "that publish is the OTA command after the tests")

calls.clear()


def ship_fail(shell, _support):
    calls.append(shell)
    return 1


held = selfloop.run_once(backlog=[{"id": "held", "title": "gate fails at publish", "status": "open"}],
                         cfg={"mode": "dev", "require_approval": False, "max_per_day": 8, "min_interval_sec": 0},
                         **kw(6_000_000, ship=ship_fail))
check(held["action"] == "discarded" and "nothing was published" in held["detail"],
      "a publish command that fails does not count as shipped")

limited = selfloop.run_once(backlog=[{"id": "later", "title": "too soon", "status": "open"}],
                            cfg={"mode": "dev", "require_approval": True, "max_per_day": 8, "min_interval_sec": 99999},
                            **kw(6_000_100))
check(limited["action"] == "refused" and "rate limit" in limited["detail"], "the rate limit refuses a run")

sel, info = selfloop.tests_for_changes(["src/rootfs/usr/lib/llmos/llmos/selfloop_ctl.py"])
check(sel and "tools/test-selfloop.py" in sel and "tools/test-selfdev.py" in sel,
      "the light gate is the tests that touch the module plus the core subset")
none, why = selfloop.tests_for_changes(["docs/no-such.txt"])
check(none is None and "Nothing was queued" in why, "a change with no test is not queued")

try:
    selfloop.assert_separate(repo, repo)
    check(False, "the running tree cannot be the checkout")
except RuntimeError:
    check(True, "the running tree cannot be the checkout")

# do_task still does not publish; this loop is the only path that builds an OTA command
src = open(os.path.join(HERE, "selfdev.py"), encoding="utf-8").read()
check("worktree" not in src, "selfdev itself still has no worktree path")
print("all good" if not fails else f"{fails} failed")
shutil.rmtree(state, ignore_errors=True)
sys.exit(1 if fails else 0)
