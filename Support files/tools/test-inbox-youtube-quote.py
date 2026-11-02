#!/usr/bin/env python3
"""Host tests for roadmap tasks 1, 3 and 5. No network, no display, no model.

1. Inbox-zero phrasings route to mail_triage (not an Amazon search) and one call
   sorts the stub inbox through to the end, or to 200 messages. Hands-off and
   balanced do not ask. The reply is one sentence plus the urgent senders.
2. "play a youtube video of …" opens a YouTube search in the installed browser
   when mpv is missing, and still calls play_media (ytsearch) when mpv and
   yt-dlp are present. "open the browser" is unchanged.
3. "quote <person>" is a Wikiquote lookup: the window shows a line from the
   stubbed page with that page's URL. A miss is said plainly. The model note
   is scrubbed.

Run: python3 tools/test-inbox-youtube-quote.py
"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"),
                  LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import agent, config, intent, llm, mail, media, tools, web  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Ctx:
    """Records questions, windows and browser launches. Answers yes if asked."""
    headless = False

    def __init__(self):
        self.asked = []
        self.windows = []
        self.launched = []
        self.tainted = False

    def confirm_action(self, tool, shown, risk):
        self.asked.append(getattr(tool, "name", tool))
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

    def show_ui(self, spec):
        self.windows.append(spec)

    def show_box(self, title, rows):
        self.windows.append({"title": title, "rows": rows})

    def launch(self, argv, name=None):
        self.launched.append((list(argv), name))

    def new_stream(self):
        return "s"

    def on_text(self, stream, text):
        pass

    def end_stream(self, stream):
        pass


def classify(system, user, schema, max_tokens=3000):
    # The instruction line names every category, including "newsletter". Judge the message itself.
    low = user.split("Return JSON", 1)[0].lower()
    if "unsubscribe" in low or "newsletter" in low:
        return {"category": "newsletter", "needs_reply": False, "urgent": False, "summary": "A newsletter."}
    return {"category": "personal", "needs_reply": True, "urgent": "urgent" in low,
            "summary": "A person wrote."}


def message(uid, sender, subject, snippet):
    return {"uid": str(uid), "from": sender, "subject": subject, "date": "", "snippet": snippet}


def install_mail(messages):
    """Stub mail.unread / mail.move / mail.count_unread. Newest messages are last in `messages`."""
    moved, sent = [], []

    def unread(limit=20, folder="INBOX"):
        live = [m for m in messages if m["uid"] not in moved]
        return list(reversed(live[-limit:]))

    def move(uids, kind="archive", folder="INBOX"):
        done = []
        for uid in uids:
            uid = str(uid)
            if uid not in moved:
                moved.append(uid)
                done.append(uid)
        return done, "Archive"

    def count_unread(folder="INBOX"):
        return sum(1 for m in messages if m["uid"] not in moved)

    def send(*a, **k):
        sent.append("send")
        return None

    def reply(*a, **k):
        sent.append("reply")
        return None

    mail.unread, mail.move, mail.count_unread = unread, move, count_unread
    mail.send, mail.reply = send, reply
    return moved, sent


def account():
    config.save_json(config.data("mail.json"), {
        "address": "me@example.com", "password": "secret", "name": "Me",
        "imap_host": "127.0.0.1", "smtp_host": "127.0.0.1",
        "imap_port": 993, "smtp_port": 587, "imap_ssl": True, "smtp_security": "starttls"})


NEWS = message("n1", "Deals <news@shop.example>", "Weekly newsletter", "Unsubscribe from these emails")
ALICE = message("p1", "Alice <alice@example.com>", "Dinner on Friday?", "This is urgent: can you make Friday?")


# ---------------------------------------------------------------- inbox zero
print("inbox zero")
config.settings.set("autonomy", "hands-off")
config.settings.set("internet", "yes")
account()
real_json = llm.complete_json
llm.complete_json = classify
real_mail = (mail.unread, mail.move, mail.count_unread, mail.send, mail.reply)

for phrase in ("I need to get to inbox zero today", "get me to inbox zero", "inbox zero", "clean up my inbox"):
    got = intent.match(phrase)
    check(got == ("mail_triage", {}), f"{phrase!r} -> mail_triage, got {got}")

check(intent.match("get me some batteries") == ("browse", {"site": "https://www.amazon.com/s?k=batteries"}),
      "get me some batteries still searches Amazon")
check(intent.match("get me to the station") == (
    "browse", {"site": "https://www.google.com/maps/dir/?api=1&destination=the+station"}),
      "get me to the station still opens directions")

moved, sent = install_mail([NEWS, ALICE])
ctx = Ctx()
reply = agent.run(ctx, "I need to get to inbox zero today", [])
check(not ctx.asked, f"hands-off asks nothing, asked {ctx.asked}")
check(moved == ["n1"], f"newsletter archived, personal stays, moved {moved}")
check(sent == [], f"no reply was sent, sent {sent}")
check(reply == "Archived 1; 1 still needs you. Urgent: Alice.", f"hands-off summary: {reply!r}")
check("ask again" not in reply.lower(), "summary does not say ask again")
check("\n" not in reply, "summary is a single line")

config.settings.set("autonomy", "balanced")
moved, sent = install_mail([NEWS, ALICE])
ctx = Ctx()
out = agent.execute(ctx, "mail_triage", {})
check(not ctx.asked, f"balanced asks nothing for triage, asked {ctx.asked}")
check(moved == ["n1"] and sent == [], f"balanced archives the newsletter only, moved {moved} sent {sent}")
check(out == "Archived 1; 1 still needs you. Urgent: Alice.", f"balanced summary: {out!r}")
check("ask again" not in out.lower(), "balanced summary does not say ask again")

config.settings.set("autonomy", "hands-off")
many = [message(i, "Deals <news@shop.example>", "Weekly newsletter", "Unsubscribe") for i in range(1, 211)]
moved, sent = install_mail(many)
ctx = Ctx()
out = agent.execute(ctx, "mail_triage", {})
check(len(moved) == 200, f"stops at 200 messages, archived {len(moved)}")
check(not ctx.asked and sent == [], "cap run asks nothing and sends nothing")
check("10 more unread were not sorted" in out, f"names the number left at the cap: {out!r}")
check("ask again" not in out.lower(), "cap summary does not say ask again")

moved, sent = install_mail([NEWS, ALICE])
ctx = Ctx()
out = agent.execute(ctx, "mail_triage", {})
check("more unread" not in out, f"a short inbox does not name a remainder: {out!r}")

llm.complete_json = real_json
mail.unread, mail.move, mail.count_unread, mail.send, mail.reply = real_mail


# ---------------------------------------------------------------- youtube
print("youtube")
real_which = tools.shutil.which
real_display = tools._display_available
real_play = media.play
real_run = media.subprocess.run


def which_present(name, *a, **k):
    if name in ("mpv", "yt-dlp"):
        return "/usr/bin/" + name
    return real_which(name, *a, **k)


def which_absent(name, *a, **k):
    if name in ("mpv", "yt-dlp"):
        return None
    return real_which(name, *a, **k)


class Proc:
    returncode = 0
    stderr = ""
    stdout = "https://www.youtube.com/watch?v=moon\tMoon landing\tNASA\t10:00\t\tfalse\n"


found = []


def fake_run(cmd, **k):
    found.append(list(cmd))
    return Proc()


tools.shutil.which = which_present
media.subprocess.run = fake_run
try:
    info = media.find("the moon landing")
finally:
    media.subprocess.run = real_run
check(any("ytsearch1:the moon landing" in str(part) for cmd in found for part in cmd),
      f"media.find uses ytsearch, commands {found}")
check(info.get("url", "").startswith("https://www.youtube.com/watch"), f"media.find parsed a result, got {info}")

played = []


def fake_play(query, audio_only=False):
    played.append(query)
    return {"title": "Moon landing", "channel": "NASA", "duration": "10:00", "video": False, "audio": True}


media.play = fake_play
ctx = Ctx()
reply = agent.run(ctx, "play a youtube video of the moon landing", [])
check(played == ["the moon landing"], f"mpv present: shortcut calls play_media, played {played}")
check(not ctx.launched, f"mpv present: browser was not opened, launched {ctx.launched}")
check("Moon landing" in reply, f"play reply: {reply!r}")

tools.shutil.which = which_absent
tools._display_available = lambda: True
media.play = real_play
played.clear()
ctx = Ctx()
reply = agent.run(ctx, "play a youtube video of the moon landing", [])
urls = [arg for argv, _name in ctx.launched for arg in argv if "youtube.com/results?search_query=" in str(arg)]
check(intent.match("play a youtube video of the moon landing") == ("play_media", {"query": "the moon landing"}),
      "the phrase still matches play_media")
check(urls == ["https://www.youtube.com/results?search_query=the+moon+landing"],
      f"mpv missing: YouTube search opened, urls {urls}")
check("Google Chrome" in reply, f"reply names the browser: {reply!r}")
check(played == [], f"mpv missing: play_media did not run, played {played}")
check("no such tool" not in reply.lower(), f"absent run is not 'no such tool': {reply!r}")

ctx = Ctx()
browser = agent.run(ctx, "open the browser", [])
check(intent.match("open the browser") == ("browse", {}), "open the browser is unchanged")
check("Google Chrome" in browser and not any("youtube.com/results" in str(arg) for argv, _n in ctx.launched for arg in argv),
      f"open the browser does not search YouTube: {browser!r} {ctx.launched}")

tools.shutil.which = real_which
tools._display_available = real_display
media.play = real_play


# ---------------------------------------------------------------- quotes
print("quotes")
for phrase, who in (("quote Ada Lovelace", "Ada Lovelace"),
                    ("Quote Ada Lovelace.", "Ada Lovelace"),
                    ("a real quote from Ada Lovelace", "Ada Lovelace")):
    got = intent.match(phrase)
    check(got == ("real_quote", {"who_or_topic": who}), f"{phrase!r} -> {got}")
check(intent.match("how does a rainbow form") is None, "a rainbow question is not a quote lookup")

LINE = "That brain of mine is something more than merely mortal, as time will show."
PAGE = "https://en.wikiquote.org/wiki/Ada_Lovelace"
real_search, real_read = web.search, web.read


def search(query, n=6):
    return [{"title": "Ada Lovelace - Wikiquote", "url": PAGE, "snippet": LINE}]


def read(url, limit=6000):
    return {"url": url, "title": "Ada Lovelace - Wikiquote",
            "text": "Wikiquote\nSee also\n1843\n" + LINE + "\nExternal links\n"}


web.search, web.read = search, read
ctx = Ctx()
out = tools.real_quote({"who_or_topic": "Ada Lovelace"}, ctx)
blocks = [b for spec in ctx.windows for b in spec.get("blocks", [])]
check(len(blocks) == 1 and blocks[0].get("type") == "quote", f"one quote block, got {blocks}")
check(blocks and blocks[0].get("text") == LINE, f"block text is the page line, got {blocks}")
check(blocks and blocks[0].get("source") == PAGE, f"block source is the page, got {blocks}")
check(LINE in out, "the tool returns the page line")
scrubbed = agent.scrub(out)
check("do not repeat" not in scrubbed.lower(), f"scrub strips the model note: {scrubbed!r}")
check(LINE in scrubbed, "scrub keeps the sourced line")

web.search = lambda query, n=6: []
ctx = Ctx()
out = tools.real_quote({"who_or_topic": "Not A Real Person Zzz"}, ctx)
check(out == "No Wikiquote page for Not A Real Person Zzz, so there is no sourced quote.", f"no page: {out!r}")
check(not ctx.windows, "no page: no invented quote window")

web.search = lambda query, n=6: [{"title": "Nobody", "url": "https://en.wikiquote.org/wiki/Nobody", "snippet": ""}]
web.read = lambda url, limit=6000: {"url": url, "title": "Nobody", "text": "See also\nCategories\nHi\n"}
ctx = Ctx()
out = tools.real_quote({"who_or_topic": "Nobody"}, ctx)
check(out == "No quoted line on https://en.wikiquote.org/wiki/Nobody, so there is no sourced quote.",
      f"no line: {out!r}")
check(not ctx.windows, "no line: no invented quote window")

web.search, web.read = real_search, real_read

print(f"{fails} failed" if fails else "all checks passed")
sys.exit(1 if fails else 0)
