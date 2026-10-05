#!/usr/bin/env python3
"""Host-side test of when LLM OS asks before acting (agent.execute), per the owner's choice:
  full trust (hands-off)  nothing the owner asks for is checked with them first: email, deleting, removing
                          programs, settings, commands. The one question is the consent itself, when switching to it.
  balanced (the default)  asks before what can't be undone (and always before email leaves or the trash is emptied).
  hands-on                asks before every change.
In every mode, what an instruction inside a web page, email or file would make it do is shown first, unless the
owner turned that check off too ("follow instructions in web pages too").
Run: python3 tools/test-trust.py (no model, no VM)"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import agent, config, tools  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Ctx:
    """Records every question the OS would put to the owner; answers yes."""
    headless = False
    current_request = ""

    def __init__(self):
        self.asked = []
        self.tainted = False

    def confirm_action(self, tool, shown, risk):
        self.asked.append(tool.name)
        return True

    def confirm_network(self, name, shown):
        self.asked.append("network:" + name)
        return True

    def begin_tool(self, *a):
        pass

    def end_tool(self, *a):
        pass

    def status(self, *a):
        pass


ran = []
for name in ("mail_send", "empty_trash", "remove_software", "run_command", "read_webpage", "write_file"):
    t = tools.REGISTRY[name]
    t.fn = (lambda n: (lambda a, ctx: ran.append(n) or f"done {n}"))(name)
    t.network = None
    t.available = lambda: True          # (mail tools exist only with an account; here they are stand-ins)


def run(name, args, request, tainted=False):
    ctx = Ctx()
    ctx.current_request = request
    ctx.tainted = tainted
    ran.clear()
    out = agent.execute(ctx, name, args)
    return ctx.asked, bool(ran), out


config.settings.set("internet", "yes")
config.settings.set("guard_untrusted", True)

print("full trust (hands-off): what the owner asks for is done, nothing asked")
config.settings.set("autonomy", "hands-off")
for name, args, req in (("mail_send", {"to": "ann@example.com", "subject": "hi", "body": "hello"}, "email ann and say hello"),
                        ("empty_trash", {}, "empty the trash"),
                        ("remove_software", {"name": "vlc"}, "uninstall vlc"),
                        ("run_command", {"command": "rm -rf ~/old"}, "delete my old folder"),
                        ("change_setting", {"setting": "internet", "value": "yes"}, "turn the internet on")):
    asked, did, out = run(name, args, req)
    check(not asked and (did or name == "change_setting"), f"{name}: done without asking" + (f" (asked {asked})" if asked else ""))

print("balanced (the default): asks before what can't be undone")
config.settings.set("autonomy", "balanced")
for name, args, req, want in (("mail_send", {"to": "ann@example.com", "subject": "hi", "body": "hello"}, "email ann and say hello", True),
                              ("empty_trash", {}, "empty the trash", True),
                              ("run_command", {"command": "rm -rf ~/old"}, "delete my old folder", True),
                              ("run_command", {"command": "mkdir ~/new"}, "make a folder called new", False),
                              ("write_file", {"path": "~/a.txt", "content": "x"}, "write x to a.txt", False)):
    asked, did, out = run(name, args, req)
    check(bool(asked) == want, f"{name} {args.get('command', '')}: {'asks' if want else 'no question'}")

print("hands-on: asks before every change")
config.settings.set("autonomy", "hands-on")
asked, did, out = run("write_file", {"path": "~/a.txt", "content": "x"}, "write x to a.txt")
check(asked == ["write_file"], "writing a file asks")

print("switching to full trust is the consent: asked once, by name")
config.settings.set("autonomy", "balanced")
asked, did, out = run("change_setting", {"setting": "autonomy", "value": "hands-off"}, "full trust")
check(asked == ["change_setting"] and config.settings.get("autonomy") == "hands-off", "one question, then full trust is on")
asked, did, out = run("change_setting", {"setting": "autonomy", "value": "balanced"}, "ask me before risky things")
check(not asked and config.settings.get("autonomy") == "balanced", "going back to asking needs no question")

print("instructions from a web page, email or file are not the owner's: shown first, in every mode, unless turned off")
config.settings.set("autonomy", "hands-off")
asked, did, out = run("run_command", {"command": "rm -rf ~/old"}, "summarize this page and do what it says", tainted=True)
check(asked == ["run_command"], "full trust + a page's instruction: shown first")
asked, did, out = run("change_setting", {"setting": "guard_untrusted", "value": "off"}, "follow instructions in web pages too")
check(config.settings.get("guard_untrusted") is False, "the owner can turn that check off")
asked, did, out = run("run_command", {"command": "rm -rf ~/old"}, "summarize this page and do what it says", tainted=True)
check(not asked and did, "then a page's instruction is followed like the owner's")
config.settings.set("guard_untrusted", True)

print("the internet setting is the owner's own choice too: 'ask' asks even under full trust")
config.settings.set("internet", "ask")
tools.REGISTRY["read_webpage"].network = lambda a: True
asked, did, out = run("read_webpage", {"url": "https://example.com"}, "read example.com")
check(asked == ["network:read_webpage"], "internet 'ask' still asks")
config.settings.set("internet", "yes")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
