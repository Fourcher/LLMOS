#!/usr/bin/env python3
"""The computer's own mailbox (devmail.py + the email_* tools): it pulls the code or confirm link out of a sign-up
email, the phrases reach the right tool, and the tools are gated right (network, present-only, never a confirm link
on a background task). No network: the free service is mocked. Run: python3 tools/test-devmail.py"""
import os, sys, tempfile
from unittest import mock
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_HOME", tempfile.mkdtemp(prefix="llmos-test-"))
os.environ.setdefault("LLMOS_ETC", tempfile.mkdtemp(prefix="llmos-etc-"))
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import devmail, intent, tools, agent  # noqa: E402

fails = 0


def check(c, w):
    global fails
    print(("  ok   " if c else "  FAIL ") + w)
    if not c:
        fails += 1


# --- pulling the code / link out of real-looking messages ---
CASES = [
    ("Your OpenRouter verification code is 739204. It expires in 10 minutes.", "", "739204", None),
    ("Enter this code to sign in: 48217", "", "48217", None),
    ("", "<p>Your code is <b>A1B2C3</b></p>", "A1B2C3", None),
    ("Please confirm your email: https://openrouter.ai/verify?token=abc.def_123", "", "", "verify"),
    ("Hi, your order #1024 ships to 90210. Call 8005551234.", "", "", None),
    ("Your login code: 9981. Do not share it. Ref 2026.", "", "9981", None),
    ("Pick one: https://x.com/u?a=1 or https://acct.site/confirm-email?k=ZZ", "", "", "confirm"),
    ("Welcome! Your temporary PIN is 0421 for first login.", "", "0421", None),
    ("Use code 12 34 56", "", "", None),
]
for text, html, want_code, want_link in CASES:
    msg = {"text": text, "html": html}
    code = devmail.extract_code(msg)
    links = devmail.extract_links(msg)
    cok = code == want_code
    lok = want_link is None or (links and want_link in links[0].lower())
    check(cok and lok, f"extract {text[:40] or html[:40]!r} -> code {code!r}, link {(links[0] if links else None)}")
check(not devmail._code_shape("2026") and devmail._code_shape("739204") and not devmail._code_shape("hello")
      and devmail._code_shape("A1B2C3") and not devmail._code_shape("123"), "code-shape: not a year, not a word, not too short")

# --- the phrases reach the right tool, and never the owner's own mail set-up ---
PHRASES = {"make yourself an email": "email_make", "create an email address": "email_make",
           "give this computer an email": "email_make", "what's your email address": "email_address",
           "what is the computer's email": "email_address", "what's the code": "email_code",
           "read the verification code": "email_code", "did we get a code": "email_code",
           "wait for the code": "email_code", "open the confirmation link": "email_confirm",
           "delete the computer's email": "email_forget"}
for q, name in PHRASES.items():
    m = intent.match(q)
    check(m and m[0] == name, f"{q!r} -> {name}")
check(intent.match("wait for the code")[1].get("wait") is True, "'wait for the code' asks to wait")
check(intent.match("set up my email account me@x.com with password p") != ("email_make", {})
      and (intent.match("what is my email address") is None or intent.match("what is my email address")[0] != "email_address"),
      "the owner's own email is not grabbed by the device-email phrases")

# --- the tools: registered, gated, honest ---
R = tools.REGISTRY
check(all(n in R for n in ("email_make", "email_address", "email_code", "email_confirm", "email_forget")), "all five email tools registered")
check(R["email_make"].risk == "change" and R["email_make"].network, "email_make is a networked change")
check(R["email_code"].risk == "read" and R["email_code"].network, "email_code is a networked read")
check(R["email_confirm"].risk == "change", "email_confirm is a change (it confirms a sign-up)")
for name in ("email_address", "email_code", "email_confirm", "email_forget"):
    check(R[name].available() is False, f"{name} is offered only once the computer has a mailbox")
check(R["email_make"].available() is True, "email_make is always offered")

# email_confirm refuses on a background (headless) task -- an injected link is never followed unattended
class Headless:
    headless = True

    def show_ui(self, *a):
        pass
with mock.patch.object(devmail, "account", return_value={"address": "x@y.z", "base": "b", "password": "p", "id": "1"}):
    out = tools.REGISTRY["email_confirm"].fn({}, Headless())
    check("not done" in out.lower(), "email_confirm refuses on a background task")

# provision stores the account (service mocked); forget with none present does not crash
seq = [(200, [{"domain": "ex.test", "isActive": True, "isPrivate": False}]), (201, {"id": "acc1"}), (200, {"token": "tkn"})]
with mock.patch.object(devmail, "_api", side_effect=seq):
    addr = devmail.provision("site")
check(addr.endswith("@ex.test") and addr.startswith("site-") and devmail.address() == addr, f"provision picks an active domain and keeps it: {addr}")
devmail.forget(delete=False)
check(devmail.account() is None, "forget clears the stored mailbox")
devmail.forget(delete=False)  # no crash with none

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
