#!/usr/bin/env python3
"""Host-side test of the model-visible wording: tool results say "you" / "your" / "on screen" / "reply",
never "the owner" (the model copied "the owner" from results into its replies).

Checks: (1) tools.py and agent.py compile; (2) no string in code that the model can see contains "the owner",
except the prompts and the tool descriptions listed in ALLOW below; (3) the hidden-note regexes still hide
each note (old and new text); (4) last_saved._opened still recognises the success replies; (5) the
shortcut and failure matchers in agent.py still work on the new text.
Run: python3 tools/test-owner-wording.py  (no VM needed)."""
import ast
import os
import py_compile
import re
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
_LLMOS = os.path.join(_ROOT, "usr/lib/llmos", "llmos")
TOOLS = os.path.join(_LLMOS, "tools.py")
AGENT = os.path.join(_LLMOS, "agent.py")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

# Allowed uses of "the owner": prompts and context the model reads as instructions (not tool results).
# Tool descriptions (@tool decorator arguments) and docstrings are skipped by the walk itself.
ALLOW = (
    "You restyle a desktop",            # tools.py _RESTYLE_SYSTEM: the CSS sub-model's prompt
    "The owner asked:",                 # tools.py restyle: the request given to that sub-model
    "You sort email for the owner",     # tools.py mail_triage: the classifier prompt
    "What is known about the owner",    # tools.py mail_triage: the classifier's facts line
    "What you know about the owner",    # agent.py context_block: the memory block of the system prompt
    "The owner's name is",              # agent.py context_block: the name line of the system prompt
    "No email account is set up",       # agent.py run: a model-only note (topic_note) in the system context
    "You are the operating system",     # agent.py SYSTEM_PROMPT_BASE
    "How to treat the owner",           # agent.py DEFAULT_CONDUCT_*
    "Carry out the owner's requests",   # agent.py DEFAULT_CONDUCT_STANDARD
)

fails = []


def check(ok, label):
    print(("ok " if ok else "FAIL ") + label)
    if not ok:
        fails.append(label)


def walk_visible(path):
    """Yield (line, text) for every string constant in code that is not a docstring, a tool description or an allowed prompt."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    skip = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr):
            skip.add(id(n.body[0].value))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tool":
            for a in ast.walk(n):
                skip.add(id(a))
    for n in ast.walk(tree):
        if id(n) in skip:
            continue
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            text = n.value
        elif isinstance(n, ast.JoinedStr):
            text = ast.get_source_segment(src, n) or ""
        else:
            continue
        if "the owner" in text.lower() and not any(p in text for p in ALLOW):
            yield n.lineno, text


# (1) compile
for p in (TOOLS, AGENT):
    try:
        py_compile.compile(p, doraise=True)
        check(True, f"compiles {os.path.basename(p)}")
    except py_compile.PyCompileError as e:
        check(False, f"compiles {os.path.basename(p)}: {e}")

# (2) no model-visible "the owner"
for p in (TOOLS, AGENT):
    bad = list(walk_visible(p))
    check(not bad, f"no 'the owner' in model-visible strings of {os.path.basename(p)}"
          + ("" if not bad else f": {[(ln, t[:60]) for ln, t in bad[:5]]}"))

from llmos import agent  # noqa: E402  (after the path setup above)

# (3) hidden notes: each note, old and new wording, is hidden by _INTERNAL; the owner never sees it
for note in ("Reply with exactly this: pick a date.", "reply with exactly this: pick a date.",
             "not done: you did not ask for 'backup' in this request.",
             "Do only what was asked.", "Say one sentence at most."):
    check(bool(agent._INTERNAL.search(note)), f"_INTERNAL hides {note!r}")
check(agent.scrub("Reply with exactly this: Hello there.") == "Hello there.",
      "scrub keeps what follows 'Reply with exactly this:'")
check(agent.scrub("Here is the file. Reply with exactly this: Saved it.") == "Here is the file. Saved it.",
      "scrub keeps the reply text after the note in the middle of a reply")
check(agent.scrub("You did not ask for a backup, so I skipped it.") == "You did not ask for a backup, so I skipped it.",
      "a normal reply that says 'did not ask' is not hidden")
check(agent.scrub("The file is saved. You did not ask for 'backup' in this request.") == "The file is saved.",
      "a guard note 'you did not ask for ...' is hidden from the owner")

# the model note on shortcut results still goes (done: reply ...)
check(agent.scrub(agent._MODEL_NOTE.sub(".", "Wallpaper set: beach.jpg. Done: reply in one sentence.")) == "Wallpaper set: beach.jpg.",
      "_MODEL_NOTE strips 'Done: reply in one sentence.'")
check(agent.scrub(agent._MODEL_NOTE.sub(".", "x is shown on screen. Say one sentence at most.")) == "x is shown on screen.",
      "_MODEL_NOTE strips 'Say one sentence at most.'")

# (4) last_saved._opened recognises the success replies (regex taken from tools.py itself)
tree = ast.parse(open(TOOLS, encoding="utf-8").read())
pattern = None
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name == "_opened":
        for m in ast.walk(n):
            if isinstance(m, ast.Call) and isinstance(m.func, ast.Attribute) and m.func.attr == "match":
                pattern = eval(compile(ast.Expression(m.args[0]), "<_opened>", "eval"), {"__builtins__": {}}, {})
check(isinstance(pattern, str), "_opened regex found in tools.py last_saved")
OK_SHAPES = ("opened new.txt in Mousepad. Done: if the request asked for more, do the next step now; otherwise reply in one sentence.",
             "opened new.txt with Eog. Say one sentence at most.",
             "now playing a song by an artist (3:10). Say one sentence at most.",
             "photo.jpg (2 KB) is shown on screen. Say one sentence at most.",
             "notes.txt is shown as text on screen. Say one sentence at most.")
for s in OK_SHAPES:
    check(bool(re.match(pattern, s)), f"_opened matches {s[:44]!r}")
for s in ("error: no such file", "you declined this (open_file). Do not retry it; continue or stop.",
          "Nothing new was saved in the last two hours."):
    check(not re.match(pattern, s), f"_opened does not match {s[:44]!r}")

# (5) agent.py matchers on the new text
check(agent._failed("you declined this (open_file). Do not retry it."), "_failed: 'you declined' counts as a refusal")
check(agent._shortcut_words("open_file", {}, "x.jpg is shown on screen. Say one sentence at most.") == "Here it is.",
      "open_file's 'is shown on screen' gives 'Here it is.'")
check(agent._shortcut_reply("mail_setup", {}, "error: bad password. Reply with exactly this and ask them to check the address.")
      == "Bad password.", "a mail_setup error shows its cause; the 'Reply with exactly this' note stays hidden")
check(agent._shortcut_words("install_to_disk", {}, "installed on /dev/sda. Alongside macOS. You see this on screen; say one sentence.")
      == "installed on /dev/sda. Alongside macOS.", "install_to_disk drops the 'You see this on screen' note")
check(agent._shortcut_words("run_command", {}, "you declined this (run_command). Do not retry it; continue or stop.")
      == "Okay, I left it alone.", "a declined action gets 'Okay, I left it alone.'")

print("\nall good" if not fails else f"\n{len(fails)} failure(s): {fails}")
sys.exit(1 if fails else 0)
