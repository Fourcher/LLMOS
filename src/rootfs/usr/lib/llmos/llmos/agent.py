"""The agent loop: turn what the user said into actions, honestly, under the
user's chosen autonomy level."""
import json
import re
import time

from . import config, i18n, intent, llm, mail, store, tools

# Small models sometimes *narrate* an action ("remembered that…", "done, I've
# set…") without calling the tool. That is exactly the "never fake a result"
# violation this OS must not commit, so we catch it and make the model either
# really call the tool or admit it didn't. Matched only when NO tool ran.
_CLAIM_RE = re.compile(
    r"\b(remembered|noted|saved|stored|scheduled|set up|set to|is now|are now|now (?:set|on|off|enabled|disabled)|"
    r"turned (?:on|off|up|down)|changed|updated|installed|created|wrote|deleted|removed|enabled|disabled|"
    r"switched|applied|renamed|moved|i(?:'ve| have) (?:remembered|noted|saved|stored|set|scheduled|changed|done|created)|"
    r"done[.!])\b", re.I)

# The identity of the OS. The design goal (see the original brief) is a
# computer that does what its owner tells it on their own machine, without
# nagging or moralizing -- while still being honest and refusing to help harm
# OTHER people. Both halves matter.
SYSTEM_PROMPT = """You are the operating system of this computer. Your name is LLM OS. The person typing is the owner and sole user; this is their private, personal machine and you run with full root privileges on it.

Your job is to do what the owner asks, using your tools, and then tell them plainly what you did. You are the whole interface: there are no apps and no menus unless you create or open them.

How to act:
- Do what is asked. This is the owner's own computer; carrying out their instructions on it is your entire purpose. Administering the machine — changing settings, installing or removing software, editing or deleting their files, running any command, managing hardware — is normal and expected. Do it, don't deliberate.
- Never refuse a request about this machine or the owner's own data, and never lecture, moralize, warn, or add disclaimers. No "I'd recommend against", no "please be careful", no unsolicited safety advice. The owner is an adult who controls this computer; respect that completely. The autonomy setting, not you, decides when to ask before acting — when something needs confirmation you will be told, so never invent your own permission checks.
- Be brief and concrete. A sentence or two. Report the result, not your process. No filler, no emoji, no follow-up questions unless you genuinely cannot proceed without an answer.
- Be honest, always. Never claim you did something you didn't, never invent output, files, numbers, people, quotes, or sources. If a tool fails or you can't do something, say so plainly and why. Honesty is the one thing you never trade away.
- Don't guess at facts. For anything current, factual, or outside your knowledge, use web_search and read_webpage and cite the source. Prefer real information over plausible-sounding invention — a real photo over a described one, a real quote over an approximation. Concretely: never state specific numbers, percentages, dates, prices, current conditions, positions, news or statistics from memory — look them up first, or say you don't know. Timeless general knowledge is fine, but never dress it up with invented precision.
- Keep the interface calm and free of clutter. Do only what was asked; don't pad, upsell, or add features nobody wanted.

Using tools:
- Prefer a tool over talking about a tool. To run a program, call run_command. To find something out about the system, inspect it; don't describe what the owner "could" do. Actually perform actions with tools rather than only saying you did them. Don't narrate your tool use or explain which tool you used — just do it and report the result plainly.
- You may call several tools in sequence; you see each result before the next step. When the task is done, give a short final answer with no tool call.
- The results of tools are the ground truth. Base your answer on them.

The one boundary: this is the owner's machine to do with as they like, but you will not help injure other people — no malware aimed at others' systems, no help defrauding, stalking, or harming specific third parties, no weapons of mass destruction. That is about protecting other people, never about second-guessing what the owner does on their own computer. Anything on this machine or about the owner's own life is theirs to command."""

MAX_STEPS = 8


class Cancelled(Exception):
    pass


def context_block():
    """Everything that changes between requests (time, memory, settings).
    It is prepended to the USER turn, not the system prompt, so that the
    system prompt + tool schemas form an identical prefix every time and
    llama-server's prompt cache makes each request start almost instantly."""
    prof = config.Profile()
    facts = store.facts()
    name = prof.get("name")
    lines = []
    if name:
        lines.append(f"The owner's name is {name}.")
    lang = config.llm_language()
    if i18n.lang_code(lang) != "en":
        lines.append(f"Reply in {lang}.")
    if facts:
        lines.append("What you know about the owner: " + "; ".join(f["fact"] for f in facts[-40:]) + ".")
    # (the autonomy level is deliberately not mentioned: confirmations are
    # enforced around the tools, and telling the model only makes it parrot
    # the policy back at the owner)
    lines.append("Now: " + time.strftime("%A %Y-%m-%d %H:%M %Z") + ".")
    return "\n".join(lines)


def build_messages(ctx, user_text, history):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs += trim_history(history)
    msgs.append({"role": "user", "content": "[context]\n" + context_block() + "\n[/context]\n\n" + user_text})
    return msgs


def warm_up():
    """Process the static prefix (system prompt + tools) once so the first
    real request doesn't pay for it. Called in the background at startup."""
    try:
        llm.chat([{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": "[context]\n[/context]\n\nhi"}],
                 tools=tools.schemas(), max_tokens=1, think=False)
    except Exception:
        pass


def trim_history(history, keep=8):
    """Small models lose the thread as context grows, so only the last few
    messages are replayed. We never begin the slice on an orphaned tool result
    or an assistant turn that was itself answering one."""
    h = history[-keep:]
    while h and (h[0].get("role") == "tool" or (h[0].get("role") == "assistant" and h[0].get("tool_calls"))):
        h = h[1:]
    return h


MAX_INPUT = 6000   # characters (~1500 tokens) — more than this is clipped, head and tail kept


def clip_input(text):
    if len(text) <= MAX_INPUT:
        return text, False
    head, tail = text[:MAX_INPUT - 1200].rstrip(), text[-1000:].lstrip()
    return f"{head}\n[… {len(text) - len(head) - len(tail)} characters left out: the request was too long …]\n{tail}", True


def run(ctx, user_text, history):
    """Run one user turn. Streams text through ctx, executes tools under the
    autonomy policy, appends to history, returns the final text."""
    user_text, clipped = clip_input(user_text)
    if clipped:
        ctx.status("that was very long; I kept the beginning and the end")
    ctx.current_request = user_text

    # Email requests without an account: answer here. Left to the model, it
    # improvises (searching the web for the person named) instead of saying so.
    if re.search(r"\b(e-?mails?|inbox|mailbox|unread mail|my mail)\b|^\s*(?:reply|respond|answer)\s+(?:back\s+)?to\b",
                 user_text, re.I) and mail.account() is None \
            and not re.search(r"\b(set ?up|configure|add|connect|log ?in)\b", user_text, re.I):
        reply = ("No email account is set up on this computer yet. Say something like: "
                 "\"set up my email: address you@example.com, password …\" (Gmail, Outlook, Yahoo and "
                 "iCloud need an app password).")
        st = ctx.new_stream()
        ctx.on_text(st, reply)
        ctx.end_stream(st)
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        return reply

    # Deterministic shortcut for a few unambiguous intents small models fumble
    # (explicit "remember X"). Runs the same tool through the same policy path.
    shortcut = intent.match(user_text)
    if shortcut:
        name, args = shortcut
        out = execute(ctx, name, args)
        reply = _cap(_shortcut_reply(name, args, out))
        st = ctx.new_stream()
        ctx.on_text(st, reply)
        ctx.end_stream(st)
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        return reply

    # The per-turn message list carries the tool-call/tool-result loop. It is
    # LOCAL to this turn -- those raw messages are never kept in `history`,
    # because replaying them between unrelated commands confuses small models
    # and violates strict chat templates (Mistral requires alternating roles).
    # Across turns we keep only clean user/assistant text (see the end).
    msgs = build_messages(ctx, user_text, history)
    final = ""
    tools_ran = 0
    nudged = False
    shrunk = 0
    for step in range(MAX_STEPS):
        stream = ctx.new_stream()
        try:
            result = llm.chat(msgs, tools=tools.schemas(),
                              on_text=lambda t: ctx.on_text(stream, t))
        except llm.ModelError as e:
            ctx.end_stream(stream)
            # too long for the model's memory (small machines run a 6k context): retry with the
            # history dropped and the request halved, twice, before giving up
            if "too long" in str(e) and not tools_ran and not final and shrunk < 2:
                shrunk += 1
                keep = max(800, len(user_text) // 2)
                user_text = user_text[:keep].rstrip() + "\n[… cut here: the request was too long …]"
                ctx.status("too long for the model's memory; trying with a shorter version")
                msgs = build_messages(ctx, user_text, [])
                continue
            raise
        except llm.ModelDown:
            ctx.end_stream(stream)
            raise
        ctx.end_stream(stream)
        content = result["content"].strip()
        calls = result["tool_calls"]
        if content:
            final = content
        if not calls:
            # honesty guard: the model narrated an action but ran no tool for it
            if not tools_ran and not nudged and _CLAIM_RE.search(content):
                nudged = True
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content":
                             "You described that as done, but you did not call any tool, so nothing "
                             "actually happened. If it needs a tool, call it now. If no tool fits, say "
                             "plainly that you did not do it. Do not claim an action you did not perform."})
                final = ""
                continue
            break
        assistant_msg = {"role": "assistant", "content": content or None,
                         "tool_calls": [{"id": c["id"] or f"call_{step}_{i}", "type": "function",
                                         "function": {"name": c["name"], "arguments": c["arguments"]}}
                                        for i, c in enumerate(calls)]}
        msgs.append(assistant_msg)
        for i, call in enumerate(calls):
            cid = call["id"] or f"call_{step}_{i}"
            out = execute(ctx, call["name"], call["arguments"])
            tools_ran += 1
            msgs.append({"role": "tool", "tool_call_id": cid, "content": out})
        if ctx.after_turn:
            break
    else:
        # ran out of steps without a plain answer: ask for one final summary
        if not final:
            try:
                msgs.append({"role": "user", "content":
                             "Stop using tools now and give me a one or two sentence plain answer "
                             "based on what you found, or say plainly if you could not do it."})
                final = llm.chat(msgs, on_text=None).get("content", "").strip()
                if final:
                    st = ctx.new_stream()
                    ctx.on_text(st, final)
                    ctx.end_stream(st)
            except llm.ModelDown:
                pass
        if not final:
            final = "I wasn't able to finish that. Try rephrasing, or check `audit` to see what I tried."
            ctx.status(i18n.t("stopped"))
    # keep only the clean exchange in cross-turn history
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": final or "(done)"})
    return final


def _cap(s):
    return s[:1].upper() + s[1:]


def _shortcut_reply(name, args, out):
    low = str(out).lower()
    if low.startswith("error: "):
        return _cap(str(out)[7:].rstrip(".")) + "."
    if low.startswith("the owner declined this"):
        return "Okay, I left it alone."
    if low.startswith("the owner declined internet"):
        return "Okay, no internet for that."
    if low.startswith("blocked: internet use is turned off"):
        return "Internet use is turned off in settings, so I can't do that."
    if name == "remember":
        if "saved" in low:
            return "Got it — I'll remember that."
        if "already" in low:
            return "I already had that noted."
        return out
    if name == "schedule_task":
        task = str(args.get("task", ""))
        if task.startswith(("tell me that my", "remind me")) and not low.startswith("error"):
            m = re.match(r"scheduled \[\w+\] (.+?): ", out, re.I)   # "scheduled [id] Thu 01 Oct 09:52: task"
            when = m.group(1).split(" ")[-1] if m else ""
            if task.startswith("tell me that my"):
                length = re.sub(r"^tell me that my (.+?) timer is done.*$", r"\1", task)
                return f"Timer set — {length}, it rings at {when}." if when else f"Timer set — {length}."
            what = re.sub(r"^remind me(?:\s*:\s*|\s+(?:to|that|about)\s+)", "", task)
            return f"Reminder set for {when}: {what}." if when else f"Reminder set: {what}."
        if low.startswith("scheduled ["):
            return "Scheduled — " + out.split("] ", 1)[1] + "."
        return out
    if name == "mail_reply":
        return ("Sent: " + out[len("replied to "):]) if low.startswith("replied to") else out
    if name == "set_appearance":
        return ("Done — " + out[len("appearance updated: "):] + ".") if low.startswith("appearance updated") else out
    if name == "play_media":
        m = re.match(r'now playing "(.+?)" by (.+?) \((.*?)\)', out)
        if m:
            return f"Now playing “{m.group(1)}” by {m.group(2)}."
        return out.split(". Done:")[0]
    if name == "open_app":
        return _cap(out.split(". Done:")[0]) + "." if low.startswith("opened") else out
    if name == "system_panel":
        return "Here it is." if low.startswith("the panel") else out
    if name == "show_panel":
        return "Here it is." if " is now shown" in low else out
    if name == "show_files":
        m = re.match(r"(\d+) item\(s\) in (.+?) are listed", out)
        return (f"{m.group(1)} item{'' if m.group(1) == '1' else 's'} in {m.group(2)}." if m else out.split(";")[0])
    if name == "screenshot":
        return _cap(out.split(". Say")[0]) + "." if low.startswith("screenshot saved") else out
    if name == "open_file":
        if " is shown on the owner's screen" in out:
            return "Here it is."
        return _cap(out.split(". Say")[0]) + "." if low.startswith(("now playing", "opened ")) else out
    if name == "delete_file":
        return _cap(out.split(" (")[0]) + "." if low.startswith(("moved ", "deleted ")) else out
    if name in ("restore_file", "empty_trash"):
        return _cap(out.split(". Say")[0]) + "." if not low.startswith("error") else out
    if name == "note_add":
        return "Added." if low.startswith("added") else ("That was already on the list." if "already" in low else out)
    if name == "notes_show":
        m = re.match(r"the (.+?) window shows (\d+) item", out)
        return ("Here it is." if m and m.group(2) != "0" else "Nothing on it yet.") if m else out
    if name == "note_done":
        return ("Done." if " is ticked off" in low else "Back on the list.") if not low.startswith("error") else out
    if name == "note_remove":
        return "Removed." if low.startswith("removed") else out
    if name == "set_passphrase":
        return "Type it in the window and press the button." if "form is on" in low else out
    if name in ("set_brightness", "set_volume"):
        return out
    if name == "manage_models":
        if low.startswith(("downloaded", "now using", "removed")):
            return out[0].upper() + out[1:].split(" (sha256")[0] + "."
        return out
    if name == "install_to_disk":
        return out.split(". The owner sees")[0].split(". Do not call")[0].rstrip(".") + "."
    if name in ("show_image", "set_wallpaper"):
        m = re.match(r"(shown|wallpaper set): (.+?) \((.*?)\)\. Source: (\S+)", out)
        if m:
            return (f"Here is {m.group(2)} — {m.group(3)}." if name == "show_image"
                    else f"Wallpaper set: {m.group(2)} ({m.group(3)}).")
        return out
    if name == "mail_setup":
        if low.startswith("email set up"):
            return "E" + out[1:] + "."
        if low.startswith("error: "):        # the tool's text is written for the model; give the owner the cause
            return ("Email setup failed: " + out[len("error: "):].split(". Tell the owner", 1)[0] +
                    ". Check the address, the password (Gmail, Outlook, Yahoo and iCloud need an app password) "
                    "and the server names, then try again.")
        return out
    return out


def _redacted(args):
    """Tool arguments as shown on screen and kept in the audit log: secrets
    the owner typed (an email password) are not echoed or stored."""
    if not isinstance(args, dict):
        return args
    return {k: ("•••" if isinstance(v, str) and re.search(r"pass|secret|token", k, re.I) else v) for k, v in args.items()}


# Irreversible actions that reach other people or end the session must be
# asked for in the CURRENT request. Small models otherwise "complete" an
# earlier failed request on their own (e.g. replying to an email when only
# asked to sort the inbox).
_ONLY_IF_ASKED = {
    "mail_send": r"\b(send|reply|respond|answer|write|e-?mail|mail|tell|let .{0,30} know|forward|notify|message)\b",
    "mail_reply": r"\b(send|reply|respond|answer|write|e-?mail|mail|tell|let .{0,30} know|forward|notify|message)\b",
    "mail_delete": r"\b(delete|trash|remove|get rid|bin|clean|clear|zero)\b",
    "system_power": r"\b(shut|power|restart|reboot|turn (it )?off|switch off)\b",
}


def execute(ctx, name, arguments):
    tool = tools.REGISTRY.get(name)
    if not tool or not tool.available():
        return f"error: no such tool '{name}'"
    need = _ONLY_IF_ASKED.get(name)
    current = getattr(ctx, "current_request", "") or ""
    if need and current and not re.search(need, current, re.I):
        store.audit(name, arguments, "blocked: not asked for in this request", allowed=False)
        return (f"not done: the owner did not ask for '{name}' in this request. Do only what was asked; "
                f"if this seems needed, say so and let the owner decide.")
    try:
        args = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else (arguments or {})
        if not isinstance(args, dict):
            args = {"value": args}
    except ValueError:
        return f"error: could not parse arguments for {name}"

    risk = tool.risk_for(args)
    network = tool.network_for(args)
    shown = _redacted(args)

    # internet policy is enforced here, not left to the model
    if network:
        pol = config.settings.get("internet", "yes")
        if pol == "no":
            store.audit(name, shown, "blocked: internet off", allowed=False)
            return ("blocked: internet use is turned off in settings. Tell the owner that; do not retry, and do not "
                    "answer from memory what you were asked to look up (no quotes, facts, news or numbers).")
        if pol == "ask" and not ctx.confirm_network(name, shown):
            store.audit(name, shown, "denied network", allowed=False)
            return "the owner declined internet access for this. Continue without it."

    if needs_confirm(risk):
        if not ctx.confirm_action(tool, shown, risk):
            store.audit(name, shown, "denied", allowed=False)
            return f"the owner declined this ({name}). Do not retry it; continue or stop."

    ctx.begin_tool(tool, shown, risk)
    try:
        result = tool.fn(args, ctx)
    except Exception as e:  # a tool must never crash the console
        store.audit(name, shown, f"error: {e}", allowed=True)
        ctx.end_tool(tool, f"error: {e}")
        return f"error while running {name}: {e}"
    store.audit(name, shown, result, allowed=True)
    ctx.end_tool(tool, result)
    return result


def needs_confirm(risk):
    auto = config.settings.get("autonomy")
    if auto == "hands-off":
        return risk == tools.SECURITY  # even hands-off confirms security-policy flips
    if auto == "balanced":
        return risk in (tools.DESTRUCTIVE, tools.SECURITY)
    return risk in (tools.CHANGE, tools.DESTRUCTIVE, tools.SECURITY)  # hands-on
