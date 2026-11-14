#!/usr/bin/env python3
"""Spoken bug fix on the laptop: context, local device loop, approval, rollback, GitHub report.

No cloud model and no full host suite. Run: python3 tools/test-bugfix.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src/rootfs/usr/lib/llmos")
state = tempfile.mkdtemp(prefix="llmos-bugfix-")
os.environ["LLMOS_SELFLOOP_DIR"] = state
os.environ["LLMOS_HOME"] = state
os.environ["LLMOS_ETC"] = os.path.join(state, "etc")
os.environ["LLMOS_SELFLOOP_CONFIG"] = os.path.join(state, "selfloop.json")
os.environ["LLMOS_OTA_ROOT"] = os.path.join(state, "ota-root-unused")
os.environ["LLMOS_OTA_DIR"] = os.path.join(state, "ota-state-unused")
os.environ["LLMOS_BOOT_FAILED"] = os.path.join(state, "no-boot-failed")
os.environ["LLMOS_HEALTH_CHECK"] = ""
os.environ["LLMOS_BUGFIX_RUN"] = "0"
os.environ["LLMOS_BUGFIX_JOURNAL"] = "0"
os.environ["LLMOS_BUGFIX_REPORT"] = "0"
os.environ["LLMOS_GITHUB_TOKEN_FILE"] = os.path.join(state, "no-token-file")
os.environ.pop("LLMOS_GITHUB_TOKEN", None)
os.makedirs(os.environ["LLMOS_ETC"], exist_ok=True)
json.dump({"mode": "dev", "backend": "cloud", "require_approval": False, "max_per_day": 8,
           "min_interval_sec": 0, "max_iterations": 3, "max_light_tests": 24},
          open(os.environ["LLMOS_SELFLOOP_CONFIG"], "w"))
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import selfloop  # noqa: E402
import selfloop_local  # noqa: E402
from llmos import bugfix, config, everyday, ghreport, intent, ota, selfloop_ctl  # noqa: E402

fails = 0
TOKEN = "github_pat_" + ("a" * 20)


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


def fake_http(plan):
    """plan is a list of (status, body) or a function. Records every call."""
    calls = []

    def transport(method, url, payload, token):
        calls.append((method, url, payload, token))
        if callable(plan):
            return plan(method, url, payload, token)
        status, body = plan.pop(0)
        return status, body

    transport.calls = calls
    return transport


def github_ok(method, url, payload, token):
    if url.endswith("/git/ref/heads/main"):
        return 200, {"object": {"sha": "a" * 40}}
    if "/git/commits/" in url and method == "GET":
        return 200, {"tree": {"sha": "b" * 40}}
    if url.endswith("/git/blobs"):
        return 201, {"sha": "c" * 40}
    if url.endswith("/git/trees"):
        return 201, {"sha": "d" * 40}
    if url.endswith("/git/commits") and method == "POST":
        return 201, {"sha": "e" * 40}
    if url.endswith("/git/refs"):
        return 201, {"ref": (payload or {}).get("ref"), "object": {"sha": "e" * 40}}
    if url.endswith("/pulls"):
        return 201, {"html_url": "https://github.com/Fourcher/LLMOS/pull/99", "number": 99}
    if url.endswith("/issues"):
        return 201, {"html_url": "https://github.com/Fourcher/LLMOS/issues/7", "number": 7}
    return 500, {"message": "unexpected"}


# --- phrases ---
yes = [
    "I found a bug, fix it",
    "hey, I found a bug here, fix it",
    "Hey I found a bug here fix it",
    "there's a bug, fix it",
    "this is broken, fix it",
    "something is broken, please fix it",
    "this doesn't work, fix it",
    "this is not working, fix it",
    "please fix this bug",
    "fix that bug",
    "I found a bug in the calculator, the total is wrong, fix it",
]
for phrase in yes:
    hit = bugfix.classify(phrase)
    routed = intent.match(phrase)
    check(hit and hit[0] == "report" and routed and routed[0] == "fix_bug" and routed[1].get("action") == "report",
          "report phrase: " + phrase)
long = bugfix.classify("I found a bug in the calculator, the total is wrong, fix it")
check(long and "calculator" in long[1] and "total is wrong" in long[1], "the owner's words stay in the description")

for phrase, action in (
    ("apply that fix", "apply"), ("yes, apply that fix", "apply"), ("install that fix", "apply"),
    ("go ahead and apply that fix", "apply"), ("undo that fix", "undo"), ("revert that fix", "undo"),
    ("undo the last fix", "undo"), ("file that as an issue", "issue"),
    ("file it as a github issue", "issue"), ("open an issue for that bug", "issue"),
    ("trust this laptop for updates", "trust"), ("sign my own updates", "trust"),
    ("make this laptop the update source", "trust"), ("use this computer as the update source", "trust"),
    ("stop signing my own updates", "distrust"), ("what happened with that fix", "status"),
    ("try the github report again", "retry"),
):
    hit = bugfix.classify(phrase)
    routed = intent.match(phrase)
    check(hit and hit[0] == action and routed and routed[0] == "fix_bug" and routed[1].get("action") == action,
          action + " phrase: " + phrase)

for phrase in ("fix the typo in my notes", "I found a bug in the article", "apply that wallpaper",
               "undo that email", "get updates from my computer", "stop updates from my computer",
               "stop the improvement loop", "what is the improvement loop doing", "this is broken"):
    check(bugfix.classify(phrase) is None, "not a bug-fix phrase: " + phrase)
check(intent.match("stop the improvement loop")[0] == "improve_os", "the kill-switch phrase is unchanged")
check(intent.match("get updates from my computer") is None, "pairing another computer is not this intent")
check("found a bug" in everyday.MATCH.pattern or everyday.MATCH.search("i found a bug, fix it"),
      "the desk's instant list includes the bug phrase")

# --- context, and a token in the logs is not kept ---
screen = os.path.join(state, "screen.txt")
log = os.path.join(state, "app.log")
open(screen, "w", encoding="utf-8").write("Total is 12")
open(log, "w", encoding="utf-8").write("desk: boom " + TOKEN + "\n")
os.environ["LLMOS_SCREEN_TEXT"] = screen
os.environ["LLMOS_BUGFIX_LOG"] = log
os.environ["LLMOS_BUGFIX_SHOT"] = ""
ctx = bugfix.capture_context()
check(ctx["screen_text"] == "Total is 12", "screen text is captured when the OS has it")
check(TOKEN not in ctx["logs"] and "[secret]" in ctx["logs"], "a token in the logs is redacted")
os.environ.pop("LLMOS_SCREEN_TEXT", None)
os.environ.pop("LLMOS_BUGFIX_LOG", None)

# --- rails on the task, kill switch, daily cap, no duplicate ---
seen = []
bugfix.set_runner(lambda item: seen.append(item))
selfloop_ctl.set_killed(True)
stopped = bugfix.report("the total is wrong")
check("stopped" in stopped.lower() and seen == [], "the kill switch refuses before a task is saved")
check(selfloop_ctl.load_backlog() == [] or all(row.get("source") != "voice" for row in selfloop_ctl.load_backlog()),
      "a refused report does not leave a voice task")
selfloop_ctl.set_killed(False)
now = time.time()
selfloop_ctl._save_runs([now - 10] * 8)
capped = bugfix.report("the total is wrong")
check("rate limit" in capped and seen == [], "the daily cap refuses the report")
selfloop_ctl._save_runs([])

item_text = bugfix.report("the total is wrong", capture=lambda: {
    "window_id": "gnumeric", "window_name": "the spreadsheet",
    "screen_text": "Total is 12", "screenshot": "", "logs": "desk: boom"})
check(seen and seen[0]["source"] == "voice" and seen[0]["mode"] == "device" and seen[0]["backend"] == "local",
      "the task is device mode on the local backend")
check("selfloop_ctl.py" in seen[0]["detail"] and "ota.py" in seen[0]["detail"]
      and "full suite" in seen[0]["detail"].lower() and "model server" in seen[0]["detail"],
      "the task tells the model the rails")
check("the spreadsheet" in item_text and "local model" in item_text and "apply that fix" in item_text,
      "the reply names the window and that nothing is installed yet")
again = bugfix.report("the total is wrong")
check("already looking" in again and len(seen) == 1, "the same open bug is not started twice")
bugfix.set_runner(None)
refused_norm = selfloop_local._normalize(os.path.join(state, "pkg"), "llmos/ota.py")
check(refused_norm[0] is None and "rails" in (refused_norm[1] or ""), "an edit of ota.py is still refused")
refused_ctl = selfloop_local._normalize(os.path.join(state, "pkg"), "llmos/selfloop_ctl.py")
check(refused_ctl[0] is None and "rails" in (refused_ctl[1] or ""), "an edit of selfloop_ctl.py is still refused")

# --- voice config keeps the caps and forces approval ---
forced = selfloop.voice_config(selfloop_ctl.load_config())
check(forced["mode"] == "device" and forced["backend"] == "local" and forced["require_approval"] is True,
      "a spoken fix forces device mode, the local model, and approval")
check(forced["max_iterations"] == 3 and forced["max_light_tests"] == 24,
      "the iteration cap and the light-test cap are unchanged")
loaded = selfloop_ctl.load_config()
check(loaded["require_approval"] is False and loaded["backend"] == "cloud",
      "the config file itself is not rewritten")

# --- the command that would start the loop ---
argv = bugfix.launch_argv("/tmp/selfloop.py", "bug-1")
joined = " ".join(argv)
check("nice" in argv and "19" in argv and "--from-voice" in argv and "bug-1" in argv,
      "the loop is started under nice, for that one bug")
check("rc-service" not in joined and "run-host-tests" not in joined and "systemctl" not in joined,
      "starting the loop does not restart a service or launch the full suite")
script = os.path.join(state, "selfloop.py")
open(script, "w", encoding="utf-8").write("raise SystemExit(0)\n")
os.environ["LLMOS_SELFLOOP_BIN"] = script
os.environ["LLMOS_BUGFIX_RUN"] = "1"
spawned = []


def capture_popen(cmd, **_kwargs):
    spawned.append(list(cmd))


check(bugfix.start_loop("bug-1", popen=capture_popen) is True and spawned and "rc-service" not in " ".join(spawned[0]),
      "the background start uses that command and does not restart a service")
os.environ["LLMOS_BUGFIX_RUN"] = "0"

# --- one staged run: approval on, live tree untouched, spoken summary ---
pkg_root = tempfile.mkdtemp(prefix="live-", dir=state)
pkg = os.path.join(pkg_root, "usr", "lib", "llmos")
os.makedirs(os.path.join(pkg, "llmos"))
open(os.path.join(pkg, "llmos", "__init__.py"), "w", encoding="utf-8").write('VERSION = "1.8.9"\n')
open(os.path.join(pkg, "llmos", "marker.py"), "w", encoding="utf-8").write('VALUE = "old"\n')
installs = []


def implement(support, item):
    path = os.path.join(support, "src", "rootfs", "usr", "lib", "llmos", "llmos", "marker.py")
    open(path, "w", encoding="utf-8").write('VALUE = "new"\n')
    return {"changed": ["llmos/marker.py"]}


def select(_paths):
    return ["tools/test-bugfix.py"], "one light test"


def gate(_support, tests):
    check(tests == ["tools/test-bugfix.py"], "the device gate is the named light test")
    return True, "host suites: 1 run, 0 failed"


voice_item = {
    "id": "bug-voice1", "title": "Fix a bug the owner found: the total is wrong",
    "description": "the total is wrong", "detail": bugfix.RAILS_NOTE, "source": "voice",
    "status": "open", "mode": "device", "backend": "local",
}
staged = selfloop.run_once(
    cfg=forced, backlog=[voice_item], now=time.time(), package_src=pkg,
    dest_parent=os.path.join(state, "stages"), implement=implement, select=select, gate=gate,
    install=lambda *_a: installs.append("no") or (True, "should not install"))
check(staged["action"] == "queued" and installs == [], "approval queues the fix and does not install it")
check("apply that fix" in (staged.get("spoken") or "") and "marker.py" in (staged.get("spoken") or ""),
      "the spoken summary names the change and asks before installing")
check(open(os.path.join(pkg, "llmos", "marker.py"), encoding="utf-8").read() == 'VALUE = "old"\n',
      "the live package is not edited while the fix is staged")
queued = selfloop_ctl.load_queue()
check(queued and queued[-1].get("source") == "voice" and "--install-local" in queued[-1].get("ship", "")
      and "&&" in queued[-1]["ship"] and "|" not in queued[-1]["ship"],
      "the queued command is the light gate && the local installer")
selfloop_ctl.assert_gated(queued[-1]["ship"])

# --- trust this laptop, and an external source stays paired ---
config.settings.set("ota", {"url": "http://10.1.2.3:8781", "key": "ssh-ed25519 AAAA", "fp": "ABCD-EF01",
                            "name": "desk", "auto": True})
trusted = bugfix.trust_self()
check("key code" in trusted and "ABCD-EF01" not in trusted and bugfix.self_trusted(),
      "trusting the laptop speaks its own key code")
fp = trusted.split("key code is ", 1)[1].split(".", 1)[0]
check(len(fp) == 9 and fp[4] == "-", "the key code is the short fingerprint")
again_trust = bugfix.trust_self()
check(fp in again_trust, "trusting again reuses the same key")
check(config.settings.get("ota", {}).get("url") == "http://10.1.2.3:8781",
      "an external update source stays paired")
status = ota.status_text()
check("10.1.2.3" in status and fp in status, "status names the external source and this laptop's key")
check("rc-service" not in trusted, "trusting the laptop does not restart a service")

# --- apply is refused until trusted was... it is trusted. undo the staged fix first via the phrase ---
ships = []


def fake_ship(item):
    ships.append(item.get("id"))
    selfloop_ctl.save_queue([row for row in selfloop_ctl.load_queue() if str(row.get("id")) != str(item.get("id"))])
    return 0, "installed by the test"


bugfix.set_ship(fake_ship)
# drop trust briefly
os.remove(os.path.join(bugfix.key_dir(), "trusted"))
refused_apply = bugfix.apply()
check("isn't trusted" in refused_apply and ships == [], "apply does nothing until the laptop is trusted")
bugfix.trust_self()
applied = bugfix.handle_line("apply that fix")
check(ships == ["bug-voice1"] and "marker.py" in applied and "Installed" in applied and "health check passed" in applied,
      "apply speaks the change, then installs")
check(all(row.get("id") != "bug-voice1" for row in selfloop_ctl.load_queue()),
      "apply selects the spoken fix")
outside = tempfile.mkdtemp(prefix="outside-", dir="/tmp")
open(os.path.join(outside, "keep"), "w", encoding="utf-8").write("stay")
inside = os.path.join(state, "staging", "drop-me")
os.makedirs(inside)
open(os.path.join(inside, "note"), "w", encoding="utf-8").write("gone")
selfloop_ctl.save_queue([{
    "id": "bug-drop", "source": "voice", "install": "local", "title": "drop me",
    "description": "the total is wrong", "spoken": "staged",
    "staging": inside, "support": outside, "tests": ["tools/test-bugfix.py"], "ship": queued[-1]["ship"],
}])
dropped = bugfix.handle_line("undo that fix")
check("Nothing was installed" in dropped and not os.path.exists(inside), "undo drops the staged copy")
check(os.path.isfile(os.path.join(outside, "keep")), "undo does not delete a directory outside the loop's files")
check(selfloop_ctl.load_queue() == [], "the staged fix is no longer waiting")
shutil.rmtree(outside, ignore_errors=True)

# --- installed fix: rollback uses the backup, and a backup outside the state dir is refused ---
live = os.path.join(state, "installed-root")
rel = os.path.join("usr", "lib", "llmos", "llmos", "marker.py")
os.makedirs(os.path.join(live, "usr", "lib", "llmos", "llmos"))
open(os.path.join(live, rel), "w", encoding="utf-8").write('VALUE = "new"\n')
backup = os.path.join(state, "ota", "backup-test.tar")
os.makedirs(os.path.dirname(backup), exist_ok=True)
buf = io.BytesIO(b'VALUE = "old"\n')
with tarfile.open(backup, "w") as bundle:
    info = tarfile.TarInfo("usr/lib/llmos/llmos/marker.py")
    info.size = len(buf.getvalue())
    bundle.addfile(info, buf)
bugfix._write_json(bugfix.receipt_file(), {
    "ok": True, "backup": backup, "new": [], "root": live,
    "names": ["usr/lib/llmos/llmos/marker.py"], "health": "ok", "item": "bug-installed",
})
undone = bugfix.undo()
check("previous files" in undone and "will not merge" in undone, "undo of an install says the files went back")
check(open(os.path.join(live, rel), encoding="utf-8").read() == 'VALUE = "old"\n',
      "rollback restored the previous file")
bugfix._write_json(bugfix.receipt_file(), {
    "ok": True, "backup": os.path.join(state, "not-here.tar"), "new": [], "root": live,
    "names": ["usr/lib/llmos/llmos/marker.py"], "health": "ok", "undone": False,
})
# the receipt reader skips undone; this one is not undone but the backup is missing and, if present, must be under state.
# point it outside the state dir
evil = os.path.join(tempfile.gettempdir(), "llmos-bugfix-evil.tar")
open(evil, "wb").close()
bugfix._write_json(bugfix.receipt_file(), {
    "ok": True, "backup": evil, "new": [], "root": live, "names": [], "health": "ok",
})
refused_undo = bugfix.undo()
check("couldn't put the previous files back" in refused_undo, "a backup outside the loop's files is not restored")
os.remove(evil)

# --- GitHub: no token queues, a network failure queues, retry sends, never merges ---
os.environ.pop("LLMOS_GITHUB_TOKEN", None)
body_calls = fake_http(github_ok)
quiet = ghreport.submit_pr({
    "item": "bug-queued", "description": "the total is wrong " + TOKEN,
    "diff": "--- a/marker.py\n+++ b/marker.py\n", "tests": "tools/test-bugfix.py; light gate passed",
    "health": "ok", "files": [{"path": "Support files/src/rootfs/usr/lib/llmos/llmos/marker.py",
                               "content": 'VALUE = "new"\n'}],
}, transport=body_calls)
check("don't have a GitHub token" in quiet and body_calls.calls == [], "no token means nothing is sent")
saved = ghreport.load_reports()
raw_queue = open(ghreport.reports_path(), encoding="utf-8").read()
check(saved and saved[0]["status"] == "pending" and saved[0]["kind"] == "pr", "the pull request is queued")
check(TOKEN not in raw_queue and "[secret]" in raw_queue, "the queued report does not contain the token")
check("## Bug" in saved[0]["body"] and "## Diff" in saved[0]["body"] and "## Light tests" in saved[0]["body"]
      and "## Health check" in saved[0]["body"] and "not merged" in saved[0]["body"],
      "the saved pull request has the bug, the diff, the tests, and the health check")

os.environ["LLMOS_GITHUB_TOKEN"] = TOKEN
ghreport.save_reports([])


def down(_method, _url, _payload, _token):
    raise OSError("offline")


offline = ghreport.submit_pr({
    "item": "bug-offline", "description": "the total is wrong",
    "diff": "diff", "tests": ["tools/test-bugfix.py"], "health": "ok",
    "files": [{"path": "Support files/src/rootfs/usr/lib/llmos/llmos/marker.py", "content": "x = 1\n"}],
}, transport=down)
check("try again later" in offline and "not merged" in offline, "a network failure queues the pull request")
ok_transport = fake_http(github_ok)
retried = ghreport.retry(force=True, transport=ok_transport)
check("pull/99" in retried and "not merged" in retried, "retry sends the saved pull request and does not merge it")
check(all("merge" not in url.lower() for _m, url, _p, _t in ok_transport.calls),
      "no GitHub call is a merge")
check(any(url.endswith("/pulls") for _m, url, _p, _t in ok_transport.calls), "retry opens a pull request")
check(all(token == TOKEN and TOKEN not in json.dumps(payload or {}) for _m, _u, payload, token in ok_transport.calls),
      "the token is a header, not part of the report")

# a real receipt: diff, health, and the rails files are not in the branch
live2 = os.path.join(state, "receipt-root")
os.makedirs(os.path.join(live2, "usr", "lib", "llmos", "llmos"))
open(os.path.join(live2, rel), "w", encoding="utf-8").write('VALUE = "new"\n')
open(os.path.join(live2, "usr", "lib", "llmos", "llmos", "ota.py"), "w", encoding="utf-8").write("x = 1\n")
backup2 = os.path.join(state, "ota", "backup-report.tar")
old = b'VALUE = "old"\n'
with tarfile.open(backup2, "w") as bundle:
    info = tarfile.TarInfo("usr/lib/llmos/llmos/marker.py")
    info.size = len(old)
    bundle.addfile(info, io.BytesIO(old))
bugfix._write_json(bugfix.receipt_file(), {
    "ok": True, "backup": backup2, "new": [], "root": live2, "health": "ok",
    "names": ["usr/lib/llmos/llmos/marker.py", "usr/lib/llmos/llmos/ota.py", "usr/lib/llmos/llmos/selfloop_ctl.py"],
})
sent = fake_http(github_ok)
said = bugfix.finish_installed({
    "id": "bug-report", "description": "the total is wrong", "title": "the total is wrong",
    "tests": ["tools/test-bugfix.py"], "summary": "host suites: 1 run, 0 failed",
}, transport=sent)
check("pull/99" in said and "not merged" in said, "a kept install opens a pull request")
pulls = [payload for method, url, payload, _t in sent.calls if url.endswith("/pulls")]
check(len(pulls) == 1 and pulls[0]["base"] == "main" and pulls[0]["head"].startswith("llmos-fix/")
      and "merge" not in pulls[0], "the pull request targets a new branch and has no merge field")
body = pulls[0]["body"]
check("the total is wrong" in body and "VALUE" in body and "tools/test-bugfix.py" in body and "ok" in body,
      "the pull request body has the bug, the diff, the light tests, and the health check")
blobs = [payload for _m, url, payload, _t in sent.calls if url.endswith("/git/blobs")]
paths = [row["path"] for _m, url, payload, _t in sent.calls if url.endswith("/git/trees") for row in payload["tree"]]
check(any(p.endswith("llmos/marker.py") for p in paths), "the changed program file is in the branch")
check(not any(p.endswith("ota.py") or p.endswith("selfloop_ctl.py") for p in paths),
      "the rails files are not part of the same update")
refs = [payload["ref"] for _m, url, payload, _t in sent.calls if url.endswith("/git/refs")]
check(refs and refs[0].startswith("refs/heads/llmos-fix/") and refs[0] != "refs/heads/main",
      "the push is a new branch, not main")
check(not any(url.endswith("/merges") or "/merge" in url for _m, url, _p, _t in sent.calls),
      "the report never calls the merge API")

# failed fix -> issue, also queued when the network is down
bugfix.remember_failure({"id": "bug-fail", "description": "the total is wrong"}, "the light gate did not pass")
issue_down = bugfix.file_issue(transport=down)
check("try again later" in issue_down, "a failed fix's issue is queued when GitHub is down")
issue_ok = fake_http(github_ok)
filed = ghreport.retry(force=True, transport=issue_ok)
check("issues/7" in filed, "retry files the saved issue")
check(any(url.endswith("/issues") for _m, url, _p, _t in issue_ok.calls), "the call is an issue, not a merge")
check(not any(url.endswith("/pulls") or "merge" in url for _m, url, _p, _t in issue_ok.calls),
      "a failed fix does not open or merge a pull request")
issue_body = [payload["body"] for _m, url, payload, _t in issue_ok.calls if url.endswith("/issues")][0]
check("the total is wrong" in issue_body and "not installed" in issue_body.lower(),
      "the issue has the bug and says the fix was not installed")

# token file is private
path = bugfix.save_github_token(TOKEN)
mode = os.stat(path).st_mode & 0o777
check(mode == 0o600, "the token file is mode 0600")
try:
    bugfix.save_github_token("not-a-token")
    check(False, "a token that is not a PAT is refused")
except ValueError:
    check(True, "a token that is not a PAT is refused")

# desk phrases
bugfix.set_runner(lambda item: None)
bugfix.set_ship(fake_ship)
desk = Desk()
check(everyday.handle(desk, "Hey, I found a bug here, fix it") and "apply that fix" in (desk.said or ""),
      "the desk answers the spoken bug report itself")
desk2 = Desk()
check(everyday.handle(desk2, "what happened with that fix") and desk2.said, "the desk can say what happened")
src = open(bugfix.__file__, encoding="utf-8").read() + open(ghreport.__file__, encoding="utf-8").read()
check("rc-service" not in src and "/merges" not in src and "auto_merge" not in src,
      "the bug-fix code does not restart services or merge")

# a swapped key is not trusted
priv = os.path.join(bugfix.key_dir(), "selfloop")
os.remove(priv)
os.remove(priv + ".pub")
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "other", "-f", priv],
               check=True, stdout=subprocess.DEVNULL)
os.chmod(priv, 0o600)
swapped = bugfix.trust_self()
check("Nothing was trusted" in swapped and not bugfix.self_trusted(),
      "a private key that does not match the pin is not trusted")

print(f"bugfix: {fails} failed")
sys.exit(1 if fails else 0)
