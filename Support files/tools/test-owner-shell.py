#!/usr/bin/env python3
"""Explicit shell lines run as root, in order, and a command that prints a URL and keeps going is left running.

The two lines that failed on the laptop:
  install tailscale with curl -fsSL tailscale.com/install.sh | sh then run tailscale up --ssh
  run tailscale set --ssh
Neither matched a route, so the model was asked and did not run them. run_command also hid output until the
process exited, and after 10 minutes threw that output away.

Run: python3 tools/test-owner-shell.py
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
_HOME = tempfile.mkdtemp(prefix="llmos-owner-shell-")
os.environ.update(LLMOS_HOME=_HOME, LLMOS_ETC=os.path.join(_HOME, "etc"),
                  LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent, config, intent, llm, rootd, rootd_client, system, tools  # noqa: E402

PHRASE_INSTALL = "install tailscale with curl -fsSL tailscale.com/install.sh | sh then run tailscale up --ssh"
PHRASE_SET = "run tailscale set --ssh"
CURL = "curl -fsSL tailscale.com/install.sh | sh"
UP = "tailscale up --ssh"
LOGIN = "https://login.example.com/a/xyz"

fails = []


def check(ok, label):
    print(("ok " if ok else "FAIL ") + label)
    if not ok:
        fails.append(label)


class Ctx:
    headless = False

    def __init__(self, allow=True):
        self.allow = allow
        self.asked = []
        self.statuses = []
        self.tainted = False

    def confirm_action(self, tool, shown, risk):
        self.asked.append(getattr(tool, "name", tool))
        return self.allow

    def confirm_network(self, name, shown):
        self.asked.append("network:" + name)
        return self.allow

    def begin_tool(self, *a):
        pass

    def end_tool(self, *a):
        pass

    def status(self, text):
        self.statuses.append(text)


class RunCtx(Ctx):
    ask_only = False

    def __init__(self):
        super().__init__(True)
        self.replies = []

    def new_stream(self):
        return object()

    def on_text(self, st, text):
        self.replies.append(text)

    def end_stream(self, st):
        pass


def kill_proc(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=2)
    except Exception:
        pass


# ---------------------------------------------------------------- intent
got = intent.match(PHRASE_INSTALL)
check(got == ("run_command", {"command": CURL, "commands": [CURL, UP]}),
      f"install-then-run is both commands in order: {got}")
check(intent.is_chain(PHRASE_INSTALL) is False, "the install phrase is not a model chain")
check(intent.match(PHRASE_SET) == ("run_command", {"command": "tailscale set --ssh"}),
      f"run tailscale set --ssh: {intent.match(PHRASE_SET)}")
check(intent.match("execute tailscale set --ssh") == ("run_command", {"command": "tailscale set --ssh"}),
      "execute … is the same command")
check(intent.match("please run tailscale set --ssh") == ("run_command", {"command": "tailscale set --ssh"}),
      "please run … drops the please")
check(intent.match("`run tailscale set --ssh`") == ("run_command", {"command": "tailscale set --ssh"}),
      "a wrapping pair of backticks is not part of the command")
check(intent.match("run tailscale up --ssh") == ("run_command", {"command": UP}), "run tailscale up --ssh")
check(intent.match("tailscale set --ssh") == ("run_command", {"command": "tailscale set --ssh"}),
      "the command itself, with no run in front")
check(intent.match(CURL) == ("run_command", {"command": CURL}), "a bare curl | sh line is that command")
check(intent.match("run the command tailscale set --ssh") == ("run_command", {"command": "tailscale set --ssh"}),
      "run the command …")

calc = intent.match("run the calculator")
check(calc == ("open_app", {"command": "calculator"}), f"run the calculator stays an app: {calc}")
spot = intent.match("install spotify")
check(spot == ("install_app", {"packages": "spotify"}), f"install spotify stays install_app: {spot}")
both = intent.match("install git and docker")
check(both is not None and both[0] == "install_app", f"install git and docker stays install_app: {both}")
flat = intent.match("install spotify with flathub")
check(flat is None or flat[0] != "run_command", f"install spotify with flathub is not a shell line: {flat}")
for q in ("what does --help do", "how do I pass --ssh to tailscale", "set my time zone to paris"):
    hit = intent.match(q)
    check(hit is None or hit[0] != "run_command", f"{q!r} is not run as a command: {hit}")

check(tools.classify_command(CURL) == tools.CHANGE, "curl | sh is a change, not destructive")
check(tools.classify_command(CURL) != tools.DESTRUCTIVE, "curl | sh is not classed destructive")
check(tools.uses_network(CURL) is True, "curl | sh uses the network")
check("When told to run or execute a command" in agent.SYSTEM_PROMPT_BASE,
      "the prompt tells the model to run a command it was given")

# ---------------------------------------------------------------- autonomy and order
real_run_shell = system.run_shell
ran = []


def fake_shell(cmd, cwd=None, env=None, on_text=None, cancel=None, poll_hook=None, timeout=600):
    ran.append(cmd)
    if "fail" in cmd:
        return ("exit", 1, "no", None)
    if on_text:
        on_text("ok")
    return ("exit", 0, "ok", None)


system.run_shell = fake_shell
config.settings.set("autonomy", "hands-off")
config.settings.set("internet", "yes")
ctx = Ctx()
out = agent.execute(ctx, "run_command", {"command": CURL, "commands": [CURL, UP]})
check(ctx.asked == [], f"hands-off does not ask: {ctx.asked}")
check(ran == [CURL, UP], f"hands-off runs both, in order: {ran}")
check(out.startswith("exit code 0\n") and UP not in out and "ok" in out, f"hands-off result: {out!r}")

ran.clear()
config.settings.set("autonomy", "hands-on")
ctx = Ctx(allow=False)
out = agent.execute(ctx, "run_command", {"command": "tailscale set --ssh"})
check(ctx.asked == ["run_command"] and ran == [], f"hands-on decline does not run: asked={ctx.asked} ran={ran} {out!r}")
ctx = Ctx(allow=True)
out = agent.execute(ctx, "run_command", {"command": "tailscale set --ssh"})
check(ctx.asked == ["run_command"] and ran == ["tailscale set --ssh"],
      f"hands-on confirm runs the command: {ran} {out!r}")

ran.clear()
config.settings.set("autonomy", "hands-off")
out = agent.execute(ctx, "run_command", {"command": "echo fail", "commands": ["echo fail", UP]})
check(ran == ["echo fail"], f"a failing step stops the rest: {ran} {out!r}")

ran.clear()

def running_shell(cmd, cwd=None, env=None, on_text=None, cancel=None, poll_hook=None, timeout=600):
    if on_text:
        on_text(LOGIN + "\n")
    return ("running", None, LOGIN + "\n", None)


system.run_shell = running_shell
ctx = Ctx()
out = tools.run_command({"command": UP}, ctx)
check(out.startswith("still running\n") and LOGIN in out, f"a URL left running is in the result: {out!r}")
check(any(LOGIN in s for s in ctx.statuses), f"the URL is shown while it runs: {ctx.statuses}")

def chat_boom(*a, **k):
    raise AssertionError("the model was asked")


real_chat = llm.chat
llm.chat = chat_boom
system.run_shell = fake_shell
ran.clear()
config.settings.set("autonomy", "hands-off")
config.settings.set("internet", "yes")
rctx = RunCtx()
try:
    reply = agent.run(rctx, PHRASE_INSTALL, [])
except Exception as e:
    reply = f"error: {type(e).__name__}: {e}"
check(ran == [CURL, UP], f"the install phrase never asks the model and runs both: {ran} reply={reply!r}")
check("ok" in str(reply).lower() and rctx.asked == [], f"the reply shows the output, no question: {reply!r} {rctx.asked}")
ran.clear()
rctx = RunCtx()
try:
    reply = agent.run(rctx, PHRASE_SET, [])
except Exception as e:
    reply = f"error: {type(e).__name__}: {e}"
check(ran == ["tailscale set --ssh"] and "ok" in str(reply).lower(),
      f"run tailscale set --ssh runs without the model: {ran} {reply!r}")
llm.chat = real_chat
system.run_shell = real_run_shell
config.settings.set("autonomy", "balanced")

# ---------------------------------------------------------------- a URL, then the command keeps running
proc = None
try:
    seen = []
    cmd = 'python3 -c \'import time; print("%s", flush=True); time.sleep(30)\'' % LOGIN
    t0 = time.monotonic()
    kind, rc, text, proc = system._run_shell_stream(cmd, cwd="/", timeout=20, url_hold=1.0, on_text=seen.append)
    elapsed = time.monotonic() - t0
    check(kind == "running" and elapsed < 8, f"URL command returns while it is still running ({elapsed:.2f}s, {kind})")
    check(LOGIN in (text or "") and any(LOGIN in s for s in seen), f"the URL was streamed: {text!r}")
    check(proc is not None and proc.poll() is None, f"the process was left running: {proc and proc.poll()}")
finally:
    kill_proc(proc)

kind, rc, text, proc = system._run_shell_stream("echo https://example.com", cwd="/", timeout=10, url_hold=1.0)
kill_proc(proc)
check(kind == "exit" and rc == 0 and "https://example.com" in (text or ""),
      f"a URL that exits is not left running: {kind} {rc} {text!r}")

# ---------------------------------------------------------------- non-root goes through rootd, not a user shell
real_euid = os.geteuid
real_popen = subprocess.Popen
real_call = rootd_client.call
try:
    os.geteuid = lambda: 1000
    subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("user shell was started"))
    sent = []

    def fake_call(verb, _timeout=None, **args):
        sent.append((verb, _timeout, dict(args)))
        return json.dumps(["exit", 0, "from-rootd"])

    rootd_client.call = fake_call
    kind, rc, out, proc = system.run_shell("tailscale set --ssh", cwd="/", timeout=600)
    check(sent and sent[0][0] == "run_shell" and sent[0][2].get("command") == "tailscale set --ssh",
          f"non-root run_shell asks rootd: {sent}")
    check(kind == "exit" and out == "from-rootd" and proc is None, f"rootd reply is the result: {kind} {out!r}")
    check(sent[0][1] == 660, f"the socket wait is the command timeout plus a minute: {sent[0][1]}")
finally:
    os.geteuid = real_euid
    subprocess.Popen = real_popen
    rootd_client.call = real_call

# ---------------------------------------------------------------- the verb itself
def bad(args):
    try:
        rootd.VERBS["run_shell"](args)
    except ValueError as e:
        return "bad args" in str(e)
    return False


for args in ({}, {"command": ""}, {"command": "  "}, {"command": 5}, {"command": "echo\x00hi"},
             {"command": "x" * 8001}, {"command": "echo hi", "timeout": 0}, {"command": "echo hi", "timeout": 601},
             {"command": "echo hi", "timeout": True}, {"command": "echo hi", "timeout": "10"},
             {"command": "echo hi", "cwd": "tmp"}, {"command": "echo hi", "extra": 1}, {"command": "echo\nhi"},
             "echo hi"):
    shown = args if not isinstance(args, dict) or not isinstance(args.get("command"), str) or len(args["command"]) < 40 else {**args, "command": args["command"][:8] + f"…({len(args['command'])})"}
    check(bad(args), f"run_shell rejects {shown!r}")

raw = rootd.VERBS["run_shell"]({"command": "echo hello"})
kind, rc, text = json.loads(raw)
check(kind == "exit" and rc == 0 and "hello" in text, f"run_shell echo hello: {raw!r}")

# ---------------------------------------------------------------- Alpine community repo
real_repos = system.APK_REPOS
real_run = subprocess.run
try:
    td = tempfile.mkdtemp(prefix="llmos-repos-")
    main = "https://dl-cdn.alpinelinux.org/alpine/v3.20/main"
    community = "https://dl-cdn.alpinelinux.org/alpine/v3.20/community"
    edge = "#https://dl-cdn.alpinelinux.org/alpine/edge/main"

    commented = os.path.join(td, "commented")
    open(commented, "w").write(main + "\n#https://dl-cdn.alpinelinux.org/alpine/v3.20/community\n")
    check(system.ensure_community_repo(commented) is True, "commented community line is enabled")
    body = open(commented).read().splitlines()
    check(community in body and not any(l.startswith("#") and community in l for l in body),
          f"community line is uncommented: {body}")

    spaced = os.path.join(td, "spaced")
    open(spaced, "w").write(main + "\n# " + community + "\n")
    check(system.ensure_community_repo(spaced) is True, "a spaced comment is uncommented")
    check(community in open(spaced).read().splitlines(), "spaced comment became the community url")

    only = os.path.join(td, "only")
    open(only, "w").write(main + "\n" + edge + "\n#https://dl-cdn.alpinelinux.org/alpine/edge/community\n")
    before = open(only).read()
    check(system.ensure_community_repo(only) is True, "main-only file gains the matching community repo")
    lines = open(only).read().splitlines()
    check(community in lines and edge in lines, f"edge stays commented, v3.20 community is added: {lines}")
    check(before.splitlines()[1] == edge, "the edge line was not rewritten in place")

    on = os.path.join(td, "on")
    text = main + "\n" + community + "\n"
    open(on, "w").write(text)
    check(system.ensure_community_repo(on) is False and open(on).read() == text, "community already on is left alone")

    target = os.path.join(td, "target")
    open(target, "w").write(main + "\n")
    link = os.path.join(td, "link")
    os.symlink(target, link)
    check(system.ensure_community_repo(link) is False and open(target).read() == main + "\n", "a symlink is refused")

    locked = os.path.join(td, "locked")
    os.mkdir(locked)
    repos = os.path.join(locked, "repositories")
    open(repos, "w").write(main + "\n")
    os.chmod(locked, 0o555)
    try:
        check(system.ensure_community_repo(repos) is False, "an unwritable repos file is left alone")
        check(open(repos).read() == main + "\n", "unwritable file is unchanged")
    finally:
        os.chmod(locked, 0o755)

    calls = []

    def fake_run(argv, **kw):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    subprocess.run = fake_run
    needs = os.path.join(td, "needs")
    open(needs, "w").write(main + "\n" + edge + "\n")
    system.APK_REPOS = needs
    system._apk_add_root(["tailscale"])
    check(calls[:2] == [["apk", "update"], ["apk", "add", "--no-progress", "tailscale"]],
          f"enabling community updates the index, then adds: {calls}")

    calls.clear()
    system.APK_REPOS = on
    system._apk_add_root(["tailscale"])
    check(calls == [["apk", "add", "--no-progress", "tailscale"]],
          f"community already on does not update first: {calls}")

    calls.clear()
    system.APK_REPOS = os.path.join(td, "missing-repositories")
    system._apk_add_root(["firefox"])
    check(calls == [["apk", "add", "--no-progress", "firefox"]],
          f"a missing repos file does not run apk update: {calls}")
finally:
    system.APK_REPOS = real_repos
    subprocess.run = real_run

print(f"\n{'all good' if not fails else str(len(fails)) + ' failure(s)'}")
for f in fails:
    print(" -", f)
sys.exit(1 if fails else 0)
