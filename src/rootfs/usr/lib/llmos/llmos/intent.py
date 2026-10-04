"""A tiny, conservative pre-router for a few utterances that are unambiguous
and that small models handle unreliably. It only ever short-circuits when the
meaning is certain; anything with the slightest doubt falls through to the
model. Today it covers just explicit memory statements, because memory is a
core feature and some small models narrate 'remembered…' without saving.

Returns a (tool_name, args) pair to run directly, or None to defer to the model.
"""
import re

# "remember (that) X", "don't forget (that) X", "keep in mind (that) X",
# "make a note (that) X", "note (that) X". The connector is captured: a "to"
# connector ("remember to buy milk") is a reminder/task, not a fact, so we
# defer it to the model.
_MEM_CMD = re.compile(
    r"^\s*(?:please\s+)?(?:remember|don'?t\s+forget|keep\s+in\s+mind|make\s+a\s+note|note)"
    r"(?:\s+(?P<conn>that|to|:))?\s+(?P<fact>.+?)\s*$", re.I)
# "my name is X" / "call me X"  -> store as a name fact. The name must not start
# with an article ("call me a taxi" is not a name).
_NAME = re.compile(r"^\s*(?:my\s+name\s+is|you\s+can\s+call\s+me|call\s+me)\s+"
                   r"(?!a\s|an\s|the\s)(?P<name>[\w .'-]{1,40})\s*$", re.I)

# Things that look like memory verbs but are really questions or other intents.
# ("forget" is not listed: the memory patterns already don't match a bare
# "forget X", and it must not veto "don't forget …".)
_NOT_MEMORY = re.compile(
    r"\b(what|which|when|who|where|why|how|do you|did you|have you|can you|could you|"
    r"tell me|show|list|remind me to)\b", re.I)


def _first_person(fact):
    """Rewrite a fact stated in the first person ('I prefer X', 'my dog is Rex')
    into third person ('User prefers X') so it reads correctly when recalled."""
    f = fact.strip().rstrip(".")
    if re.match(r"^i'?m\b", f, re.I):
        return "User is " + re.sub(r"^i'?m\s+", "", f, flags=re.I)
    if re.match(r"^i\s+am\b", f, re.I):
        return "User is " + re.sub(r"^i\s+am\s+", "", f, flags=re.I)
    if re.match(r"^i\b", f, re.I):
        return "User " + re.sub(r"^i\s+", "", f, flags=re.I)
    if re.match(r"^my\b", f, re.I):
        return "User's " + re.sub(r"^my\s+", "", f, flags=re.I)
    return f[0].upper() + f[1:] if f else f


# ---------------------------------------------------------------- scheduling
# "in 20 minutes, remind me to stretch" / "remind me to stretch in 20 minutes"
# / "every morning at 8 give me the weather". The time phrase must parse with
# the real scheduler parser and the task must read as an instruction.
_WHEN = (r"(?:in\s+(?:\d+(?:\.\d+)?|an?|one|two|three|four|five|ten|fifteen|twenty|thirty|half\s+an)\s+"
         r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)"
         r"|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?"
         r"|tomorrow(?:\s+(?:morning|evening|night|noon|afternoon))?(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?"
         r"|tonight(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?"
         r"|every\s+(?:\w+\s+){0,2}?(?:at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|morning|evening|afternoon|noon|night|"
         r"midnight|hour|day|week|weekday|weekend|\d+\s*(?:minutes?|mins?|hours?|days?))"
         r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?)")   # "every morning AT 8"
_TIME_LEAD = re.compile(rf"^\s*(?P<when>{_WHEN})\s*[,:]?\s+(?P<task>\S.+?)\s*$", re.I)
_TIME_TRAIL = re.compile(rf"^\s*(?P<task>.+?)[,]?\s+(?P<when>{_WHEN})\s*[.!]?\s*$", re.I)
_IMPERATIVE = re.compile(
    r"^(?:please\s+)?(?:remind|tell|give|send|show|run|check|play|make|create|back\s*up|turn|set|open|close|"
    r"download|install|update|upgrade|wake|summari[sz]e|fetch|search|find|delete|remove|clean|start|stop|"
    r"restart|reboot|shut|lock|ping|email|write|read|list|notify|alert|call|text|buy|water|take|do|put|"
    r"add|sync|look|get|pull|push|compile|build|test|generate|prepare|report|log|record|save|export|"
    r"import|convert|copy|move|rename|archive|compress|empty|clear|kill|change|switch|enable|disable|"
    r"mute|unmute|dim|brighten|lower|raise|pause|resume|remember|note)\b", re.I)
_QUESTION = re.compile(r"\?\s*$|^\s*(?:what|when|where|who|why|how|is|are|do|does|did|can|could|will|would|should)\b", re.I)


def _schedule(text):
    if _QUESTION.search(text):
        return None
    for rx in (_TIME_LEAD, _TIME_TRAIL):
        m = rx.match(text)
        if not m:
            continue
        when, task = m.group("when").strip(), m.group("task").strip().rstrip(".,;")
        if not _IMPERATIVE.match(task):
            continue
        try:
            from . import store
            store.parse_when(when)
        except Exception:
            continue
        return ("schedule_task", {"when": when, "task": task})
    return None


# ---------------------------------------------------------------- email replies
# "reply to Alice that Friday works" / "reply to Bob saying I'll pay by the 30th":
# the owner dictated the text; send it as a reply to that person's latest
# message. Only when a mail account exists; small models otherwise read the
# time words in the text as a scheduling request.
_REPLY = re.compile(
    r"^\s*(?:please\s+)?(?:reply|respond|answer)\s+(?:back\s+)?to\s+(?P<who>[A-Za-z][\w.'\- ]{0,40}?)"
    r"(?:'s\s+(?:e-?mail|message|mail))?\s*(?:,|:|that|saying|with|and say|and tell (?:him|her|them))\s+(?P<body>.+?)\s*$",
    re.I)


def _reply(text):
    m = _REPLY.match(text)
    if not m:
        return None
    try:
        from . import mail
        if not mail.account():
            return None
    except Exception:
        return None
    who, body = m.group("who").strip(), m.group("body").strip()
    if len(body) < 2 or _QUESTION.search(body[:1]):
        return None
    return ("mail_reply", {"id": who, "body": body[0].upper() + body[1:]})


# ---------------------------------------------------------------- email account
# "set up my email: address me@example.com, password …, imap host …, port 993":
# the owner spelled the account out, so every field is passed through as
# given. Left to the model, fields it doesn't expect get dropped (it once lost
# the SMTP host and port and then told the owner to use a "real provider").
_MAIL_SETUP = re.compile(
    r"^\s*(?:please\s+)?(?:set\s*up|configure|add|connect|log\s*in\s+to|use)\s+(?:my\s+|an?\s+|the\s+)?"
    r"(?:e-?mail|mail)(?:\s+account)?\s*[:,\-]?\s*(?P<fields>.+)$", re.I)
_MAIL_FIELD = re.compile(
    r"(?<![\w@.])(?P<key>address|e-?mail|user(?:\s*name)?|login|password|pass|pwd|"
    r"imap[\s_-]*(?:host|server|port|ssl|tls)|smtp[\s_-]*(?:host|server|port|security|encryption)|"
    r"port|(?:display\s+)?name)\b\s*(?:[:=]|is)?\s*", re.I)
_MAIL_KEYS = {"address": "address", "email": "address", "e-mail": "address", "user": "address",
              "username": "address", "login": "address", "password": "password", "pass": "password",
              "pwd": "password", "imaphost": "imap_host", "imapserver": "imap_host", "imapport": "imap_port",
              "imapssl": "imap_ssl", "imaptls": "imap_ssl", "smtphost": "smtp_host", "smtpserver": "smtp_host",
              "smtpport": "smtp_port", "smtpsecurity": "smtp_security", "smtpencryption": "smtp_security",
              "name": "name", "displayname": "name"}


def _mail_setup(text):
    m = _MAIL_SETUP.match(text)
    if not m:
        return None
    fields = m.group("fields")
    hits = list(_MAIL_FIELD.finditer(fields))
    args, last_host = {}, ""
    for i, h in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(fields)
        val = re.sub(r"\s+(?:and|&)$", "", fields[h.end():end].strip().rstrip(",;.").strip(), flags=re.I)
        val = val.strip(" '\"“”‘’")
        key = re.sub(r"[\s_-]", "", h.group("key").lower())
        if key == "port":                       # "imap server X port 993": the port of the host just named
            key = {"imap_host": "imapport", "smtp_host": "smtpport"}.get(last_host, "")
        key = _MAIL_KEYS.get(key)
        if not key or not val:
            continue
        if key in ("imap_port", "smtp_port"):
            if not val.isdigit():
                continue
            val = int(val)
        elif key == "imap_ssl":
            val = val.lower() not in ("no", "false", "off", "0", "none", "plain")
        elif key == "smtp_security":
            v = val.lower()
            val = "none" if v in ("none", "no", "plain", "off", "false", "0") else \
                "ssl" if v in ("ssl", "smtps", "implicit", "tls/ssl") else "starttls"
        elif key in ("imap_host", "smtp_host"):
            last_host = key
        args[key] = val
    if "@" not in args.get("address", "") or not args.get("password"):
        return None
    return ("mail_setup", args)


# ---------------------------------------------------------------- the look
# "make everything purple", "make the background dark blue", "turn the text
# green with square corners", "rounded corners", "no sharp corners": the owner
# named a colour the theme engine knows, so the change is exact (the model
# once turned "everything green" into black text on white with green frames).
# Anything vaguer about the look ("make it cosier") still goes to the model.
_CORNER_WORDS = {"square": "square", "sharp": "square", "rounded": "rounded", "round": "rounded",
                 "double": "double", "heavy": "heavy", "no": "none", "none": "none"}
_LOOK = re.compile(
    r"^\s*(?:please\s+)?(?:make|turn|set|change|paint|colou?r)\s+"
    r"(?P<what>everything|it all|it|the\s+(?:whole\s+)?(?:screen|interface|ui|display|theme|look|console|terminal|colou?rs?)|"
    r"(?:the\s+|my\s+)?(?:text|font|letters|writing|foreground)|(?:the\s+|my\s+)?background|"
    r"(?:the\s+|my\s+)?(?:accent|highlights?|frames?|prompt))"
    r"(?:\s+colou?r)?\s+(?:to\s+|into\s+|in\s+)?(?P<color>#?[0-9a-f]{3,6}|[a-z]+(?:\s+[a-z]+)?)"
    r"(?:\s*(?:,|and|with|,\s*with)\s+(?P<corners>square|sharp|rounded?|round|double|heavy|no)\s+corners)?"
    r"(?:\s+please)?\s*[.!]?\s*$", re.I)
_CORNERS = re.compile(
    r"^\s*(?:please\s+)?(?:(?:make|set|use|give me|i want|switch to)\s+)?(?:the\s+|everything\s+with\s+)?"
    r"(?P<corners>square|sharp|rounded?|round|double|heavy|no)\s+corners(?:\s+(?:please|everywhere|only))?\s*[.!]?\s*$"
    r"|^\s*(?:please\s+)?no\s+(?P<nosharp>sharp)\s+corners\s*[.!]?\s*$", re.I)


_SCALE = re.compile(
    r"^\s*(?:please\s+)?(?:(?:make|turn)\s+(?:everything|the\s+text|the\s+font|the\s+letters|it|the\s+interface|the\s+screen)\s+"
    r"(?:a\s+(?:bit|little)\s+|much\s+|way\s+)?(?P<how>bigger|larger|smaller|tinier|huge|normal\s+size(?:d)?|the\s+default\s+size)"
    r"|(?P<how2>bigger|larger|smaller)\s+(?:text|font|letters|writing)|zoom\s+(?P<zoom>in|out)|(?:reset|normal)\s+(?:the\s+)?(?:text\s+)?size)"
    r"(?:\s+please)?\s*[.!]?\s*$", re.I)


def _scale(text):
    m = _SCALE.match(text)
    if not m:
        return None
    how = (m.group("how") or m.group("how2") or m.group("zoom") or "default").lower()
    if how in ("bigger", "larger", "huge", "in"):
        return ("set_appearance", {"scale": "bigger"})
    if how in ("smaller", "tinier", "out"):
        return ("set_appearance", {"scale": "smaller"})
    return ("set_appearance", {"scale": "default"})


_MOTION = re.compile(r"^\s*(?:please\s+)?(?:(?:turn|switch)\s+(?:the\s+)?(?:animations?|motion|effects)\s+(?:back\s+)?(?P<onoff>on|off)"
                     r"|(?:turn|switch)\s+(?P<onoff2>on|off)\s+(?:the\s+)?(?:animations?|motion|effects)"
                     r"|(?:disable|stop|remove|kill)\s+(?:the\s+|all\s+)?(?P<dis>animations?|motion|effects)"
                     r"|(?:enable|restore)\s+(?:the\s+|all\s+)?(?P<en>animations?|motion|effects)"
                     r"|(?P<no>no|without)\s+(?:animations?|motion|effects)"
                     r"|(?P<less>fewer|less|reduce|reduced|minimal|calmer|subtle)\s+(?:animations?|motion|effects)"
                     r"|reduce\s+(?:the\s+)?(?P<less2>motion|animations?)"
                     r"|(?P<more>more|full|all|normal)\s+(?:animations?|motion|effects)"
                     r"|(?:animations?|motion|effects)\s+(?P<lvl>on|off|full|reduced|none|minimal))(?:\s+please)?\s*[.!]?\s*$", re.I)


def _motion(text):
    m = _MOTION.match(text)
    if not m or _QUESTION.search(text):
        return None
    g = m.groupdict()
    if g["less"] or g["less2"]:
        lvl = "reduced"
    elif g["dis"] or g["no"] or (g["onoff"] or g["onoff2"] or "").lower() == "off":
        lvl = "off"
    elif g["lvl"]:
        lvl = {"on": "full", "off": "off", "full": "full", "reduced": "reduced", "none": "off", "minimal": "reduced"}[g["lvl"].lower()]
    else:
        lvl = "full"
    return ("set_appearance", {"motion": lvl})


# "I want a Windows 7 clone desktop" / "make it look like a Mac" / "give me a clean desk": the desk's
# arrangement, with colours to match. Plain "normal"/"clean"/"default" need a desk word to count.
_LAYOUT = re.compile(r"^\s*(?:please\s+)?(?:i\s+want\s+|i'?d\s+like\s+|give\s+me\s+|make\s+(?:it|this|the\s+desk(?:top)?|everything)\s+(?:look\s+)?(?:like\s+)?|"
                     r"(?:(?:switch|change|go|turn)\s+(?:it\s+|this\s+)?)?(?:back\s+)?(?:to|into)\s+|use\s+|build\s+(?:me\s+)?|construct\s+(?:me\s+)?)?(?:a\s+|an\s+|the\s+)?"
                     r"(?P<which>windows(?:\s*(?:7|xp|10|11|vista))?|win\s*7|mac\s*os(?:\s+[a-z]+)?|macos(?:\s+[a-z]+)?|mojave|mac|classic|traditional|normal|clean|default|llm\s*os)"
                     r"(?:[\s-]+(?:style|like|clone|look|looking))?(?:\s+(?P<desk>desk(?:top)?|layout|interface|ui|look|shell))?\s*[.!]?\s*$", re.I)
_LAYOUT_PRESETS = {"windows": {"layout": "windows", "accent": "#4aa3ff", "background": "#143259", "color": "#f2f6fb"},
                   "mac": {"layout": "mac", "accent": "#0a84ff", "background": "#1e1e22", "color": "#ececec"},
                   "clean": {"layout": "clean", "accent": "default", "background": "default", "color": "default"}}


def _layout(text):
    m = _LAYOUT.match(text)
    if not m or _QUESTION.search(text):
        return None
    w = m.group("which").lower()
    if w in ("normal", "clean", "default") and not m.group("desk"):
        return None
    if w == "mac" and not m.group("desk") and not re.search(r"\b(?:like|style)\b", text, re.I):
        return None
    which = "mac" if ("mac" in w or "mojave" in w) else "clean" if w in ("normal", "clean", "default") or "llm" in w else "windows"
    return ("set_appearance", dict(_LAYOUT_PRESETS[which]))


def _look(text):
    lay = _layout(text)
    if lay:
        return lay
    mo = _motion(text)
    if mo:
        return mo
    sc = _scale(text)
    if sc:
        return sc
    m = _CORNERS.match(text)
    if m:
        c = "rounded" if m.group("nosharp") else _CORNER_WORDS[m.group("corners").lower()]
        return ("set_appearance", {"corners": c})
    m = _LOOK.match(text)
    if not m or _QUESTION.search(text):
        return None
    from . import ui
    color = m.group("color").strip()
    if ui.parse_color(color) is None and color.lower() not in ("default", "normal"):
        return None
    what = m.group("what").lower()
    key = "background" if "background" in what else \
        "accent" if re.search(r"accent|highlight|frame|prompt", what) else "color"
    args = {key: color}
    if key == "color" and not re.search(r"text|font|letters|writing|foreground", what):
        args["accent"] = color        # "everything purple": text AND frames, buttons, highlights
    if m.group("corners"):
        args["corners"] = _CORNER_WORDS[m.group("corners").lower()]
    return ("set_appearance", args)


# installing onto the computer's disk: deterministic on purpose (never leave a
# disk write to the model). The confirmation phrase carries the plan token
# that only the plan window's button knows.
_INSTALL = re.compile(r"^\s*(?:please\s+)?(?:(?P<erase>erase|wipe|format)\s+(?:the\s+)?(?:whole\s+|entire\s+)?(?:disk|drive|computer|machine|everything)\s+and\s+)?"
                      r"install\s+(?:llm\s*os|this\s+(?:os|system)|yourself)\s+(?:on|onto|to)\s+(?:it|(?:this|the|my)\s+"
                      r"(?P<what>computer|machine|pc|mac|laptop|disk|drive|hard\s*drive|ssd|internal\s+disk))"
                      r"(?:\s+(?P<how>next\s+to|alongside|beside|with|keeping|without\s+erasing)\b.*|\s+\((?P<paren>[^)]*)\))?\s*[.!]?\s*$", re.I)
_INSTALL_OK = re.compile(r"^\s*install\s+llm\s*os:\s*confirmed\s+(?P<token>[0-9a-f]{8})\s*$", re.I)


def _install(text):
    m = _INSTALL_OK.match(text)
    if m:
        return ("install_to_disk", {"token": m.group("token")})
    m = _INSTALL.match(text)
    if not m:
        return None
    whole = bool(m.group("erase")) or re.search(r"\b(whole|entire|erase|wipe|all of it)\b", text, re.I) is not None
    return ("install_to_disk", {"mode": "whole" if whole else "alongside"})


# ---------------------------------------------------------------- policies, language, power
# Security policies, the interface language and powering off are simple
# sentences with exact meanings; they are routed here so that the policy
# confirmations (loosening asks) and the firewall changes never depend on the
# model reading them right. Every route still goes through the same tool.
_INTERNET = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"(?P<ask>ask(?:\s+me)?\s+(?:each\s+time|every\s+time|first|before)(?:\s+(?:before\s+)?(?:you\s+)?(?:use|using|go(?:ing)?\s+(?:on|online)|access(?:ing)?|connect(?:ing)?\s+to)\s+(?:the\s+)?(?:internet|web|network))?"
    r"|(?:set\s+)?(?:the\s+)?internet\s+(?:to\s+)?ask(?:\s+each\s+time)?)"
    r"|(?P<off>(?:turn|switch)\s+(?:the\s+)?internet\s+off|(?:no|disable|block|cut)\s+(?:the\s+)?internet(?:\s+access|\s+use)?|go\s+offline|internet\s+off)"
    r"|(?P<on>(?:allow|enable|turn\s+on|switch\s+on)\s+(?:the\s+)?internet(?:\s+use|\s+access)?|(?:turn|switch)\s+(?:the\s+)?internet(?:\s+back)?\s+on|go\s+online|internet\s+on)"
    r")\s*[.!]?\s*$", re.I)
_TOR = re.compile(r"^\s*(?:please\s+)?(?:(?P<on>(?:use|enable|turn\s+on|switch\s+on)\s+tor|(?:route|send)\s+(?:everything|all\s+traffic|the\s+internet|my\s+traffic)\s+(?:through|via|over)\s+tor|internet\s+through\s+tor|tor\s+on)"
                  r"|(?P<off>(?:stop\s+using|disable|turn\s+off|switch\s+off)\s+tor|tor\s+off|no\s+tor))\s*[.!]?\s*$", re.I)
_AUTONOMY = re.compile(r"^\s*(?:please\s+)?(?:(?:switch|change|set|go|put\s+me)\s+(?:back\s+)?(?:to|into|in)\s+|be\s+|use\s+)?"
                       r"(?P<mode>hands[\s-]?off|hands[\s-]?on|balanced|fully\s+autonomous|autonomous|supervised)(?:\s+mode)?\s*[.!]?\s*$", re.I)
_ASK_BEFORE = re.compile(r"^\s*(?:please\s+)?(?:always\s+)?ask(?:\s+me)?(?:\s+first)?\s+before\s+(?P<what>.+?)\s*[.!]?\s*$", re.I)
_NEVER_ASK = re.compile(r"^\s*(?:please\s+)?(?:don'?t|do\s+not|never|stop)\s+ask(?:ing)?(?:\s+me)?(?:\s+(?:for\s+permission|before\s+(?:doing\s+)?(?:anything|things|changes)|anything))?\s*[.!]?\s*$", re.I)
_SPEAK = re.compile(r"^\s*(?:please\s+)?(?:(?P<on>(?:read|speak|say)\s+(?:your\s+|the\s+|all\s+)?(?:replies|answers|responses)\s+(?:aloud|out\s+loud)|speak\s+(?:to\s+me|your\s+replies)|talk\s+to\s+me)"
                    r"|(?P<off>(?:stop|don'?t)\s+(?:reading|speaking|saying)\s+(?:your\s+|the\s+)?(?:replies|answers|responses)(?:\s+aloud|\s+out\s+loud)?|(?:be\s+)?quiet|stop\s+talking))\s*[.!]?\s*$", re.I)
_FOCUS = re.compile(r"^\s*(?:please\s+)?(?:(?P<on>(?:turn\s+on|enable|start|begin)\s+focus(?:\s+mode)?|focus\s+mode(?:\s+on)?|focus)(?:\s+for\s+(?P<n>\d+)\s*(?P<u>minutes?|mins?|hours?|hrs?))?"
                    r"|(?P<off>(?:turn\s+off|disable|stop|end)\s+focus(?:\s+mode)?|focus\s+mode\s+off))\s*[.!]?\s*$", re.I)
_LANGUAGE = re.compile(r"^\s*(?:please\s+)?(?:(?:put|switch|set|change|make|turn)\s+(?:everything|the\s+(?:whole\s+)?(?:interface|system|os|ui)|it|yourself|all\s+of\s+it)\s+(?:back\s+)?(?:in|to|into)\s+|speak\s+|talk\s+(?:to\s+me\s+)?in\s+|(?:use|switch\s+to)\s+)"
                       r"(?P<lang>[^\W\d_][^\W\d_ ]{1,20}(?:\s+\([^)]{2,20}\))?)\s*(?:from\s+now\s+on)?\s*[.!]?\s*$", re.I)
_SPLIT_LANG = re.compile(r"^\s*(?:please\s+)?(?:put\s+|show\s+|make\s+)?(?:the\s+)?settings\s+in\s+(?P<sl>[^\W\d_]{2,20})(?:\s*,?\s*(?:but|and)\s+(?:keep\s+)?(?:everything\s+else|the\s+rest|all\s+else)\s+in\s+(?P<l>[^\W\d_]{2,20}))?\s*[.!]?\s*$", re.I)
_POWER = re.compile(r"^\s*(?:please\s+)?(?:(?P<off>shut\s*down|power\s+off|turn\s+off|switch\s+off|power\s+down)|(?P<re>restart|reboot))"
                    r"(?:\s+(?:the\s+|this\s+|my\s+)?(?:computer|machine|pc|system|laptop|it|yourself|llm\s*os))?(?:\s+now|\s+please)?\s*[.!]?\s*$", re.I)
_NOT_A_LANGUAGE = {"purple", "green", "blue", "red", "black", "white", "dark", "light", "chinese food", "order", "half", "full", "focus"}
# where it thinks (the settings panel's three phrases and their natural variants); checked before the
# internet/"ask me before" rules, which would otherwise swallow "ask me before going online"
_ONLINE = r"(?:the\s+)?(?:online\s+(?:model|ai|brain)|cloud(?:\s+model)?|claude)"
_BRAIN = re.compile(r"^\s*(?:please\s+)?(?:(?P<local>(?:think|answer|do\s+everything|keep\s+(?:everything|it\s+all)|stay)\s+(?:only\s+)?(?:on|here\s+on)\s+this\s+(?:computer|machine)(?:\s+only)?"
                    r"|(?:stop|don'?t|never)\s+(?:use|using)\s+" + _ONLINE + r"(?:\s+(?:any\s*more|again))?|(?:go|stay)\s+offline\s+for\s+(?:the\s+)?(?:thinking|answers|ai))"
                    r"|(?P<ask>ask(?:\s+me)?(?:\s+first)?\s+before\s+(?:going\s+online|using\s+" + _ONLINE + r"|sending\s+(?:anything|a\s+request)\s+online)(?:\s+for\s+big\s+(?:tasks|requests|ones|things))?)"
                    r"|(?P<cloud>(?:use|let)\s+" + _ONLINE + r"\s+(?:for|do|answer|handle)\s+everything|send\s+everything\s+(?:to\s+)?" + _ONLINE + r"|(?:always\s+)?use\s+" + _ONLINE + r"))\s*[.!]?\s*$", re.I)
_CLOUD_SETUP = re.compile(r"^\s*(?:please\s+)?(?:(?P<setup>(?:set\s+up|add|connect|configure)\s+(?:the\s+|an\s+|my\s+)?(?:online\s+(?:model|ai)|cloud\s+model|claude(?:\s+account)?|openai|anthropic))"
                          r"|(?P<forget>(?:forget|remove|disconnect|delete)\s+(?:the\s+|my\s+)?(?:online\s+(?:model|ai)|cloud\s+model|claude(?:\s+account)?|openai|anthropic)(?:\s+account)?))\s*[.!]?\s*$", re.I)
# switching the online model: "use the online model claude-opus-5-5", "switch the online model to opus", "use opus online"
_ONLINE_USE = re.compile(r"^\s*(?:please\s+)?(?:"
                         r"(?:switch|change|set)\s+(?:the\s+)?online\s+(?:model|ai)\s+to\s+(?P<n1>[\w][\w .\-]{1,40}?)"
                         r"|use\s+(?:the\s+)?online\s+(?:model|ai)\s+(?P<n2>[\w][\w .\-]{1,40}?)"
                         r"|(?:use|switch\s+to)\s+(?P<n3>[\w][\w .\-]{1,40}?)\s+online)\s*[.!]?\s*$", re.I)


# the agentic model refresh, and adding a specific Hugging Face repo
_NEW_MODELS = re.compile(r"^\s*(?:please\s+)?(?:(?:check|look|search)\s+(?:for\s+)?|find\s+|see\s+if\s+there\s+are\s+(?:any\s+)?|are\s+there\s+(?:any\s+)?|is\s+there\s+(?:a\s+)?|refresh\s+(?:the\s+)?)"
                         r"(?:new|newer|updated|the\s+latest|better)?\s*(?:and\s+(?:updated|newer))?\s*models?(?:\s+(?:list|available|out|i\s+can\s+use|to\s+use))?\s*[.!?]?\s*$"
                         r"|^\s*(?:please\s+)?refresh\s+(?:the\s+)?models?(?:\s+list)?\s*[.!]?\s*$", re.I)
_ADD_MODEL = re.compile(r"^\s*(?:please\s+)?(?:add|install|get)\s+(?:the\s+)?(?:model|gguf)\s+(?P<repo>[\w.\-]+/[\w.\-]+)(?:\s+(?P<file>[\w.\-]+\.gguf))?\s*[.!]?\s*$", re.I)


# connectors (the apps of this OS): add / enable / disable / remove
_CONN_TOGGLE = re.compile(r"^\s*(?:please\s+)?(?P<act>enable|disable|turn\s+on|turn\s+off|remove|delete|uninstall)\s+(?:the\s+)?connector\s+(?P<name>[\w.\-]{1,40})\s*[.!]?\s*$", re.I)
_CONN_ADD = re.compile(r"^\s*(?:please\s+)?(?:add|install|set\s+up|create)\s+(?:a\s+|an\s+|the\s+)?(?:connector|app|plugin)"
                       r"(?:\s+(?:named|called)\s+(?P<name>[\w.\-]{1,40}))?"
                       r"(?:\s+(?:that\s+runs|running|with\s+(?:the\s+)?command)\s+(?P<cmd>.+?)|\s+(?:at|from|url)\s+(?P<url>https?://\S+))?\s*[.!]?\s*$", re.I)


# "pop the hood": edit the conduct section of the system prompt (the owner's, not the model's, to change)
_CONDUCT = re.compile(r"^\s*(?:please\s+)?(?:"
                      r"(?P<open>(?:edit|change|customi[sz]e|open|view|show|see|tweak)\s+(?:me\s+)?(?:the\s+|my\s+|its\s+)?(?:conduct|safety(?:\s+(?:rules|settings|section|part))?|system\s+prompt|rules|guidelines|instructions)(?:\s+(?:section|editor|rules|settings|text))?"
                      r"|pop\s+the\s+hood(?:\s+on\s+(?:the\s+)?(?:conduct|safety|rules))?)"
                      r"|(?P<reset>(?:reset|restore|revert)\s+(?:the\s+)?(?:conduct|safety\s+rules|rules)(?:\s+(?:to\s+)?(?:the\s+)?default)?))\s*[.!]?\s*$", re.I)


def _conduct(text):
    m = _CONDUCT.match(text)
    if m:
        return ("edit_conduct", {"action": "reset" if m.group("reset") else "open"})
    return None


def _connector(text):
    m = _CONN_TOGGLE.match(text)
    if m:
        act = m.group("act").lower()
        action = "remove" if act in ("remove", "delete", "uninstall") else "disable" if act in ("disable", "turn off") else "enable"
        return ("manage_connectors", {"action": action, "name": m.group("name").strip()})
    m = _CONN_ADD.match(text)
    if m:
        args = {"action": "add"}
        if m.group("name"):
            args["name"] = m.group("name")
        if m.group("cmd"):
            args["command"] = m.group("cmd").strip().strip("'\"")
            args["transport"] = "stdio"
        elif m.group("url"):
            args["url"] = m.group("url").strip()
            args["transport"] = "http"
        return ("manage_connectors", args)
    return None


# speech-to-text (voice) models: "use the turbo voice model", "download the best speech model"
_VOICE_MODEL = re.compile(r"^\s*(?:please\s+)?(?P<verb>use|switch\s+to|download|get|fetch|install|remove|delete|uninstall)\s+(?:the\s+)?"
                          r"(?P<name>[\w .\-]{1,30}?)\s+(?:voice|speech|dictation|transcription|whisper)(?:\s+to\s+text)?\s+model\s*[.!]?\s*$", re.I)
_VOICE_LIST = re.compile(r"^\s*(?:please\s+)?(?:show|list|open|what\s+are)\s+(?:me\s+)?(?:the\s+|my\s+)?(?:voice|speech|dictation|transcription)\s+models?\s*[.!?]?\s*$", re.I)


def _voice_model(text):
    m = _VOICE_MODEL.match(text)
    if m:
        verb = m.group("verb").lower()
        action = "download" if verb in ("download", "get", "fetch", "install") else \
            "remove" if verb in ("remove", "delete", "uninstall") else "use"
        return ("manage_voice", {"action": action, "model": m.group("name").strip()})
    if _VOICE_LIST.match(text):
        return ("manage_voice", {"action": "list"})
    return None


def _models_discover(text):
    if _NEW_MODELS.match(text):
        return ("check_new_models", {})
    m = _ADD_MODEL.match(text)
    if m:
        args = {"repo": m.group("repo")}
        if m.group("file"):
            args["file"] = m.group("file")
        return ("add_model", args)
    return None


def _online_model(text):
    if _BRAIN.match(text):
        return None   # "use the online model for everything" is the brain setting, handled in _policy
    m = _CLOUD_SETUP.match(text)
    if m:
        return ("online_model", {"action": "set up" if m.group("setup") else "forget"})
    m = _ONLINE_USE.match(text)
    if m:
        name = (m.group("n1") or m.group("n2") or m.group("n3") or "").strip()
        if not name:
            return None
        if not (m.group("n1") or m.group("n2")):
            # bare "use X online": only when X is a known online model, so ordinary "use X" is not stolen
            try:
                from . import llm
                low = name.lower().replace("-", " ")
                known = any(low in (mm["id"].replace("-", " ") + " " + mm["name"].lower())
                            for p in llm.CLOUD_PROVIDERS.values() for mm in p.get("models", []))
            except Exception:
                known = False
            if not known:
                return None
        return ("online_model", {"action": "use", "model": name})
    return None


def _policy(text):
    m = _POWER.match(text)
    if m:
        return ("system_power", {"action": "shutdown" if m.group("off") else "restart"})
    m = _BRAIN.match(text)
    if m:
        return ("change_setting", {"setting": "brain", "value": "local" if m.group("local") else "ask" if m.group("ask") else "cloud"})
    m = _INTERNET.match(text)
    if m:
        return ("change_setting", {"setting": "internet", "value": "ask" if m.group("ask") else "no" if m.group("off") else "yes"})
    m = _TOR.match(text)
    if m:
        return ("change_setting", {"setting": "tor", "value": "on" if m.group("on") else "off"})
    m = _AUTONOMY.match(text)
    if m:
        mode = re.sub(r"[\s-]+", "-", m.group("mode").lower())
        mode = {"fully-autonomous": "hands-off", "autonomous": "hands-off", "supervised": "hands-on"}.get(mode, mode)
        return ("change_setting", {"setting": "autonomy", "value": mode})
    m = _ASK_BEFORE.match(text)
    if m:
        what = m.group("what").lower()
        if re.search(r"\b(delet|destroy|remov|irreversible|destructive|danger|erasing|wiping)", what):
            return ("change_setting", {"setting": "autonomy", "value": "balanced"})
        if re.search(r"\b(every|any|each|all)\b.*\b(change|action|thing)|\b(changing|doing)\s+(anything|things)|\beverything\b", what):
            return ("change_setting", {"setting": "autonomy", "value": "hands-on"})
        if re.search(r"internet|web|online|network", what):
            return ("change_setting", {"setting": "internet", "value": "ask"})
        return None
    if _NEVER_ASK.match(text):
        return ("change_setting", {"setting": "autonomy", "value": "hands-off"})
    m = _SPEAK.match(text)
    if m:
        return ("change_setting", {"setting": "speak_replies", "value": "on" if m.group("on") else "off"})
    m = _FOCUS.match(text)
    if m:
        args = {"setting": "focus_mode", "value": "on" if m.group("on") else "off"}
        if m.group("on") and m.group("n"):
            n = int(m.group("n"))
            args["minutes"] = n * 60 if m.group("u").lower().startswith("h") else n
        return ("change_setting", args)
    m = _SPLIT_LANG.match(text)
    if m:
        args = {"settings_language": m.group("sl")}
        if m.group("l"):
            args["language"] = m.group("l")
        return ("set_appearance", args)
    m = _LANGUAGE.match(text)
    if m:
        lang = m.group("lang").strip()
        if lang.lower() not in _NOT_A_LANGUAGE and not _QUESTION.search(text):
            from . import ui
            if ui.parse_color(lang) is None:
                return ("set_appearance", {"language": lang})
    return None


# "download gemma 4 e2b" / "use ministral 8b" / "remove granite 3b": the name
# is matched against the catalog here (the model asked which id to use).
_MODEL_CMD = re.compile(r"^\s*(?:please\s+)?(?P<verb>download|get|fetch|install|use|switch\s+to|load|run|remove|delete|uninstall)\s+"
                        r"(?:the\s+)?(?:(?:model|llm)\s+)?(?P<name>[\w][\w .\-]{1,40}?)(?:\s+(?:model|llm|instead|now|please))?\s*[.!]?\s*$", re.I)


def _model_id(name):
    """Catalog id for a spoken model name ('gemma 4 e2b', 'ministral 8b')."""
    try:
        from . import models
        cat = models.catalog()
    except Exception:
        return None
    toks = [t for t in re.split(r"[\s\-_.]+", name.lower()) if t]
    if not toks:
        return None
    best = None
    for m in cat:
        idt = [t for t in re.split(r"[\s\-_.]+", m["id"].lower()) if t]
        namet = [t for t in re.split(r"[\s\-_.]+", m["name"].lower()) if t]
        if all(t in idt or t in namet for t in toks):
            score = len(toks) / max(len(idt), 1)
            if best is None or score > best[0]:
                best = (score, m["id"])
    # a family name alone ("gemma") is ambiguous: needs a size or version too
    if best and (len(toks) >= 2 or best[0] >= 0.99):
        return best[1]
    return None


def _model(text):
    m = _MODEL_CMD.match(text)
    if not m:
        return None
    mid = _model_id(m.group("name"))
    if not mid:
        return None
    verb = m.group("verb").lower()
    action = "download" if verb in ("download", "get", "fetch", "install") else \
        "remove" if verb in ("remove", "delete", "uninstall") else "use"
    return ("manage_models", {"action": action, "model": mid})


# "show my files" / "what's in ~/projects" / "take a screenshot"
_FILES = re.compile(r"^\s*(?:please\s+)?(?:(?:show|open|list)\s+(?:me\s+)?(?:my\s+|the\s+)?(?:files|documents|downloads|pictures|desktop|home|folder)(?:\s+(?:folder|directory|dir))?(?:\s+(?:in|of|at)\s+(?P<p>\S+))?"
                    r"|(?:show|list)\s+(?:me\s+)?(?:my\s+)?files\s+in\s+(?P<p2>\S+)|what(?:'s|\s+is)\s+in\s+(?P<p3>(?:~|/)\S*))\s*[.!?]?\s*$", re.I)
_SHOT = re.compile(r"^\s*(?:please\s+)?(?:take|grab|capture)\s+(?:a\s+)?screenshot(?:\s+of\s+(?:the\s+)?screen)?\s*[.!]?\s*$|^\s*screenshot\s*[.!]?\s*$", re.I)


_OPEN_FILE = re.compile(r"^\s*(?:please\s+)?(?:open|show|read|view)\s+(?:me\s+)?(?:the\s+)?file\s+(?P<p>(?:~|/)\S*)\s*[.!]?\s*$", re.I)
_DEL_FILE = re.compile(r"^\s*(?:please\s+)?(?:delete|remove|trash)\s+(?:the\s+)?(?:file|folder)\s+(?P<p>(?:~|/)\S*)\s*[.!]?\s*$", re.I)


_LIST_W = r"[\w' -]+?"
_NOTE_ADD = re.compile(r"^\s*(?:please\s+)?(?:add|put)\s+(?P<item>.+)\s+(?:to|on|onto)\s+(?:my\s+|the\s+)?(?P<list>[\w'-]+(?:\s[\w'-]+)?)\s+list\s*[.!]?\s*$", re.I)
_NOTE_PLAIN = re.compile(r"^\s*(?:please\s+)?(?:(?:take\s+a\s+|make\s+a\s+)?note(?:\s+that|\s+down|:)?\s+(?P<note>.+?)"
                         r"|remember\s+to\s+(?P<todo>.+?)|(?:add|new)\s+(?:a\s+)?(?:to-?do|task)(?:\s+item)?:?\s+(?P<todo2>.+?))\s*[.!]?\s*$", re.I)
_NOTES_SHOW = re.compile(r"^\s*(?:please\s+)?(?:(?:show|open|read|list)\s+(?:me\s+)?(?:my\s+|the\s+)?(?P<list>" + _LIST_W + r")\s+list"
                         r"|what(?:'s|\s+is)\s+on\s+(?:my\s+|the\s+)?(?P<list2>" + _LIST_W + r")\s+list"
                         r"|(?:show|open|read)\s+(?:me\s+)?(?:my\s+)?(?P<all>notes|lists)|what(?:'s|\s+is)\s+on\s+my\s+(?P<all2>lists?))\s*[.!?]?\s*$", re.I)
_NOTE_DONE = re.compile(r"^\s*(?:please\s+)?(?:(?:tick|check|cross)\s+off\s+(?P<a>.+?)|mark\s+(?P<b>.+?)\s+(?:as\s+)?done|un-?tick\s+(?P<u>.+?))\s*[.!]?\s*$", re.I)
_NOTE_REMOVE = re.compile(r"^\s*(?:please\s+)?(?:(?:remove|delete|take)\s+(?P<item>.+?)\s+(?:from|off)\s+(?:my\s+|the\s+)?(?P<list>" + _LIST_W + r")\s+list"
                          r"|(?:clear|empty)\s+(?:my\s+|the\s+)?(?P<list2>" + _LIST_W + r")\s+list)\s*[.!]?\s*$", re.I)
_TRASH = re.compile(r"^\s*(?:please\s+)?(?:(?P<empty>empty)\s+(?:my\s+|the\s+)?trash|(?:show|open)\s+(?:me\s+)?(?:my\s+|the\s+)?(?P<show>trash)"
                    r"|(?:restore|put\s+back|undelete)\s+(?P<name>.+?)\s+from\s+(?:my\s+|the\s+)?trash|(?:restore|put\s+back|undelete)\s+(?P<file>\S+\.\w{1,5}))\s*[.!]?\s*$", re.I)


def _notes(text):
    m = _TRASH.match(text)
    if m:
        if m.group("empty"):
            return ("empty_trash", {})
        if m.group("show"):
            return ("show_files", {"path": "~/.Trash"})
        return ("restore_file", {"name": (m.group("name") or m.group("file")).strip()})
    m = _NOTE_ADD.match(text)
    if m and not _QUESTION.search(text):
        return ("note_add", {"text": m.group("item").strip(), "list": m.group("list").strip()})
    m = _NOTES_SHOW.match(text)
    if m:
        lst = m.group("list") or m.group("list2")
        return ("notes_show", {"list": lst.strip()} if lst else {})
    m = _NOTE_REMOVE.match(text)
    if m:
        item = (m.group("item") or "all").strip()
        if item != "all" and not _note_exists(item):
            return None               # not on any list: let the model work it out
        return ("note_remove", {"item": item, "list": (m.group("list") or m.group("list2")).strip()})
    m = _NOTE_PLAIN.match(text)
    if m and not _QUESTION.search(text):
        if m.group("note"):
            note = m.group("note").strip()
            if re.match(r"(?i)^(?:i|i'm|i am|my|we|our)\b", note):
                return None           # "note that I'm vegetarian" is a fact about the owner: memory, not a list
            return ("note_add", {"text": note, "list": "notes"})
        return ("note_add", {"text": (m.group("todo") or m.group("todo2")).strip(), "list": "to-do"})
    m = _NOTE_DONE.match(text)
    if m and not _QUESTION.search(text):
        item = re.sub(r"(?i)^item\s+", "", (m.group("u") or m.group("a") or m.group("b")).strip())
        if not _note_exists(item):
            return None
        return ("note_done", {"item": item, "done": not m.group("u")})
    return None


def _note_exists(ref):
    """Only tick or remove things that are really on a list; anything else goes to the model."""
    try:
        from . import store
        return store.find_note(ref) is not None
    except Exception:
        return False


_UNIT = r"(?P<u>seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)"
_TIMER = re.compile(r"^\s*(?:please\s+)?(?:(?:set|start)\s+)?(?:a\s+)?(?:timer|countdown)\s+(?:for\s+)?(?P<n>\d+)\s*" + _UNIT + r"\b(?:\s+(?:for|to)\s+(?P<what>.+?))?\s*[.!]?\s*$", re.I)
_REMIND = re.compile(r"^\s*(?:please\s+)?(?:remind|ping|tell|alert)\s+me\s+in\s+(?P<n>\d+)\s*" + _UNIT + r"\b(?:\s+(?P<conn>to|that|about)\s+(?P<what>.+?))?\s*[.!]?\s*$", re.I)


def _timer(text):
    m = _TIMER.match(text) or _REMIND.match(text)
    if not m:
        return None
    n, u = int(m.group("n")), m.group("u").lower()
    unit = "second" if u[0] == "s" else "hour" if u[0] == "h" else "minute"
    when = f"in {n} {unit}{'s' if n != 1 else ''}"
    what = (m.group("what") or "").strip()
    length = f"{n} {unit}{'s' if n != 1 else ''}"
    if what:
        return ("schedule_task", {"when": when, "task": what, "kind": "reminder"})
    return ("schedule_task", {"when": when, "task": length, "kind": "timer"})


_AUTOLOCK = re.compile(r"^\s*(?:please\s+)?(?:(?:auto-?lock|lock(?:\s+(?:the\s+)?(?:screen|computer|vault|itself))?)\s+after\s+(?P<n>\d+)\s*(?P<u>minutes?|mins?|hours?|hrs?)"
                       r"(?:\s+(?:of\s+)?(?:idle|inactivity|no\s+activity|without\s+me))?|(?:turn\s+off|disable|no|stop)\s+(?:the\s+)?auto-?lock(?:ing)?"
                       r"|(?:never|don'?t)\s+(?:auto-?)?lock(?:\s+(?:automatically|by\s+itself|on\s+its\s+own))?)\s*[.!]?\s*$", re.I)


_PASS = re.compile(r"^\s*(?:please\s+)?(?:(?:set|set\s+up|add|create|make)\s+(?:a\s+|my\s+)?(?:passphrase|password|vault)(?:\s+for\s+(?:my\s+)?(?:data|files|computer))?"
                   r"|(?:protect|encrypt|secure)\s+(?:my\s+)?(?:data|files|storage|computer|everything)(?:\s+with\s+(?:a\s+)?(?:passphrase|password))?)\s*[.!]?\s*$", re.I)


def _autolock(text):
    if _PASS.match(text) and not _QUESTION.search(text):
        return ("set_passphrase", {})
    m = _AUTOLOCK.match(text)
    if not m:
        return None
    if m.group("n"):
        n = int(m.group("n")) * (60 if m.group("u").lower().startswith("h") else 1)
        return ("change_setting", {"setting": "autolock", "value": str(n)})
    return ("change_setting", {"setting": "autolock", "value": "off"})


_BRIGHT = re.compile(r"^\s*(?:please\s+)?(?:(?:set\s+|make\s+|put\s+)?(?:the\s+)?(?:screen\s+)?brightness\s+(?:to\s+|at\s+)?(?P<n>\d{1,3})\s*%?"
                     r"|(?:turn|make)\s+(?:the\s+)?(?:screen|brightness|display)\s+(?P<dir>up|down|brighter|dimmer|darker)|(?:increase|raise|turn\s+up)\s+(?:the\s+)?(?:screen\s+)?brightness(?P<up>)"
                     r"|(?:decrease|lower|reduce|turn\s+down|dim)\s+(?:the\s+)?(?:screen\s+)?(?:brightness|screen)(?P<down>)|(?P<b>brighter|dimmer))\s*[.!]?\s*$", re.I)
_VOL = re.compile(r"^\s*(?:please\s+)?(?:(?:set\s+|make\s+|put\s+)?(?:the\s+)?(?:volume|sound)\s+(?:to\s+|at\s+)?(?P<n>\d{1,3})\s*%?"
                  r"|(?:turn|make)\s+(?:the\s+)?(?:volume|sound|music|it)\s+(?P<dir>up|down|louder|quieter|softer)|(?:increase|raise|turn\s+up)\s+(?:the\s+)?(?:volume|sound)(?P<up>)"
                  r"|(?:decrease|lower|reduce|turn\s+down)\s+(?:the\s+)?(?:volume|sound)(?P<down>)|(?P<l>louder|quieter|softer)"
                  r"|(?P<mute>mute|unmute)(?:\s+(?:the\s+)?(?:sound|speakers?|volume|audio|it))?|(?:turn\s+(?:the\s+)?(?:sound|audio|speakers?)\s+(?P<onoff>on|off)))\s*[.!]?\s*$", re.I)


def _device(text):
    m = _BRIGHT.match(text)
    if m and not _QUESTION.search(text):
        if m.group("n"):
            return ("set_brightness", {"percent": int(m.group("n"))})
        d = (m.group("dir") or m.group("b") or ("up" if m.group("up") is not None else "down")).lower()
        return ("set_brightness", {"delta": 15 if d in ("up", "brighter") else -15})
    m = _VOL.match(text)
    if m and not _QUESTION.search(text):
        if m.group("n"):
            return ("set_volume", {"percent": int(m.group("n"))})
        if m.group("mute"):
            return ("set_volume", {"mute": m.group("mute").lower() == "mute"})
        if m.group("onoff"):
            return ("set_volume", {"mute": m.group("onoff").lower() == "off"})
        d = (m.group("dir") or m.group("l") or ("up" if m.group("up") is not None else "down")).lower()
        return ("set_volume", {"delta": 10 if d in ("up", "louder") else -10})
    return None


def _files(text):
    m = _SHOT.match(text)
    if m:
        return ("screenshot", {})
    m = _OPEN_FILE.match(text)
    if m:
        return ("open_file", {"path": m.group("p")})
    m = _DEL_FILE.match(text)
    if m:
        return ("delete_file", {"path": m.group("p")})
    m = _FILES.match(text)
    if not m:
        return None
    p = m.group("p") or m.group("p2") or m.group("p3") or ""
    if not p:
        low = text.lower()
        for word, folder in (("downloads", "~/Downloads"), ("pictures", "~/Pictures"), ("desktop", "~/Desktop"), ("documents", "~/Documents")):
            if word in low:
                p = folder
    return ("show_files", {"path": p.rstrip("?.,") or "~"})


# "show me my disk, memory and tasks in one panel" / "system status": a panel
# of real numbers, composed by the OS (the model tends to describe it in
# words instead of drawing it).
_PANEL = re.compile(r"^\s*(?:please\s+)?(?:(?:show|give|put|display)\s+(?:me\s+)?(?:my\s+|the\s+)?(?P<items>[\w ,/&]+?)\s+(?:in|on|as)\s+(?:one|a|a\s+single|the\s+same)\s+(?:panel|window|dashboard|view|screen|place|card|overview)"
                    r"|(?:show\s+(?:me\s+)?(?:my\s+|the\s+)?)?(?P<status>system\s+status|status\s+of\s+(?:this|my)\s+(?:computer|machine|system)|(?:this|my)\s+(?:computer|machine|system)'?s?\s+(?:status|health|state)|(?:a\s+)?(?:system\s+)?dashboard))\s*[.!?]?\s*$", re.I)
_PANEL_WORDS = {"disk", "storage", "space", "memory", "ram", "cpu", "processor", "load", "uptime", "battery", "power",
                "network", "wifi", "internet", "ip", "tasks", "schedule", "scheduled", "reminders"}


_PANEL_OPEN = re.compile(r"^\s*(?:please\s+)?(?:open|show|go\s+to|bring\s+up|display)\s+(?:me\s+)?(?:the\s+|my\s+)?(?P<p>settings|preferences|models|model\s+list|"
                         r"connectors|apps|plugins|integrations|scheduled\s+tasks|schedule|tasks|memory|what\s+you\s+remember|audit|recent\s+actions|activity\s+log|help)"
                         r"(?:\s+(?:panel|window|screen|page|list))?(?:\s+please)?\s*[.!]?\s*$", re.I)
_PANEL_NAMES = {"settings": "settings", "preferences": "settings", "models": "models", "model list": "models", "scheduled tasks": "tasks",
                "connectors": "connectors", "apps": "connectors", "plugins": "connectors", "integrations": "connectors",
                "schedule": "tasks", "tasks": "tasks", "memory": "memory", "what you remember": "memory", "audit": "audit",
                "recent actions": "audit", "activity log": "audit", "help": "help"}


def _panel(text):
    m = _PANEL_OPEN.match(text)
    if m:
        return ("show_panel", {"panel": _PANEL_NAMES[re.sub(r"\s+", " ", m.group("p").lower())]})
    m = _PANEL.match(text)
    if not m:
        return None
    if m.group("status"):
        return ("system_panel", {"items": []})
    words = [w for w in re.findall(r"[a-z]+", m.group("items").lower()) if w in _PANEL_WORDS]
    if not words:
        return None
    return ("system_panel", {"items": words})


# "show me a photo of the Matterhorn" is a photo window; "use a photo of the
# Alps as my wallpaper" is the wallpaper. Kept apart deterministically: given
# both tools, the model once did both for a plain "show me a photo".
_PHOTO = re.compile(r"^\s*(?:please\s+)?(?:show|find|get|pull up|bring up|display)\s+(?:me\s+)?(?:a|an|the|some)?\s*"
                    r"(?:real\s+|nice\s+|good\s+)?(?:photo(?:graph)?|picture|image|pic)s?\s+(?:of|showing)\s+(?P<what>.+?)\s*[.!?]?\s*$", re.I)
_WALLPAPER = re.compile(r"^\s*(?:please\s+)?(?:(?:use|set|put|make|show)\s+(?:a|an|the)?\s*(?:real\s+)?(?:photo(?:graph)?|picture|image)\s+of\s+(?P<what>.+?)\s+"
                        r"as\s+(?:my|the)\s+(?:wallpaper|desktop|background(?:\s+picture|\s+image)?)"
                        r"|(?:set|change|make)\s+(?:my|the)\s+(?:wallpaper|desktop background|background picture)\s+to\s+(?:a\s+)?(?:photo\s+of\s+)?(?P<what2>.+?)"
                        r"|(?P<none>remove|clear|turn off|no)\s+(?:my\s+|the\s+)?wallpaper)\s*[.!]?\s*$", re.I)


def _photo(text):
    m = _WALLPAPER.match(text)
    if m:
        if m.group("none"):
            return ("set_wallpaper", {"subject": "none"})
        return ("set_wallpaper", {"subject": (m.group("what") or m.group("what2")).strip()})
    m = _PHOTO.match(text)
    if m and not re.search(r"\bwallpaper|background\b", text, re.I):
        what = m.group("what").strip()
        if 2 <= len(what) <= 80 and not _QUESTION.search(what):
            return ("show_image", {"subject": what})
    return None


# "open https://example.com in the browser" (also what a link on the desk says)
_OPEN_URL = re.compile(r"^\s*(?:please\s+)?(?:open|go to|visit|browse|show me|load)\s+(?P<url>https?://\S+)"
                       r"(?:\s+in\s+(?:the\s+|a\s+)?(?:web\s+)?browser)?\s*[.!]?\s*$", re.I)


def _open_url(text):
    m = _OPEN_URL.match(text)
    if not m:
        return None
    import shutil
    browser = next((b for b in ("firefox-esr", "firefox", "chromium", "epiphany") if shutil.which(b)), None)
    if not browser:
        return None          # the model installs one first
    return ("open_app", {"command": f"{browser} {m.group('url').rstrip('.,)')}", "graphical": True})


_TERMINAL = re.compile(r"^\s*(?:please\s+)?(?:open|show|give me|start|launch|bring up)\s+(?:a|the|me a)?\s*"
                       r"(?:terminal|console|shell)(?:\s+window)?(?:\s+on\s+the\s+screen)?\s*[.!]?\s*$", re.I)


# "play some lofi hip hop" / "pull up a YouTube video of X and play it on the
# screen": unambiguous when media words are present; small models otherwise
# search, pause, replay and show pictures around a request that is just "play".
_PLAY = re.compile(r"^\s*(?:please\s+)?(?:play|put on|pull up|start)\s+(?:me\s+)?(?:a|an|some|the)?\s*"
                   r"(?P<q>.+?)(?:\s+(?:and\s+)?(?:play\s+it)?(?:\s+(?:on|in)\s+(?:the\s+)?(?:screen|window|background)))?"
                   r"(?:\s+please)?\s*[.!]?\s*$", re.I)
_MEDIA_WORDS = re.compile(r"\b(video|youtube|music|song|songs|stream|album|podcast|playlist|radio|mix|lofi|lo-fi|live|concert|trailer|movie|clip)\b", re.I)


def _play(text):
    m = _PLAY.match(text)
    if not m or not _MEDIA_WORDS.search(text) or _QUESTION.search(text):
        return None
    q = re.sub(r"^(?:youtube\s+)?(?:video|videos|clip)\s+(?:of|about|with)\s+", "", m.group("q").strip(), flags=re.I)
    q = re.sub(r"\s+(?:on|from)\s+youtube\b", "", q, flags=re.I).strip(" .")
    return ("play_media", {"query": q}) if len(q) >= 2 else None


def match(text):
    t = text.strip()
    if len(t) > 400 or "\n" in t:
        return None
    ms = _mail_setup(t)
    if ms:
        return ms
    if len(t) > 200:
        return None
    lk = _look(t)
    if lk:
        return lk
    ou = _open_url(t)
    if ou:
        return ou
    ins = _install(t)
    if ins:
        return ins
    ph = _photo(t)
    if ph:
        return ph
    pn = _panel(t)
    if pn:
        return pn
    fl = _files(t)
    if fl:
        return fl
    for fn in (_notes, _timer, _autolock, _device):
        r = fn(t)
        if r:
            return r
    cd = _conduct(t)
    if cd:
        return cd
    cn = _connector(t)
    if cn:
        return cn
    vm = _voice_model(t)
    if vm:
        return vm
    dm = _models_discover(t)
    if dm:
        return dm
    om = _online_model(t)
    if om:
        return om
    md = _model(t)
    if md:
        return md
    po = _policy(t)
    if po:
        return po
    if _TERMINAL.match(t):
        return ("open_app", {"command": "foot", "graphical": True})
    pl = _play(t)
    if pl:
        return pl
    rep = _reply(t)
    if rep:
        return rep
    sched = _schedule(t)
    if sched:
        return sched
    m = _NAME.match(t)
    if m:
        name = m.group("name").strip()
        if name and not _NOT_MEMORY.search(name):
            return ("remember", {"fact": f"User's name is {name}"})
    m = _MEM_CMD.match(t)
    if m:
        fact = m.group("fact").strip()
        # "remember to <do something>" is a reminder/task -> let the model decide
        if (m.group("conn") or "").lower() == "to":
            return None
        if len(fact) < 3 or _NOT_MEMORY.search(t):
            return None
        return ("remember", {"fact": _first_person(fact)})
    return None
