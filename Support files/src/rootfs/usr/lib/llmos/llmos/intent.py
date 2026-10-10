"""A tiny, conservative pre-router for a few utterances that are unambiguous
and that small models handle unreliably. It only ever short-circuits when the
meaning is certain; anything with the slightest doubt falls through to the
model. Today it covers just explicit memory statements, because memory is a
core feature and some small models narrate 'remembered…' without saving.

Returns a (tool_name, args) pair to run directly, or None to defer to the model.
"""
import re

from . import i18n

_TYPOS = {"opn": "open", "oepn": "open", "chang": "change", "chnage": "change", "volum": "volume", "voluem": "volume",
          "wat": "what", "waht": "what", "hwo": "how", "teh": "the", "remindme": "remind me", "pls": "please", "plz": "please",
          "brightnes": "brightness", "screne": "screen", "musci": "music", "pley": "play", "stpo": "stop", "timr": "timer",
          "settigns": "settings", "setings": "settings", "wifi's": "wifi", "calender": "calendar", "calcualtor": "calculator"}
_TYPO_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(_TYPOS, key=len, reverse=True)) + r")\b", re.I)


def fix_typos(text):
    """Common misspellings of command words, fixed before matching (the owner's words are otherwise kept as typed)."""
    t = str(text or "")
    if re.search(r"\b(?:password|passphrase|pin|saying|says|that says|message|email|text|note|write|type|wi-?fi|network|join|connect|ssid|name|called|named|rename)\b|[\"“”']", t, re.I):
        return t                              # the owner's own words (a message, a secret) are never touched
    words = t.split(" ")
    head = " ".join(words[:3])                # only the command words at the start
    return _TYPO_RE.sub(lambda m: _TYPOS[m.group(1).lower()], head) + ("" if len(words) <= 3 else " " + " ".join(words[3:]))

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
    r"^\s*(?:please\s+)?(?:reply|respond|answer)\s+(?:back\s+)?to\s+"
    r"(?P<who>(?!(?:the|a|an|this|that|these|those|my|our|your|his|her|their|its|it|him|them|me|us)\b)[A-Za-z][\w.'\- ]{0,40}?)"
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
# "no corners" is the brief's own example of rounding everything ("no corners and everything to be rounded")
_CORNER_WORDS = {"square": "square", "sharp": "square", "rounded": "rounded", "round": "rounded",
                 "double": "double", "heavy": "heavy", "no": "rounded", "none": "none"}
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


_MODE = re.compile(r"^\s*(?:please\s+)?(?:(?:turn|switch|put|set|change|go)\s+(?:on\s+|it\s+|everything\s+|the\s+(?:screen|computer|system|os)\s+)?"
                   r"(?:on\s+|to\s+|in(?:to)?\s+)?|use\s+|enable\s+|activate\s+|give\s+me\s+|i\s+(?:want|prefer|like)\s+|make\s+(?:it|everything|the\s+\w+)\s+)?"
                   r"(?:a\s+|an\s+|the\s+)?(?P<t>[\w #-]{2,40}?)\s+(?:mode|theme|look|colou?r\s+scheme|style|palette|skin)"
                   r"(?:\s+(?:on|please|for\s+everything|everywhere))?\s*[.!]?\s*$", re.I)
_DARK = re.compile(r"^\s*(?:please\s+)?(?:make\s+(?:it|everything|the\s+screen)\s+)?(?P<t>dark(?:er)?|light(?:er)?|darker please|lighter please)\s*[.!]?\s*$", re.I)
_FONT = re.compile(r"^\s*(?:please\s+)?(?:(?:change|switch|set|make)\s+(?:the\s+)?(?:font|typeface|letters|text\s+style|lettering)\s+(?:to\s+|into\s+)?(?:a\s+|an\s+)?|"
                   r"(?:use|give\s+me|i\s+want)\s+(?:a\s+|an\s+)?)(?P<f>[\w -]{2,30}?)(?:\s+(?:font|typeface|letters|text))?\s*[.!]?\s*$", re.I)
_BACKDROP = re.compile(r"^\s*(?:please\s+)?(?:(?:turn|switch)\s+(?P<onoff>on|off)\s+(?:the\s+)?(?:animated|living|moving)\s+(?:background|backdrop)|"
                       r"(?:make|set|turn|switch|change)\s+(?:the\s+)?(?:background|backdrop)\s+(?:to\s+|into\s+)?(?:a\s+|an\s+)?(?P<style>animated|living|alive|moving|still|static|"
                       r"plain|solid|simple|calm|photo|picture|wallpaper)|(?P<style2>animated|living|still|static|plain|solid)\s+(?:background|backdrop)(?:\s+please)?|"
                       r"(?:stop|freeze)\s+the\s+(?:background|backdrop)(?:\s+(?:moving|animation))?)\s*[.!]?\s*$", re.I)


def _theme(text):
    from . import themes
    m = _BACKDROP.match(text)
    if m:
        st = (m.group("style") or m.group("style2") or "").lower()
        if m.group("onoff"):
            st = "living" if m.group("onoff").lower() == "on" else "still"
        st = {"animated": "living", "alive": "living", "moving": "living", "static": "still", "calm": "still", "solid": "plain",
              "simple": "plain", "picture": "photo", "wallpaper": "photo", "": "still"}.get(st, st)
        return ("set_appearance", {"backdrop": st})
    m = re.fullmatch(r"(?:make|set|use|switch to|change to|give me|turn)\s+(?:it|the (?:theme|look|colou?rs?|screen))?\s*(?:to\s+|a\s+|an\s+)?(?:a\s+)?(?P<t>patriotic|patriot|americana|stars and stripes|red,? white,? (?:and|&) blue)(?:\s+(?:theme|look|colou?rs?|style))?", text.lower().strip().rstrip(".!?"))
    if m:
        return ("set_appearance", {"theme": "patriotic"})
    m = _DARK.match(text)
    if m:
        return ("set_appearance", {"theme": "dark" if m.group("t").lower().startswith("dark") else "light"})
    m = _MODE.match(text)
    if m and m.group("t").strip().lower() in ("default", "original", "normal", "standard", "stock", "usual"):
        return ("set_appearance", {"theme": "default theme"})
    if m and themes.resolve(m.group("t")) and not re.search(r"\b(?:app|airplane|aeroplane|flight|focus|sleep|power|safe|kiosk)\b", m.group("t"), re.I):
        return ("set_appearance", {"theme": m.group("t").strip()})
    m = _FONT.match(text)
    if m and re.search(r"\b(?:font|typeface|letters|lettering|text style)\b", text, re.I) and themes.font_for(m.group("f")):
        return ("set_appearance", {"font": themes.font_for(m.group("f"))})
    return None


_RESET_LOOK = re.compile(r"^\s*(?:please\s+)?(?:(?:go\s+|switch\s+|change\s+(?:it\s+)?|put\s+it\s+)?back\s+to\s+(?:the\s+)?(?:default|original|normal|standard|stock|usual|old)\s+"
                         r"(?:theme|look|colou?rs?|appearance|style)|reset\s+(?:the\s+|my\s+)?(?:theme|look|colou?rs?|appearance|style)(?:\s+to\s+(?:the\s+)?default)?|"
                         r"reset\s+(?:everything|the\s+screen)\s+to\s+(?:the\s+)?default(?:\s+look)?)\s*[.!]?\s*$", re.I)

def _look(text):
    t = text.strip().lower().rstrip(".!")
    m = re.match(r"^(?:change|set|make|use)\s+(?:the\s+)?(?:font|typeface|text\s+font)\s+(?:to\s+|into\s+)?(?P<f>[a-z][a-z -]{1,24}?)(?:,?\s+(?:size\s+)?(?P<n>\d{1,2})(?:\s*(?:pt|px|points?))?)?$", t)
    if m and m.group("f").strip() not in ("bigger", "smaller", "larger", "big", "small"):
        args = {"font": m.group("f").strip()}
        if m.group("n"):                       # "size 14": 14 point is the size desks use at about 117 %
            args["scale"] = str(max(80, min(250, round(int(m.group("n")) / 12 * 100 / 5) * 5)))
        return ("set_appearance", args)
    if t in ("high contrast", "more contrast", "higher contrast", "stronger colours", "stronger colors"):
        return ("set_appearance", {"theme": "high contrast"})
    if t in ("bigger", "even bigger", "larger", "smaller", "even smaller", "bigger please", "smaller please"):
        return ("set_appearance", {"scale": "smaller" if "small" in t else "bigger"})
    if _RESET_LOOK.match(text):
        return ("set_appearance", {"theme": "default theme"})
    th = _theme(text)
    if th:
        return th
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
        args = {"theme": color}       # "everything purple": a whole purple look that stays readable, not purple text
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
_INSTALL_LOOSE = re.compile(r"^\s*(?:please\s+)?(?:how\s+(?:do|can)\s+i\s+|can\s+(?:you|i)\s+|i\s+(?:want|would\s+like|'d\s+like)\s+to\s+|let'?s\s+)?"
                            r"install\s+(?P<os>llm\s*os|this\s+(?:os|system|operating\s+system)|the\s+(?:os|system|operating\s+system)|yourself|it|this)?\s*"
                            r"(?P<target>(?:on|onto|to|into)\s+(?:the\s+|my\s+|this\s+)?(?:computer|machine|pc|laptop|desktop|disk|drive|hard\s*drive|"
                            r"hard\s*disk|ssd|internal\s+(?:disk|drive)|nvme))?\s*(?:permanently|for\s+good)?\s*[.?!]?\s*$", re.I)
_INSTALL_OK = re.compile(r"^\s*install\s+llm\s*os:\s*confirmed\s+(?P<token>[0-9a-f]{8})\s*$", re.I)


# "install spotify" / "get me gimp" / "i need vs code": programs people know by name (tools.APP_NAMES); anything
# else goes to the model, which knows the package names
_INSTALL_PROG = re.compile(r"^\s*(?:please\s+)?(?:can\s+you\s+)?(?:install|get\s+me|download(?:\s+and\s+install)?)\s+"
                           r"(?:the\s+|a\s+)?(?P<app>[a-z][a-z0-9 .+-]{1,30}?)(?:\s+(?:app|program|please))?\s*[.!?]?\s*$", re.I)


_TZ = re.compile(r"^\s*(?:please\s+)?(?:(?:set|change|switch|update|put)\s+(?:my\s+|the\s+)?(?:time\s*zone|clock|time)\s+to|"
                 r"my\s+time\s*zone\s+is|i(?:'m|\s+am)\s+(?:now\s+)?in\s+the|use)\s+(?P<z>[a-z][a-z /_+-]{1,40}?)(?:\s+time(?:\s*zone)?)?\s*[.!]?\s*$", re.I)


_SCREEN_OFF = re.compile(r"^\s*(?:please\s+)?(?:(?P<keep>keep|leave)\s+(?:the\s+|my\s+)?(?:screen|display|computer)\s+(?:on|awake)(?:\s+(?:all\s+the\s+time|always))?|"
                         r"(?:never|don'?t|do\s+not|stop)\s+(?:turn(?:ing)?\s+off|blank(?:ing)?|dim(?:ming)?)\s+(?:the\s+|my\s+)?(?:screen|display)|presentation\s+mode(?:\s+on)?|"
                         r"(?:turn|switch)\s+(?:the\s+|my\s+)?(?:screen|display)\s+off\s+after\s+(?P<n>\d+)\s*(?P<u>min(?:ute)?s?|hours?)|"
                         r"(?:put\s+(?:the\s+|my\s+)?computer\s+to\s+sleep|sleep)\s+after\s+(?P<s>\d+)\s*(?P<su>min(?:ute)?s?|hours?)(?:\s+(?:of\s+)?(?:idle|inactivity|not\s+using\s+it))?|"
                         r"(?P<lidn>(?:when\s+i\s+)?clos(?:e|ing)\s+the\s+lid\s+(?:should\s+)?(?:do(?:es)?\s+nothing|keep(?:s)?\s+(?:it\s+)?running|stay(?:s)?\s+awake)|don'?t\s+sleep\s+when\s+i\s+close\s+the\s+lid))\s*[.!]?\s*$", re.I)


_DND = re.compile(r"^\s*(?:please\s+)?(?:(?P<on>turn\s+on|enable|start|switch\s+on)\s+|(?P<off>turn\s+off|disable|stop|switch\s+off|end)\s+)?"
                  r"(?:the\s+)?(?P<what>do\s+not\s+disturb|don'?t\s+disturb|dnd|night\s+light|night\s+mode|night\s+shift|blue\s+light\s+filter|warm(?:er)?\s+screen)"
                  r"(?:\s+(?P<on2>on)|\s+(?P<off2>off))?(?:\s+mode)?\s*[.!]?\s*$|^\s*(?P<quiet>(?:no|stop|hide|silence|mute)\s+(?:the\s+)?notifications|(?P<shownot>show\s+(?:the\s+)?notifications(?:\s+again)?))\s*[.!]?\s*$", re.I)


def _dnd(text):
    m = _DND.match(text)
    if not m:
        return None
    if m.group("quiet"):
        return ("change_setting", {"setting": "do_not_disturb", "value": "off" if m.group("shownot") else "on"})
    off = bool(m.group("off") or m.group("off2"))
    which = "night_light" if re.search(r"night|blue|warm", m.group("what"), re.I) else "do_not_disturb"
    return ("change_setting", {"setting": which, "value": "off" if off else "on"})


_GUARD = re.compile(r"^\s*(?:please\s+)?(?:(?P<off>follow|obey|do\s+what)\s+(?:the\s+)?instructions\s+(?:in|from|inside)\s+(?:web\s*pages|websites|emails?|files?)(?:(?:,|\s+and|\s+or)\s+(?:web\s*pages|websites|emails?|files?))*(?:\s+too|\s+as\s+well)?|"
                    r"(?P<off2>stop|don'?t|do\s+not)\s+(?:showing\s+me|checking|asking\s+about)\s+(?:what\s+)?(?:web\s*pages|websites|emails?|files?|instructions)(?:\s+(?:tell\s+you|say|want))?(?:\s+(?:to\s+do|first))?|"
                    r"turn\s+(?P<onoff>on|off)\s+the\s+(?:web\s*page|untrusted|instructions?|injection)\s+check|"
                    r"(?:show|ask)\s+me\s+(?:first\s+)?(?:before\s+(?:you\s+)?(?:follow|do)\s+)?(?:what\s+)?(?:instructions\s+in\s+)?(?:web\s*pages|websites|emails?|files?)\s+(?:tell\s+you\s+to\s+do|say|want)(?:\s+first)?)\s*[.!]?\s*$", re.I)


def _guard(text):
    m = _GUARD.match(text)
    if not m:
        return None
    off = bool(m.group("off") or m.group("off2") or (m.group("onoff") or "").lower() == "off")
    return ("change_setting", {"setting": "guard_untrusted", "value": "off" if off else "on"})


_LANG_SET = re.compile(r"^\s*(?:please\s+)?(?:change|set|switch|put)\s+(?:the\s+|my\s+)?(?:system\s+|os\s+|computer'?s?\s+)?language\s+(?:to|into)\s+(?P<l>[a-zA-Z\u00c0-\u024f\u4e00-\u9fff\u3040-\u30ff]+)\s*[.!]?\s*$", re.I)


def _screen_power(text):
    m = _LANG_SET.match(text)
    if m:
        return ("set_appearance", {"language": m.group("l")})
    if re.match(r"^\s*(?:please\s+)?(?:don'?t|do\s+not|never)\s+(?:go\s+to\s+)?sleep|^\s*(?:please\s+)?(?:stay|keep\s+(?:it|yourself))\s+awake|^\s*no\s+sleep(?:ing)?\b", text, re.I):
        return ("change_setting", {"setting": "sleep_after", "value": "never"})
    g = _guard(text)
    if g:
        return g
    d = _dnd(text)
    if d:
        return d
    m = _SCREEN_OFF.match(text)
    if not m:
        return None
    if m.group("lidn"):
        return ("change_setting", {"setting": "lid", "value": "nothing"})
    if m.group("s"):
        n = int(m.group("s")) * (60 if m.group("su").lower().startswith("h") else 1)
        return ("change_setting", {"setting": "sleep_after", "value": str(n)})
    if m.group("n"):
        n = int(m.group("n")) * (60 if m.group("u").lower().startswith("h") else 1)
        return ("change_setting", {"setting": "screen_off", "value": str(n)})
    return ("change_setting", {"setting": "screen_off", "value": "never"})


def _timezone(text):
    m = _TZ.match(text)
    if not m or (text.strip().lower().startswith("use") and not re.search(r"time\s*zone|\btime$", text, re.I)):
        return None
    z = m.group("z").strip()
    if re.fullmatch(r"\d.*|(?:dark|light)\b.*|\d+\s*(?:am|pm)", z, re.I):
        return None
    from . import system
    return ("change_setting", {"setting": "timezone", "value": z}) if system.find_timezone(z) else None


def _install(text):
    sp = _screen_power(text)
    if sp:
        return sp
    tz = _timezone(text)
    if tz:
        return tz
    m = _UNINSTALL.match(text)
    if m:
        from .tools import APP_NAMES
        if m.group("n").lower().strip() in APP_NAMES:
            return ("remove_software", {"name": m.group("n").lower().strip()})
    m = _INSTALL_PROG.match(text)
    if m:
        from .tools import APP_NAMES
        app = m.group("app").lower().strip()
        if app in APP_NAMES:
            return ("install_app", {"packages": app})
    m = _INSTALL_OK.match(text)
    if m:
        return ("install_to_disk", {"token": m.group("token")})
    m = _INSTALL.match(text)
    if not m:
        m2 = _INSTALL_LOOSE.match(text)
        if m2 and (m2.group("target") or (m2.group("os") and m2.group("os").lower() != "it")):
            return ("install_to_disk", {"mode": "alongside"})      # shows the plan first; nothing is written yet
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
_LANGUAGE = re.compile(r"^\s*(?:please\s+)?(?:(?:put|switch|set|change|make|turn)\s+(?:everything|the\s+(?:whole\s+)?(?:interface|system|os|ui)|it|yourself|all\s+of\s+it)\s+(?:back\s+)?(?:in|to|into)\s+|speak\s+(?:in\s+)?|talk\s+(?:to\s+me\s+)?in\s+|(?:use|switch\s+to)\s+)"
                       r"(?P<lang>[^\W\d_][^\W\d_ ]{1,20}(?:\s+\([^)]{2,20}\))?)\s*(?:from\s+now\s+on)?\s*[.!]?\s*$", re.I)
_SPLIT_LANG = re.compile(r"^\s*(?:please\s+)?(?:i\s+(?:want|would\s+like|'d\s+like)\s+)?(?:put\s+|show\s+|make\s+|set\s+)?(?:the\s+)?"
                         r"settings\s+(?:in|to)\s+(?P<sl>[^\W\d_]{2,20})(?:\s*[,;]?\s*(?:but|and|with)?\s*(?:keep\s+)?"
                         r"(?:everything\s+else|(?:the\s+)?rest(?:\s+of\s+(?:the\s+)?(?:os|system|interface|computer|ui|desk))?|all\s+else)"
                         r"\s+(?:in|to)\s+(?P<l>[^\W\d_]{2,20}))?\s*[.!]?\s*$", re.I)
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


# connecting an account without typing a key: "sign in to Claude", "log in to ChatGPT", "connect claude"
_SIGNIN = re.compile(r"^\s*(?:please\s+)?(?:(?:sign|log)\s*(?:in\s+(?:to|with)|into)|connect(?:\s+to)?)\s+(?:my\s+)?"
                     r"(?P<p>claude|anthropic|chatgpt|chat\s*gpt|openai)(?:\s+account)?\s*[.!]?\s*$", re.I)
_OTHER_ONLINE = re.compile(r"^\s*(?:please\s+)?connect\s+(?:another|a\s+different|some\s+other|an?\s+other)\s+online\s+"
                           r"(?:service|model|account)\s*[.!]?\s*$", re.I)


def _online_model(text):
    if _BRAIN.match(text):
        return None
    if re.match(r"^\s*(?:sign\s*in|log\s*in|login|connect\s+my\s+account|connect\s+an?\s+(?:online\s+)?account)\s*[.!]?\s*$", text, re.I):
        return ("online_model", {"action": "set up"})   # "use the online model for everything" is the brain setting, handled in _policy
    m = _SIGNIN.match(text)
    if m:
        p = m.group("p").lower().replace(" ", "")
        return ("online_model", {"action": "sign in", "provider": "claude" if p in ("claude", "anthropic") else "chatgpt"})
    if _OTHER_ONLINE.match(text):
        return ("online_model", {"action": "set up", "provider": "other"})     # the form for any OpenAI-compatible service
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
        if re.search(r"\b(delet|destroy|remov|irreversible|destructive|danger|erasing|wiping|risky|big|important|serious)", what):
            return ("change_setting", {"setting": "autonomy", "value": "balanced"})
        if re.search(r"\b(every|any|each|all)\b.*\b(change|action|thing)|\b(changing|doing)\s+(anything|things)|\beverything\b", what):
            return ("change_setting", {"setting": "autonomy", "value": "hands-on"})
        if re.search(r"internet|web|online|network", what):
            return ("change_setting", {"setting": "internet", "value": "ask"})
        return None
    if _NEVER_ASK.match(text) or re.match(r"^\s*(?:please\s+)?(?:(?:turn\s+on|switch\s+to|use|give\s+(?:it|yourself|you)|i\s+give\s+you|go)\s+)?"
                                          r"(?:full|total|complete)\s+(?:trust|control|rein|reign|freedom|access)(?:\s+mode)?(?:\s+on)?\s*[.!]?\s*$", text, re.I):
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
    if m and i18n.is_language(m.group("sl")) and (not m.group("l") or i18n.is_language(m.group("l"))):
        args = {"settings_language": m.group("sl")}
        if m.group("l"):
            args["language"] = m.group("l")
        return ("set_appearance", args)
    m = _LANGUAGE.match(text)
    if m:
        lang = m.group("lang").strip()
        if lang.lower() not in _NOT_A_LANGUAGE and not _QUESTION.search(text) and i18n.is_language(lang):
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
_SHOT = re.compile(r"^\s*(?:please\s+)?(?:take|grab|capture|make|do)\s+(?:a\s+|me\s+a\s+)?screen ?shot(?:\s+of\s+(?:the\s+|my\s+|this\s+)?(?:screen|window|page|desktop))?\s*[.!]?\s*$|"
                   r"^\s*(?:screen ?shot|snip|print screen)(?:\s+(?:this|the|my)\s+(?:screen|window|page))?\s*[.!]?\s*$|"
                   r"^\s*(?:take a picture of|capture) (?:the|my|this) screen\s*[.!]?\s*$", re.I)


_UNZIP = re.compile(r"^\s*(?:please\s+)?(?:unzip|extract|unpack|open\s+up|decompress)\s+(?:the\s+)?(?:file\s+)?(?P<p>(?:~|/)\S.*?|this|that|it|these)\s*$", re.I)
_UNINSTALL = re.compile(r"^\s*(?:please\s+)?(?:uninstall|remove\s+the\s+program|get\s+rid\s+of\s+the\s+program)\s+(?P<n>[a-z][a-z0-9 .+-]{1,30}?)\s*[.!]?\s*$", re.I)
_WALL_THIS = re.compile(r"^\s*(?:please\s+)?(?:set|use|make)\s+(?:this|that|the)\s+(?:photo|picture|image|pic)\s+(?:as|my)\s+(?:my\s+|the\s+)?(?:wallpaper|background)\s*[.!]?\s*$", re.I)
_EDIT_FILE = re.compile(r"^\s*(?:please\s+)?(?:edit|change|modify)\s+(?:the\s+)?(?:file\s+)?(?P<p>(?:~|/)\S.*?)\s*$", re.I)
_PRINT_FILE = re.compile(r"^\s*(?:please\s+)?print\s+(?:the\s+)?(?:file\s+)?(?P<p>(?:~|/)\S.*?)\s*$", re.I)
_WALL_FILE = re.compile(r"^\s*(?:please\s+)?(?:set|use|make)\s+(?P<p>(?:~|/)\S.*?)\s+(?:as|my)\s+(?:my\s+|the\s+)?(?:wallpaper|background|desktop background)\s*$", re.I)
_OPEN_FILE = re.compile(r"^\s*(?:please\s+)?(?:open|show|read|view)\s+(?:me\s+)?(?:the\s+)?file\s+(?P<p>(?:~|/).*?)\s*$", re.I)
_DEL_FILE = re.compile(r"^\s*(?:please\s+)?(?:delete|remove|trash)\s+(?:the\s+|my\s+)?(?:file|folder)\s+(?:called\s+|named\s+)?(?P<p>(?:~|/)\S*|\w[\w.-]*)\s*[.!]?\s*$", re.I)


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
_TRASH = re.compile(r"^\s*(?:please\s+)?(?:(?P<empty>empty)\s+(?:my\s+|the\s+)?(?:trash|recycle\s+bin|bin)|(?:show|open|check)\s+(?:me\s+)?(?:my\s+|the\s+)?(?P<show>trash|recycle\s+bin|bin|deleted\s+(?:files|stuff|things))"
                    r"|(?P<oops>(?:oops,?\s+)?i\s+(?:accidentally\s+)?(?:deleted|removed|lost|trashed)\s+(?:something|a\s+file|my\s+\w+|the\s+wrong\s+(?:file|thing))(?:\s+by\s+(?:accident|mistake))?"
                    r"|(?:how\s+(?:do|can)\s+i\s+|can\s+(?:you|i)\s+)?(?:get\s+back|recover|restore|undelete)\s+(?:a\s+|my\s+|the\s+)?(?:deleted\s+(?:file|files|stuff|photo|photos)|(?:file|files|something)\s+i\s+deleted)"
                    r"|where\s+(?:do|did)\s+(?:deleted\s+files|my\s+deleted\s+files|things\s+i\s+delete(?:d)?)\s+go|where(?:'s|\s+is)\s+(?:the\s+)?(?:trash|recycle\s+bin))"
                    r"|(?:restore|put\s+back|undelete)\s+(?P<name>.+?)\s+from\s+(?:my\s+|the\s+)?trash|(?:restore|put\s+back|undelete)\s+(?P<file>\S+\.\w{1,5}))\s*[.!]?\s*$", re.I)


def _notes(text):
    m = _TRASH.match(text)
    if m:
        if m.group("empty"):
            return ("empty_trash", {})
        if m.group("show") or m.group("oops"):
            return ("show_files", {"path": "~/.Trash"})
        return ("restore_file", {"name": (m.group("name") or m.group("file")).strip()})
    m = _NOTE_ADD.match(text)
    if m and not _QUESTION.search(text):
        return ("note_add", {"text": m.group("item").strip(), "list": m.group("list").strip()})
    m = _NOTES_SHOW.match(text)
    if m and not re.search(r"\b(?:files?|folders?|documents|downloads|pictures|photos|music|videos|icons?)\b", m.group("list") or m.group("list2") or "", re.I):
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


_PASS = re.compile(r"^\s*(?:please\s+)?(?:(?:set|set\s+up|add|create|make|change|reset|update|new)\s+(?:a\s+|my\s+|the\s+)?(?:new\s+)?(?:passphrase|password|vault|login\s+password|lock\s+(?:screen\s+)?password)(?:\s+for\s+(?:my\s+)?(?:data|files|computer))?"
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
                  r"|(?:turn|make)\s+(?:the\s+)?(?:volume|sound|music|it)\s+(?P<dir>up|down|louder|quieter|softer)|(?:change|put|set|move)\s+(?:the\s+)?(?:volume|sound|music)\s+(?P<dir2>up|down|louder|quieter|softer)|(?:increase|raise|turn\s+up)\s+(?:the\s+)?(?:volume|sound)(?P<up>)"
                  r"|(?:decrease|lower|reduce|turn\s+down)\s+(?:the\s+)?(?:volume|sound)(?P<down>)|(?P<l>louder|quieter|softer)"
                  r"|(?P<mute>mute|unmute)(?:\s+(?:the\s+)?(?:sound|speakers?|volume|audio|it))?|(?:turn\s+(?:the\s+)?(?:sound|audio|speakers?)\s+(?P<onoff>on|off)))\s*[.!]?\s*$", re.I)


def _device(text):
    text = re.sub(r"(?i)\b(?:a\s+(?:little|bit|touch|notch|tad)(?:\s+bit)?|slightly|somewhat|just)\s+", "", text)
    text = re.sub(r"(?i)\s+(?:a\s+(?:little|bit|touch|notch|tad)(?:\s+bit)?|slightly|some)\s*([.!]?)\s*$", r"\1", text)
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
        d = (m.group("dir") or m.group("dir2") or m.group("l") or ("up" if m.group("up") is not None else "down")).lower()
        return ("set_volume", {"delta": 10 if d in ("up", "louder") else -10})
    return None


def _files(text):
    m = re.match(r"^\s*(?:please\s+)?(?:find|open|show)\s+(?:me\s+)?(?:the\s+|my\s+)?(?:file|document|thing)s?\s+(?:that\s+)?i(?:\s+(?:was\s+just|was|were|have\s+been)|['’]ve\s+been)\s+working\s+on(?:\s+(?:yesterday|today|last\s+night|earlier|before))?\s*[?.!]?\s*$"
                 r"|^\s*(?:please\s+)?(?:show|open|list)\s+(?:me\s+)?(?:my\s+)?(?:recent|latest|newest)\s+(?:files|documents)\s*[?.!]?\s*$", text, re.I)
    if m:
        return ("show_files", {"path": "~", "sort": "date"})
    m = _SHOT.match(text)
    if m:
        return ("screenshot", {"area": True} if re.match(r"^\s*snip\b", text, re.I) else {})
    if re.match(r"^\s*(?:please\s+)?(?:take\s+a\s+|grab\s+a\s+)?(?:screen\s*shot|snip|capture)\s+(?:of\s+)?(?:an?\s+|part\s+of\s+the\s+|a\s+part\s+of\s+the\s+|some\s+of\s+the\s+)?(?:area|region|part|section|bit)(?:\s+of\s+the\s+screen)?\s*[.!]?\s*$|^\s*snipping\s+tool\s*$", text, re.I):
        return ("screenshot", {"area": True})
    if _WALL_THIS.match(text):
        return ("which_file", {"request": text.strip()})
    m = re.match(r"^\s*(?:please\s+)?open\s+(?P<p>(?:~|/)\S.*?)\s+in\s+(?:files|the\s+file\s+manager|thunar)\s*$", text, re.I)
    if m:
        import shlex
        return ("open_app", {"command": "thunar " + shlex.quote(m.group("p")), "graphical": True})
    if re.match(r"^\s*(?:please\s+)?(?:where\s+(?:did|do|does|is|are)\s+(?:that|the|my|it|this|these|those)?\s*(?:download(?:ed)?(?:\s+(?:file|files|things))?|file\s+i\s+(?:just\s+)?downloaded|downloads?)"
                r"(?:\s+(?:go|end\s+up|get\s+saved|saved|save|go\s+to|land))?|where\s+(?:do|did)\s+(?:my\s+)?downloads\s+go|(?:show|open)\s+(?:me\s+)?(?:my\s+|the\s+)?downloads(?:\s+folder)?)\s*[?.!]*\s*$", text, re.I):
        return ("show_files", {"path": "~/Downloads"})
    m = re.match(r"^\s*(?:please\s+)?(?:delete|remove|trash|get\s+rid\s+of|clear\s+out|empty|wipe)\s+(?:all\s+(?:of\s+)?|everything\s+in\s+|every\s+file\s+in\s+)?"
                 r"(?:my|the)\s+(?P<f>files|documents|docs|downloads|pictures|photos|music|videos|desktop|stuff)(?:\s+folder)?\s*[.!]?\s*$", text, re.I)
    if m and (re.search(r"\b(all|everything|every|clear\s+out|empty|wipe)\b", text, re.I) or m.group("f").lower() in ("files", "stuff")):
        f = m.group("f").lower()
        sub = {"documents": "Documents", "docs": "Documents", "downloads": "Downloads", "pictures": "Pictures", "photos": "Pictures",
               "music": "Music", "videos": "Videos", "desktop": "Desktop"}.get(f, "")
        return ("delete_file", {"path": "~/" + sub if sub else "~", "contents": True})
    m = re.match(r"^\s*(?:please\s+)?(?:show|find|list|what(?:\s+is|\s+are|'s))\s+(?:me\s+)?(?:my\s+|the\s+)?(?:biggest|largest)\s+files?\s+in\s+(?:my\s+|the\s+)?(?P<f>documents|docs|downloads|pictures|photos|music|videos|desktop)(?:\s+folder)?\s*[?.!]?\s*$", text, re.I)
    if m:
        f = m.group("f").lower()
        sub = {"documents": "Documents", "docs": "Documents", "downloads": "Downloads", "pictures": "Pictures", "photos": "Pictures",
               "music": "Music", "videos": "Videos", "desktop": "Desktop"}[f]
        return ("biggest_files", {"folder": "~/" + sub})
    m = re.match(r"^\s*(?:please\s+)?(?:show|find|list|what(?:\s+is|\s+are|'s))\s+(?:me\s+)?(?P<my>my\s+|the\s+)?(?:biggest|largest)\s+files?(?P<pc>\s+on\s+(?:the|this|my)\s+(?:computer|disk|drive|machine))?\s*[?.!]?\s*$"
                 r"|^\s*what(?:'s|\s+is)\s+taking\s+up\s+(?:the\s+most\s+|all\s+the\s+|so\s+much\s+)?(?:space|room|disk\s+space)(?:\s+on\s+(?:my|the|this)\s+(?:computer|disk|drive))?\s*[?.!]*\s*$", text, re.I)
    if m:
        return ("biggest_files", {"folder": "~"} if (m.group("my") or "").strip().lower() == "my" and not m.group("pc") else {})
    m = re.match(r"^\s*(?:please\s+)?(?:sort|order|arrange)\s+(?:them|it|these|the\s+files|my\s+files|files)?\s*(?:by\s+)?(?P<o>date|newest|latest|recent|name|alphabetical(?:ly)?|size|biggest|largest)(?:\s+first)?\s*[.!]?\s*$", text, re.I)
    if m:
        o = m.group("o").lower()
        return ("show_files", {"sort": "date" if o in ("date", "newest", "latest", "recent") else "size" if o in ("size", "biggest", "largest") else "name"})
    # "open http://… in firefox": that exact page in the browser
    m = re.match(r"^\s*(?:please\s+)?(?:open|go\s+to|visit|load|show(?:\s+me)?)\s+(?:the\s+)?(?:page\s+|site\s+|address\s+|link\s+)?(?P<u>https?://\S+|www\.\S+)"
                 r"(?:\s+(?:in|with|using|on)\s+(?:firefox|the\s+browser|my\s+browser|a\s+browser|the\s+web\s+browser))?\s*[.!]?\s*$", text, re.I)
    if m:
        return ("browse", {"site": m.group("u").rstrip(".,;")})
    m = re.match(r"^\s*(?:please\s+)?(?:convert|turn|save|export|make)\s+(?P<p>(?:~|/)\S.*?|this|that|it)\s+(?:to|into|as)\s+(?:a\s+)?pdf\s*[.!]?\s*$", text, re.I)
    if m:
        return ("convert_to_pdf", {"path": m.group("p")}) if m.group("p")[0] in "~/" else ("which_file", {"request": text.strip()})
    m = re.match(r"^\s*(?:please\s+)?(?:connect\s+(?:to\s+)?|open\s+|sync\s+(?:with\s+)?|set\s+up\s+|use\s+)(?:my\s+)?(?P<s>google\s+drive|one\s*drive|dropbox|icloud(?:\s+drive)?)\b.*$", text, re.I)
    if m:
        site = {"googledrive": "google drive", "onedrive": "https://onedrive.live.com", "dropbox": "https://www.dropbox.com/home",
                "icloud": "https://www.icloud.com/iclouddrive", "iclouddrive": "https://www.icloud.com/iclouddrive"}[re.sub(r"\s+", "", m.group("s").lower())]
        return ("browse", {"site": site})
    if re.match(r"^\s*(?:please\s+)?(?:put|place|drop|send)\s+(?:this|that|it|these)\s+(?:on|onto|in|into|to)\b", text, re.I):
        return ("which_file", {"request": text.strip()})
    if re.match(r"^\s*(?:what(?:'s|\s+is)|tell\s+me\s+about)\s+(?:this|that)\s+(?:file|document|thing)\s*[?.!]*\s*$", text, re.I):
        return ("which_file", {"request": text.strip()})
    m = re.match(r"^\s*(?:is|check\s+(?:if|whether)?)\s*(?:the\s+(?:site|website)\s+)?(?P<d>(?:https?://)?[\w.-]+\.[a-z]{2,}(?:/\S*)?)\s*(?:is\s+)?(?:safe|legit|real|a\s+scam|trustworthy|secure|ok)?\s*[?.!]*\s*$", text, re.I)
    if m and re.search(r"\b(?:safe|legit|real|scam|trustworthy|secure|check|ok)\b", text, re.I):
        return ("check_site", {"address": m.group("d")})
    m = re.match(r"^\s*(?:please\s+)?(?:make|shrink|resize|rotate|turn|crop|make)\s+(?P<p>(?:~|/)\S.*?|this(?:\s+(?:picture|photo|image|pic))?|that(?:\s+(?:picture|photo|image))?)\s+"
                 r"(?P<a>smaller(?:\s+(?:to|for)\s+(?:email|e-mail|send(?:ing)?))?|(?:to\s+the\s+)?(?:left|right)|square|(?:to\s+)?(?:a\s+)?square|black\s+and\s+white|grey(?:scale)?|gray(?:scale)?)\s*[.!]?\s*$", text, re.I)
    if m:
        a = m.group("a").lower()
        act = ("smaller" if "small" in a else "rotate left" if "left" in a else "rotate right" if "right" in a else
               "square" if "square" in a else "black and white")
        if m.group("p")[0] not in "~/":
            return ("which_file", {"request": text.strip()})
        return ("edit_image", {"path": m.group("p"), "action": act})
    if re.match(r"^\s*(?:please\s+)?crop\s+(?:this|that|the)\s+(?:photo|picture|image|pic)\s*[.!]?\s*$", text, re.I):
        return ("which_file", {"request": text.strip()})
    m = _UNZIP.match(text)
    if m:
        return ("extract_archive", {"path": m.group("p")}) if m.group("p")[0] in "~/" else ("which_file", {"request": text.strip()})
    if re.match(r"^\s*(?:please\s+)?(?:zip|compress)\s+(?:up\s+)?(?:this|these|that|those|them|it)(?:\s+(?:up|files?|folder))?\s*[.!]?\s*$", text, re.I):
        return ("which_file", {"request": text.strip()})
    m = re.match(r"^\s*(?:please\s+)?(?:zip|compress|make\s+a\s+zip\s+of)\s+(?:up\s+)?(?:the\s+(?:file|folder)\s+)?(?P<p>(?:~|/)\S.*?)\s*$|"
                 r"^\s*(?:please\s+)?(?:zip|compress|make\s+a\s+zip\s+of)\s+(?:up\s+)?my\s+(?P<f>documents|downloads|pictures|photos|music|videos|desktop)(?:\s+folder)?\s*[.!]?\s*$", text, re.I)
    if m:
        f = (m.group("f") or "").lower()
        sub = {"documents": "Documents", "downloads": "Downloads", "pictures": "Pictures", "photos": "Pictures", "music": "Music",
               "videos": "Videos", "desktop": "Desktop"}.get(f)
        return ("compress_files", {"path": m.group("p") if m.group("p") else "~/" + sub})
    m = _EDIT_FILE.match(text)
    if m:
        return ("open_file", {"path": m.group("p"), "edit": True})
    m = _PRINT_FILE.match(text)
    if m:
        return ("print_file", {"path": m.group("p")})
    m = _WALL_FILE.match(text)
    if m:
        return ("set_wallpaper", {"subject": m.group("p")})
    m = _OPEN_FILE.match(text)
    if m:
        return ("open_file", {"path": m.group("p")})
    m = _DEL_FILE.match(text)
    if m:
        p = m.group("p")
        return ("delete_file", {"path": p if p.startswith(("~", "/")) else "~/" + p})
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
_OPEN_URL = re.compile(r"^\s*(?:please\s+)?(?:(?:open|go to|visit|browse|show me|load|join)\s+(?:this\s+(?:link|meeting|call|meet|zoom)(?:\s+link)?:?\s+)?|(?:join\s+)?)(?P<url>https?://\S+)"
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
_PLAY = re.compile(r"^\s*(?:please\s+)?(?:play|put on|pull up|start|listen\s+to|i\s+want\s+to\s+(?:listen\s+to|hear|watch))\s+(?:me\s+)?(?:a|an|some|the)?\s*"
                   r"(?P<q>.+?)(?:\s+(?:and\s+)?(?:play\s+it)?(?:\s+(?:on|in)\s+(?:the\s+)?(?:screen|window|background)))?"
                   r"(?:\s+please)?\s*[.!]?\s*$", re.I)
_MEDIA_WORDS = re.compile(r"\b(video|youtube|music|song|songs|stream|album|podcast|playlist|radio|mix|lofi|lo-fi|live|concert|trailer|movie|clip|"
                          r"jazz|rock|pop|classical|hip hop|hip-hop|rap|country|blues|reggae|metal|edm|techno|house|ambient|r&b|soul|funk|"
                          r"disco|punk|indie|folk|opera|piano|guitar|beats|tunes)\b", re.I)
# "music", "play something", "some tunes": a request for music with nothing named -- a real mix, not a site's front page
_ANY_MUSIC = re.compile(r"^\s*(?:please\s+)?(?:(?:play|put\s+on|listen\s+to|i\s+want\s+to\s+(?:listen\s+to|hear))\s+)?(?:me\s+)?(?:some\s+|a\s+(?:little\s+)?bit\s+of\s+)?"
                        r"(?:music|songs|tunes|something(?:\s+(?:to\s+listen\s+to|nice|good))?|a\s+song|anything)\s*[.!]?\s*$", re.I)
DEFAULT_MUSIC = "chill instrumental music mix"


_CALL = re.compile(r"^\s*(?:please\s+)?(?:start|make|begin|open|set\s+up|host|do|have|i\s+(?:want|need)\s+to\s+(?:start|make|do|have))\s+(?:a\s+|an\s+)?"
                   r"(?:new\s+)?(?P<kind>video\s+call|video\s+chat|call|meeting|video\s+meeting|zoom(?:\s+call|\s+meeting)?|google\s+meet|meet|facetime|teams\s+(?:call|meeting))\s*[.!]?\s*$", re.I)


def _play(text):
    if re.match(r"^\s*(?:please\s+)?(?:play|open|watch|start)\s+(?:this|that|the)\s+(?:video|song|clip|movie|file)\s*[.!]?\s*$", text, re.I):
        return ("which_file", {"request": text.strip()})
    m = _CALL.match(text)
    if m:
        k = m.group("kind").lower()
        return ("browse", {"site": "zoom" if "zoom" in k else ("https://teams.live.com" if "teams" in k else "https://meet.google.com/new")})
    if re.search(r"\b(video|zoom|teams)\s+(?:call|chat|meeting)s?\b|\bcall\b", text, re.I):
        return None          # about a call, not something to play
    if re.match(r"^\s*(?:please\s+)?(?:play|put\s+on|listen\s+to|turn\s+on)\s+(?:the\s+|some\s+)?radio\s*[.!]?\s*$", text, re.I):
        return ("play_media", {"query": "live radio music stream", "audio_only": True})
    if _ANY_MUSIC.match(text) and re.search(r"\b(music|songs|tunes|song|play|put on|listen)\b", text, re.I):
        return ("play_media", {"query": DEFAULT_MUSIC})
    m = _PLAY.match(text)
    if not m or not _MEDIA_WORDS.search(text) or _QUESTION.search(text):
        return None
    q = re.sub(r"^(?:youtube\s+)?(?:video|videos|clip)\s+(?:of|about|with)\s+", "", m.group("q").strip(), flags=re.I)
    q = re.sub(r"\s+(?:on|from)\s+youtube\b", "", q, flags=re.I).strip(" .")
    return ("play_media", {"query": q}) if len(q) >= 2 else None


# apps: "make me a calculator", "build a habit tracker app with a dark theme", "open my calculator", "show my apps"
_APP_NOUN = r"(?:app|apps|application|program|widget|tool|utility|game)"
_MAKE_APP = re.compile(
    r"^\s*(?:(?:please|hey|ok|okay|so)[,\s]+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need|would\s+like|'d\s+like)"
    r"(?:\s+you)?\s+to\s+|let'?s\s+|go\s+ahead\s+and\s+)?(?:please\s+)?(?:make|create|build|write|code|design|program|generate|whip\s+up|"
    r"put\s+together|give|get)\s+(?:me\s+|us\s+)?(?:(?:a|an|another|some|one|my\s+own|a\s+new|a\s+simple|a\s+little|a\s+small|a\s+basic)\s+)?"
    r"(?P<rest>.+?)\s*(?:please)?[.!?]*\s*$", re.I)
_WANT_APP = re.compile(r"^\s*(?:i\s+(?:want|need)|give\s+me|get\s+me)\s+(?:a|an)\s+(?P<rest>.+?)\s*[.!?]*\s*$", re.I)
_LOOK_SPLIT = re.compile(r"\s+(?:with|in|using|that\s+(?:looks|has|is)|which\s+(?:looks|has|is)|themed|styled|but)\s+(?:a\s+|an\s+)?(?P<look>.+)$", re.I)
_LOOKISH = re.compile(r"theme|look|style|colou?r|dark|light|neon|retro|pastel|font|button|design|skin|mode|vibe|aesthetic|"
                      r"red|orange|yellow|green|blue|purple|pink|black|white|gold|silver|teal|cyan|magenta|grey|gray|brown", re.I)
_OPEN_APP = re.compile(r"^\s*(?:please\s+)?(?:open|launch|start|run|bring\s+up|pull\s+up|show\s+me|show)\s+(?:up\s+)?(?:the\s+|my\s+)?"
                       r"(?:app\s+)?(?P<n>[\w' -]{2,40}?)(?:\s+(?:app|application|program))?\s*[.!?]*\s*$", re.I)
_LIST_APPS = re.compile(r"^\s*(?:please\s+)?(?:(?:show|list|open|see)\s+(?:me\s+)?(?:all\s+)?(?:of\s+)?(?:my|the)\s+(?:apps|programs|applications|software)|"
                        r"(?:what|which)\s+(?:apps|programs|applications|software)\s+(?:do\s+i\s+have|are\s+there|are\s+installed|have\s+i\s+(?:got|made))|"
                        r"my\s+(?:apps|programs)|apps|programs|all\s+(?:apps|programs)|app\s+menu|start\s+menu)\s*[.!?]*\s*$", re.I)
_REMOVE_APP = re.compile(r"^\s*(?:please\s+)?(?:delete|remove|uninstall|get\s+rid\s+of|trash)\s+(?:the\s+|my\s+)?(?:app\s+)?(?P<n>.+?)"
                         r"(?:\s+app)?\s*[.!?]*\s*$", re.I)


_UNDO_RE = re.compile(r"^\s*(?:please\s+)?(?:undo(?:\s+(?:that|it|the\s+last\s+(?:thing|change)|what\s+you\s+(?:just\s+)?did))?|oops|whoops|"
                      r"(?:no,?\s+)?put\s+it\s+back|revert\s+(?:that|it|the\s+last\s+change)|change\s+it\s+back|go\s+back\s+to\s+(?:how\s+it\s+was|before)|"
                      r"take\s+(?:that|it)\s+back)\s*[.!]?\s*$", re.I)


_BROWSER_WORDS = r"(?:the\s+)?(?:internet|web|world\s+wide\s+web|browser|web\s+browser|firefox|chrome|google\s+chrome|safari|edge)"
_OPEN_BROWSER = re.compile(r"^\s*(?:please\s+)?(?:(?:open|launch|start|run|bring\s+up|go\s+on|get\s+on|use)\s+(?:up\s+)?" + _BROWSER_WORDS +
                           r"|" + _BROWSER_WORDS + r"|go\s+online|browse(?:\s+the\s+(?:web|internet))?|surf\s+the\s+(?:web|internet))\s*[.!]?\s*$", re.I)
_SITE = re.compile(r"^\s*(?:please\s+)?(?:open|go\s+to|visit|take\s+me\s+to|load|bring\s+up|pull\s+up|navigate\s+to|show\s+me|watch|check|"
                   r"(?:i\s+want\s+to\s+|let'?s\s+)?(?:watch|go\s+on|use|browse))\s+(?:the\s+|some\s+)?"
                   r"(?P<site>[\w.-]+\.[a-z]{2,}(?:/\S*)?|[\w ]{2,20}?)(?:\s+(?:website|site|page|\.com))?(?:\s+in\s+(?:the\s+)?browser)?\s*[.!]?\s*$", re.I)
_WEB_SEARCH = re.compile(r"^\s*(?:please\s+)?(?:google|bing|search\s+(?:the\s+web|online|the\s+internet|google)\s+for|search\s+online\s+for|"
                         r"look\s+up|web\s+search(?:\s+for)?|search\s+for)\s+(?P<q>.+?)\s*[.!?]?\s*$", re.I)
_FILEISH = re.compile(r"\b(?:my|file|files|document|documents|doc|docx|pdf|resume|cv|photo|photos|picture|pictures|folder|spreadsheet|"
                      r"downloaded|saved|i\s+(?:saved|wrote|downloaded))\b", re.I)
_FIND_FILE = re.compile(r"^\s*(?:please\s+)?(?:find|search\s+for|look\s+for|where(?:'s|\s+is|\s+are|\s+did\s+i\s+(?:save|put))|locate)\s+"
                        r"(?P<q>.+?)\s*[.?!]?\s*$", re.I)
_OPEN_FOLDER = re.compile(r"^\s*(?:please\s+)?(?:open|show(?:\s+me)?|go\s+to|browse|where(?:'s|\s+is|\s+are))\s+(?:my\s+|the\s+)?"
                          r"(?P<f>documents|docs|downloads|pictures|photos|pics|images|music|songs|videos|movies|desktop|home(?:\s+folder)?|stuff)"
                          r"(?:\s+folder)?\s*[.?!]?\s*$", re.I)
_MAKE_FOLDER = re.compile(r"^\s*(?:please\s+)?(?:make|create|add|new)\s+(?:me\s+)?(?:a\s+)?(?:new\s+)?folder(?:\s+(?:called|named))?(?:\s+(?P<name>.+?))?"
                          r"(?:\s+(?:in|on|inside)\s+(?:my\s+|the\s+)?(?P<where>documents|downloads|desktop|home|pictures|music|videos))?\s*[.!]?\s*$", re.I)
_RENAME = re.compile(r"^\s*(?:please\s+)?rename\s+(?:the\s+file\s+|my\s+)?(?P<n>.+?)\s+(?:to|as)\s+(?P<to>.+?)\s*[.!]?\s*$", re.I)
_MOVE = re.compile(r"^\s*(?:please\s+)?(?P<op>move|copy|put\s+a\s+copy\s+of|put|transfer|back\s+up)\s+(?:all\s+)?(?:of\s+)?(?:the\s+|my\s+)?(?P<what>.+?)"
                   r"(?:\s+(?:from|in|out\s+of)\s+(?:my\s+|the\s+)?(?P<frm>documents|downloads|desktop|home|pictures|photos|music|videos))?"
                   r"\s+(?:to|into|onto|on)\s+(?:my\s+|the\s+|a\s+)?(?P<to>documents|downloads|desktop|home|pictures|photos|music|videos|"
                   r"usb(?:\s+stick|\s+drive)?|stick|flash\s*drive|thumb\s*drive|external\s+drive)\s*[.!]?\s*$", re.I)
_LATEST = re.compile(r"^\s*(?:please\s+)?open\s+(?:the\s+|my\s+)?(?:latest|newest|last|most\s+recent)\s+(?:download|downloaded\s+file|file\s+i\s+downloaded)|"
                     r"^\s*(?:please\s+)?open\s+what\s+i\s+(?:just\s+)?downloaded", re.I)


_THIS_FILE = re.compile(r"^\s*(?:please\s+)?(?:delete|trash|remove|rename|open|print|copy|move|send|attach|email)\s+(?:this|that|it)"
                        r"(?:\s+(?:file|pdf|document|docx|photo|picture|one))?(?:\s+.*)?$", re.I)


def _everyday(text):
    from . import tools as T
    if re.match(r"^\s*(?:please\s+)?(?:make|convert|turn|save|change)\s+(?:this|that|it)(?:\s+(?:file|one|picture|photo|document|video|song))?\s+(?:in)?(?:to\s+|as\s+)?(?:an?\s+)?(?:jpe?g|png|gif|webp|heic|pdf|docx?|txt|mp3|mp4|mkv|wav)\b\s*[.!?]?\s*$", text, re.I):
        return ("which_file", {"request": text})
    if re.match(r"^\s*(?:please\s+)?(?:summari[sz]e|read|split|sign|merge|compress|translate|proofread|check)\s+(?:this|that)\s+(?:pdf|doc|docx|document|file|letter|report|essay)(?:\s+(?:to|for|out\s+loud|aloud)(?:\s+me)?)?\s*[.!?]?\s*$", text, re.I):
        return ("which_file", {"request": text})
    if _THIS_FILE.match(text) and not re.search(r"\b(?:to|as)\s+\S+\.\w{2,4}\b|\busb|stick|flash|monitor|screen|display|workspace|desktop \d|^\s*(?:please\s+)?rename\s+(?:this|that|it)(?:\s+(?:file|folder|one))?\s+(?:to|as)\s+\S", text, re.I):
        return ("which_file", {"request": text})
    m = re.match(r"^\s*show\s+the\s+folder\s+(?P<p>(?:~|/).*?)\s*$", text)
    if m:
        return ("show_files", {"path": m.group("p")})
    if _OPEN_BROWSER.match(text):
        return ("browse", {})
    m = _OPEN_FOLDER.match(text)
    if m:
        f = m.group("f").lower().split()[0]
        return ("show_files", {"path": "~/" + T.FOLDERS.get(f, "") if T.FOLDERS.get(f, "") else "~"})
    if _LATEST.match(text):
        return ("open_latest", {"where": "downloads"})
    m = _MAKE_FOLDER.match(text)
    if m:
        args = {"name": (m.group("name") or "New folder").strip().strip("'\"")}
        if m.group("where"):
            args["where"] = m.group("where").lower()
        return ("make_folder", args)
    m2 = (re.match(r"^\s*(?:please\s+)?call\s+it\s+(?!(?:after|for|by|like|something|anything|whatever|what|how|as)\b)(?P<to>[\w .()-]{1,60}?)\s+instead\s*[.!]?\s*$", text, re.I)
          or re.match(r"^\s*(?:please\s+)?(?:call|name)\s+it\s+(?P<to>[\w ()-]{1,55}\.\w{1,5})\s*[.!]?\s*$", text, re.I)
          or re.match(r"^\s*(?:please\s+)?name\s+it\s+(?!(?:after|for|by|like|something|anything|whatever|what|how|as)\b)(?P<to>[\w .()-]{1,60}?)\s*[.!]?\s*$", text, re.I))
    if m2 and not re.fullmatch(r"(?:a\s+)?(?:day|night|quits|even|a\s+wrap|done)", m2.group("to").strip(), re.I):
        return ("rename_file", {"name": "it", "to": m2.group("to").strip()})
    m = _RENAME.match(text)
    if m and re.search(r"\b(?:every|all|each)\b.*\b(?:files?|photos?|pictures?|documents?|songs?)\b|\b(?:files|photos|pictures|documents|songs)\b", m.group("n"), re.I):
        # many files by a rule ("rename every file on my desktop to lowercase with dashes instead of spaces")
        rule, n = m.group("to").lower(), m.group("n").lower()
        args = {}
        fm = re.search(r"\b(?:on|in)\s+(?:my\s+|the\s+)?(desktop|documents|downloads|pictures|photos|music|videos)\b", n)
        if fm:
            args["folder"] = "~/" + {"photos": "Pictures"}.get(fm.group(1), fm.group(1).capitalize())
        elif re.search(r"\b(?:photos?|pictures?)\b", n):
            args["folder"] = "~/Pictures"
        elif re.search(r"\bsongs?\b", n):
            args["folder"] = "~/Music"
        if re.search(r"lower ?case|small letters", rule):
            args["case"] = "lower"
        elif re.search(r"upper ?case|capitals|caps", rule):
            args["case"] = "upper"
        elif re.search(r"title case", rule):
            args["case"] = "title"
        if re.search(r"dash|hyphen", rule):
            args["spaces"] = "dashes"
        elif re.search(r"underscore", rule):
            args["spaces"] = "underscores"
        elif re.search(r"no spaces|without spaces|remove (?:the )?spaces", rule):
            args["spaces"] = "remove"
        if len(args) > (1 if "folder" in args else 0):
            return ("rename_files", args)
        return None                       # many files by some other rule: the model decides
    if m and not re.search(r"\b(?:wifi|network|computer|keyboard)\b", m.group("n"), re.I):
        if m.group("n").strip().strip("'\"").lower() in ("these", "those", "them"):
            return ("which_file", {"request": text.strip()})
        return ("rename_file", {"name": m.group("n").strip().strip("'\""), "to": m.group("to").strip().strip("'\"")})
    # "make a copy of report.txt from my downloads in my documents": a copy, the source folder named before the destination
    m = re.match(r"^\s*(?:please\s+)?(?:make|put|create)\s+a\s+copy\s+of\s+(?:the\s+|my\s+)?(?P<what>.+?)"
                 r"(?:\s+(?:from|out\s+of)\s+(?:my\s+|the\s+)?(?P<frm>documents|downloads|desktop|home|pictures|photos|music|videos))?"
                 r"\s+(?:in|into|to|onto|on)\s+(?:my\s+|the\s+)?(?P<to>documents|downloads|desktop|home|pictures|photos|music|videos)\s*[.!]?\s*$", text, re.I)
    if m:
        args = {"what": m.group("what").strip(), "to": m.group("to").lower(), "copy": True}
        if m.group("frm"):
            args["from"] = m.group("frm").lower()
        return ("move_files", args)
    m = _MOVE.match(text)
    if m:
        to = m.group("to").lower()
        to = "usb" if re.search(r"usb|stick|flash|thumb|external", to) else to
        args = {"what": m.group("what").strip(), "to": to, "copy": bool(re.match(r"copy|put a copy|back up", m.group("op"), re.I)) or to == "usb"}
        if m.group("frm"):
            args["from"] = m.group("frm").lower()
        if str(args.get("what", "")).lower().strip() in ("this", "that", "it", "these", "those", "them"):
            return ("which_file", {"request": text.strip()})
        return ("move_files", args)
    m = _WEB_SEARCH.match(text)
    if m and not _FILEISH.search(m.group("q")):
        return ("browse", {"search": m.group("q")})
    m = _FIND_FILE.match(text)
    if m and _FILEISH.search(text) and not re.search(r"\be-?mails?\b", text, re.I) and not re.search(r"\b(?:near|restaurant|flight|hotel|recipe|weather|news)\b", text, re.I) and not re.search(r"\b(?:biggest|largest)\s+files?\b", text, re.I) and not re.search(r"\bworking\s+on\b", text, re.I):
        q = re.sub(r"\b(?:my|the|that|file|files|folder|folders|called|named|i|saved|downloaded|put|was|working|on|about|yesterday)\b", " ", m.group("q"), flags=re.I)
        if q.strip():
            return ("find_files", {"query": " ".join(q.split())})
    m = _SITE.match(text)
    if m and re.search(r"\.(?:txt|md|pdf|docx?|odt|rtf|xlsx?|ods|csv|pptx?|odp|jpe?g|png|gif|webp|svg|mp3|m4a|wav|flac|ogg|mp4|mkv|mov|webm|zip|7z|tar|gz|html?|json|py|sh)$",
                      m.group("site").strip(), re.I) and not re.match(r"(?i)^(?:https?://|www\.)", m.group("site").strip()):
        return ("open_file", {"path": m.group("site").strip()})
    if m:
        site = m.group("site").strip().lower()
        if site in T.SITES or re.match(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", site):
            return ("browse", {"site": site})
    if text.strip().lower().rstrip(".!") in T.SITES and len(text.split()) <= 2:
        return ("browse", {"site": text.strip().lower().rstrip(".!")})
    return None


def _apps(text):
    if _UNDO_RE.match(text):
        return ("undo", {})
    from . import apps
    m = _LIST_APPS.match(text)
    if m:
        return ("manage_apps", {"action": "list"})
    m = _REMOVE_APP.match(text)
    if m and re.search(r"\bapp\b", text, re.I) and apps.find(m.group("n")):
        return ("manage_apps", {"action": "remove", "name": m.group("n").strip()})
    if re.search(r"\b(spreadsheet|excel|word document|word doc|document in word|presentation|slides|powerpoint)\b", text, re.I) and \
            re.match(r"^\s*(?:please\s+)?(?:make|create|start|open|i\s+(?:want|need)|new|build|set\s+up)\b", text, re.I):
        kind = "spreadsheet" if re.search(r"spreadsheet|excel", text, re.I) else \
            "presentation" if re.search(r"presentation|slides|powerpoint", text, re.I) else "word processor"
        from . import programs
        if programs.find(kind):
            return ("open_app", {"command": kind})
    m = _MAKE_APP.match(text) or _WANT_APP.match(text)
    if m and re.search(r"\b(?:remind|reminds|reminding|notify|notifies|alert|nag|nags|every (?:hour|day|morning|evening|night|\d+)|"
                       r"each (?:hour|day)|at \d|email|send|share)\b", text, re.I):
        m = None                          # an app and something more (a reminder, an email): the model does both
    if m:
        rest = m.group("rest").strip()
        look = ""
        lm = _LOOK_SPLIT.search(rest)
        if lm and _LOOKISH.search(lm.group("look")):
            look, rest = lm.group("look").strip(), rest[:lm.start()].strip()
        # "a pink calculator", "a retro-looking timer": the look can come first too
        what = re.sub(r"\b" + _APP_NOUN + r"\b", " ", rest, flags=re.I).strip(" -,")
        if re.search(r"\b" + _APP_NOUN + r"\b", rest, re.I) or apps.match_template(what):
            if not re.search(r"\b(?:note|reminder|timer for|wallpaper|backup|screenshot|folder|file|playlist|list called)\b", rest, re.I) \
                    or re.search(r"\b" + _APP_NOUN + r"\b", rest, re.I):
                if not look:
                    t = apps.match_template(what)
                    lead = what[:what.lower().find(t["id"])] if t and t["id"] in what.lower() else ""
                    if lead.strip() and _LOOKISH.search(lead):
                        look = lead.strip()
                return ("make_app", {"what": what or rest, "look": look} if look else {"what": what or rest})
    # "make the calculator red" (an open app changes colour) and "make a red calculator": the same app, in that look
    _COL = r"(?:red|blue|green|yellow|orange|pink|purple|violet|black|white|grey|gray|brown|teal|navy|gold|silver|dark|light)"
    m = re.fullmatch(r"(?:make|turn|change|colou?r|paint|dye)\s+(?:the |my |this |that )?(?P<what>[a-z][a-z -]{1,30}?)\s+(?:to\s+)?(?P<look>" + _COL + r")", text.lower().strip().rstrip(".!?")) \
        or re.fullmatch(r"(?:make|create|build|design|open)\s+(?:me\s+)?(?:a|an|the)\s+(?P<look>" + _COL + r")\s+(?P<what>[a-z][a-z -]{1,30})", text.lower().strip().rstrip(".!?"))
    if m and re.fullmatch(r"(?:the |my )?(?:calculator|calc|timer|stopwatch|clock|to-?do(?: list)?|tracker|counter|converter|quiz|flashcards?|sudoku|minesweeper|game|app|tool|widget|planner|calendar)", m.group("what").strip()):
        return ("make_app", {"what": m.group("what").strip(), "look": m.group("look")})
    bare = text.strip().lower().rstrip(".!?")
    if 1 <= len(bare.split()) <= 2 and apps.match_template(bare) and any(bare.replace(" ", "_") == w or bare == w.replace("_", " ")
                                                                          for tt in apps.templates() for w in [tt["id"]] + tt["words"]):
        return ("open_app", {"command": bare})
    m = re.match(r"^\s*(?:a\s+|an\s+|the\s+|my\s+)?(?P<n>[a-z][a-z -]{1,25}?)\s+app\s*[.!?]?\s*$", text, re.I)
    if m and (apps.find(m.group("n")) or apps.match_template(m.group("n"))):
        return ("open_app", {"command": m.group("n").strip()})
    m = _OPEN_APP.match(text)
    if m:
        n = m.group("n").strip()
        from . import tools as _T
        if n.lower().removeprefix("my ").strip() in _T.FOLDERS or n.lower() in ("files", "my files", "file"):
            return None              # "show my files": the folder, not a program called something like Files
        from . import programs
        if apps.find(n) or (apps.match_template(n) and len(n.split()) <= 3) or programs.find(n):
            return ("open_app", {"command": n})
    return None


# An open app of the OS's own (calculator, timer…): closing it and reading what it shows are done by the OS itself.
# The app's name is resolved by desk.py (apps.find); here only the wording counts.
_APP_NAME = r"[a-z][a-z0-9 -]{1,30}?"
_APP_READ_RE = re.compile(
    r"what(?:'s| does| is) (?:on |showing on |shown on )?(?:the |my |this )?(?P<r1>" + _APP_NAME + r") (?:show|shows|say|says|display|displays)"
    r"|what(?:'s| is) (?:the |my )?(?P<r2>" + _APP_NAME + r") (?:showing|displaying|saying)"
    r"|what(?:'s| is) (?:on|showing on|shown on) (?:the |my |this )?(?P<r3>" + _APP_NAME + r")"
    r"|read (?:the |my |this )?(?P<r4>" + _APP_NAME + r")")
_APP_CLOSE_RE = re.compile(r"(?:please )?(?:close|quit|exit) (?:the |my |this )?(?P<c1>" + _APP_NAME + r")(?: app| program| window)?")
_NOT_AN_APP = {"window", "windows", "app", "program", "tab", "it", "that", "one", "everything", "all", "screen", "page",
               "answer", "reply", "text", "message", "last", "settings", "files", "browser", "terminal", "the", "this"}


def app_question(text):
    """("read", name) for 'what does the calculator show' / 'what's on the calculator' / 'read the calculator',
    ("close", name) for 'close the calculator'; None for anything else. The name is looked up by the desk."""
    low = plain(text).lower().strip().rstrip("?.!").strip()
    m = _APP_CLOSE_RE.fullmatch(low)
    if m and not _generic(m.group("c1")):
        return ("close", m.group("c1").strip())
    m = _APP_READ_RE.fullmatch(low)
    if m:
        name = next(g for g in (m.group("r1"), m.group("r2"), m.group("r3"), m.group("r4")) if g).strip()
        if not _generic(name):
            return ("read", name)
    return None


def _generic(name):
    """'window', 'all windows', 'the last answer': words about the OS's own windows or replies, not an app's name."""
    return all(w in _NOT_AN_APP for w in str(name).split())


def app_reading(page, title):
    """What an open app shows, in words: its display (the calculator's number) when it has one, else its text.
    `page` is the app's read result {"text", "controls", "none"}; the display is the control apps label
    'display value: …' (calculator.html), so no keypad label is ever mistaken for it."""
    name = str(title or "the app").lower()
    if not page or page.get("none"):
        return f"I could not read the {name}."
    shown = [str(c)[len("display value: "):] for c in (page.get("controls") or []) if str(c).lower().startswith("display value: ")]
    if shown:
        return f"The {name} shows {shown[0]}."
    text = " ".join(str(page.get("text") or "").split())[:300]
    return f"The {name} shows: {text}." if text else f"The {name} shows nothing readable."


def plain(text):
    """Typed text as the patterns expect it: phones and Macs turn ' and " into curly quotes (what’s, “this”)."""
    return str(text or "").translate({0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"', 0x2032: "'"})


# ------------------------------------------------------------------ everyday requests found by the use-case runs
_DARK_WORDS = re.compile(r"^\s*(?:pon(?:er)?|activa(?:r)?|mets?|active|aktiviere|schalte?|开启|打开|切换到)?\s*(?:el\s+|le\s+|den\s+)?"
                         r"(?P<d>modo\s+oscuro|mode\s+sombre|th[eè]me\s+sombre|dunkel(?:er)?\s*modus|dark\s*mode|深色模式|暗色模式|ダークモード)"
                         r"|^\s*(?:pon(?:er)?|activa(?:r)?|mets?|aktiviere)?\s*(?:el\s+|le\s+)?(?P<l>modo\s+claro|mode\s+clair|hell(?:er)?\s*modus|浅色模式|ライトモード)", re.I)


def _everyday2(text):
    t = text.strip()
    low = t.lower().rstrip(".!?")
    import urllib.parse as _u
    # finding the owner's own things by what they are about
    m = re.match(r"^(?:please\s+)?(?:find|show(?:\s+me)?|where(?:'s|\s+is|\s+are)|look\s+for|get(?:\s+me)?|open)\s+(?:the|my|that|those)\s+(?:photos?|pictures?|pics?|images?|snaps?)\s+"
                 r"(?:of|with|from|where|showing|that\s+(?:has|have|shows?)|i\s+took\s+(?:of|at|in))\s+(?P<q>.+)$"
                 r"|^(?:please\s+)?(?:find|show(?:\s+me)?)\s+(?:my\s+)?(?:photos?|pictures?|pics?)\s+(?:of|with|from)\s+(?P<q2>.+?)\s+(?:i\s+took|from\s+my\s+(?:photos|pictures|phone|camera))$", low)
    if m:
        return ("find_by_meaning", {"query": (m.group("q") or m.group("q2")).strip(), "kind": "photos"})
    m = re.match(r"^(?:please\s+)?(?:find|show(?:\s+me)?|where(?:'s|\s+is|\s+are)|look\s+for|get(?:\s+me)?|open)\s+(?:the|my|that)\s+"
                 r"(?:document|doc|file|pdf|letter|note|essay|report|spreadsheet|invoice|receipt|contract|recipe|presentation|story|cv|resume|form)s?\s+"
                 r"(?:about|on|for|regarding|that\s+(?:mentions|talks\s+about|is\s+about|says)|mentioning|with|where\s+i\s+(?:wrote|talked)\s+about)\s+(?P<q>.+)$"
                 r"|^(?:please\s+)?search\s+(?:through\s+)?(?:my|all\s+my|the)\s+(?:files|documents|stuff|computer|notes)\s+for\s+(?P<q2>.+)$", low)
    if m:
        return ("find_by_meaning", {"query": (m.group("q") or m.group("q2")).strip(), "kind": "documents" if m.group("q") else "any"})
    # "set a timer for 15 minutes for the pasta": the same timer, with the length first
    m = re.match(r"^(?:please\s+)?(?:set|start|make)\s+(?:a\s+|me\s+a\s+)?timer\s+for\s+(?P<n>\d+(?:\.\d+)?|one|two|three|four|five|ten|fifteen|twenty|thirty)"
                 r"\s*(?P<u>sec(?:ond)?s?|min(?:ute)?s?|h(?:ou)?rs?)(?:\s+for\s+(?P<what>.+))?$", low)
    if m:
        u = {"s": "seconds", "m": "minutes", "h": "hours"}[m.group("u")[0]]
        length = f"{m.group('n')} {u}"
        return ("schedule_task", {"when": f"in {length}", "task": length + (f" ({m.group('what')})" if m.group("what") else ""), "kind": "timer"})
    # "set a 3 minute timer", "3 minute timer", "a 90 second timer for the eggs"
    m = re.match(r"^(?:please\s+)?(?:set\s+|start\s+|make\s+)?(?:a|an|me\s+a)?\s*(?P<n>\d+(?:\.\d+)?|one|two|three|four|five|ten|fifteen|twenty|thirty|half\s+an?)\s*[- ]?"
                 r"(?P<u>sec(?:ond)?s?|min(?:ute)?s?|h(?:ou)?rs?)\s+timer(?:\s+for\s+(?P<what>.+))?$", low)
    if m:
        u = {"s": "seconds", "m": "minutes", "h": "hours"}[m.group("u")[0]]
        n = m.group("n").replace("half an", "30").replace("half a", "30")
        if "half" in m.group("n"):
            u = "minutes" if u == "hours" else u
        length = f"{n} {u}"
        return ("schedule_task", {"when": f"in {length}", "task": length + (f" ({m.group('what')})" if m.group("what") else ""), "kind": "timer"})
    # a new text file: "make a text file called todo on my desktop"
    m = re.match(r"^(?:please\s+)?(?:make|create|start|new)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:new\s+)?(?:empty\s+|blank\s+)?(?:text\s+|txt\s+|plain\s+text\s+)?file\s+"
                 r"(?:called|named)\s+(?P<n>[\w .,'-]+?)(?:\s+(?:on|in)\s+(?:my\s+|the\s+)?(?P<w>desktop|documents|downloads|home(?:\s+folder)?))?$", low)
    if m:
        name = t[m.start("n"):m.end("n")].strip().strip("'\"")
        if not re.search(r"\.\w{1,5}$", name):
            name += ".txt"
        where = (m.group("w") or "documents").split()[0]
        folder = "~" if where == "home" else "~/" + where.capitalize()
        return ("write_file", {"path": f"{folder}/{name}", "content": "", "append": True})   # (an existing file is kept as it is)
    # sort a folder: "sort my downloads by newest"
    m = re.match(r"^(?:please\s+)?(?:sort|order|arrange|show)\s+(?:my\s+|the\s+)?(?P<f>desktop|documents|downloads|pictures|photos|music|videos|files|home folder)"
                 r"(?:\s+folder)?\s+(?:by\s+|with\s+(?:the\s+)?)?(?P<o>newest|latest|most recent|date|oldest|name|alphabetical(?:ly)?|a-z|size|biggest|largest)(?:\s+first)?$", low)
    if m:
        f = {"photos": "Pictures", "files": "", "home folder": ""}.get(m.group("f"), m.group("f").capitalize())
        o = m.group("o")
        order = "date" if o in ("newest", "latest", "most recent", "date", "oldest") else "size" if o in ("size", "biggest", "largest") else "name"
        return ("show_files", {"path": "~/" + f if f else "~", "sort": order})
    em = _mail_send_direct(t)
    if em:
        return em
    m = re.match(r"^(?:please\s+)?(?:open|show|go\s+to|find|get|pull\s+up)\s+(?:me\s+)?(?:the\s+)?wikipedia\s+(?:page|article|entry)\s+(?:about|on|for)\s+(?P<q>.+?)\s*[.!?]?$", low)
    if m:
        import urllib.parse as _u
        words = [w for w in m.group("q").split() if w not in ("the", "a", "an")] or m.group("q").split()
        title = "_".join(w[:1].upper() + w[1:] for w in words)
        return ("browse", {"site": "https://en.wikipedia.org/wiki/" + _u.quote(title)})
    m = re.match(r"^(?:please\s+)?(?:find|get|look\s+up|search\s+for|show)\s+(?:me\s+)?(?:a\s+|an\s+|some\s+)?(?P<q>.+?)\s+recipes?\s*[.!?]?$|"
                 r"^(?:please\s+)?(?:find|get|look\s+up|search\s+for|show)\s+(?:me\s+)?(?:a\s+|an\s+)?recipes?\s+(?:for|on)\s+(?P<q2>.+?)\s*[.!?]?$", low)
    if m:
        return ("browse", {"search": ((m.group("q") or m.group("q2")) + " recipe").strip()})
    if re.match(r"^\s*(?:please\s+)?print\s+(?:\d+\s+cop(?:y|ies)|(?:it|this)\s+(?:double|single)[- ]sided|(?:double|single)[- ]sided)\b", t, re.I):
        return ("which_file", {"request": t})
    m = re.match(r"^(?:please\s+)?print\s+(?:me\s+)?(?:my\s+|the\s+|that\s+|a\s+)?(?P<f>[\w .'()-]+?)\s*[.!]?$", t, re.I)
    if m and m.group("f").lower() not in ("this", "that", "it", "this page", "this document", "page", "it out") \
            and not re.search(r"\b(?:how|what|why|where|which)\b|^\d+\s+cop(?:y|ies)\b|\b(?:double|single)[- ]sided\b|\bin colou?r\b|\bblack and white\b|\blandscape\b|\bportrait\b", m.group("f"), re.I):
        return ("print_file", {"path": m.group("f").strip()})
    # the newest PDF I downloaded: "open the pdf I downloaded today"
    m = re.match(r"^(?:please\s+)?(?:open|show|view)\s+(?:the\s+|my\s+|that\s+)?(?P<k>pdf|picture|photo|image|video|song|document|file)\s+"
                 r"(?:i|that\s+i)\s+(?:just\s+)?(?:downloaded|got|saved)(?:\s+(?:today|yesterday|last night))?$", t, re.I)
    if m:
        return ("open_latest", {"where": "downloads", "kind": m.group("k").lower()})
    # email said plainly: "send craig@x.com an email saying …", "send bob@x.com a quick email saying …", "reply to the last email saying …", "email my resume to craig@x.com"
    m = re.match(r"^(?:please\s+)?send\s+(?P<to>[\w.+-]+@[\w.-]+)\s+(?:an?\s+)?(?:(?:quick|short|brief|little)\s+)?e-?mail\s+(?:saying|that|to\s+say|telling\s+(?:him|her|them)|with)\s+(?P<b>.+)$", t, re.I)
    if m:
        body = m.group("b").strip().strip("'\"")
        body = body[:1].upper() + body[1:]
        return ("mail_send", {"to": m.group("to"), "subject": " ".join(re.sub(r"[.!?]$", "", body).split()[:7]),
                              "body": body if re.search(r"[.!?]$", body) else body + "."})
    m = re.match(r"^(?:please\s+)?(?:reply|respond|answer)\s+(?:to\s+)?(?:the\s+)?(?:last|latest|newest|most\s+recent)\s+(?:e-?mail|message|mail)\s+"
                 r"(?:saying|with|that\s+says|telling\s+\S+)\s+(?P<b>.+)$", t, re.I)
    if m:
        body = m.group("b").strip().strip("'\"")
        return ("mail_reply", {"id": "latest", "body": body[:1].upper() + body[1:]})
    m = re.match(r"^(?:please\s+)?(?:e-?mail|send)\s+(?:my\s+|the\s+)?(?P<f>[\w .'-]+?)\s+to\s+(?P<to>[\w.+-]+@[\w.-]+)$", t, re.I)
    if m and not re.search(r"\b(?:saying|that|about)\b", t, re.I):
        f = m.group("f").strip()
        return ("mail_send", {"to": m.group("to"), "subject": f[:1].upper() + f[1:], "body": f"Please find {f} attached.", "attach": [f]})
    # email in plain words (only with an account; otherwise the agent says how to set one up)
    if re.match(r"^(?:how many|do i have any|have i got any|any)\s+(?:new\s+|unread\s+)*(?:e-?mails?|mail|messages)(?:\s+do\s+i\s+have)?$", low):
        return ("mail_inbox", {})
    if re.match(r"^(?:read|open|show)\s+(?:me\s+)?(?:my\s+|the\s+)?(?:latest|newest|last|most recent|new)\s+(?:e-?mail|mail|message)$", low):
        return ("mail_read", {"id": "latest"})
    m = re.match(r"^(?:did|has)\s+(?P<w>[a-z][\w.@ -]*?)\s+(?:reply|replied|answer(?:ed)?|write back|written back|e-?mail(?:ed)?(?:\s+me)?|get back to me|respond(?:ed)?)$"
                 r"|^(?:any|is there an?)\s+(?:new\s+)?(?:e-?mail|mail|message|reply)\s+from\s+(?P<w2>[\w.@ -]+)$", low)
    if m:
        return ("mail_read", {"id": (m.group("w") or m.group("w2")).strip()})
    m = re.match(r"^(?:please\s+)?(?:switch\s+to|use|set|turn\s+on|make\s+it|show\s+(?:the\s+)?time\s+in|change\s+to|go\s+to)\s+(?:the\s+|a\s+)?"
                 r"(?P<h>24|12|twenty[- ]four|twelve)[- ]?hour\s+(?:clock|time|format)(?:\s+please)?$", low)
    if m:
        return ("change_setting", {"setting": "clock", "value": "24" if m.group("h") in ("24", "twenty four", "twenty-four", "twenty") else "12"})
    # a quick look at the volume; the newest video or song
    if re.match(r"^how\s+(?:loud|high)\s+is\s+(?:the\s+)?(?:volume|sound|it|the\s+sound|the\s+speakers?)(?:\s+(?:right\s+)?now)?$|"
                r"^what(?:'s|\s+is)\s+the\s+volume(?:\s+(?:right\s+)?now)?$", low):
        return ("set_volume", {})
    m = re.match(r"^(?:please\s+)?(?:play|open|show)\s+(?:me\s+)?(?:the\s+|my\s+)?(?:newest|latest|last|most\s+recent)\s+"
                 r"(?P<k>video|movie|clip|song|track|recording)s?(?:\s+(?:in|from)\s+(?:my\s+)?(?P<f>videos|music|downloads|desktop|documents))?$", low)
    if m:
        where = m.group("f") or ("music" if m.group("k") in ("song", "track", "recording") else "videos")
        return ("open_latest", {"where": where})
    m = re.match(r"^(?:please\s+)?remind\s+me\s+(?:to\s+)?(?P<what>.+?)\s+(?P<when>every\s+(?:day|morning|evening|night|weekday|weekend|week|hour|"
                 r"(?:mon|tues|wednes|thurs|fri|satur|sun)day)(?:\s+(?:at\s+)?\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?)\s*[.!]?$", low)
    if m:
        return ("schedule_task", {"when": m.group("when"), "task": m.group("what"), "kind": "reminder"})
    # alarms and the list of what's scheduled
    m = re.match(r"^(?:please\s+)?(?:set|make|add)\s+(?:an?\s+|my\s+)?alarm\s+(?:for|at)\s+(?P<w>.+?)(?:\s+(?:to|and)\s+(?P<why>.+))?$"
                 r"|^wake\s+me\s+(?:up\s+)?(?:at|for)\s+(?P<w2>.+?)(?:\s+(?:to|and)\s+(?P<why2>.+))?$", low)
    if m:
        why = (m.group("why") or m.group("why2") or "").strip()
        return ("schedule_task", {"when": m.group("w") or m.group("w2"), "task": "Alarm" + (f": {why}" if why else ""), "kind": "reminder"})
    if re.match(r"^(?:what|which)\s+(?:reminders|alarms|timers|tasks)\s+(?:do\s+i\s+have|are\s+(?:set|on|there))|^(?:show|list|see)\s+(?:me\s+)?(?:all\s+)?"
                r"(?:my\s+|the\s+)?(?:reminders|alarms|timers)$|^what(?:'s|\s+is)\s+scheduled$|^my\s+(?:reminders|alarms|timers)$", low):
        return ("manage_tasks", {"action": "list"})
    m = re.match(r"^(?:please\s+)?(?:cancel|delete|remove|stop|turn\s+off)\s+(?:the\s+|my\s+)?(?:(?P<what>[\w: ]+?)\s+)?(?P<kind>alarm|reminder|timer)s?$", low)
    if m and not re.search(r"\bevery\b", low):
        return ("manage_tasks", {"action": "cancel", "which": ("all" if (m.group("what") or "").strip() in ("all", "all the", "all my", "every") else
                                                                  (m.group("what") or "").strip() or m.group("kind"))})
    # notes first: "write down: dentist on friday at 3" is a note, not a task at 3
    m = re.match(r"^(?:please\s+)?(?:write|jot|put|get|note|scribble)\s+(?:this\s+|that\s+|it\s+)?down\s*:?\s+(?P<n>.+)$|^(?:take|make)\s+a\s+note\s*:?\s+(?P<n2>.+)$", t, re.I)
    if m:
        n = (m.group("n") or m.group("n2")).strip().strip("'\"")
        if not re.match(r"(?i)^(?:that\s+)?(?:i|i'm|i am|my)\b", n):
            return ("note_add", {"text": n, "list": "notes"})
    m = re.match(r"^(?:please\s+)?(?:delete|remove|get rid of|erase|cross out)\s+(?:the|my|that)\s+note\s+(?:about|on|that says|saying|with)\s+(?P<x>.+)$", low)
    if m:
        return ("note_remove", {"item": re.sub(r"^(?:the|a|an|my)\s+", "", m.group("x").strip()), "list": "notes"})
    if re.match(r"^(?:(?:show|open|read|see|list)\s+(?:me\s+)?(?:all\s+)?my\s+notes|my\s+notes|what\s+notes\s+do\s+i\s+have|what(?:'s| is)\s+in\s+my\s+notes|"
                r"what\s+(?:did\s+i|have\s+i)\s+(?:write|wrote|put|written|saved)\s+(?:down\s+)?(?:in|on)\s+my\s+notes)$", low):
        return ("notes_show", {"list": "notes"})
    m = re.match(r"^(?:cut|trim|remove|chop|take)\s+(?:off\s+)?(?:the\s+)?(?P<w>first|last|beginning|start|end|opening)(?:\s+(?P<n>[\d:.]+\s*(?:seconds?|secs?|s|minutes?|mins?|m)?(?:\s+and\s+\d+\s*(?:seconds?|secs?))?))?"
                 r"(?:\s+(?:of|off|from)\s+(?:this|that|the|my)?\s*(?P<v>video|clip|recording|movie|song|audio|[\w .-]+\.(?:mp4|mkv|mov|webm|avi|m4v|mp3|m4a|wav|ogg|flac)))?$", low)
    if m and m.group("n") and m.group("v"):
        n = m.group("n").strip()
        args = {"cut_start" if m.group("w") in ("first", "beginning", "start", "opening") else "cut_end": n,
                "kind": "audio" if m.group("v") in ("song", "audio", "recording") else "video"}
        if "." in (m.group("v") or ""):
            args["path"] = m.group("v")
        return ("trim_video", args)
    m = re.match(r"^(?:keep|cut|trim)\s+(?:only\s+)?(?:this|that|the|my)?\s*(?:video|clip|recording|song)?\s*(?:from|between)\s+(?P<a>[\d:.]+\s*\w*)\s+(?:to|and|until|till)\s+(?P<b>[\d:.]+\s*\w*)$", low)
    if m:
        return ("trim_video", {"keep_from": m.group("a"), "keep_to": m.group("b")})
    if re.match(r"^(?:(?:when i )?close the lid and (?:keep|stay)\b.*|keep (?:it |the computer )?(?:running|on|awake) when (?:i )?close (?:the|its) lid|"
                r"(?:don'?t|do not) (?:go to )?sleep when (?:i )?close (?:the|its) lid|(?:closing )?the lid (?:closed|shut) (?:and )?(?:keep|stay) (?:running|on|awake)|"
                r"lid closed,? (?:keep|stay) (?:running|on|awake))$", low):
        return ("change_setting", {"setting": "lid", "value": "nothing"})
    if re.match(r"^(?:sleep|go to sleep|suspend) when (?:i )?close (?:the|its) lid$|^closing the lid should (?:sleep|suspend)$", low):
        return ("change_setting", {"setting": "lid", "value": "sleep"})
    m = re.match(r"^(?P<what>.+?),?\s+(?P<when>(?:every time|each time|whenever|when|as soon as)\s+i\s+(?:unlock|log ?in|sign in|log on|"
                 r"start (?:up|the computer)|turn (?:it|the computer) on)(?:\s+(?:the|my)\s+(?:computer|pc|laptop|screen))?)$", low)
    if m:
        what = t[:len(m.group("what"))].strip()
        say = re.match(r"(?i)^(?:say|tell me|greet me with|remind me(?: to| that| about)?)\s+(?P<x>.+?)(?:\s+to me)?$", what)
        if say:
            words = say.group("x").strip().strip("'\"")
            return ("schedule_task", {"when": m.group("when"), "task": words[:1].upper() + words[1:], "kind": "reminder"})
        return ("schedule_task", {"when": m.group("when"), "task": what})
    m = re.match(r"^(?:please\s+)?(?:speak|talk|answer|reply|write)\s+(?:to me\s+)?(?:in\s+)?(?P<l>[a-z]+(?:\s+[a-z]+)?)(?:\s+(?:from now on|please|instead|again|now|only))*$"
                 r"|^(?:please\s+)?(?:use|switch to|change (?:the |my )?language to|set (?:the |my )?language to)\s+(?P<l2>[a-z]+)(?:\s+(?:from now on|please|instead|language))*$", low)
    if m:
        lang = (m.group("l") or m.group("l2") or "").strip()
        from . import i18n
        known = {"english", "spanish", "french", "german", "italian", "portuguese", "dutch", "swedish", "norwegian", "danish", "finnish",
                 "polish", "czech", "greek", "turkish", "russian", "ukrainian", "arabic", "hebrew", "hindi", "bengali", "urdu", "chinese",
                 "mandarin", "cantonese", "japanese", "korean", "vietnamese", "thai", "indonesian", "malay", "filipino", "tagalog", "swahili",
                 "romanian", "hungarian", "persian", "farsi", "irish", "welsh", "catalan", "basque", "latin", "esperanto", "klingon", "elvish"}
        if lang in known:
            return ("set_appearance", {"language": lang})
    m = re.match(r"^(?:merge|combine|join|put together)\s+(?:all\s+)?(?:of\s+)?(?:these|the|my|those|them|all)?\s*(?:the\s+)?pdfs?(?:\s+files)?"
                 r"(?:\s+in\s+(?:my\s+)?(?P<f>[\w .~/-]+?))?(?:\s+(?:into|in|to|as)\s+(?:one(?:\s+(?:pdf|file))?|a\s+single\s+(?:pdf|file)|(?:a\s+(?:pdf|file)\s+called\s+)?(?P<n>[\w .-]+?)))?$", low)
    if m:
        args = {}
        if m.group("f"):
            f = m.group("f").strip()
            args["folder"] = {"downloads": "~/Downloads", "documents": "~/Documents", "desktop": "~/Desktop"}.get(f, f)
        if m.group("n") and m.group("n").strip() not in ("one", "one pdf", "one file"):
            args["name"] = t[m.start("n"):m.end("n")].strip()
        return ("merge_pdfs", args)
    m = re.match(r"^(?:copy|get|read|grab|extract|pull|take)\s+(?:out\s+)?(?:the\s+|all\s+the\s+)?(?:text|words|writing)\s+(?:out\s+)?(?:from|of|in|off)\s+"
                 r"(?:this|that|the|my|a)?\s*(?:last\s+|latest\s+|newest\s+)?(?P<w>image|picture|photo|screenshot|scan|pic|png|jpg)(?:\s*/\s*(?:image|screenshot|picture|photo))?$"
                 r"|^(?:ocr|scan)\s+(?:this|that|the|my)?\s*(?:image|picture|screenshot)(?:\s+for\s+text)?$|^what\s+does\s+(?:this|that|the)\s+(?:screenshot|image|picture)\s+say$", low)
    if m:
        return ("text_from_image", {})
    if re.match(r"^(?:(?:make|set|put|change)\s+)?(?:everything|all|the\s+text|text|it)?\s*(?:back\s+)?(?:to\s+)?(?:normal|regular|default|standard)\s+(?:text\s+)?size(?:d)?(?:\s+(?:everything|again|text))?$"
                r"|^(?:everything|text)\s+(?:back\s+)?(?:to\s+)?(?:normal|regular|default)\s+size$", low):
        return ("set_appearance", {"scale": "default"})
    m = re.match(r"^(?:share|send)\s+(?:this|that|the|my|a)?\s*(?P<f>[\w .~/-]+?)?\s*(?:folder|files?|photos|pictures|documents)?\s+"
                 r"(?:with|to)\s+(?:my\s+|the\s+|another\s+|other\s+)*(?:other\s+)?(?:computer|laptop|pc|mac|phone|tablet|ipad|devices?)s?(?:\s+on\s+(?:the|my)\s+(?:wi-?fi|network))?$"
                 r"|^share\s+(?:this|that|the|my)?\s*(?P<f2>[\w .~/-]+?)?\s*folder(?:\s+on\s+(?:the|my)\s+(?:wi-?fi|network))?$", low)
    if m and "screen" not in low:
        f = (m.group("f") or m.group("f2") or "").strip()
        f = {"photos": "~/Pictures", "pictures": "~/Pictures", "music": "~/Music", "documents": "~/Documents", "downloads": "~/Downloads",
             "videos": "~/Videos", "desktop": "~/Desktop"}.get(f, f if f.startswith(("~", "/")) else "")
        return ("share_folder", {"path": f} if f else {})
    if re.match(r"^(?:stop|end|turn off)\s+(?:the\s+)?shar(?:ing|e)(?:\s+(?:the\s+|this\s+|my\s+)?(?:folder|files))?$", low):
        return ("share_folder", {"stop": True})
    m = re.match(r"^(?:show|see|view|display|unhide|reveal)\s+(?:the\s+|all\s+|my\s+)?(?:hidden|dot)\s*files?(?:\s+(?:too|as well))?$|^show\s+(?:me\s+)?(?:the\s+)?files?\s+that\s+are\s+hidden$", low)
    if m:
        return ("show_files", {"hidden": True})
    if re.match(r"^(?:hide|stop showing)\s+(?:the\s+)?(?:hidden|dot)\s*files?(?:\s+again)?$", low):
        return ("show_files", {"hidden": False})
    m = re.match(r"^(?:rename|name)\s+(?:all\s+)?(?:of\s+)?(?:these|the|my|those|all)?\s*(?:the\s+)?(?P<k>photos|pictures|pics|images|videos|songs|music|files)"
                 r"(?:\s+in\s+(?P<f>.+?))?\s+(?:to|as)\s+(?P<b>.+?)(?:\s*\d+\s*(?:,\s*\d+\s*)*(?:,?\s*(?:\.\.\.|…|etc\.?|and so on))?)?$", low)
    if m and m.group("b").strip(" ,'\"") and not re.search(r"lower ?case|upper ?case|capitals|caps|dash|hyphen|underscore|title case|spaces", m.group("b")):
        k = {"photos": "photos", "pictures": "photos", "pics": "photos", "images": "photos", "videos": "videos", "songs": "music", "music": "music"}.get(m.group("k"), "all")
        b = t[m.start("b"):m.start("b") + len(m.group("b"))].strip(" ,'\"")     # (the owner's own capitals)
        args = {"name": b, "kind": k}
        if m.group("f"):
            args["folder"] = m.group("f")
        return ("rename_series", args)
    m = re.match(r"^(?:find|show|look for|check for|get rid of|remove|delete|clean up)\s+(?:me\s+)?(?:all\s+)?(?:the\s+|my\s+|any\s+)?(?:duplicates?|duplicate\s+(?:files|photos|pictures|songs)|"
                 r"(?:files|photos|pictures) (?:that are|i have) (?:twice|duplicated))(?:\s+(?:in|from)\s+(?:my\s+)?(?P<f>.+?))?$", low)
    if m:
        delete = bool(re.match(r"^(?:get rid of|remove|delete|clean up)", low))
        f = (m.group("f") or "").strip()
        f = {"photos": "~/Pictures", "pictures": "~/Pictures", "pics": "~/Pictures", "music": "~/Music", "songs": "~/Music", "documents": "~/Documents",
             "docs": "~/Documents", "downloads": "~/Downloads", "videos": "~/Videos", "desktop": "~/Desktop", "files": "~", "home folder": "~"}.get(f, f or "~")
        return ("find_duplicates", {"folder": f, "delete": True} if delete else {"folder": f})
    if re.fullmatch(r"(?:make|turn|switch|put|set)\s+(?:the\s+|my\s+)?(?:web\s+)?(?:browser|firefox|internet)(?:\s+to)?\s+dark(?:\s+mode)?|dark\s+mode\s+(?:for|in|on)\s+(?:the\s+|my\s+)?(?:browser|firefox)", t.strip().rstrip(".!"), re.I):
        return ("set_appearance", {"theme": "dark"})          # the browser follows the system's look
    m = _DARK_WORDS.match(t)
    if m and len(t.split()) <= 4:
        return ("set_appearance", {"theme": "dark" if m.group("d") else "light"})
    m = re.match(r"^(?:give\s+me\s+|get\s+|show\s+me\s+)?(?:the\s+)?(?:directions|route|way)\s+(?:to|for)\s+(?P<p>.+)$|^how\s+do\s+i\s+get\s+to\s+(?P<p2>.+)$|^(?:navigate|drive)\s+to\s+(?P<p3>.+)$", low)
    if m:
        place = (m.group("p") or m.group("p2") or m.group("p3")).strip()
        return ("browse", {"site": "https://www.google.com/maps/dir/?api=1&destination=" + _u.quote_plus(place)})
    if re.match(r"^(?:help\s+me\s+)?(?:apply\s+for|find|look\s+for|search\s+for)\s+(?:a\s+)?jobs?(?:\s+.*)?$|^job\s+search$", low):
        q = re.sub(r"^(?:help\s+me\s+)?(?:apply\s+for|find|look\s+for|search\s+for)\s+(?:a\s+)?jobs?\s*", "", low).strip()
        return ("browse", {"site": "https://www.indeed.com/jobs?q=" + _u.quote_plus(q) if q else "https://www.indeed.com"})
    m = re.match(r"^(?:order|buy|get\s+me|reorder)\s+(?:some\s+)?(?:more\s+)?(?P<w>.+?)(?:\s+online)?$", low)
    if m and not re.search(r"\b(app|program|software|pizza|food|uber|taxi|ride)\b", low):
        return ("browse", {"site": "https://www.amazon.com/s?k=" + _u.quote_plus(m.group("w"))})
    m = re.match(r"^pay\s+(?:my\s+|the\s+)?(?P<w>[\w\s]+?\s+)?bill(?:s)?(?:\s+online)?$", low)
    if m:
        return ("browse", {"search": f"pay {(m.group('w') or '').strip()} bill online".replace("  ", " ")})
    m = re.match(r"^(?:book|make|schedule)\s+(?:a\s+|an\s+)?(?P<w>[\w'\s]+?)\s+appointment$", low)
    if m:
        return ("browse", {"search": f"book {m.group('w').strip()} appointment online near me"})
    m = re.match(r"^(?:define|definition\s+of|what\s+does\s+(?P<w2>[\w'-]+)\s+mean|look\s+up\s+the\s+word|dictionary)\s*(?P<w>[\w'-]*)$", low)
    if m and (m.group("w") or m.group("w2") or low == "dictionary"):
        w = m.group("w") or m.group("w2")
        return ("browse", {"site": f"https://www.merriam-webster.com/dictionary/{_u.quote(w)}" if w else "https://www.merriam-webster.com"})
    m = re.match(r"^(?:connect|add|sync|open|set\s+up)\s+(?:my\s+)?(?P<w>google|outlook|icloud|apple)(?:\s*(?:/|or|and)\s*(?:google|outlook|icloud|apple))?\s+calendars?$", low)
    if m:
        return ("browse", {"site": {"google": "https://calendar.google.com", "outlook": "https://outlook.live.com/calendar",
                                    "icloud": "https://www.icloud.com/calendar", "apple": "https://www.icloud.com/calendar"}[m.group("w")]})
    m = re.match(r"^(?:add|put)\s+(?P<what>.+?)\s+(?:to|on|in)\s+(?:my\s+|the\s+)?calendar(?:\s+(?:for|on|at)\s+(?P<when2>.+))?$", low)
    if m:
        what, when = m.group("what"), m.group("when2") or ""
        wm = re.search(r"\b((?:on\s+|this\s+|next\s+)?(?:mon|tues|wednes|thurs|fri|satur|sun)day(?:\s+(?:at\s+)?\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?|tomorrow(?:\s+(?:at\s+)?\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?|"
                       r"(?:at\s+)?\d{1,2}(?::\d\d)?\s*(?:am|pm)|\d{4}-\d\d-\d\d(?:\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?)\b.*$", what)
        if wm and not when:
            when, what = wm.group(0), what[:wm.start()].strip()
        if when:
            return ("schedule_task", {"when": when.strip(), "task": what.strip(), "kind": "reminder"})
    m = re.match(r"^(?P<when>every\s+(?:day|weekday|weekend|morning|evening|night|week|month|(?:mon|tues|wednes|thurs|fri|satur|sun)day)s?(?:\s+(?:at\s+)?\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?)"
                 r"\s*,?\s+remind\s+me\s+(?:to\s+)?(?P<what>.+)$", low)
    if m:
        return ("schedule_task", {"when": m.group("when"), "task": m.group("what"), "kind": "reminder"})
    m = re.match(r"^(?:lock|auto-?lock)\s+(?:the\s+(?:screen|computer)\s+)?(?:automatically\s+)?after\s+(?P<n>\d+)\s*(?:minutes?|mins?)(?:\s+of\s+(?:inactivity|idle|not\s+using\s+it))?$", low)
    if m:
        return ("change_setting", {"setting": "autolock", "value": m.group("n")})
    if re.match(r"^(?:turn\s+off|stop|disable|mute|silence|hide)\s+(?:all\s+)?(?:the\s+)?notifications$", low):
        return ("change_setting", {"setting": "do_not_disturb", "value": "on"})
    m = re.match(r"^(?:turn\s+off|stop|disable|mute|silence|hide|pause)\s+(?:all\s+)?(?:the\s+)?notifications?\s+for\s+"
                 r"(?:(?P<a>an?)\s+hour|(?P<n>\d+)\s*(?P<u>minutes?|mins?|hours?))$", low)
    if m:
        mins = 60 if m.group("a") else int(m.group("n")) * (60 if (m.group("u") or "").startswith("hour") else 1)
        return ("change_setting", {"setting": "do_not_disturb", "value": "on", "minutes": mins})
    m = re.match(r"^(?:ssh|connect|log\s*in)\s+(?:in)?to\s+(?:my\s+)?(?:server\s+)?(?P<h>[\w.@-]+\.[\w.-]+|\d+\.\d+\.\d+\.\d+)$|^ssh\s+(?P<h2>[\w.@-]+)$", low)
    if m:
        import shlex as _sh
        return ("open_app", {"command": "foot ssh " + _sh.quote(m.group("h") or m.group("h2")), "graphical": True})
    m = re.match(r"^(?:clone|git\s+clone|download)\s+(?:this\s+|the\s+)?(?:repo(?:sitory)?\s+)?(?P<u>https?://\S+|git@\S+)$", t, re.I)
    if m:
        import shlex as _sh
        return ("run_command", {"command": "mkdir -p ~/Projects && cd ~/Projects && git clone " + _sh.quote(m.group("u"))})
    m = re.match(r"^(?:edit|open|change)\s+(?:my\s+|the\s+)?(?P<f>\.?(?:bashrc|profile|zshrc|ashrc|vimrc|gitconfig|bash_profile))(?:\s+file)?$", low)
    if m:
        f = m.group("f")
        return ("open_file", {"path": "~/" + (f if f.startswith(".") else "." + f), "edit": True})
    if re.match(r"^(?:open|show|go\s+to)\s+(?:the\s+)?(?:last|most\s+recent)\s+(?:thing|file|document)\s+(?:i\s+(?:was\s+)?(?:using|working\s+on|opened|had\s+open))?$", low):
        return ("open_latest", {"where": "home"})
    m = re.match(r"^(?:make|write|create|start|help\s+me\s+(?:write|make))\s+(?:me\s+)?(?:a\s+|my\s+)?(?:new\s+)?(?P<k>resume|résumé|cv|cover\s+letter|letter)$", low)
    if m:
        k = m.group("k").replace("résumé", "resume").replace("cv", "resume")
        return ("make_document", {"kind": "cover letter" if "cover" in k else k})
    if re.match(r"^(?:back\s*up|backup|save\s+a\s+copy\s+of|copy)\s+(?:all\s+)?(?:my\s+)?(?:files|stuff|documents|photos|computer|everything)(?:\s+(?:to|onto)\s+(?:the\s+|my\s+)?(?:usb|stick|usb\s+stick|external\s+(?:drive|disk)|drive))?$|^make\s+a\s+backup$", low):
        return ("backup_files", {})
    if re.match(r"^(?:restore|bring\s+back|get\s+back)\s+(?:my\s+)?(?:files|stuff|everything)\s+from\s+(?:the\s+|my\s+)?(?:backup|usb|stick|drive)$|^restore\s+(?:my\s+|the\s+)?backup$", low):
        return ("restore_backup", {})
    if re.match(r"^(?:format|erase|wipe|reformat)\s+(?:this\s+|the\s+|my\s+)?(?:usb(?:\s+stick|\s+drive)?|stick|flash\s*drive|thumb\s*drive|sd\s+card|memory\s+card|external\s+(?:drive|disk))$", low):
        return ("format_drive", {})
    m = re.match(r"^(?:let'?s\s+)?(?:play|open|start)\s+(?:a\s+game\s+of\s+|some\s+)?(?P<g>chess|solitaire|minesweeper|sudoku|tic[- ]?tac[- ]?toe|noughts\s+and\s+crosses|snake)(?:\s+with\s+me)?$", low)
    if m:
        g = m.group("g").replace(" ", "").replace("-", "")
        if g == "chess":
            return ("browse", {"site": "https://lichess.org"})
        if g == "solitaire":
            return ("browse", {"site": "https://www.google.com/search?q=solitaire"})
        return ("open_app", {"command": {"tictactoe": "tic-tac-toe", "noughtsandcrosses": "tic-tac-toe"}.get(g, g)})
    # several programs at once: "install python / node / git", "install git and docker"
    m = re.match(r"^(?:please\s+)?install\s+(?P<l>[\w.+-]+(?:\s*(?:/|,|\band\b|&)\s*[\w.+-]+)+)$", low)
    if m:
        from .tools import APP_NAMES
        names = [n.strip() for n in re.split(r"\s*(?:/|,|\band\b|&)\s*", m.group("l")) if n.strip()]
        pk = [APP_NAMES.get(n, n) for n in names]
        if all(not str(p).startswith("flathub:") for p in pk):
            return ("install_app", {"packages": " ".join(pk)})
    return None


_STEP_VERB = (r"(?:turn|flip|rotate|add|call|name|rename|email|e-mail|send|mail|move|copy|put|make|zip|shrink|resize|save|read|"
              r"open|convert|delete|remove|write|set|play|crop|summari[sz]e|remind|tell|show|print|attach|upload|download|"
              r"find|search|look|count|sort|list|share|lock|unlock|close|start|stop|cancel|schedule|install|create|build|draw)")
_CHAIN = re.compile(rf"(?:,|;|\band)\s*(?:then\s+|and\s+|also\s+|after that\s+|finally\s+)?{_STEP_VERB}\b.*(?:,|\band\b|\bthen\b)|"
                    rf"\bthen\s+{_STEP_VERB}\b|\bafter that\b|\bfinally\b", re.I)


def is_chain(text):
    """Several steps where later ones build on earlier ones ("turn it into a pdf, flip it, then email it"): no single
    word route may take it; the model does the whole chain. Two plain requests ("open my email and play music") are not."""
    t = str(text or "")
    if _mail_setup(t.strip()):
        return False
    if re.search(r"\b(?:make|build|create|write|draw|design)\b.*\band\s+(?:also\s+)?(?:remind|reminds|notify|notifies|nag|nags|email|"
                 r"emails|send|sends|share|schedule|play|open)\b", t, re.I):
        return True                       # make something, and also do something with it / about it
    steps = len(re.findall(rf"(?:^|,|;|\band\b|\bthen\b)\s*(?:then\s+|and\s+|also\s+)?{_STEP_VERB}\b", t, re.I))
    return steps >= 3 or bool(re.search(rf"\bthen\s+{_STEP_VERB}\b.*\b(?:it|them|that|the \w+)\b|\b(?:it|them)\b.*\bthen\b", t, re.I)) \
        or (steps >= 2 and bool(re.search(r"\b(?:it|them|those|these)\b", t, re.I)) and "," in t)


def _fix_schedule(r):
    """A clock time left in the task ("shut down at 11pm", when "every night") belongs to the time."""
    if not r or r[0] != "schedule_task":
        return r
    a = dict(r[1])
    m = re.search(r"\s*\bat\s+(\d{1,2}(?::\d\d)?\s*(?:am|pm)|\d{1,2}:\d\d|noon|midnight)\b", a.get("task", ""), re.I)
    if m and not re.search(r"\d|noon|midnight", a.get("when", "")):
        a["when"] = f"{a['when']} at {m.group(1)}".strip()
        a["task"] = (a["task"][:m.start()] + a["task"][m.end():]).strip()
    return (r[0], a)


def match(text):
    return _fix_schedule(_match(text))


def _analyze_program(t):
    """'analyze the app in my reatest folder', 'look inside the program reatest/app': the analysis tool, deterministic."""
    m = re.match(r"^\s*(?:please\s+)?(?:analy[sz]e|inspect|look\s+inside|open\s+up|take\s+apart|reverse\s+engineer|how\s+is)\s+"
                 r"(?:the\s+|this\s+|that\s+|my\s+)?(?:app|program|application|file|folder|package|software)\s*"
                 r"(?:in|from|at|called|named)?\s*(?:my\s+|the\s+)?(?P<path>[\w./ -]+?)\s*(?:folder|directory)?\s*[.!?]?\s*$", t, re.I)
    if not m:
        return None
    path = re.sub(r"\s+(?:built|made|works?|made up|done|work|folder|directory)$", "", m.group("path").strip().rstrip("/"), flags=re.I)
    return ("analyze_program", {"path": path})


def _mail_send_direct(t):
    # email straight to an address: "email craig@example.com saying the meeting moved", "write a short email to X saying … and send it"
    m = re.match(r"^(?:please\s+)?(?:e-?mail|send\s+(?:an?\s+)?e-?mail\s+to|write\s+(?:an?\s+)?(?:short\s+|quick\s+|brief\s+|new\s+|nice\s+|little\s+)?e-?mail\s+to|message)\s+(?P<to>[\w.+-]+@[\w.-]+)\s*,?\s+"
                 r"(?:saying|that|to\s+say|telling\s+(?:him|her|them)|and\s+(?:say|tell\s+(?:him|her|them))|:)\s*(?P<b>.+)$", t, re.I)
    if not m:
        return None
    body = m.group("b").strip().strip("'\"")
    body = re.sub(r"[,;]?\s+(?:and|then)\s+(?:send|email|mail)\s+it\.?$", "", body, flags=re.I).strip()
    body = body[:1].upper() + body[1:]
    if not re.search(r"[.!?]$", body):
        body += "."
    subject = " ".join(re.sub(r"[.!?]$", "", body).split()[:7])
    return ("mail_send", {"to": m.group("to"), "subject": subject, "body": body})


def _match(text):
    text = plain(text)
    t = text.strip()
    if len(t) > 400 or "\n" in t:
        return None
    ms = _mail_setup(t)
    if ms:
        return ms
    ap2 = _analyze_program(t)
    if ap2:
        return ap2
    em = _mail_send_direct(t)                 # "write an email to X saying … and send it": one action, not a chain
    if em:
        return em
    if is_chain(t):
        return None
    if len(t) > 200:
        return None
    ev2 = _everyday2(t)
    if ev2:
        return ev2
    ap = _apps(t)
    if ap:
        return ap
    ev = _everyday(t)
    if ev:
        return ev
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
    return _restyle(t)


# A whole-look change the fixed look options can't express ("make the windows look like ...", "turn the interface into ...")
# goes to restyle, which writes a style for it; a known theme or option is left to set_appearance and the rules above.
_RESTYLE = re.compile(r"^(?:please\s+)?(?:(?:make|turn|change|convert|transform|redo|restyle|redesign)\s+(?:all\s+(?:of\s+)?)?(?:the\s+|my\s+|this\s+)?"
                      r"(?:entire\s+|whole\s+)?(?P<what>interface|ui|desk(?:top)?|screen|windows?|everything|it|look|buttons?|text|title ?bars?|icons?|menus?)"
                      r"\s+(?:look\s+)?(?:(?:like|into|to|in(?:\s+the\s+style\s+of)?|as)\s+)?(?P<how>.+)"
                      r"|(?:i\s+want|give\s+me)\s+(?:the\s+|my\s+|a\s+)?(?:interface|desk(?:top)?|screen|windows?|everything|look)\s+(?:to\s+look\s+|that\s+looks\s+|looking\s+)?(?:like\s+)?(?P<how2>.+))$", re.I)
_LOOK_HANDLED = re.compile(r"^(?:dark|light|bigger|smaller|larger|default|normal|back|readable|brighter|dimmer|louder|quieter|"
                           r"(?:full|half)\s*screen|maximi[sz]ed?|minimi[sz]ed?|on|off)\b", re.I)


def _restyle(t):
    m = _RESTYLE.match(t.rstrip(".!"))
    if not m:
        return None
    how = (m.group("how") or m.group("how2") or "").strip()
    if not how or _LOOK_HANDLED.match(how):
        return None
    if re.search(r"look(?:s)? like (?:windows|mac|macos|the mac|a mac|the windows)", how, re.I):
        return None                                   # a desk layout (taskbar or menu bar): the layout options do it
    if re.search(r"\b(?:dimm?(?:er)?|brighter|brightness|darker|lighter)\b", how, re.I) and (m.group("what") or "").lower() in ("screen", "display", "it"):
        return None                                   # the screen's brightness, not its style
    if (m.group("what") or "").lower() == "screen" and re.search(r"upside|rotat|flip|sideways|portrait|landscape", how, re.I):
        return None                                   # the real screen turns (display rotation), not just the desk's look
    if (m.group("what") or "").lower() == "it" and not re.search(r"\blook\b|\bstyle\b|\binto\b", t, re.I):
        return None                                   # "make it X" alone could be about anything
    from . import themes
    short = len(re.findall(r"[\w']+", how)) <= 3
    if short and ui_color(how):
        return None                                   # a colour: the look options do it exactly (rules above)
    if short and themes.resolve(how):
        return ("set_appearance", {"theme": how})      # a look the OS knows by name
    return ("restyle", {"description": t.strip()})


def ui_color(words):
    from . import ui
    w = re.sub(r"^(?:all\s+|completely\s+|totally\s+)", "", str(words).lower()).strip()
    return ui.parse_color(w) is not None
