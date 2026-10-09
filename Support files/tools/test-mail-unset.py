#!/usr/bin/env python3
"""Host-side unit test: a mail_* tool asked for with no email account set up opens the
"Set up email" window and answers in plain words (not "error: set up email to use this tool").
Run: python3 tools/test-mail-unset.py  (no VM needed). Exit status 0 = pass."""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, agent

WANT = "Email isn't set up yet. Type your address and password in the Set up email window."


class OpensSetupCtx:
    """A context whose desk can open the Set up email window; records the call."""
    def __init__(self):
        self.opened = False

    def open_mail_setup(self):
        self.opened = True


class NoSetupCtx:
    """A context with no open_mail_setup attribute at all."""
    pass


def _check(label, ok, detail=""):
    if not ok:
        print(f"FAIL {label} {detail}".rstrip())
        sys.exit(1)
    print(f"ok   {label}")


# Make mail_send look unavailable (no account), the way it is on a fresh install.
mail_send = tools.REGISTRY["mail_send"]
_saved_available = mail_send.available
mail_send.available = lambda: False
try:
    args = {"to": "craig@localhost", "subject": "Hello", "body": "Hello."}

    ctx = OpensSetupCtx()
    reply = agent.execute(ctx, "mail_send", dict(args))
    _check("setup window opened", ctx.opened is True, f"(flag={ctx.opened!r})")
    _check("reply is the plain sentence", reply == WANT, f"(got {reply!r})")

    ctx2 = NoSetupCtx()
    try:
        reply2 = agent.execute(ctx2, "mail_send", dict(args))
    except Exception as e:
        _check("no open_mail_setup: no exception", False, f"(raised {e!r})")
    _check("no open_mail_setup: no exception", True)
    _check("no open_mail_setup: same reply", reply2 == WANT, f"(got {reply2!r})")
finally:
    mail_send.available = _saved_available

print("all good")
