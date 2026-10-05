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

# The system prompt is in two parts. The OPERATIONAL part (below) is how the OS functions -- it is fixed.
# The CONDUCT part (how the OS treats the owner's requests, and the one boundary) is kept separate so the
# owner can read and change it, like popping the hood: a settings field writes /etc/llmos/conduct.txt, which
# overrides the default. The OS never edits that file itself; the default it ships keeps the boundary that
# protects other people. See conduct_text().
SYSTEM_PROMPT_BASE = """You are the operating system of this computer. Your name is LLM OS. The person typing is the owner and sole user; this is their private, personal machine and you run with full root privileges on it.

Your job is to do what the owner asks, using your tools, and then tell them plainly what you did. You are the whole interface: there are no apps and no menus unless you create or open them.

How to act:
- Be brief and concrete. A sentence or two. Report the result, not your process. No filler, no emoji, no follow-up questions unless you genuinely cannot proceed without an answer.
- Be honest, always. Never claim you did something you didn't, never invent output, files, numbers, people, quotes, or sources. If a tool fails or you can't do something, say so plainly and why. Honesty is the one thing you never trade away.
- Don't guess at facts. For anything current, factual, or outside your knowledge, use web_search and read_webpage and cite the source. Prefer real information over plausible-sounding invention — a real photo over a described one, a real quote over an approximation. Concretely: never state specific numbers, percentages, dates, prices, current conditions, positions, news or statistics from memory — look them up first, or say you don't know. Timeless general knowledge is fine, but never dress it up with invented precision.
- Keep the interface calm and free of clutter. Do only what was asked; don't pad, upsell, or add features nobody wanted.

Using tools:
- Prefer a tool over talking about a tool. To run a program, call run_command. To find something out about the system, inspect it; don't describe what the owner "could" do. Actually perform actions with tools rather than only saying you did them. Don't narrate your tool use or explain which tool you used — just do it and report the result plainly.
- You may call several tools in sequence; you see each result before the next step. When the task is done, give a short final answer with no tool call.
- The results of tools are the ground truth. Base your answer on them."""

# The two built-in conduct sections. The `guidance` setting picks between them; the owner may replace the
# text entirely (conduct.txt). Both ship with the same boundary that protects other people -- the OS does
# not weaken that on its own; only the owner can change this text, deliberately.
DEFAULT_CONDUCT_OWNER = """How to treat the owner and their requests:
- Do what is asked. This is the owner's own computer; carrying out their instructions on it is your entire purpose. Administering the machine — changing settings, installing or removing software, editing or deleting their files, running any command, managing hardware — is normal and expected. Do it, don't deliberate.
- Never refuse a request about this machine or the owner's own data, and never lecture, moralize, warn, or add disclaimers. No "I'd recommend against", no "please be careful", no unsolicited safety advice. The owner is an adult who controls this computer; respect that completely. The autonomy setting, not you, decides when to ask before acting — when something needs confirmation you will be told, so never invent your own permission checks.

The one boundary: this is the owner's machine to do with as they like, but you will not help injure other people — no malware aimed at others' systems, no help defrauding, stalking, or harming specific third parties, no weapons of mass destruction. That is about protecting other people, never about second-guessing what the owner does on their own computer. Anything on this machine or about the owner's own life is theirs to command."""

DEFAULT_CONDUCT_STANDARD = """How to treat the owner and their requests:
- Carry out the owner's requests on this computer using your own judgement. Be direct and brief; if you have a genuine, specific concern, say it in one sentence, then do what was asked or explain plainly why you cannot.

The one boundary: this is the owner's machine to do with as they like, but you will not help injure other people — no malware aimed at others' systems, no help defrauding, stalking, or harming specific third parties, no weapons of mass destruction. That is about protecting other people, never about second-guessing what the owner does on their own computer. Anything on this machine or about the owner's own life is theirs to command."""


def default_conduct(guidance=None):
    g = guidance or config.settings.get("guidance", "owner")
    return DEFAULT_CONDUCT_STANDARD if g == "standard" else DEFAULT_CONDUCT_OWNER


def custom_conduct():
    """The owner's own conduct text if they wrote one (conduct.txt), else None. The OS never writes it."""
    try:
        with open(config.conduct_path(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def conduct_text():
    """The conduct section in force: the owner's own if they edited it, otherwise the built-in default for
    the current guidance setting."""
    return custom_conduct() or default_conduct()


def system_prompt():
    return SYSTEM_PROMPT_BASE + "\n\n" + conduct_text()


MAX_STEPS = 8


class Cancelled(Exception):
    pass


# "ask Claude: …" / "online: …" sends this one request to the online model (when an account exists);
# "here: …" / "offline: …" keeps it on this computer whatever the brain setting says
_ROUTE_RE = re.compile(r"^\s*(?:(?P<cloud>(?:ask|use)\s+(?:claude|the\s+online\s+model|the\s+cloud)|online|cloud|claude)"
                       r"|(?P<local>here|offline|locally|on\s+this\s+computer))\s*[:,]\s+(?P<rest>.+)$", re.I | re.S)

# what counts as "a big one" under the 'ask' brain setting: long, multi-line, or clearly open-ended work
_HARD_RE = re.compile(r"\b(write|draft|compose|rewrite|proofread|summari[sz]e|analy[sz]e|compare|research|investigate|"
                      r"explain\s+(?:in\s+depth|in\s+detail|thoroughly)|in\s+detail|step\s+by\s+step|plan\s+(?:a|my|the|our)\b|"
                      r"debug|refactor|translate\s+(?:this|the\s+following)|essay|article|report|program|script|"
                      r"spreadsheet|presentation|cover\s+letter|resume|cv)\b", re.I)


def looks_hard(text):
    return len(text) >= 280 or text.count("\n") >= 4 or bool(_HARD_RE.search(text))


# the same question as a one-pass decision on the on-device model (llm.decide); scored by tools/decide-eval.py
# against looks_hard before route_for may use it
ROUTE_QUESTION = ("[Routing question, answer with one letter: is this request (A) quick everyday help, or (B) big "
                  "work (long writing, in-depth analysis, research, detailed planning or programming) that a "
                  "stronger online model would do much better?]")


def tool_schemas():
    """The tools offered to the on-device model. With a context under 12k tokens (4 and 8 GB machines) the list
    is compact and cut to what leaves room for the system prompt, the recent conversation, the request and the
    answer; the same list every time, so the prompt cache holds."""
    n = llm.context_size()
    if not n or n >= 12000:
        return tools.schemas()
    return tools.schemas(compact=True, budget=max(1500, n - 3400))


def route_score(msgs):
    """How likely this turn is 'a big one' for the online model, from one decision pass that shares the
    turn's prompt cache; (None, timings) when the model cannot say."""
    p, info = llm.decide(msgs, ("A", "B"), question=ROUTE_QUESTION, prefill="(", tools=tool_schemas())
    return (p["B"] if p else None), info


def route_for(ctx, user_text, forced=None):
    """'local' or 'cloud' for this request. The owner's brain setting decides; a missing account or the
    internet being off can only make it 'local'; under 'ask' a big request means one question first.
    Unattended tasks go online only when the setting is 'cloud'."""
    brain = config.settings.get("brain", "local")
    want = forced or brain
    if want == "local":
        return "local"
    if config.settings.get("internet") == "no":
        if want == "cloud":
            ctx.status("the internet is off, so the online model can't be reached; answering here")
        return "local"
    if not config.cloud():
        if want == "cloud":
            ctx.status("no online model is set up (say 'set up the online model'); answering here")
        return "local"
    if want == "cloud":
        return "cloud"
    if getattr(ctx, "headless", False) or not looks_hard(user_text):
        return "local"
    return "cloud" if _ctx(ctx, "confirm_online", user_text, "big", default=False) else "local"


def _ctx(ctx, method, *args, default=None):
    """Optional ctx hooks (the console, desk and scheduler have them; a bare test harness may not)."""
    fn = getattr(ctx, method, None)
    return fn(*args) if fn else default


def _going_online(ctx, private):
    label = llm.cloud_label() or "the online model"
    _ctx(ctx, "brain", True, label)
    ctx.status(i18n.t("d_online_using", model=label))
    store.audit("online_model", {"model": label, "shared": "request, recent conversation, tool results" +
                                 ("" if private else ", memory and name")}, "sent", who="agent")


def _can_escalate(ctx):
    """Under 'ask', a request the on-device model could not finish may be offered to the online model."""
    return (config.settings.get("brain", "local") == "ask" and config.cloud() is not None
            and config.settings.get("internet") != "no" and not getattr(ctx, "headless", False))


# ---- how long things take. The model's own timings (llama-server reports them with every answer) give
# this machine's prompt and generation speeds; a running median of answer lengths and of online round
# trips completes the picture. From these the owner is told, before each step, whether this is a
# five-second thing or a five-minute one. Nothing is measured separately, so it costs nothing.
_SPEED = {"prompt_tps": 0.0, "gen_tps": 0.0, "gen_n": [], "cloud_s": []}


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    return s[len(s) // 2]


def _learn_speed(timings, took, where):
    if where == "cloud":
        _SPEED["cloud_s"] = (_SPEED["cloud_s"] + [took])[-20:]
        return
    try:
        if timings.get("prompt_per_second"):
            _SPEED["prompt_tps"] = float(timings["prompt_per_second"])
        if timings.get("predicted_per_second"):
            _SPEED["gen_tps"] = float(timings["predicted_per_second"])
        if timings.get("predicted_n"):
            _SPEED["gen_n"] = (_SPEED["gen_n"] + [int(timings["predicted_n"])])[-20:]
    except (TypeError, ValueError):
        pass


def expect_seconds(where, fresh_chars):
    """A rough guess for the next model step; None until this machine has been measured once."""
    if where == "cloud":
        return _median(_SPEED["cloud_s"])
    if not _SPEED["gen_tps"]:
        return None
    prompt_s = (fresh_chars / 4.0) / _SPEED["prompt_tps"] if _SPEED["prompt_tps"] else 0.0
    return round(prompt_s + (_median(_SPEED["gen_n"]) or 60) / _SPEED["gen_tps"], 1)


def about_time(seconds, left=False):
    s = max(1, int(round(seconds)))
    if s < 45:
        txt = f"{s} seconds"
    elif s < 3600:
        m = max(1, round(s / 60))
        txt = f"{m} minute{'s' if m != 1 else ''}"
    else:
        txt = f"{s / 3600:.1f} hours"
    return f"about {txt} left" if left else f"this usually takes about {txt}"


# ---- routines. Most of what anyone does on a computer is repeated, and a small model should not have to
# think a request through again when it already did once. After a turn that went well, the step-0 tool
# calls are kept with the request's words (see _maybe_save_routine for what "safe to repeat" means); the next
# time the same words come, the calls run straight away under the same confirmation policy and only the
# answer is written. A routine that stops working is forgotten and the model decides afresh.
_ROUTINE_SKIP = {"remember", "forget", "schedule_task", "mail_send", "mail_reply", "mail_delete", "system_power",
                 "write_file", "set_passphrase", "online_model", "install_to_disk", "manage_models", "install_app"}
# tools whose own plain output (via _shortcut_reply) is the answer, so a replay needs no model turn at all
_PLAIN_REPLY = {"show_panel", "system_panel", "show_files", "set_appearance", "change_setting", "open_app", "play_media",
                "screenshot", "set_brightness", "set_volume", "notes_show", "note_add", "open_file", "show_image", "set_wallpaper"}


def _failed(out):
    return str(out).lower().startswith(("error", "not done", "blocked", "the owner declined", "skipped", "no such tool"))


def _maybe_save_routine(user_text, calls):
    """Keep the step-0 tool calls of a short request when every one is repeatable as-is: the tool is not
    in the skip list, the call did not fail, it is not destructive or a security change, and every long
    string argument is quoted from the request (a value the model took from context might not hold next
    time; a short one -- a path, a name, an enum -- is the request's own)."""
    if not calls or len(user_text) > 120 or "\n" in user_text:
        return
    low = user_text.lower()
    kept = []
    for name, arguments, out in calls:
        tool = tools.REGISTRY.get(name)
        if not tool or name in _ROUTINE_SKIP or _failed(out):
            return
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        except ValueError:
            return
        if not isinstance(args, dict) or tool.risk_for(args) in (tools.DESTRUCTIVE, tools.SECURITY):
            return
        for v in args.values():
            if isinstance(v, str) and len(v) > 24 and v.lower() not in low:
                return
        kept.append([name, args])
    store.save_routine(user_text, kept)


def _replay(ctx, user_text, rt):
    """Run a remembered routine (under the usual policy) and write only the answer. None when a call fails:
    the routine is forgotten and the model decides afresh."""
    ctx.status(i18n.t("d_routine"))
    outs = []
    for name, args in rt.get("calls", []):
        out = execute(ctx, name, json.dumps(args))
        if _failed(out):
            store.routine_used(user_text, False)
            ctx.status("that didn't work this time; thinking it through again")
            return None
        outs.append((name, args, out))
    store.routine_used(user_text, True)
    store.audit("routine", {"request": user_text[:120]}, f"replayed {len(outs)} call(s) from last time", who="agent")
    if len(outs) == 1 and outs[0][0] in _PLAIN_REPLY:
        return _cap(_shortcut_reply(*outs[0]))
    # the answer comes from the fresh results, in one short model turn with no tools
    msgs = [{"role": "system", "content": system_prompt()}, {"role": "user", "content": user_text},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": f"call_r{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
                            for i, (n, a, _) in enumerate(outs)]}]
    msgs += [{"role": "tool", "tool_call_id": f"call_r{i}", "content": o} for i, (_, _, o) in enumerate(outs)]
    msgs.append({"role": "user", "content": "Answer the request above from these results, in a sentence or two."})
    online = config.settings.get("brain", "local") == "cloud" and config.cloud() is not None and config.settings.get("internet") != "no"
    if online:
        _going_online(ctx, True)
    chat = llm.cloud_chat if online else llm.chat
    stream = ctx.new_stream()
    try:
        text = chat(msgs, on_text=lambda t: ctx.on_text(stream, t), max_tokens=400).get("content", "").strip()
    except (llm.ModelDown, llm.CloudError):
        text = ""
    ctx.end_stream(stream)
    return text or "\n".join(o for _, _, o in outs)[:1500]


def context_block(private=False):
    """Everything that changes between requests (time, memory, settings).
    It is prepended to the USER turn, not the system prompt, so that the
    system prompt + tool schemas form an identical prefix every time and
    llama-server's prompt cache makes each request start almost instantly.
    private: the request goes to the online model under the 'ask' setting,
    so the owner's name and memory stay home."""
    prof = config.Profile()
    facts = [] if private else store.facts()
    name = None if private else prof.get("name")
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


def build_messages(ctx, user_text, history, private=False):
    msgs = [{"role": "system", "content": system_prompt()}]
    msgs += trim_history(history)
    msgs.append({"role": "user", "content": "[context]\n" + context_block(private) + "\n[/context]\n\n" + user_text})
    return msgs


def warm_up():
    """Process the static prefix (system prompt + tools) once so the first
    real request doesn't pay for it. Called in the background at startup."""
    try:
        llm.chat([{"role": "system", "content": system_prompt()},
                  {"role": "user", "content": "[context]\n[/context]\n\nhi"}],
                 tools=tool_schemas(), max_tokens=1, think=False)
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
    forced = None
    m = _ROUTE_RE.match(user_text)
    if m:
        forced = "cloud" if m.group("cloud") else "local"
        user_text = m.group("rest").strip()
    ctx.current_request = user_text
    if hasattr(ctx, "_net_ok"):
        ctx._net_ok.clear()   # "ask each time" means each request, not once per boot

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
        history.append({"role": "user", "content": _for_history(user_text)})
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
        history.append({"role": "user", "content": _for_history(user_text)})
        history.append({"role": "assistant", "content": reply})
        return reply

    # The same short request as before, whose tool calls depended on nothing that may have changed: they
    # run straight away and only the answer is written (see _replay). Not when the owner named a route.
    rt = None if forced else store.routine(user_text)
    if rt:
        reply = _replay(ctx, user_text, rt)
        if reply is not None:
            history.append({"role": "user", "content": _for_history(user_text)})
            history.append({"role": "assistant", "content": reply})
            return reply

    # Where this request is answered: on this computer, or (only if the owner's brain setting and an
    # account allow it) by the online model. Under 'ask' the request goes but the memory stays home.
    where = route_for(ctx, user_text, forced)
    private = where == "cloud" and config.settings.get("brain", "local") != "cloud"
    if where == "cloud":
        _going_online(ctx, private)

    # The per-turn message list carries the tool-call/tool-result loop. It is
    # LOCAL to this turn -- those raw messages are never kept in `history`,
    # because replaying them between unrelated commands confuses small models
    # and violates strict chat templates (Mistral requires alternating roles).
    # Across turns we keep only clean user/assistant text (see the end).
    msgs = build_messages(ctx, user_text, history, private=private)
    final = ""
    tools_ran = 0
    nudged = False
    shrunk = 0
    escalated = False
    first_calls = []           # the step-0 tool calls, kept as a routine when the turn goes well
    tool_steps = 0
    fresh = len(msgs[-1].get("content") or "")   # characters the model has not seen yet (its cache holds the rest)
    while True:
        chat = llm.cloud_chat if where == "cloud" else llm.chat
        for step in range(MAX_STEPS):
            stream = ctx.new_stream()
            est = expect_seconds(where, fresh)
            if est:
                _ctx(ctx, "expect", est, step)
            t0 = time.time()
            try:
                result = chat(msgs, tools=tools.schemas() if where == "cloud" else tool_schemas(),
                              on_text=lambda t: ctx.on_text(stream, t))
            except llm.CloudError as e:
                # the online model did not answer: say so and carry on here with the same messages
                ctx.end_stream(stream)
                _ctx(ctx, "brain", False, "")
                ctx.status(f"the online model did not answer ({e}); answering here")
                where, chat, escalated = "local", llm.chat, True
                continue
            except llm.ModelError as e:
                ctx.end_stream(stream)
                # too long for the model's memory (small machines run a 6k context): retry with the
                # history dropped and the request halved, twice, before giving up
                if "too long" in str(e) and not tools_ran and not final and shrunk < 2:
                    shrunk += 1
                    keep = max(800, len(user_text) // 2)
                    user_text = user_text[:keep].rstrip() + "\n[… cut here: the request was too long …]"
                    ctx.status("too long for the model's memory; trying with a shorter version")
                    msgs = build_messages(ctx, user_text, [], private=private)
                    continue
                raise
            except llm.ModelDown:
                ctx.end_stream(stream)
                raise
            ctx.end_stream(stream)
            _learn_speed(result.get("timings") or {}, time.time() - t0, where)
            content = result["content"].strip()
            calls = result["tool_calls"]
            if content:
                final = content
            if not calls:
                # honesty guard: the model narrated an action but ran no tool for it
                if not tools_ran and not nudged and _CLAIM_RE.search(content):
                    nudged = True
                    msgs.append({"role": "assistant", "content": content, **({"_anthropic": result["raw"]} if result.get("raw") else {})})
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
            if result.get("raw"):
                assistant_msg["_anthropic"] = result["raw"]     # replayed unchanged on the next step (llm.py)
            msgs.append(assistant_msg)
            fresh = 0
            for i, call in enumerate(calls):
                cid = call["id"] or f"call_{step}_{i}"
                out = execute(ctx, call["name"], call["arguments"])
                tools_ran += 1
                fresh += len(out)
                if tool_steps == 0:
                    first_calls.append((call["name"], call["arguments"], out))
                msgs.append({"role": "tool", "tool_call_id": cid, "content": out})
            tool_steps += 1
            if ctx.after_turn:
                break
        else:
            # ran out of steps without a plain answer: ask for one final summary
            if not final:
                try:
                    msgs.append({"role": "user", "content":
                                 "Stop using tools now and give me a one or two sentence plain answer "
                                 "based on what you found, or say plainly if you could not do it."})
                    final = chat(msgs, on_text=None).get("content", "").strip()
                    if final:
                        st = ctx.new_stream()
                        ctx.on_text(st, final)
                        ctx.end_stream(st)
                except (llm.ModelDown, llm.CloudError):
                    pass
            # under 'ask', a request this computer could not finish may go to the online model -- with a yes
            if not final and not escalated and where == "local" and _can_escalate(ctx) and _ctx(ctx, "confirm_online", user_text, "failed", default=False):
                escalated, where = True, "cloud"
                _going_online(ctx, True)
                msgs = build_messages(ctx, user_text, history, private=True)
                tools_ran, nudged = 0, False
                continue
            if not final:
                final = "I wasn't able to finish that. Try rephrasing, or check `audit` to see what I tried."
                ctx.status(i18n.t("stopped"))
        break
    # a turn that went well in one tool step may be repeated without thinking next time
    if tool_steps == 1 and final and not nudged and not shrunk and not forced and not getattr(ctx, "after_turn", None):
        _maybe_save_routine(user_text, first_calls)
    # keep only the clean exchange in cross-turn history
    history.append({"role": "user", "content": _for_history(user_text)})
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
        task, kind = str(args.get("task", "")), args.get("kind")
        if kind in ("timer", "reminder") and not low.startswith("error"):
            m = re.match(r"scheduled \[\w+\] (.+?): ", out, re.I)   # "scheduled [id] Thu 01 Oct 09:52: task"
            desc = m.group(1) if m else ""
            repeating = desc.lower().startswith("every")
            when = desc.split(" ")[-1] if desc and not repeating else ""
            if kind == "timer":
                return f"Timer set — {task}, it rings at {when}." if when else f"Timer set — {task}."
            if repeating:
                return f"Reminder {desc}: {task}."
            return f"Reminder set for {when}: {task}." if when else f"Reminder set: {task}."
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


_SECRET_NAME = re.compile(r"pass|secret|token|credential|authori|cookie|^(?:api_?)?key$|_key$|apikey|private", re.I)
_SECRET_VALUE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|sk-ant-[A-Za-z0-9_-]{8,}|xox[abp]-[A-Za-z0-9-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|"
                           r"hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})")


def _redacted(args):
    """Tool arguments as shown on screen and kept in the audit log: secrets the owner typed (an email or Wi-Fi
    password, an API key, a token in a connector's environment or headers) are not echoed or stored -- by the
    argument's name, inside nested settings, and by the look of the value (sk-..., tokens) wherever it is."""
    if isinstance(args, dict):
        return {k: ("•••" if isinstance(v, (str, int)) and _SECRET_NAME.search(str(k)) and str(v) else _redacted(v))
                for k, v in args.items()}
    if isinstance(args, list):
        return [_redacted(v) for v in args]
    if isinstance(args, str):
        return _SECRET_VALUE.sub("•••", args)
    return args


# a request that carries a credential ("set up my email: ... password hunter2", "connect to Wi-Fi X with password
# Y", "key sk-...") is kept in the conversation without it: the conversation is replayed to the model on later
# turns, and to the online model when the owner's brain setting sends one there
_CREDENTIAL_IN_TEXT = re.compile(r"(\b(?:pass(?:word|phrase|code)?|pwd|api[\s_-]?key|key|token|secret)(?:\s+is)?(?:\s*[=:]\s*|\s+))(\S{4,})", re.I)
_PROVIDES_CREDENTIAL = re.compile(r"set ?up|connect|log ?in|sign ?in|account|wi-?fi|e-?mail|\bmail\b|online model|\bapi\b", re.I)


def _for_history(text):
    t = _SECRET_VALUE.sub("•••", text)
    if _PROVIDES_CREDENTIAL.search(t):
        t = _CREDENTIAL_IN_TEXT.sub(lambda m: m.group(1) + "•••", t)
    return t


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

    # unattended runs (the scheduler) go through ctx.confirm_action for anything irreversible: it follows the owner's
    # autonomy level (hands-off runs what was scheduled; balanced/hands-on leave it undone), and never a security change
    if needs_confirm(risk) or (getattr(ctx, "headless", False) and risk in (tools.DESTRUCTIVE, tools.SECURITY)):
        if not ctx.confirm_action(tool, shown, risk):
            store.audit(name, shown, "denied", allowed=False)
            return f"the owner declined this ({name}). Do not retry it; continue or stop."

    ctx.begin_tool(tool, shown, risk)
    try:
        result = tool.fn(args, ctx)
    except Cancelled:
        raise
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
