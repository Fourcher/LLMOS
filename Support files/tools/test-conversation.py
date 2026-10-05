#!/usr/bin/env python3
"""Host-side test of the never-cleared conversation (llmos/conversation.py): a follow-up continues the topic in
progress and brings only that topic's last exchanges; an unrelated request starts clean; an earlier topic comes back
as a short note when asked about; side chats are separate; topics can be resumed and forgotten.
Run: python3 tools/test-conversation.py"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import conversation as C  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


FLOW = [("what's the capital of australia?", "Canberra is the capital of Australia.", False),
        ("how many people live there?", "About 470,000 people.", True),
        ("make me a calculator", "Made the calculator.", False),
        ("make it pink", "Done.", True),
        ("music", "Now playing some rock.", False),
        ("install this on my computer", "Here is the plan.", False),
        ("what is the weather like in tokyo", "Sunny, 22°C.", False),
        ("and tomorrow?", "Rain likely.", True),
        ("write a short poem about autumn leaves", "Leaves fall softly...", False),
        ("make the poem rhyme", "Here is a rhyming version.", True),
        ("dark mode", "Done — dark mode.", False),
        ("why is my computer slow", "The model uses most of the memory.", False),
        ("what can I do about it", "Close some windows.", True),
        ("what was the capital of australia again", "Canberra.", False),
        ("new topic: tell me a joke", "Why did the…", False),
        ("another one", "Knock knock.", True)]

print("topics follow the conversation")
c = C.Chat("main")
for q, a, want in FLOW:
    got = c.continues(q)
    msgs, note = c.context(q)
    check(got == want, f"{'continues' if want else 'new topic'}: {q!r}" + ("" if got == want else f" (got {'continue' if got else 'new'})"))
    if q.startswith("what was the capital"):
        check(not msgs and "Canberra" in note, "an earlier topic comes back as a note, not as replayed messages")
    if q == "make it pink":
        check(len(msgs) == 2 and msgs[0]["content"] == "make me a calculator", "a follow-up brings only its own topic's exchange")
    c.record(q, a, got)
check(len(c.topics) == sum(1 for _, _, w in FLOW if not w), f"{len(c.topics)} topics kept")
check(all(len(c.context(x)[0]) <= C.REPLAY_MSGS for x in ("and then?", "more")), "never more than a few messages are replayed")

print("it is kept, and survives a restart")
c2 = C.Chat("main")
check(len(c2.msgs) == 2 * len(FLOW) and len(c2.topics) == len(c.topics), "the log and the topics are read back")
c2.new_topic()
check(not c2.continues("another one"), "after 'new topic' even a follow-up starts clean")

print("topics can be resumed and forgotten")
t0 = c2.topics[0]
c2.resume(t0["id"])
check(c2.current()["id"] == t0["id"] and c2.continues("how many people live there?"), "resuming an old topic makes it the one in progress")
c2.forget_topic(t0["id"])
check(all(m.get("topic") != t0["id"] for m in C.Chat("main").msgs), "a forgotten topic's messages are gone from disk")

print("a new request that only shares a verb starts clean")
r = C.Chat("recall-test")
r.record("write an email to my landlord about the leak", "No email account is set up yet.", False)
r.new_topic()
check(r.context("write a letter")[1] == "", "'write a letter' brings no note about the landlord email")
check("landlord" in r.context("what did you say about the landlord?")[1], "asking about it brings it back")

print("side chats are separate")
s = C.new_side("cooking")
s.record("give me a pasta idea", "Aglio e olio.", False)
check(C.Chat(s.id).transcript()[-1]["content"] == "Aglio e olio." and not any("pasta" in m["content"] for m in C.Chat("main").msgs),
      "a side chat keeps its own messages; the main chat never sees them")
check(any(x["id"] == s.id and x["title"] == "cooking" for x in C.side_chats()), "side chats are listed with their title")
C.delete(s.id)
check(not any(x["id"] == s.id for x in C.side_chats()), "a side chat can be deleted")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
