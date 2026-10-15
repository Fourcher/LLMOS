"""Everyday requests the OS answers or does itself, at once, without the model (found by the use-case runs):
days until a date, a work-hours timer, what is using a port (and stopping it), a local web server / HTML preview,
temperatures, battery and disk health, parcel tracking, typing and language practice, the computer's name, and a
focus mode that blocks distracting sites for a while.

handle(desk, line) -> True when it answered. MATCH is a quick test the desk uses to decide the request is instant."""
import collections
import datetime as dt
import errno
import glob
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse

from . import config, rootd_client
from . import system as _system
from .system import _hosts_name_ok, _write_hosts

NAME_BAD = "that name isn't allowed: use letters, numbers and dashes"


def _web_err(e):
    """A web.WebError as plain words. Its messages are mostly plain already (passed through, first line, no period);
    raw curl text becomes the owner's words, and anything with a URL, path or curl exit code becomes "something went wrong"."""
    raw = str(e).strip()
    text = raw.splitlines()[0][:120].strip() if raw else ""
    low = text.lower()
    if "curl" in low or re.search(r"\((6|7|28)\)", text) or "resolve host" in low or "timed out" in low or "failed to connect" in low:
        if "(6)" in text or "resolve host" in low:
            return "no internet connection"
        if "(28)" in text or "timed out" in low:
            return "no answer from the internet"
        if "(7)" in text or "failed to connect" in low:
            return "couldn't reach the site"
        return "something went wrong"
    if not text or "/" in text or "://" in text:
        return "something went wrong"
    return text.rstrip(". ") or "something went wrong"


def _plain_err(e, bad="that name or value isn't allowed"):
    """A short plain-words reason for an error, so the owner never sees Python's raw text (no errno, no paths).
    A system-helper refusal ("bad args: …") gives `bad`; the helper's other plain messages are shown as they are."""
    if isinstance(e, rootd_client.RootdError) or isinstance(e, ValueError):
        text = str(e).strip()
        if text.startswith("bad args"):
            return bad
        if isinstance(e, rootd_client.RootdError) and text:
            return text.splitlines()[0][:120]
    try:
        from . import web  # lazy: everyday still imports without web
    except ImportError:
        web = None
    if web is not None and isinstance(e, web.WebError):
        return _web_err(e)
    if isinstance(e, PermissionError):
        return "it isn't allowed here"
    if isinstance(e, FileNotFoundError):
        return "it isn't there"
    if isinstance(e, FileExistsError):
        return "something with that name already exists"
    if isinstance(e, IsADirectoryError):
        return "that's a folder"
    if isinstance(e, NotADirectoryError):
        return "that isn't a folder"
    if isinstance(e, OSError) and getattr(e, "errno", None) == errno.ENOSPC:
        return "the disk is full"
    if isinstance(e, (socket.timeout, TimeoutError, urllib.error.URLError)):
        return "no answer from the internet"
    return "something went wrong"


_JOKE_PAT = (r"(?:^(?:please\s+)?(?:tell|give)\s+me\s+(?:a\s+|another\s+|one\s+more\s+)?"
             r"(?:(?:good|funny|short|clean|dad|bad)\s+)?joke(?:\s+please)?[.!?]*$|"
             r"^(?:say|know)\s+(?:a|any)\s+jokes?\??$|"
             r"^make\s+me\s+laugh[.!?]*$)")

# "how much space is left", "is my disk full", "free up space": the disk's real numbers (free_space), case-insensitive.
_FREE_SPACE_Q = (r"(?i:how much (?:free |disk )?(?:space|storage|room)(?: is)? (?:left|free|remaining|do i have)(?: on (?:my |the )?(?:disk|computer|drive|hard drive|machine))?"
                 r"|how much (?:disk )?space (?:is )?(?:left|free)"
                 r"|(?:is|why is) my (?:disk|computer) full|how full is my disk"
                 r"|(?:check )?(?:disk space|storage|free space)|free up (?:disk )?space)")

# simple fact questions ("how tall is mount everest"): the subject may not be about the owner, this/that, a place
# needing a location, or a personal object (email, file, computer...), so those still go to the model
_FACT_SUBJ = (r"(?!.*\b(?:i|me|my|mine|we|us|our|you|your|it|its|this|that|these|those|here|there|home|work|near|nearby|away|to|from|"
              r"email|mail|message|file|folder|document|photo|video|picture|contacts?|computer|laptop|phone|screen|printer|wifi|desktop|pc|calendar|inbox)\b)"
              r"[a-z][a-z .'-]{1,40}?")
_FACT_PATS = (rf"how (?:tall|high|big|old|far|long|deep|heavy|fast) is (?:the )?({_FACT_SUBJ})",
              rf"when was ({_FACT_SUBJ}) (?:born|built|founded|made)",
              rf"what is the population of ({_FACT_SUBJ})",
              rf"what(?:'s| is) the capital of ({_FACT_SUBJ})",
              rf"who (?:wrote|painted|invented|founded|discovered) ({_FACT_SUBJ})")
_LIVE_FACTS = tuple(re.compile(p) for p in _FACT_PATS)
_FACT_MATCH = "^(?:" + "|".join(_FACT_PATS) + r")[?.!]?$"

MATCH = re.compile(
    r"\b(?:version|build)\b|^(?:which|what)\s+(?:ai\s+|language\s+|llm\s+)?model\b|(?:ai|llm|brain)\s+(?:are\s+you|is\s+this)|running on\??$|updates? (?:from|off|status|source)|updates (?:come|coming) from|^(?:pair|connect|link) .* for updates$|^" + _FREE_SPACE_Q + r"[?.!]?$|" +
    r"^how much (?:free |disk )?(?:space|storage|room)(?: is| do i have)?(?: (?:left|free|remaining))?(?: on (?:my |the )?(?:disk|computer|drive|hard drive|machine))?(?: (?:left|free|remaining))?$|^how much (?:disk )?space (?:is )?(?:left|free)$|"
    r"^(?:turn|switch) (?:on|off) (?:the |my )?bluetooth$|^(?:turn|switch) (?:the |my )?bluetooth (?:on|off)$|^bluetooth (?:on|off)$|^(?:yes|yeah|yep|yup|sure|ok|okay)$|(?:the |my )?(?:screen|computer|pc|laptop|everything) (?:has |have )?(?:froze|frozen|locked up|is stuck)$|"
    r"(?:computer|pc|laptop|machine) (?:is |has been |got |feels )?(?:really |very |so |quite )?slow\b|"
    r"\b(?:days? (?:until|till|to|left)|is (?!it\b|this\b|my\b|that\b|the (?:computer|screen|wifi|sound|mouse|printer|keyboard|battery|camera)\b)[a-z][a-z .'-]{1,30} (?:down|broken|having (?:issues|problems|an outage))\b|what time does [a-z' .-]{2,40} (?:open|close)\b|who won (?:the )?[a-z' .-]{2,40}(?: last night| yesterday| today| this week)?\b|countdown|how long (?:until|till)|work timer|^clock (?:in|out)$|i'?m clocking (?:in|out)|track(?:ing)? (?:my )?(?:hours|time)|"
    r"hours (?:did i|have i) work|port \d+|on \d{2,5}\b|web ?server|serve (?:this|the)|(?:stop|end|close|kill) (?:the |my )?local website|stop serving|preview (?:this|the|my)|temperature|"
    r"(?:too |so |very |running |getting )?hot\b|overheat|battery (?:health|dying|dead|draining|drains|life|is draining)|"
    r"drive health|disk health|hard ?drive (?:health|failing|dying|ok)|ssd health|smart status|track (?:my )?(?:parcel|package|order|delivery)|"
    r"order status|where is my (?:parcel|package|order)|typing (?:practice|tutor|lessons?|test)|teach me to type|learn (?:to type|\w+ish|french|spanish|german|"
    r"italian|japanese|chinese|korean|portuguese|arabic|russian|hindi|dutch)|computer(?:'?s)? name|hostname|name (?:this|the) computer|"
    r"call this computer|rename (?:this|the) computer|focus mode|block (?:youtube|facebook|instagram|tiktok|reddit|twitter|social media|"
    r"distracting|websites|sites)|stop focus|end focus|double[- ]?clicks?|sticky keys|(?:mouse )?(?:pointer|cursor)\b|hands? (?:shake|shaking|tremor)|tremor|"
    r"(?:startup|start-up|boot|notification|clicking|click|system|alert) sounds?|the chime|chime (?:on|off)|"
    r"when i (?:log ?in|sign in|start (?:up|the computer))|automatically|autostart|start(?:s)? (?:up )?with the computer|startup (?:programs|apps)|"
    r"vpn|wireguard|openvpn|proxy|"
    r"\bcd\b|\bdvd\b|blu-?ray|disc drive|"
    r"on (?:my |the )?tv|chromecast|cast (?:to|this|my)|airplay|"
    r"colou?r ?blind|colou?r filter|deuteranop|protanop|tritanop|profile (?:picture|photo|pic)|avatar|screen ?saver|clock when idle|"
    r"\.exe\b|windows (?:program|app|software|game)s?|\.deb\b|appimage|"
    r"(?:keep|stay|put) (?:this |it |the window )?(?:always )?on top|always on top|picture[- ]in[- ]picture|\bpip\b|"
    r"(?:other|second|external|left|right) (?:monitor|screen|display)|new (?:workspace|desktop)|(?:game ?)?controller|gamepad|joystick|"
    r"phone'?s? (?:internet|data|hotspot)|tether|hotspot|drawing tablet|wacom|pen tablet|touch ?screen|"
    r"(?:share|send|export|give|save) (?:the |my |this |that )?(?:app|game|tool)s?\b|encrypt|stolen|guest|someone else is using|disk encryption|passwords\b|password (?:manager|keeper|vault|safe)|logs?\b|journalctl|dmesg|service (?:fail|crash)|default shell|shell to|"
    r"cloud|new (?:computer|pc|laptop)|settings and apps|snapshot|roll ?back|restore point|kids? mode|child mode|parental|only let my|shortcut for|"
    r"\d+(?:\.\d+)?\s*(?:times|plus|minus|divided|x|\*|/|\+|-|%)\s*\d+|\d+\s*%\s*of|square root|power of|\bconvert\b|how many \w+ (?:are )?in an? |"
    r"\b(?:split|divide) \$?\d|time (?:is it )?in [a-z]|how (?:long|much time) (?:is it )?(?:until|till) \d|^(?:how (?:do (?:you|i) )?)?spell\b|"
    r"^define\b|definition of|what does \w+ mean|meaning of|words? for \w+$|synonyms? (?:of|for)|"
    r"\d+\s*(?:degrees|°)?\s*(?:fahrenheit|celsius|f|c)\b|\d+\s*(?:kg|kilos?|pounds?|lbs?|miles?|km|feet|foot|inch(?:es)?|cm|meters?|metres?|ounces?|oz|grams?|liters?|litres?|gallons?|cups?|mph)\s+(?:to|in|into)\b|"
    r"\d+(?:\.\d+)?\s*(?:%|percent)\s+(?:tip|tax|discount|off|service|gratuity)|\d+(?:\.\d+)?\s*(?:percent|per\s*cent)\s+of\s+[\d,]|what\s+percent(?:age)?\s+(?:of\s+[\d,.]+\s+is|is\s+[\d,.]+\s+of)\s+[\d,.]+|^(?:thanks?|thank you|thx|cheers|ta)\b|"
    r"how (?:big|large) is|how much (?:space|room) does|how many (?:files|things|items|photos|pictures|songs) (?:are |do i have )?in|"
    r"(?:what|which) (?:wi-?fi|network)|what(?:'s| is) (?:my |the )?(?:wi-?fi|network)|am i (?:on|connected to) (?:the )?wi-?fi|"
    r"what(?:'s| is) (?:this |the )?(?:playing|song|track)|what song is this|what am i listening to|now playing|"
    r"(?:open|show|view|play)(?: me)? (?:the |my )?(?:last|latest|newest|most recent|recent) (?:screenshot|photo|picture|image|download|pdf|document|video|song|recording)|"
    r"\bweather\b|\bforecast\b|(?:is|are) (?:the )?[a-z .'-]{2,30}? (?:down|offline|not working|broken)\b|\bnews\b|\bheadlines\b|\bcalendar\b|\bagenda\b|"
    r"\bmy schedule\b|(?:open|check|show) (?:my )?(?:e-?mail|mail|inbox)\b|\bumbrella\b|\braincoat\b|"
    r"(?:bring|take|grab|wear) (?:an? )?(?:coat|jacket|jumper|sweater)\b|(?:will|is) it (?:going to )?(?:rain|snow|be (?:hot|cold|sunny|windy))|do i need an? (?:umbrella|coat|jacket)|how (?:hot|cold|warm) (?:is it|will it be)|"
    r"internet (?:working|up|down|ok|on|connected)|am i (?:online|connected)|do i have (?:the )?internet|(?:wi-?fi|network) working|are we online|"
    r"^what day (?:of the week )?(?:is|was|will be|falls on|does)\b|"
    r"^world clock\b|^current time in\b|^(?!(?:the|my|your|our|this|that|what|what's|current|local|real|bed|lunch|next|last|day|night|good|game|show|meeting)\b)[a-z][a-z .'-]{1,30} time[?.!]?$|"
    r"\.(?:txt|md|csv|log)$|"
    r"^(?:please )?(?:block|unblock|ban)\b|^(?:please )?allow (?:all|every)|(?:remove|clear) (?:all )?(?:the )?(?:website )?blocks?)|" + _FACT_MATCH + "|" + _JOKE_PAT, re.I)


def _say(desk, line, text):
    desk.instant_reply(line, text)
    return True


def _open(desk, url):
    from . import agent
    agent.execute(desk.ctx, "browse", {"site": url})


# the internet, by the owner's setting: "yes" always, "no" never, "ask" asks the desk (once per kind of request, as the agent does)
_OFF_WEATHER = "The internet is switched off in settings, so I can't get the forecast."
_NET_DECLINED = "Okay, no internet for that."


def _net_ok(desk, what, args):
    """May this request go out on the internet? Under "ask" the desk's own question decides (no desk to ask, as in tests, counts as yes)."""
    s = config.settings.get("internet")
    if s == "no":
        return False
    if s != "ask":
        return True
    ask = getattr(getattr(desk, "ctx", None), "confirm_network", None)
    return True if ask is None else bool(ask(what, args))


def _net_no(off):
    """The reply when _net_ok said no: the function's switched-off words under "no", the decline under "ask"."""
    return off if config.settings.get("internet") == "no" else _NET_DECLINED


# ------------------------------------------------------------------ days until

def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    return dt.date(y, (h + l_ - 7 * m + 114) // 31, (h + l_ - 7 * m + 114) % 31 + 1)


def _thanksgiving(y):
    d = dt.date(y, 11, 1)
    return d + dt.timedelta(days=(3 - d.weekday()) % 7 + 21)


_HOLIDAYS = {"christmas": lambda y: dt.date(y, 12, 25), "xmas": lambda y: dt.date(y, 12, 25), "christmas eve": lambda y: dt.date(y, 12, 24),
             "new year": lambda y: dt.date(y, 1, 1), "new years": lambda y: dt.date(y, 1, 1), "new year's": lambda y: dt.date(y, 1, 1), "new year's day": lambda y: dt.date(y, 1, 1),
             "new years day": lambda y: dt.date(y, 1, 1), "christmas day": lambda y: dt.date(y, 12, 25), "boxing day": lambda y: dt.date(y, 12, 26),
             "new year's eve": lambda y: dt.date(y, 12, 31), "new years eve": lambda y: dt.date(y, 12, 31), "halloween": lambda y: dt.date(y, 10, 31),
             "valentine's day": lambda y: dt.date(y, 2, 14), "valentines day": lambda y: dt.date(y, 2, 14), "valentines": lambda y: dt.date(y, 2, 14),
             "the fourth of july": lambda y: dt.date(y, 7, 4), "fourth of july": lambda y: dt.date(y, 7, 4), "independence day": lambda y: dt.date(y, 7, 4),
             "thanksgiving": _thanksgiving, "easter": _easter, "st patrick's day": lambda y: dt.date(y, 3, 17), "st patricks day": lambda y: dt.date(y, 3, 17)}
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                       "november", "december"], 1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9


_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def _date_of(words, today):
    w = words.strip().lower().rstrip("?.! ").removeprefix("the ")
    wd = re.fullmatch(r"(?:(next|this|on)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?", w)
    if wd:
        # "next friday" is the Friday after this one; "friday" alone is the coming one (today counts)
        target = _WEEKDAYS[wd.group(2)]
        ahead = (target - today.weekday()) % 7
        if wd.group(1) == "next" and ahead == 0:
            ahead = 7
        return today + dt.timedelta(days=ahead), w
    w = re.sub(r"^(?:next |this )", "", w)
    if w in _HOLIDAYS:
        d = _HOLIDAYS[w](today.year)
        return d if d >= today else _HOLIDAYS[w](today.year + 1), w
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", w)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), w
    m = re.fullmatch(r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)|([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?)(?:,?\s+(\d{4}))?", w)
    if m:
        day, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        if mon in _MONTHS:
            y = int(m.group(5)) if m.group(5) else today.year
            try:
                d = dt.date(y, _MONTHS[mon], int(day))
            except ValueError:
                return None, w
            if d < today and not m.group(5):
                d = d.replace(year=y + 1)
            return d, w
    return None, w


def days_until(desk, line, low):
    m = re.search(r"(?:how many (?:more )?days? (?:are there |is it |left )?(?:until|till|to|before)|days? (?:until|till|left (?:until|till|to|before))|"
                  r"countdown (?:to|until|till)|how long (?:is it )?(?:until|till))\s+(?P<w>.+)$", low)
    if not m:
        return False
    today = dt.date.today()
    d, w = _date_of(m.group("w"), today)
    if d is None:
        return _say(desk, line, "When is it? Say the date, for example “how many days until 20 july”.")
    n = (d - today).days
    name = (" ".join(x if x in ("of",) else x[:1].upper() + x[1:] for x in w.split()) if w in _HOLIDAYS
            else d.strftime("%A %d %B %Y").replace(" 0", " "))
    if n == 0:
        return _say(desk, line, f"It's today: {name}.")
    if n < 0:
        return _say(desk, line, f"That was {-n} day{'s' if n != -1 else ''} ago ({d.strftime('%d %B %Y').lstrip('0')}).")
    weeks = f" (about {n // 7} weeks)" if n >= 14 else ""
    return _say(desk, line, f"{n} day{'s' if n != 1 else ''} until {name}{weeks}" + (f": {d.strftime('%A %d %B %Y').replace(' 0', ' ')}." if w in _HOLIDAYS else "."))


# ------------------------------------------------------------------ work timer

def _log_path():
    return config.data("worktime.json")


def _log():
    try:
        with open(_log_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"running": None, "done": []}


def _save_log(lg):
    with open(_log_path(), "w", encoding="utf-8") as f:
        json.dump(lg, f)


def _hm(secs):
    secs = int(secs)
    h, m = secs // 3600, secs % 3600 // 60
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _total(lg, since):
    tot = sum(max(0, min(e, time.time()) - max(s, since)) for s, e in lg["done"] if e > since)
    if lg["running"]:
        tot += time.time() - max(lg["running"], since)
    return tot


def work_timer(desk, line, low):
    lg = _log()
    midnight = time.mktime(dt.date.today().timetuple())
    week = midnight - dt.date.today().weekday() * 86400
    if re.search(r"\b(?:start|begin|resume)(?:ing)? (?:the |my |a )?(?:work )?timer|^clock in$|clocking in|start tracking|track(?:ing)? (?:my )?(?:hours|time)$|^track my hours", low):
        if lg["running"]:
            return _say(desk, line, f"The work timer is already running, since {time.strftime('%H:%M', time.localtime(lg['running']))} "
                                    f"({_hm(time.time() - lg['running'])} so far). Say “stop the work timer” to stop it.")
        lg["running"] = time.time()
        _save_log(lg)
        return _say(desk, line, f"Work timer started at {time.strftime('%H:%M')}. Say “stop the work timer” when you stop; "
                                f"today so far: {_hm(_total(lg, midnight))}.")
    if re.search(r"\b(?:stop|end|pause|finish)(?:ing)? (?:the |my )?(?:work )?timer|^clock out$|clocking out|stop tracking", low):
        if not lg["running"]:
            return _say(desk, line, "The work timer isn't running. Today: " + _hm(_total(lg, midnight)) + ".")
        took = time.time() - lg["running"]
        lg["done"].append([lg["running"], time.time()])
        lg["running"] = None
        lg["done"] = lg["done"][-2000:]
        _save_log(lg)
        return _say(desk, line, f"Stopped: {_hm(took)} this time. Today: {_hm(_total(lg, midnight))}; this week: {_hm(_total(lg, week))}.")
    if re.search(r"hours (?:did i|have i) work|how (?:much|long) (?:did i|have i) work|work(?:ed)? (?:time|hours)|track(?:ing)? (?:my )?(?:hours|time)", low):
        run = f" The timer is running since {time.strftime('%H:%M', time.localtime(lg['running']))}." if lg["running"] else ""
        return _say(desk, line, f"Today: {_hm(_total(lg, midnight))}; this week: {_hm(_total(lg, week))}.{run}")
    return False


# ------------------------------------------------------------------ ports

def _listeners(port):
    """[(pid, name)] listening on a TCP port."""
    out = []
    try:
        r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"], capture_output=True, text=True, timeout=10).stdout
        pid = None
        for ln in r.splitlines():
            if ln.startswith("p"):
                pid = int(ln[1:])
            elif ln.startswith("c") and pid:
                out.append((pid, ln[1:]))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    if not out:
        try:
            r = subprocess.run(["netstat", "-ltnp"], capture_output=True, text=True, timeout=10).stdout
            for ln in r.splitlines():
                m = re.search(r":(\d+)\s+\S+\s+LISTEN\s+(\d+)/(\S+)", ln)
                if m and int(m.group(1)) == port:
                    out.append((int(m.group(2)), m.group(3)))
        except (OSError, subprocess.SubprocessError):
            pass
    return list(dict.fromkeys(out))


def ports(desk, line, low):
    m = re.search(r"(?:kill|stop|end|close|free(?: up)?)\s+(?:whatever(?:'?s| is)|what(?:'?s| is)|the (?:thing|program|process|server)|anything)?\s*"
                  r"(?:on|using|running on|listening on|holding)?\s*(?:port\s*)?(?P<p>\d{2,5})$|^free (?:up )?port (?P<p2>\d{2,5})$", low)
    if m:
        port = int(m.group("p") or m.group("p2"))
        who = _listeners(port)
        if not who:
            return _say(desk, line, f"Nothing is running on port {port}.")
        for pid, _ in who:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        time.sleep(1.0)
        left = _listeners(port)
        for pid, _ in left:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return _say(desk, line, f"Stopped {', '.join(f'{n} ({p})' for p, n in who)}: port {port} is free.")
    m = re.search(r"(?:what(?:'?s| is)|who(?:'?s| is)|which (?:program|process|app) is)\s+(?:running|listening|using|on|open on)?\s*(?:on |using )?(?:port\s*)(?P<p>\d{2,5})|"
                  r"is (?:anything|something) (?:on|using|running on|listening on) (?:port\s*)?(?P<p2>\d{2,5})|port (?P<p3>\d{2,5}) (?:is )?(?:in use|busy|taken)", low)
    if m:
        port = int(m.group("p") or m.group("p2") or m.group("p3"))
        who = _listeners(port)
        if not who:
            return _say(desk, line, f"Nothing is running on port {port}.")
        return _say(desk, line, f"Port {port}: {', '.join(n for _, n in who)}. Say “kill whatever's on {port}” to stop it.")
    return False


# ------------------------------------------------------------------ local web server

_SERVER = {}


def web_server(desk, line, low):
    from . import tools
    if re.search(r"(?:stop|end|close|kill) (?:the |my )?(?:local )?web ?server|(?:stop|end|close|kill) (?:the |my )?local website|stop serving", low):
        p = _SERVER.pop("p", None)
        if p and p.poll() is None:
            p.terminate()
            return _say(desk, line, "The local website is stopped.")
        return _say(desk, line, "No local website was running.")
    m = re.search(r"(?:start|run|launch|open|spin up|make) (?:a |the |my )?(?:local |simple |quick )?(?:web ?|http ?)server(?: (?:here|in (?:this|the|my) (?P<f>[\w .~/-]+?)(?: folder)?))?$|"
                  r"^serve (?:this|the|my) (?P<f2>[\w .~/-]+?)?\s*(?:folder|directory|site|files)?$|^preview (?:this|the|my) (?P<h>[\w .~/-]*?\.html?|html(?: file| page)?|(?:web ?)?(?:page|site))$", low)
    if not m:
        return False
    folder = tools._LAST_FOLDER or tools._path("~")
    page = ""
    f = (m.group("f") or m.group("f2") or "").strip()
    if f and f not in ("folder", "directory"):
        cand = tools._path(f if f.startswith(("~", "/")) else "~/" + f)
        folder = cand if os.path.isdir(cand) else folder
    if m.group("h") is not None or low.startswith("preview"):
        h = (m.group("h") or "").strip()
        if h.endswith((".html", ".htm")):
            hit = next((os.path.join(d, h) for d in (folder, tools._path("~/Downloads"), tools._path("~/Desktop"), tools._path("~/Documents"), tools._path("~"))
                        if os.path.isfile(os.path.join(d, h))), None)
        else:
            hit = tools._newest([folder, "~/Downloads", "~/Desktop", "~/Documents", "~/Projects"], (".html", ".htm"))
        if not hit:
            return _say(desk, line, "There's no web page here to preview: open the folder it's in (“show my files in …”) and say it again.")
        folder, page = os.path.dirname(hit), os.path.basename(hit)
    old = _SERVER.pop("p", None)
    if old and old.poll() is None:
        old.terminate()
    port = 8000
    while _listeners(port) and port < 8100:
        port += 1
    _SERVER["p"] = subprocess.Popen(["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", folder],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(0.6)
    url = f"http://127.0.0.1:{port}/" + urllib.parse.quote(page)
    _open(desk, url)
    home = config.home().rstrip("/")
    shown = "~" + folder[len(home):] if folder.startswith(home) else folder
    return _say(desk, line, f"Showing {shown} at {url} (this computer only); it's open in the browser. Say “stop the local website” to end it.")


# ------------------------------------------------------------------ health

def _temps():
    out = []
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        try:
            t = int(open(z + "/temp").read()) / 1000
            kind = open(z + "/type").read().strip()
            out.append((kind, t))
        except (OSError, ValueError):
            pass
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            name = open(h + "/name").read().strip()
        except OSError:
            name = "sensor"
        for f in glob.glob(h + "/temp*_input"):
            try:
                lab = open(f.replace("_input", "_label")).read().strip() if os.path.exists(f.replace("_input", "_label")) else name
                out.append((lab, int(open(f).read()) / 1000))
            except (OSError, ValueError):
                pass
    return [(k, t) for k, t in out if 0 < t < 130]


def _top_cpu(n=3):
    try:
        r = subprocess.run(["ps", "-eo", "pid,pcpu,comm", "--sort=-pcpu"], capture_output=True, text=True, timeout=5).stdout.splitlines()[1:n + 1]
        return [(ln.split(None, 2)[2], float(ln.split()[1])) for ln in r if ln.strip()]
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        pass
    try:   # busybox ps: one snapshot of top
        r = subprocess.run(["top", "-b", "-n", "1"], capture_output=True, text=True, timeout=5).stdout.splitlines()
        rows = [ln.split() for ln in r if re.match(r"\s*\d+\s", ln)]
        return [(" ".join(x[8:])[:30] if len(x) > 8 else x[-1], float(x[7].rstrip("%")) if len(x) > 7 else 0.0) for x in rows[:n]]
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return []


def health(desk, line, low):
    if re.search(r"temperature|\bhot\b|overheat", low):
        ts = _temps()
        busy = _top_cpu()
        load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0
        cpu = f" Busiest now: {', '.join(f'{n} ({c:.0f}% CPU)' for n, c in busy if c >= 5)}." if any(c >= 5 for _, c in busy) else ""
        if not ts:
            return _say(desk, line, "This computer doesn't report its temperatures (virtual machines and some laptops don't)." + cpu +
                        (" It's working hard right now." if load > (os.cpu_count() or 2) * 0.8 else ""))
        hot = max(t for _, t in ts)
        verdict = ("normal" if hot < 60 else "warm but fine (it's working)" if hot < 80 else
                   "hot: close what you don't need, keep the vents clear, and use it on a hard surface" if hot < 92 else
                   "very hot: it may slow itself down or switch off to protect itself. Save your work, close heavy programs and let it cool")
        return _say(desk, line, f"Hottest part: {hot:.0f} °C, which is {verdict}." + cpu)
    if re.search(r"battery", low):
        bats = glob.glob("/sys/class/power_supply/BAT*")
        if not bats:
            return _say(desk, line, "This computer has no battery (or doesn't report one).")
        b = bats[0]
        rd = lambda n: open(os.path.join(b, n)).read().strip() if os.path.exists(os.path.join(b, n)) else None
        full = rd("energy_full") or rd("charge_full")
        design = rd("energy_full_design") or rd("charge_full_design")
        cycles = rd("cycle_count")
        cap = rd("capacity")
        parts = []
        if full and design and int(design) > 0:
            pct = int(full) * 100 // int(design)
            parts.append(f"it holds {pct}% of what it did when new" + (" (fine)" if pct >= 80 else " (worn: it runs out sooner; a replacement brings it back)" if pct >= 60
                                                                            else " (badly worn: worth replacing)"))
        if cycles and cycles != "0":
            parts.append(f"{cycles} charge cycles")
        if cap:
            parts.append(f"charged {cap}% now")
        drain = ""
        if re.search(r"drain|fast|quick|dying|life", low):
            busy = [x for x in _top_cpu(4) if x[1] >= 5]
            drain = (" Using the most power now: " + ", ".join(f"{n} ({c:.0f}% CPU)" for n, c in busy) +
                     ". Closing those, a dimmer screen and “battery saver on” help most.") if busy else \
                " Nothing is working hard right now; a dimmer screen and “battery saver on” help most."
        return _say(desk, line, ("Battery: " + "; ".join(parts) + "." if parts else "The battery doesn't report its health.") + drain)
    if re.search(r"(?:drive|disk|ssd)\b.*\b(?:health|healthy|failing|dying|dead|ok|okay|good|bad|broken)|(?:health|check)\b.*\b(?:drive|disk|ssd)|smart status", low):
        if not shutil.which("smartctl"):
            return _say(desk, line, "The drive checker isn't installed: say “install smartmontools” and ask again.")
        disks = [d for d in glob.glob("/sys/block/*") if not re.search(r"/(loop|ram|zram|dm-|sr)\w*$", d)]
        res = []
        for d in disks:
            dev = "/dev/" + os.path.basename(d)
            r = subprocess.run(["smartctl", "-H", "-A", dev], capture_output=True, text=True, timeout=30).stdout
            if "PASSED" in r or "SMART Health Status: OK" in r:
                verdict = "healthy"
            elif "FAILED" in r:
                verdict = "FAILING: copy your files off it now (“back up my files”)"
            else:
                verdict = "doesn't report its health"
            m = re.search(r"Percentage Used:\s+(\d+)%", r)
            wear = f", {m.group(1)}% worn" if m else ""
            res.append(f"{dev}: {verdict}{wear}")
        return _say(desk, line, "; ".join(res) + "." if res else "No drives found to check.")
    return False


# ------------------------------------------------------------------ web shortcuts

def sites(desk, line, low):
    m = re.search(r"track (?:my )?(?:parcel|package|order|delivery|shipment)(?: (?:number )?(?P<n>[A-Za-z0-9]{8,}))?|where is my (?:parcel|package|order)|"
                  r"(?:check )?(?:my )?order status", low)
    if m:
        n = m.group("n") if m.groupdict().get("n") else None
        if n:
            _open(desk, f"https://parcelsapp.com/en/tracking/{n.upper()}")
            return _say(desk, line, f"Tracking {n.upper()} in the browser.")
        _open(desk, "https://parcelsapp.com/en")
        return _say(desk, line, "Opened a parcel tracker: paste the tracking number from your order email (or say “track my parcel” and the number). "
                                "For an Amazon order: “open amazon orders”.")
    if re.search(r"typing (?:practice|tutor|lessons?|test)|teach me to type|learn to type", low):
        _open(desk, "https://www.keybr.com")
        return _say(desk, line, "Opened keybr.com: it teaches touch typing with short lessons that adapt to the keys you miss.")
    m = re.search(r"learn (?P<l>spanish|french|german|italian|japanese|chinese|korean|portuguese|arabic|russian|hindi|dutch|english)", low)
    if m:
        _open(desk, "https://www.duolingo.com/register")
        return _say(desk, line, f"Opened Duolingo to learn {m.group('l').capitalize()} (free). Say “make me {m.group('l')} flashcards” for practice here too.")
    return False


# ------------------------------------------------------------------ the computer's name

def hostname(desk, line, low):
    m = re.search(r"(?:change|set|rename) (?:the |this |my )?computer(?:'?s)? name(?: to (?P<n>[\w-]+))?|(?:name|call|rename) (?:this|the|my) computer (?:to )?(?P<n2>[\w-]+)|"
                  r"(?:change|set) (?:the )?hostname(?: to (?P<n3>[\w-]+))?", low)
    if m:
        n = m.group("n") or m.group("n2") or m.group("n3")
        if not n:
            return _say(desk, line, f"It's called “{os.uname().nodename}” now. What should it be? Say “call this computer kitchen-pc” "
                                    "(letters, numbers and dashes).")
        n = re.sub(r"[^a-z0-9-]", "", n.lower())[:63].strip("-")
        if not n:
            return _say(desk, line, "Use letters, numbers and dashes for the name, for example \u201ckitchen-pc\u201d.")
        old = os.uname().nodename
        try:
            rootd_client.call("set_hostname", name=n)
            subprocess.run(["hostname", n], capture_output=True, timeout=5)
            hosts = open(_system.HOSTS).read()
            hosts = re.sub(rf"\b{re.escape(old)}\b", n, hosts)
            _write_hosts(hosts)
        except OSError as e:
            return _say(desk, line, f"Couldn't rename it: {_plain_err(e)}.")
        except rootd_client.RootdError as e:
            return _say(desk, line, f"Couldn't rename it: {_plain_err(e, bad=NAME_BAD)}.")
        return _say(desk, line, f"This computer is now called “{n}” (it was “{old}”). Other devices on the network see the new name after a restart.")
    if re.search(r"what(?:'?s| is) (?:the |this |my )?computer(?:'?s)? name|what(?:'?s| is) (?:the |my )?hostname|^hostname$", low):
        return _say(desk, line, f"This computer is called “{os.uname().nodename}”. Say “call this computer …” to change it.")
    return False


# ------------------------------------------------------------------ focus mode

FOCUS_SITES = ["youtube.com", "www.youtube.com", "m.youtube.com", "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
               "tiktok.com", "www.tiktok.com", "twitter.com", "x.com", "www.reddit.com", "reddit.com", "netflix.com", "www.netflix.com"]
_MARK = "# llmos focus mode"
_POLICY = "/usr/lib/firefox/distribution/policies.json"


def _focus_state():
    try:
        with open(config.data("focus.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _hosts_block(focus_sites):
    """Write what is blocked now: the focus period's sites plus the owner's own blocks ("block reddit", "block every
    website except wikipedia"); to /etc/hosts (every program) and Firefox's own filter (it may look names up itself)."""
    wb = config.settings.get("web_block") or {}
    blocked = sorted(set(list(focus_sites) + list(wb.get("block") or [])))
    allow_only = list(wb.get("allow_only") or [])
    host_sites = [h for s in blocked for h in (s, "www." + s) if not s.startswith("www.")] + [s for s in blocked if s.startswith("www.")]
    try:
        lines = [ln for ln in open(_system.HOSTS).read().splitlines() if _MARK not in ln]
        lines += [f"0.0.0.0 {s} {_MARK}" for s in dict.fromkeys(host_sites) if _hosts_name_ok(s)]
        _write_hosts("\n".join(lines) + "\n")
    except OSError:
        pass
    try:
        pol = json.load(open(_POLICY))
        if allow_only:
            pol["policies"]["WebsiteFilter"] = {"Block": ["<all_urls>"],
                                                "Exceptions": [f"*://{s}/*" for s in allow_only] + [f"*://*.{s}/*" for s in allow_only]}
        elif blocked:
            pol["policies"]["WebsiteFilter"] = {"Block": [f"*://{s}/*" for s in blocked] + [f"*://*.{s}/*" for s in blocked if not s.startswith("www.")]}
        else:
            pol["policies"].pop("WebsiteFilter", None)
        with open(_POLICY, "w") as f:
            json.dump(pol, f, indent=2)
    except (OSError, ValueError, KeyError):
        pass


def _site(word):
    w = word.strip().lower().strip(".,")
    w = re.sub(r"^(?:https?://)?(?:www\.)?", "", w).split("/")[0]
    known = {"youtube": "youtube.com", "facebook": "facebook.com", "instagram": "instagram.com", "tiktok": "tiktok.com", "reddit": "reddit.com",
             "twitter": "twitter.com", "x": "x.com", "netflix": "netflix.com", "wikipedia": "wikipedia.org", "google": "google.com",
             "amazon": "amazon.com", "ebay": "ebay.com", "twitch": "twitch.tv", "discord": "discord.com", "news": "news.google.com"}
    return known.get(w, w if "." in w else w + ".com")


def _firefox_note():
    return " (Firefox applies it fully the next time it starts)" if subprocess.run(["pgrep", "-x", "firefox"], capture_output=True).returncode == 0 else ""


def web_block(desk, line, low):
    m = re.search(r"^(?:please\s+)?(?:block|stop|ban)\s+(?:every|all(?: the)?|any)\s+(?:website|site|web ?page)s?\s+(?:except|but|apart from|other than)\s+(?P<keep>.+)$", low)
    if m:
        keep = [_site(w) for w in re.split(r",|\band\b|\bor\b", m.group("keep")) if w.strip()]
        config.settings.set("web_block", {"allow_only": keep, "block": []})
        _hosts_block(_focus_sites())
        return _say(desk, line, f"Only {', '.join(keep)} open in the browser now; every other website is blocked{_firefox_note()}. "
                                "Say \u201cunblock all websites\u201d to undo.")
    m = re.search(r"^(?:please\s+)?(?:unblock|allow)\s+(?:all|every|the)?\s*(?:websites?|sites?|everything|the internet|web)$|^(?:remove|clear|stop) (?:all )?(?:the )?(?:website )?blocks?(?:ing)?$", low)
    if m:
        config.settings.set("web_block", {})
        _hosts_block(_focus_sites())
        return _say(desk, line, "All websites open again" + (" (focus mode is still on until it ends)" if _focus_sites() else "") + ".")
    m = re.search(r"^(?:please\s+)?unblock\s+(?P<s>[\w., -]+)$", low)
    if m:
        wb = dict(config.settings.get("web_block") or {})
        drop = {_site(w) for w in re.split(r",|\band\b", m.group("s")) if w.strip()}
        wb["block"] = [x for x in wb.get("block") or [] if x not in drop]
        config.settings.set("web_block", wb)
        _hosts_block(_focus_sites())
        return _say(desk, line, f"{', '.join(sorted(drop))} open again.")
    m = re.search(r"^(?:please\s+)?block\s+(?P<s>(?!every|all\b)(?:https?://|[\w.,/ -])+?)(?:\s+(?:forever|for good|permanently|from now on))?$", low)
    if m and not re.search(r"\b(?:for|until|while)\b", m.group("s")) \
            and all(_one_token(w) for w in re.split(r",|\band\b", m.group("s")) if w.strip()):
        wb = dict(config.settings.get("web_block") or {})
        typed = [_typed_site(w) for w in re.split(r",|\band\b", m.group("s")) if w.strip()]
        add = [s for s in typed if _hosts_name_ok(s)]          # only names that will really be written
        skipped = [s for s in typed if not _hosts_name_ok(s)]
        if add:
            wb["block"] = sorted(set((wb.get("block") or []) + add))
            wb.pop("allow_only", None)
            config.settings.set("web_block", wb)
            _hosts_block(_focus_sites())
            reply = f"Blocked {', '.join(add)}{_firefox_note()}. Say \u201cunblock {add[0].split('.')[0]}\u201d to undo."
        else:
            reply = "Nothing was blocked."
        if skipped:
            reply += f" I couldn't block {', '.join(skipped)}: they aren't website names."
        return _say(desk, line, reply)
    return False


def _one_token(word):
    """A web_block target is one token: no space inside (so "port 8080" or "the camera" falls through) and no colon
    outside a leading http:// or https:// (so "10.0.0.1:22" falls through)."""
    w = word.strip()
    return " " not in w and ":" not in re.sub(r"^https?://", "", w)


def _typed_site(word):
    """A site as the owner types it: a leading http:// or https:// and any path are dropped, a www. is kept;
    a plain word ("reddit") becomes its site name as _site() gives it."""
    w = word.strip().lower().strip(".,")
    w = re.sub(r"^https?://", "", w).split("/")[0]
    return w if "." in w else _site(w)


def _focus_sites():
    st = _focus_state()
    return st.get("sites", []) if st else []


def focus_end(desk=None, quiet=False):
    st = _focus_state()
    _hosts_block([])
    try:
        os.remove(config.data("focus.json"))
    except OSError:
        pass
    if st:
        config.settings.set("do_not_disturb", bool(st.get("dnd_before")))
    if desk and st and not quiet:
        desk.emit({"t": "toast", "text": "Focus time is over: sites and notifications are back.", "long": True})
    return st


def _end_later(desk, until):
    """End this focus period when its time is up (a later one, started meanwhile, is left alone)."""
    def done():
        st = _focus_state()
        if st and abs(st["until"] - until) < 1:
            focus_end(desk)
    t = threading.Timer(max(0.0, until - time.time()), done)
    t.daemon = True
    t.start()


def focus_resume(desk):
    """At start: a focus period still running carries on; one that ended while the computer was off is undone."""
    st = _focus_state()
    if not st:
        return
    left = st["until"] - time.time()
    if left <= 0:
        focus_end(desk, quiet=True)
    else:
        _end_later(desk, st["until"])


def focus(desk, line, low):
    if re.search(r"(?:stop|end|cancel|turn off|exit|leave) (?:the )?focus(?: mode)?|unblock (?:youtube|sites|websites|everything)", low):
        st = focus_end()
        return _say(desk, line, "Focus mode is off: sites and notifications are back." if st else "Focus mode wasn't on.")
    m = re.search(r"focus mode|block (?:youtube|facebook|instagram|tiktok|reddit|twitter|social media|distracting (?:sites|websites)|websites|sites)", low)
    if not m or ("focus" not in low and not re.search(r"\b(?:for|while|until|during)\b", low)):
        return False                      # "block reddit" with no time: a lasting block (web_block), not a focus period
    mins = 60
    d = re.search(r"(?:for|during) (?:an? |the next )?(?P<n>\d+(?:\.\d+)?|half an|an|one|two|three|four)?\s*(?P<u>hours?|hrs?|minutes?|mins?)", low)
    if d:
        n = {"half an": 0.5, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, None: 1}.get(d.group("n"), None)
        n = float(d.group("n")) if n is None else n
        mins = n * 60 if d.group("u").startswith("h") else n
    elif "while i study" in low or "while i work" in low:
        mins = 120
    mins = max(5, min(int(mins), 12 * 60))
    named = re.findall(r"\b(youtube|facebook|instagram|tiktok|reddit|twitter|netflix)\b", low)
    sites = [s for s in FOCUS_SITES if any(n in s for n in named)] if named and "social" not in low else FOCUS_SITES
    if "x.com" not in sites and "twitter" in named:
        sites.append("x.com")
    before = _focus_state()
    dnd_before = before["dnd_before"] if before else bool(config.settings.get("do_not_disturb"))
    until = time.time() + mins * 60
    with open(config.data("focus.json"), "w", encoding="utf-8") as f:
        json.dump({"until": until, "sites": sites, "dnd_before": dnd_before}, f)
    _hosts_block(sites)
    config.settings.set("do_not_disturb", True)
    _end_later(desk, until)
    nice = {"youtube": "YouTube", "tiktok": "TikTok", "x": "X (Twitter)", "twitter": "X (Twitter)"}
    names = sorted({nice.get(k, k.capitalize()) for k in (re.sub(r"^(?:www\.|m\.)", "", s).split(".")[0] for s in sites)})
    ff = " (Firefox applies it fully the next time it starts)" if subprocess.run(["pgrep", "-x", "firefox"], capture_output=True).returncode == 0 else ""
    return _say(desk, line, f"Focus mode until {time.strftime('%H:%M', time.localtime(until))}: {', '.join(names)} blocked{ff}, and notifications are quiet. "
                            "Say “end focus mode” to stop early.")


# ------------------------------------------------------------------ settings in plain words

def access(desk, line, low):
    if re.search(r"double[- ]?clicks? (?:is |are )?(?:hard|difficult|too fast|tricky)|hands? (?:shake|shaking)|tremor|slow(?:er)? double[- ]?click|double[- ]?click (?:slower|speed)", low):
        inp = dict(config.settings.get("input", {}) or {})
        inp.update(double_click_ms=900, repeat_delay=1000, repeat_rate=15)
        config.settings.set("input", inp)
        desk.apply_input()
        return _say(desk, line, "Done: a double-click now counts even when the two clicks are almost a second apart, and a held key waits a "
                                "second before it repeats (no accidental \u201caaaa\u201d). Remember you can also say what you want instead of "
                                "clicking. Say \u201cnormal double click\u201d to undo.")
    if re.search(r"normal double[- ]?click|double[- ]?click (?:back to )?normal|faster double[- ]?click", low):
        inp = dict(config.settings.get("input", {}) or {})
        inp.update(double_click_ms=500, repeat_delay=600, repeat_rate=25)
        config.settings.set("input", inp)
        desk.apply_input()
        return _say(desk, line, "Double-click and key repeat are back to normal.")
    m = re.search(r"(?:mouse |the )?(?:pointer|cursor|arrow)\b.*\b(?P<s>huge|giant|enormous|massive|bigger|big|larger|large|smaller|small|tiny|normal|default)\b|"
                  r"(?P<s2>bigger|larger|smaller|huge|giant|normal) (?:mouse )?(?:pointer|cursor)", low)
    if m:
        w = m.group("s") or m.group("s2")
        size = {"huge": 96, "giant": 96, "enormous": 128, "massive": 128, "bigger": 48, "big": 48, "larger": 48, "large": 48,
                "smaller": 16, "small": 16, "tiny": 16, "normal": 24, "default": 24}[w]
        inp = dict(config.settings.get("input", {}) or {})
        inp["cursor_size"] = size
        config.settings.set("input", inp)
        desk.apply_input()
        try:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(size)], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
        return _say(desk, line, f"Pointer size set to {size} (normal is 24). Programs opened from now on use it; the desk's own pointer "
                                "changes the next time the computer starts.")
    if re.search(r"sticky keys", low):
        return _say(desk, line, "Sticky keys (pressing Ctrl, then C, instead of both together) aren't available on LLM OS yet. What helps now: say what "
                                "you want instead of using a shortcut (\u201ccopy this\u201d, \u201cswitch to the browser\u201d), or \u201cmy hands shake\u201d "
                                "for a slower double-click and key repeat.")
    return False


def sounds(desk, line, low):
    if not re.search(r"sounds?|chime", low):
        return False
    off = re.search(r"\b(?:off|no|stop|disable|mute|silence|without|quiet)\b", low)
    on = re.search(r"\b(?:on|enable|back|unmute)\b", low) and not off
    startup = re.search(r"startup|start-up|boot", low)
    if off:
        config.settings.set("chime", False)
        return _say(desk, line, ("LLM OS has no startup sound, and no click sounds. " if startup or "click" in low else "") +
                    "The one sound it makes, the chime for timers and finished work, is now off (timers still show on the screen). "
                    "Say \u201cturn the chime on\u201d to bring it back.")
    if on:
        config.settings.set("chime", True)
        return _say(desk, line, "The chime is on: it sounds when a timer rings or background work finishes.")
    if re.search(r"change|different|pick|choose", low):
        return _say(desk, line, "LLM OS has one sound, a short chime for timers and finished work; it can be on or off (\u201cturn off the chime\u201d) "
                                "but not swapped yet. Programs' own notification sounds are set inside each program.")
    return False


def autostart(desk, line, low):
    lst = [a for a in (config.settings.get("autostart") or []) if a]
    m = re.search(r"(?:don'?t|do not|stop|no longer) (?:start|open|launch|run)(?:ing)? (?P<a>.+?) (?:automatically|when i (?:log ?in|sign in|start)|at (?:start ?up|login))"
                  r"|(?:stop|prevent|keep) (?P<a2>.+?) from (?:starting|opening|launching) (?:automatically|at (?:start ?up|login)|when i log ?in)"
                  r"|remove (?P<a3>.+?) from (?:startup|autostart)", low)
    if m:
        a = (m.group("a") or m.group("a2") or m.group("a3")).strip()
        a = re.sub(r"^(?:the|my) ", "", a)
        keep = [x for x in lst if x.lower() != a.lower()]
        config.settings.set("autostart", keep)
        if len(keep) == len(lst):
            return _say(desk, line, f"{a.capitalize()} wasn't set to start by itself" + (f"; these are: {', '.join(lst)}." if lst else ". Nothing is."))
        return _say(desk, line, f"{a.capitalize()} won't start by itself any more.")
    m = re.search(r"(?:start|open|launch|run) (?P<a>.+?) (?:automatically )?(?:when i (?:log ?in|sign in|unlock|start (?:up|the computer))|at (?:start ?up|login)|"
                  r"with the computer|every time i (?:log ?in|start))|(?:make|have|let) (?P<a2>.+?) (?:start|open) (?:automatically|by itself|at (?:start ?up|login))|"
                  r"add (?P<a3>.+?) to (?:startup|autostart)", low)
    if m:
        a = re.sub(r"^(?:the|my) ", "", (m.group("a") or m.group("a2") or m.group("a3")).strip())
        if a in ("x", "it", "this", "that", "something", "a program", "an app", "programs", "apps"):
            return _say(desk, line, "Which program? Say, for example, \u201cstart Firefox when I log in\u201d." +
                        (f" Starting by itself now: {', '.join(lst)}." if lst else ""))
        if a.lower() not in [x.lower() for x in lst]:
            lst.append(a)
            config.settings.set("autostart", lst)
        return _say(desk, line, f"{a.capitalize()} will open by itself each time you unlock the desk. Say \u201cdon't start {a} automatically\u201d to undo.")
    if re.search(r"what (?:starts|opens|runs|launches)(?: by itself)? (?:automatically|when i log ?in|at start ?up)|startup (?:programs|apps)|autostart", low):
        return _say(desk, line, ("Starting by itself: " + ", ".join(lst) + ".") if lst else "Nothing starts by itself. Say \u201cstart <program> when I log in\u201d to add one.")
    return False


NET_DIR = "/sys/class/net"
VPN_WAIT = 6.0


def _vpn_tun_names():
    """The tun/tap interface names present now (empty when the list can't be read)."""
    try:
        return {n for n in os.listdir(NET_DIR) if n.startswith(("tun", "tap"))}
    except Exception:
        return set()


def _vpn_tun_up(before=frozenset()):
    """True when a tun/tap interface exists that was not there before openvpn started."""
    return bool(_vpn_tun_names() - set(before))


def _vpn_alive():
    """True/False from pgrep; None when the check itself fails."""
    try:
        return subprocess.run(["pgrep", "-x", "openvpn"], capture_output=True).returncode == 0
    except Exception:
        return None


def _vpn_wait(before=frozenset()):
    """Wait up to 6 s for the tunnel. True as soon as a tun/tap interface new since `before` (the names taken before
    openvpn started) exists and openvpn runs; False when openvpn is gone on two polls in a row (after 0.5 s); at 6 s,
    True exactly when openvpn still runs (the old rule)."""
    start = time.monotonic()
    gone = 0
    while True:
        t = time.monotonic() - start
        alive = _vpn_alive()
        if alive and _vpn_tun_up(before):
            return True
        if alive is False and t >= 0.5:
            gone += 1
            if gone >= 2:
                return False
        else:
            gone = 0
        if t >= VPN_WAIT:
            return alive is True
        time.sleep(0.25)


def vpn(desk, line, low):
    if not re.search(r"vpn|wireguard|openvpn|proxy", low):
        return False
    from . import tools
    if re.search(r"(?:disconnect|turn off|stop|end|close)(?: (?:the|my|from))? (?:work )?vpn|vpn off", low):
        n = 0
        for conf in glob.glob("/etc/wireguard/*.conf"):
            if subprocess.run(["wg-quick", "down", conf], capture_output=True, timeout=30).returncode == 0:
                n += 1
        if subprocess.run(["pkill", "-x", "openvpn"], capture_output=True).returncode == 0:
            n += 1
        return _say(desk, line, "The VPN is off." if n else "No VPN was on.")
    if re.match(r"(?:why|what|how (?:does|do|is|are)|is |are |should|do i need|does|can you explain|explain)", low) or \
            not re.search(r"(?:connect|set ?up|use|turn on|start|join|log ?in|sign in|enable|configure|add)\b", low):
        return False                      # a question about VPNs is answered like any question
    if "proxy" in low and "vpn" not in low:
        return _say(desk, line, "A proxy is set in the browser: Firefox → Settings → Network Settings → Settings… (manual proxy). For everything on this "
                                "computer to go through a private route, say \u201cturn on Tor\u201d, or connect a VPN from its file (\u201cconnect to my vpn\u201d).")
    f = None
    for d in ("~/Downloads", "~/Documents", "~/Desktop", "~"):
        for c in sorted(glob.glob(os.path.join(tools._path(d), "*.conf")) + glob.glob(os.path.join(tools._path(d), "*.ovpn")), key=os.path.getmtime, reverse=True):
            try:
                body = open(c, errors="replace").read(20000)
            except OSError:
                continue
            if ("[Interface]" in body and "PrivateKey" in body) or (c.endswith(".ovpn") and re.search(r"^\s*remote\s", body, re.M)):
                f = c
                break
        if f:
            break
    if not f:
        return _say(desk, line, "Put the VPN's file here first: your work or VPN company gives you a WireGuard file (.conf) or an OpenVPN file (.ovpn). "
                                "Save it in Downloads (from the email, or a USB stick) and say \u201cconnect to my vpn\u201d again. "
                                "Apps-only VPNs (some paid services) offer such a file on their website under \u201cmanual setup\u201d or \u201cLinux\u201d.")
    kind = "openvpn" if f.endswith(".ovpn") else "wireguard"
    need = "openvpn" if kind == "openvpn" else "wireguard-tools"
    if not shutil.which("openvpn" if kind == "openvpn" else "wg-quick"):
        desk.emit({"t": "toast", "text": "Getting the VPN program…", "sticky": "vpn"})
        rc, out, err = _system.apk_add([need], quiet=True, timeout=600)
        desk.emit({"t": "toast", "text": "", "sticky": "vpn"})
        if rc != 0:
            return _say(desk, line, f"Couldn't get the VPN program ({need}): {(err or out).strip()[-150:]}")
    if kind == "wireguard":
        os.makedirs("/etc/wireguard", exist_ok=True)
        name = re.sub(r"[^a-zA-Z0-9_=+.-]", "", os.path.splitext(os.path.basename(f))[0])[:15] or "vpn"
        dest = f"/etc/wireguard/{name}.conf"
        shutil.copy(f, dest)
        os.chmod(dest, 0o600)
        r = subprocess.run(["wg-quick", "up", dest], capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
        err = (r.stderr or "").strip().splitlines()[-1:] if not ok else []
    else:
        body = open(f, errors="replace").read()
        if re.search(r"^\s*auth-user-pass\s*$", body, re.M):
            return _say(desk, line, f"{os.path.basename(f)} needs a user name and password, which isn't supported here yet. If your VPN offers a "
                                    "WireGuard file, that one works.")
        before = _vpn_tun_names()
        r = subprocess.run(["openvpn", "--config", f, "--daemon", "llmos-vpn"], capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0 and _vpn_wait(before)
        err = [(r.stderr or r.stdout).strip()[-150:]] if not ok else []
    if not ok:
        why = ' '.join(err) or "the other end didn't answer"
        return _say(desk, line, f"The VPN from {os.path.basename(f)} didn't connect: {why}.")
    if config.settings.get("internet") == "no":
        note = " Note: the internet is switched off in settings, so nothing goes out until you turn it on."
    else:
        note = ""
    return _say(desk, line, f"Connected to the VPN from {os.path.basename(f)}: the internet now goes through it. Say \u201cdisconnect the vpn\u201d to stop.{note}")


def discs(desk, line, low):
    if not re.search(r"\b(?:cd|dvd|blu-?ray|disc)s?\b", low) or not re.search(r"\b(?:play|rip|copy|import|burn|watch|listen|drive|read|open)\b", low) \
            or re.match(r"cd\s+[~/.]", low):
        return False
    drives = glob.glob("/dev/sr[0-9]")
    if not drives:
        return _say(desk, line, "This computer has no disc drive. A USB DVD drive works once plugged in; then ask again.")
    if re.search(r"play", low):
        subprocess.Popen(["mpv", "--fs", ("dvd://" if "dvd" in low else "cdda://"), f"--{'dvd' if 'dvd' in low else 'cdda'}-device={drives[0]}"],
                         env=desk._child_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return _say(desk, line, "Playing the disc. (Most shop-bought DVDs are copy-protected; if it won't play, that's why.)")
    if re.search(r"rip|copy|import", low):
        if not shutil.which("abcde"):
            return _say(desk, line, "Say \u201cinstall abcde\u201d to get the CD copier, then ask again: it saves each song to Music.")
        subprocess.Popen(["foot", "abcde", "-N", "-o", "mp3", "-d", drives[0]], cwd=os.path.join(config.home(), "Music"), env=desk._child_env(),
                         start_new_session=True)
        return _say(desk, line, "Copying the CD into Music; the terminal window shows each song as it's done.")
    return False


HOWTO = [
    (r"(?:play|watch|show|put|stream|mirror|send)\b.*\b(?:on|to) (?:my |the )?tv|chromecast|cast (?:to|this|my)|airplay",
     "With a cable: plug the TV into the computer's HDMI port, then say \u201cmirror the displays\u201d (or \u201cuse only the tv\u201d). "
     "Without a cable: YouTube and Netflix have a Cast button in their pages in Chrome-based browsers, but not in Firefox; on the TV's YouTube app you can "
     "choose \u201cLink with TV code\u201d and enter the code at youtube.com/pair. Casting your whole screen to a Chromecast isn't available yet."),
    (r"colou?r ?blind|colou?r filter|deuteranop|protanop|tritanop",
     "A colour-blind filter for the whole screen isn't available yet. What helps now: \u201chigh contrast\u201d (strong, clearly different colours), "
     "\u201cbigger text\u201d, and in pictures I can describe colours for you: ask \u201cwhat colour is this\u201d with a screenshot."),
    (r"(?:change|set|update|add|pick) (?:my |a )?(?:profile (?:picture|photo|pic)|avatar|account (?:picture|photo))|profile (?:picture|photo|pic)",
     "LLM OS doesn't use a profile picture: there's no account list to show it in. The lock screen shows your wallpaper (\u201cchange the wallpaper\u201d), "
     "and I call you by your name (\u201ccall me Sam\u201d)."),
    (r"(?:set|change|turn on|use|add) (?:a |the |my )?screen ?saver|screen ?saver|(?:show|display) (?:a |the )?clock when (?:i'?m )?idle",
     "There's no screensaver: when you leave it alone the screen turns off after a while, which saves power and the screen. "
     "Say \u201cturn the screen off after 10 minutes\u201d (or \u201cnever\u201d) to choose when."),
    (r"\.exe\b|windows (?:program|app|software|game)s?|run (?:a )?windows|\.deb\b|appimage",
     "Windows programs (.exe) and other Linux systems' packages (.deb, AppImage) are made for different systems and usually don't run here. "
     "Most programs have a version for this one: say \u201cinstall\u201d and the program's name (\u201cinstall vlc\u201d, \u201cinstall spotify\u201d) "
     "and I'll find it, from Alpine or Flathub. On a PC with an Intel or AMD processor, \u201cinstall wine\u201d lets some Windows programs run too."),
    (r"(?:move|put|send|drag) (?:this|it|that|the \w+|the window)(?: window)? (?:to|onto|on) (?:my |the )?(?:other|second|external|left|right) (?:monitor|screen|display)",
     "Click the window, then press Super+Shift+Right (or Left): it jumps to the other screen. You can also drag it there by its title bar."),
    (r"new (?:workspace|desktop|virtual desktop)|(?:add|make|create) (?:a |another )?(?:workspace|virtual desktop)",
     "There are four workspaces ready: Super+1 to 4 jumps to one (or “go to workspace 2”), Ctrl+Alt+Left/Right moves between them, and "
     "Ctrl+Alt+Shift+Left/Right takes the window you're in along."),
    (r"back ?up (?:my (?:files|stuff|photos|computer) )?(?:to|in|on(?:to)?) (?:the )?(?:cloud|google drive|onedrive|dropbox|icloud)|cloud back ?up",
     "Simplest: open your cloud's website (“open google drive”, “open onedrive”, “open dropbox”) and drag your Documents and "
     "Pictures folders into it. Automatic cloud backup (rclone) isn't set up here yet; for an automatic backup, plug in a USB drive and say "
     "“back up my files every week”."),
    (r"(?:move|transfer|copy|bring) (?:all )?(?:my )?(?:stuff|files|things|everything|data) (?:to|onto|over to) (?:a |my |the )?(?:new|other|another) (?:computer|pc|laptop)|"
     "(?:export|save) my settings and apps",
     "Plug in a USB drive and say “back up my files”: it copies your Documents, Pictures, Music, Videos, Desktop, Downloads and the apps you made. "
     "On the new computer (with LLM OS), plug the drive in and say “restore my files from backup”. Settings like your name and look take a "
     "sentence each to set again (“call me …”, “dark mode”)."),
    (r"snapshot|roll ?back (?:the )?(?:system|computer|changes|update)|restore point|undo (?:the |that )?(?:update|change to the system)",
     "System snapshots aren't available yet. What you have: deleted files wait in the trash (“show the trash”), “back up my files” keeps a "
     "copy of your files on a USB drive, and “what did you do” lists every change I made, so any of them can be undone by asking."),
    (r"kids? mode|child mode|parental controls?|only let (?:my )?(?:kid|child|son|daughter)s? use|(?:limit|restrict) (?:what )?(?:my )?(?:kid|child)",
     "There's no kids mode yet (no separate accounts to put limits on). What works now: “focus mode for an hour” blocks YouTube and "
     "social sites for a set time, “hands-on” makes me ask before every change, and “make a game for my kid” makes them something to do."),
    (r"(?:is there|what'?s) (?:a |the )?(?:keyboard )?shortcut (?:for|to do) (?:this|that|it)",
     "Main shortcuts: Super+Space talks to me, Alt+Tab switches windows, Super+Up/Left/Right sizes a window, Super+L locks, Super+E files, "
     "Ctrl+Alt+T terminal, Super+V clipboard history, Print takes a screenshot, Super+T keeps a window on top. Tell me what you're doing and I'll name the one for it."),
    (r"(?:game ?)?controller|gamepad|joystick",
     "Plug it in with its USB cable and it works straight away in games and the browser. Wireless (Xbox, PlayStation, Switch Pro): hold its pairing "
     "button until the light flashes, then say “bluetooth search” and press Connect next to it. Test it at gamepadtester.com."),
    (r"phone'?s? (?:internet|data|hotspot)|tether|hotspot",
     "On the phone, turn on its hotspot (iPhone: Settings → Personal Hotspot; Android: Settings → Network → Hotspot), then say “show wifi networks” "
     "and pick the phone's name. Or connect an Android phone with a USB cable and turn on “USB tethering” on it."),
    (r"drawing tablet|wacom|pen tablet",
     "Plug it in: it works as a pen straight away, with pressure in drawing programs. Say “install krita” for a full painting program; "
     "“make a sketch app” makes a simple one here."),
    (r"touch ?screen",
     "A touchscreen works without setup: tap to click, drag to scroll. If it doesn't respond, restart the computer with it plugged in (an external one "
     "needs its USB cable as well as the video cable). If touches land on the wrong screen with two screens, say “use only the main display”."),
    (r"(?:keep|stay|put|make) (?:this |it |that |the \w+ )?(?:window )?(?:always )?on top|always on top|picture[- ]in[- ]picture|\bpip\b",
     "Click the window, then press Super+T: it stays above the others (Super+T again to undo). For a video in Firefox, hover over it and click the "
     "picture-in-picture button: it floats in a small window that stays on top while you work."),
]


def privacy(desk, line, low):
    if re.search(r"encrypt (?:my |the |this )?(?:disk|drive|computer|laptop|files|data|hard ?drive|ssd)|(?:laptop|computer|pc) (?:gets |is |was )?(?:stolen|lost)|"
                 r"is (?:my )?(?:disk|data|computer) encrypted|disk encryption", low):
        from . import vault
        if config.settings.get("vault"):
            return _say(desk, line, "Your files are already encrypted: everything in your home folder (files, apps, conversations, settings for "
                                    "programs) lives in a vault locked with your passphrase (LUKS, AES-256). If the computer is stolen, a thief "
                                    "sees only scrambled data unless they know the passphrase. Lock it when you step away (Super+L) so it's closed "
                                    "even while the computer is on. The system itself (programs, the AI model) isn't encrypted; it holds nothing of yours.")
        return _say(desk, line, "Your files are NOT encrypted yet: anyone with the disk could read them. Say “set a passphrase” and I'll move "
                                "them into an encrypted vault (LUKS, AES-256) that opens only with that passphrase.")
    if re.search(r"(?:store|save|keep|manage|remember|organi[sz]e) (?:all )?(?:my |the )?passwords|password (?:manager|keeper|vault|safe)|where (?:are|do i find) my (?:saved )?passwords", low):
        return _say(desk, line, "Firefox keeps your passwords: when you sign in somewhere it offers to save it, and fills it in next time. See or "
                                "change them at about:logins (they're inside your encrypted vault). For a separate password manager say "
                                "\u201cinstall keepassxc\u201d (offline) or use Bitwarden's add-on in Firefox (syncs with your phone).")
    if re.search(r"guest (?:mode|account|session|user)|someone else (?:is using|uses|wants to use|will use) (?:my |the |this )?computer|let (?:someone|a friend|my \w+) use (?:my |the |this )?computer", low):
        return _say(desk, line, "There's no guest mode yet: whoever uses the computer uses it as you, with your files. For a short while: open Firefox "
                                "in a private window (Ctrl+Shift+P) for them, and say “hands-on” so I ask before every change. "
                                "Lock it afterwards (Super+L) and nothing of theirs stays in the browser.")
    return False


def system_more(desk, line, low):
    if re.search(r"(?:show|see|check|read|open) (?:me )?(?:the )?(?:system|error|kernel|computer'?s?) logs?|^(?:show|see|check) (?:me )?(?:the )?logs?$|journalctl|dmesg|why did (?:that|the|a) (?:service|program|thing) (?:fail|crash|stop)", low):
        try:
            k = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            k = []
        bad = [ln for ln in k if re.search(r"error|fail|warn|segfault|oom|killed|i/o", ln, re.I)][-12:]
        try:
            st = subprocess.run(["rc-status", "-a"], capture_output=True, text=True, timeout=10).stdout
            crashed = sorted(set(re.findall(r"^\s*(\S+)\s+\[\s*crashed\s*\]", st, re.M)))
        except (OSError, subprocess.SubprocessError):
            crashed = []
        rows = [{"title": ln[:160]} for ln in (bad or k[-12:])]
        desk.open_window({"id": "logs", "replace": True, "title": "System log", "size": "l", "blocks": [
            {"type": "text", "text": ("Services that stopped unexpectedly: " + ", ".join(crashed) + ". Say “restart " + crashed[0] + "” to try again.")
                                     if crashed else "Every system service is running normally."},
            {"type": "text", "text": "Recent problems the system noted:" if bad else "Nothing went wrong recently; the latest messages:", "dim": True},
            {"type": "list", "items": rows}]})
        return _say(desk, line, (f"{len(crashed)} service(s) stopped unexpectedly: {', '.join(crashed)}. " if crashed else "All services are running. ") +
                    (f"{len(bad)} recent problem message(s) are in the window." if bad else "No recent problems in the system log."))
    m = re.search(r"(?:change|switch|set|make) (?:the |my )?(?:default )?shell (?:to )?(?P<s>zsh|bash|fish|sh|ash)|use (?P<s2>zsh|bash|fish) (?:as (?:my|the) (?:default )?shell|by default)", low)
    if m:
        sh = m.group("s") or m.group("s2")
        path = "/bin/sh" if sh == "sh" else shutil.which(sh)
        if not path:
            desk.emit({"t": "toast", "text": f"Getting {sh}…", "sticky": "sh"})
            rc, out, err = _system.apk_add([sh], quiet=True, timeout=600)
            desk.emit({"t": "toast", "text": "", "sticky": "sh"})
            path = shutil.which(sh)
            if not path:
                return _say(desk, line, f"Couldn't install {sh}: {(err or out).strip()[-150:]}")
        try:
            _system.set_shell("root", path)
        except OSError as e:
            return _say(desk, line, f"Couldn't change it: {_plain_err(e)}.")
        extra = " For oh-my-zsh, say “run the oh-my-zsh installer”." if sh == "zsh" else ""
        return _say(desk, line, f"New terminals now use {sh} ({path}).{extra}")
    return False


_OTA = re.compile(r"^(?:please )?(?P<stop>stop|turn off|no more|disable|forget) (?:getting |receiving |the )?updates? from (?:my|the|that) (?:own )?(?:computer|mac|pc|laptop|desktop|build machine)$|"
                  r"^(?:please )?(?:get|receive|take|accept|pull|turn on|enable) (?:the )?updates? (?:from|off) (?:my |the )?(?:own )?(?:(?P<addr>\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?|computer|mac|pc|laptop|desktop|build machine)(?: over (?:the )?(?:network|wi-?fi|air))?$|"
                  r"^(?:pair|connect|link) (?:this computer )?(?:with|to) my (?:computer|mac|pc|laptop) for updates$|"
                  r"^(?P<status>(?:where do|where are) (?:my |the )?updates (?:come|coming) from|updates? source|are updates from my (?:computer|mac) on)$")


_VERSION_Q = re.compile(r"^(?:(?:can|could) you\s+)?(?:what(?:'s| is)?|which|tell me(?: the)?|show(?: me)?(?: the)?|pull up(?: the)?|give me(?: the)?|check(?: the)?|find(?: the)?|get(?: the)?)\s+(?:my\s+|the\s+|this\s+)?(?:(?:llm ?os|os|system|software)\s+)?"
                        r"(?:version|build|release)(?:\s+(?:of\s+)?(?:llm ?os|the os|the system|this|this computer|this system))?"
                        r"(?:\s+(?:is\s+(?:this|it|installed|running)|am\s+i\s+(?:on|running|using)|do\s+i\s+have|are\s+(?:we|you)\s+(?:on|running)|is\s+(?:this\s+)?(?:computer|system)\s+on))?\s*\??$|"
                        r"^(?:llm ?os\s+)?(?:version|build)\??$")


_MODEL_Q = re.compile(r"^(?:which|what)\s+(?:ai\s+|language\s+|llm\s+)?model\s+(?:are\s+you|am\s+i|is\s+(?:this|it))(?:\s+(?:using|running|on))?(?:\s+(?:now|right now))?\??$|"
                      r"^(?:what|which)\s+(?:ai|llm|brain)\s+(?:are\s+you|is\s+this)(?:\s+using)?\??$|^what\s+are\s+you\s+running\s+on\??$")


def model_answer(desk, line, low):
    """'Which model are you using?': the chat model this computer runs (and the online one when it is used)."""
    if not _MODEL_Q.match(low):
        return False
    from . import models
    m = models.active()
    text = (f"I'm using {m['name']} on this computer ({m['size'] / 1e9:.1f} GB)." if m else "No on-device model is set up yet.")
    try:
        if config.settings.get("brain") not in (None, "local"):
            from . import llm
            label = llm.cloud_label()
            if label:
                text += f" Online: {label}, " + ("for everything." if config.settings.get("brain") == "cloud" else "when you allow it.")
    except Exception:
        pass
    desk.instant_reply(line, text + " Change it on the Models page.")
    return True


def version_answer(desk, line, low):
    """'What LLM OS version is this?': the build stamp, at once (no model), and where updates come from."""
    if not _VERSION_Q.match(low):
        return False
    from . import version_line
    text = f"This is {version_line()}."
    try:
        from . import ota
        o = ota.paired()
        if o:
            last = (ota._state().get("last") or {})
            text += f" Updates come from {o['name']}" + (f"; the last one ({last.get('version')}) was "
                                                        f"{'installed' if last.get('ok') else 'not kept'}." if last else ".")
    except Exception:
        pass
    desk.instant_reply(line, text)
    return True


def ota_updates(desk, line, low):
    """Updates pushed from the owner's own computer (ota.py): pair, unpair, status."""
    m = _OTA.match(low)
    if not m:
        return False
    from . import ota
    if m.group("status"):
        desk.instant_reply(line, ota.status_text())
        return True
    if m.group("stop"):
        o = ota.unpair()
        desk.instant_reply(line, f"Done. This computer no longer takes updates from {o['name']}." if o else
                           "Updates from your computer were already off.")
        return True
    if m.group("addr"):
        found = [s for s in [ota.hello(f"http://{m.group('addr')}:{ota.PORT}")] if s]
    else:
        if config.settings.get("internet", "yes") == "no":
            desk.instant_reply(line, "The internet is off, so I can't look around the network. Say “get updates "
                               "from” and your computer's address, like 192.168.1.20.")
            return True
        found = ota.find_servers()
    if not found:
        desk.instant_reply(line, "I didn't find an update server. On your computer, run "
                           "“tools/ota.py serve” in the LLM OS folder, then say this again.")
        return True
    if len(found) > 1:
        desk.instant_reply(line, "I found more than one: " + "; ".join(f"{s['name']} at {s['url'].split('//')[1]} "
                           f"(key {s['fp']})" for s in found) + ". Say “get updates from” and the address you want.")
        return True
    s = ota.pair(found[0])
    desk.instant_reply(line, f"Done. Updates now come from {s['name']} ({s['url'].split('//')[1]}). Its key is "
                       f"{s['fp']}; your computer shows the same. Each one installs on its own and is undone if the desk "
                       f"doesn't come back. Say “stop updates from my computer” to end it.")
    return True


def share_app(desk, line, low):
    m = re.search(r"(?:share|send|export|give|save) (?:the |my |this |that )?(?:app|game|tool)s?(?: (?:i|you|we) made| called (?P<n>[\w .-]+?))?"
                  r"(?: (?:with|to) .+| as a file| to (?:a )?file)?$", low)
    if not m:
        return False
    from . import apps
    a = apps.find(m.group("n")) if m.group("n") else None
    if not a:
        made = apps.installed()
        a = made[0] if made else None
    if not a:
        return _say(desk, line, "You haven't made an app yet: say “make me a …” first.")
    dest_dir = os.path.join(config.home(), "Desktop")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, re.sub(r'[/\\:*?"<>|]', "-", a["title"]).strip() + ".html")
    shutil.copy(a["file"], dest)
    return _say(desk, line, f"Saved “{a['title']}” as one file on your Desktop ({os.path.basename(dest)}). Send it like any file, by email or "
                            "a USB stick: your friend opens it in any web browser, on a computer or phone. (What they do in it stays on their device.)")


def howto(desk, line, low):
    for rx, text in HOWTO:
        if re.search(rx, low):
            return _say(desk, line, text)
    return False


# ------------------------------------------------------------------ the boring basics, exactly

_UNITS = {  # unit -> (kind, factor to the base unit)
    "mm": ("len", .001), "millimeter": ("len", .001), "millimetre": ("len", .001), "cm": ("len", .01), "centimeter": ("len", .01),
    "centimetre": ("len", .01), "m": ("len", 1), "meter": ("len", 1), "metre": ("len", 1), "km": ("len", 1000), "kilometer": ("len", 1000),
    "kilometre": ("len", 1000), "in": ("len", .0254), "inch": ("len", .0254), "inches": ("len", .0254), "ft": ("len", .3048),
    "foot": ("len", .3048), "feet": ("len", .3048), "yd": ("len", .9144), "yard": ("len", .9144), "mi": ("len", 1609.344),
    "mile": ("len", 1609.344),
    "mg": ("mass", .001), "milligram": ("mass", .001), "g": ("mass", 1), "gram": ("mass", 1), "kg": ("mass", 1000), "kilo": ("mass", 1000),
    "kilogram": ("mass", 1000), "oz": ("mass", 28.349523125), "ounce": ("mass", 28.349523125), "lb": ("mass", 453.59237),
    "lbs": ("mass", 453.59237), "pound": ("mass", 453.59237), "stone": ("mass", 6350.29318), "ton": ("mass", 907184.74),
    "tonne": ("mass", 1e6),
    "ml": ("vol", .001), "milliliter": ("vol", .001), "millilitre": ("vol", .001), "l": ("vol", 1), "liter": ("vol", 1), "litre": ("vol", 1),
    "tsp": ("vol", .00492892), "teaspoon": ("vol", .00492892), "tbsp": ("vol", .0147868), "tablespoon": ("vol", .0147868),
    "cup": ("vol", .236588), "pint": ("vol", .473176), "quart": ("vol", .946353), "gallon": ("vol", 3.78541),
    "fl oz": ("vol", .0295735), "fluid ounce": ("vol", .0295735),
    "mph": ("speed", .44704), "kph": ("speed", 1 / 3.6), "km/h": ("speed", 1 / 3.6), "kmh": ("speed", 1 / 3.6), "m/s": ("speed", 1),
    "knot": ("speed", .514444),
    "sq ft": ("area", .092903), "square foot": ("area", .092903), "square feet": ("area", .092903), "sq m": ("area", 1),
    "square meter": ("area", 1), "square metre": ("area", 1), "acre": ("area", 4046.86), "hectare": ("area", 10000),
    "byte": ("data", 1), "kb": ("data", 1e3), "mb": ("data", 1e6), "gb": ("data", 1e9), "tb": ("data", 1e12),
    "second": ("time", 1), "minute": ("time", 60), "hour": ("time", 3600), "day": ("time", 86400), "week": ("time", 604800),
    "year": ("time", 31557600),
}
_TEMP = {"c": "c", "celsius": "c", "centigrade": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}


def _unit(w):
    w = w.strip().lower().rstrip(".").replace("degrees ", "").replace("°", "")
    if w in _UNITS or w in _TEMP:
        return w
    if w.endswith("es") and w[:-2] in _UNITS:
        return w[:-2]
    if w.endswith("s") and w[:-1] in _UNITS:
        return w[:-1]
    return None


def _num(x):
    x = round(x, 4)
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}".rstrip("0").rstrip(".") if abs(x) >= 1 else f"{x:.4g}"


def _convert(n, a, b):
    a, b = _unit(a), _unit(b)
    if not a or not b:
        return None
    if a in _TEMP or b in _TEMP:
        ta, tb = _TEMP.get(a), _TEMP.get(b)
        if not ta or not tb:
            return None
        c = n if ta == "c" else (n - 32) * 5 / 9 if ta == "f" else n - 273.15
        return c if tb == "c" else c * 9 / 5 + 32 if tb == "f" else c + 273.15
    ka, kb = _UNITS[a], _UNITS[b]
    if ka[0] != kb[0]:
        return None
    return n * ka[1] / kb[1]


def quick(desk, line, low):
    q = low.strip().rstrip("?.!")
    q = re.sub(r"^(?:hey |ok |so |please |can you |could you |tell me |do you know )+", "", q)
    if re.fullmatch(r"thanks?(?: you| a lot| so much| very much)?|thank you(?: so much| very much)?|thx|thanks again|cheers|ta", q):
        return _say(desk, line, "You're welcome.")
    # a tip, a tax or a discount: "what's an 18 percent tip on 46 dollars"
    m = re.fullmatch(r"(?:what(?:'s| is) )?(?:an? )?(?P<p>\d+(?:\.\d+)?)\s*(?:%|percent)\s+(?P<k>tip|tax|discount|off|service(?: charge)?|gratuity)"
                     r"(?:\s+(?:on|of|for))?\s+\$?(?P<n>\d[\d,]*(?:\.\d+)?)(?:\s*(?:dollars|bucks|usd|euros?|pounds?))?", q)
    if m:
        p, n = float(m.group("p")), float(m.group("n").replace(",", ""))
        amount = n * p / 100
        cur = "$" if re.search(r"dollars|bucks|usd|\$", q) else ""
        f = (lambda v: f"{cur}{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{cur}{v:,.2f}")
        if m.group("k") in ("discount", "off"):
            return _say(desk, line, f"{p:g}% off {f(n)} saves {f(amount)}, so you pay {f(n - amount)}.")
        return _say(desk, line, f"A {p:g}% {m.group('k').split()[0]} on {f(n)} is {f(amount)}, for a total of {f(n + amount)}.")
    # percentages: "15% of 240", "what's 12.5 percent of 80" -> 36; "what percent is 45 of 240" -> 18.75%
    def _pct_num(s):
        return float(s.replace(",", ""))

    def _pct_fmt(v):
        v = round(v, 2)
        return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.2f}".rstrip("0").rstrip(".")
    m = re.fullmatch(r"(?:what(?:'s|s|\s+is)\s+|calculate\s+|work\s+out\s+)?(?P<p>\d+(?:\.\d+)?)\s*(?:%|percent|per\s*cent)\s+of\s+(?P<n>[\d,]+(?:\.\d+)?)\s*\??", q)
    if m:
        try:
            p, n = _pct_num(m.group("p")), _pct_num(m.group("n"))
            return _say(desk, line, f"{_pct_fmt(p)}% of {_pct_fmt(n)} is {_pct_fmt(n * p / 100)}.")
        except ValueError:
            return False
    m = re.fullmatch(r"what\s+percent(?:age)?\s+(?:of\s+(?P<b>[\d,.]+)\s+is\s+(?P<a>[\d,.]+)|is\s+(?P<a2>[\d,.]+)\s+of\s+(?P<b2>[\d,.]+))\s*\??", q)
    if m:
        try:
            a = _pct_num(m.group("a") or m.group("a2"))
            b = _pct_num(m.group("b") or m.group("b2"))
        except ValueError:
            return False
        if b == 0:
            return False
        return _say(desk, line, f"{_pct_fmt(a)} is {_pct_fmt(a / b * 100)}% of {_pct_fmt(b)}.")
    # unit conversions: "convert 5 miles to km","5 miles in km", "72 fahrenheit in celsius", "how many ounces in a pound"
    unit = r"(?:degrees\s+)?[a-z°/ ]{1,18}?"
    m = re.fullmatch(rf"(?:convert |what(?:'s| is) |how much is |how many )?(?P<n>-?[\d.,]+)\s*(?P<a>{unit})\s+(?:to|in|into|as)\s+(?P<b>{unit})", q) or \
        re.fullmatch(rf"how many (?P<b>{unit}) (?:are )?(?:in|per) (?:a |an |one )?(?P<a>{unit})", q)
    if m:
        n = float(m.group("n").replace(",", "")) if m.groupdict().get("n") else 1.0
        r = _convert(n, m.group("a"), m.group("b"))
        if r is not None:
            a, b = m.group("a").strip(), m.group("b").strip()
            sym = {"c": "°C", "f": "°F", "k": "K"}
            ta, tb = _TEMP.get(_unit(a) or ""), _TEMP.get(_unit(b) or "")
            if ta and tb:
                return _say(desk, line, f"{_num(n)}{sym[ta]} is {_num(r)}{sym[tb]}.")
            return _say(desk, line, f"{_num(n)} {a} is {_num(r)} {b}.")
    # splitting a bill
    m = re.fullmatch(r"(?:split|divide) \$?(?P<n>[\d.,]+)(?: dollars| euros| pounds| bucks)? (?:between|among|by|for) (?P<k>\d+|two|three|four|five|six|seven|eight)(?: people| ways| of us| friends)?", q)
    if m:
        k = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}.get(m.group("k")) or int(m.group("k"))
        n = float(m.group("n").replace(",", ""))
        return _say(desk, line, f"{_num(n / k)} each ({_num(n)} ÷ {k}).")
    # arithmetic: "23 times 47", "what's 15% of 80", "what is 2 to the power of 10"
    m = re.fullmatch(r"(?:what(?:'s| is) |calculate |compute |how much is |work out )?(?P<e>[\d.,()\s+\-*/x×÷%^]+(?:\s*(?:times|plus|minus|divided by|over|"
                     r"multiplied by|to the power of|percent of|% of|squared|cubed)\s*[\d.,()\s+\-*/x×÷%^]*)+|[\d.,]+\s*%\s*of\s*[\d.,]+|square root of [\d.,]+)", q)
    if m and re.search(r"\d", m.group("e")):
        e = m.group("e")
        for w, op in (("multiplied by", "*"), ("divided by", "/"), ("to the power of", "**"), ("percent of", "% of"), ("times", "*"),
                      ("plus", "+"), ("minus", "-"), ("over", "/"), (" x ", "*")):
            e = e.replace(w, op)
        e = re.sub(r"([\d.)]+)\s*squared", r"(\1)**2", e)
        e = re.sub(r"([\d.)]+)\s*cubed", r"(\1)**3", e)
        e = re.sub(r"square root of ([\d.,]+)", r"sqrt(\1)", e)
        from . import tools
        r = tools.calculate({"expression": e}, desk.ctx)
        mm = re.search(r"=\s*(.+)$", str(r))
        val = (mm.group(1) if mm else str(r)).strip()
        if not str(r).lower().startswith("error"):
            return _say(desk, line, val)
    # the time somewhere else
    m = re.fullmatch(r"what(?:'s| is) (?:the )?time (?:is it )?in (?P<c>[a-z .'-]+)|what time is it in (?P<c2>[a-z .'-]+)|time in (?P<c3>[a-z .'-]+)|"
                     r"current time in (?P<c6>[a-z .'-]+)|world clock (?:in |for )?(?!app\b)(?P<c4>[a-z .'-]+)|"
                     r"(?!(?:the|my|your|our|this|that|what|what's|current|local|real|bed|lunch|next|last|day|night|good|game|show|meeting)\b)(?P<c5>[a-z][a-z .'-]*?) time", q)
    if m:
        from . import system
        system.apply_timezone_env()           # (the owner may have changed this computer's zone since the desk started)
        place = next(g for g in (m.group("c"), m.group("c2"), m.group("c3"), m.group("c4"), m.group("c5"), m.group("c6")) if g).strip()
        zone = system.find_timezone(place)
        if zone:
            import zoneinfo
            now = dt.datetime.now(zoneinfo.ZoneInfo(zone))
            here = dt.datetime.now().astimezone()
            diff = (now.utcoffset() - here.utcoffset()).total_seconds() / 3600
            rel = "the same time as here" if diff == 0 else f"{_num(abs(diff))} hour{'s' if abs(diff) != 1 else ''} {'ahead of' if diff > 0 else 'behind'} you"
            return _say(desk, line, f"It's {now.strftime('%H:%M')} on {now.strftime('%A')} in {place.title()} ({rel}).")
    # time until an hour today: "how long until 5pm"
    m = re.fullmatch(r"how (?:long|much time|many (?:hours|minutes)) (?:is it |is there |do i have )?(?:until|till|before) (?P<h>\d{1,2})(?::(?P<mi>\d\d))?\s*(?P<ap>am|pm)?", q)
    if m:
        h, mi = int(m.group("h")), int(m.group("mi") or 0)
        if m.group("ap") == "pm" and h < 12:
            h += 12
        elif m.group("ap") == "am" and h == 12:
            h = 0
        now = dt.datetime.now()
        tgt = now.replace(hour=h % 24, minute=mi, second=0, microsecond=0)
        if tgt <= now:
            tgt += dt.timedelta(days=1)
        left = int((tgt - now).total_seconds() // 60)
        return _say(desk, line, f"{left // 60} h {left % 60:02d} min until {tgt.strftime('%H:%M')}" + (" tomorrow." if tgt.date() != now.date() else "."))
    # spelling
    m = re.fullmatch(r"(?:how (?:do (?:you|i) )?spell|spell(?: out)?|what(?:'s| is) the spelling of) (?:the word )?['\"]?(?P<w>[a-z'-]{2,30})['\"]?", q)
    if m:
        w = m.group("w")
        return _say(desk, line, f"{w}: {'-'.join(w.upper())}")
    # definitions and synonyms from free dictionaries (exact, with a source); the model answers if they can't be reached
    m = re.fullmatch(r"(?:define|definition of|what does (?P<w2>[a-z'-]+) mean|what(?:'s| is) the meaning of|meaning of|what is a|what(?:'s| is) an?) ?(?P<w>[a-z'-]+)?", q)
    if m and (m.group("w") or m.group("w2")) and (q.startswith(("define", "definition", "meaning", "what does", "what's the meaning", "what is the meaning"))):
        w = m.group("w2") or m.group("w")
        from . import web
        wikt = f"https://en.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(w)}"
        if not _net_ok(desk, "read_webpage", {"url": wikt}):
            return _say(desk, line, _net_no("The internet is switched off, so I can't look that up."))
        try:      # Wiktionary's own API (free, no key)
            raw = web.fetch(wikt, max_bytes=400000, timeout=8)[3]
            for e in json.loads(raw).get("en", []):
                for dd in e.get("definitions", []):
                    d = re.sub(r"<[^>]+>", "", dd.get("definition", "")).strip()
                    if d:
                        return _say(desk, line, f"{w} ({e.get('partOfSpeech', '').lower()}): {d}")
        except Exception:
            pass
        free = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(w)}"
        if not _net_ok(desk, "read_webpage", {"url": free}):
            return _say(desk, line, _net_no("The internet is switched off, so I can't look that up."))
        try:      # the Free Dictionary API (built on Wiktionary too)
            raw = web.fetch(free, max_bytes=200000, timeout=8)[3]
            mean = json.loads(raw)[0]["meanings"][0]
            return _say(desk, line, f"{w} ({mean.get('partOfSpeech', '')}): {mean['definitions'][0]['definition']}")
        except Exception:
            return False
    m = re.fullmatch(r"(?:another|other|a different) words? for (?P<w>[a-z'-]+)|synonyms? (?:of|for) (?P<w2>[a-z'-]+)|what(?:'s| is) a synonym (?:of|for) (?P<w3>[a-z'-]+)", q)
    if m:
        w = m.group("w") or m.group("w2") or m.group("w3")
        syn = f"https://api.datamuse.com/words?rel_syn={urllib.parse.quote(w)}&max=8"
        if not _net_ok(desk, "read_webpage", {"url": syn}):
            return _say(desk, line, _net_no("The internet is switched off, so I can't look that up."))
        try:
            from . import web
            raw = web.fetch(syn, max_bytes=50000, timeout=8)[3]
            words = [x["word"] for x in json.loads(raw)][:8]
            if words:
                return _say(desk, line, f"Other words for {w}: {', '.join(words)}.")
        except Exception:
            return False
    return False


_FOLDERS = {"documents": "Documents", "docs": "Documents", "downloads": "Downloads", "desktop": "Desktop", "pictures": "Pictures",
            "photos": "Pictures", "music": "Music", "videos": "Videos", "apps": "Apps", "home": "", "home folder": "", "trash": ".Trash"}
_KINDS = {"screenshot": ("~/Pictures", r"^screenshot", None), "photo": ("~/Pictures", None, (".jpg", ".jpeg", ".png", ".heic", ".webp")),
          "picture": ("~/Pictures", None, (".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif")), "image": ("~/Pictures", None, (".jpg", ".jpeg", ".png", ".gif", ".webp")),
          "download": ("~/Downloads", None, None), "pdf": ("~", None, (".pdf",)), "document": ("~/Documents", None, None),
          "video": ("~/Videos", None, (".mp4", ".mkv", ".webm", ".mov")), "song": ("~/Music", None, (".mp3", ".m4a", ".flac", ".ogg", ".wav")),
          "recording": ("~/Music", r"^recording", None)}


def _human(n):
    for u in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "bytes" else f"{n:.1f} {u}"
        n /= 1024


def files_and_status(desk, line, low):
    from . import tools
    q = low.strip().rstrip("?.!")
    # a folder's size and how many files are in it, counted, not guessed
    m = re.fullmatch(r"how (?:big|large) is (?:my |the )?(?P<f>[a-z ]+?)(?: folder)?|how much (?:space|room) (?:does|do) (?:my |the )?(?P<f2>[a-z ]+?)(?: folder)? (?:take|use)(?: up)?"
                     r"|how many (?:files|things|items|photos|pictures|songs) (?:are |do i have )?in (?:my |the )?(?P<f3>[a-z ]+?)(?: folder)?", q)
    if m:
        name = (m.group("f") or m.group("f2") or m.group("f3")).strip()
        if name in _FOLDERS:
            d = tools._path("~/" + _FOLDERS[name]) if _FOLDERS[name] else tools._path("~")
            size, count = 0, 0
            for root, _, fs in os.walk(d):
                for f in fs:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                        count += 1
                    except OSError:
                        pass
            label = name.capitalize() if name not in ("home", "home folder") else "Your home folder"
            return _say(desk, line, f"{label}: {count} file(s), {_human(size)}.")
    # which network
    if re.fullmatch(r"(?:what|which) (?:wi-?fi|wifi network|network)(?: am i| is this computer| are we)? (?:on|connected to|using)|what(?:'s| is) (?:my |the )?(?:wi-?fi|network)(?: name| called)?|am i (?:on|connected to) (?:the )?wi-?fi", q):
        from . import desk as deskmod
        ssid = deskmod._wifi_now()
        if ssid:
            return _say(desk, line, f"You're on the Wi-Fi network “{ssid}”.")
        try:
            out = subprocess.run(["ip", "-4", "-o", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        if out.strip():
            dev = re.search(r"\bdev (\S+)", out)
            return _say(desk, line, f"You're connected by cable ({dev.group(1) if dev else 'wired'}), not Wi-Fi.")
        return _say(desk, line, "You're not connected to any network. Say “wifi” to pick one.")
    # what's playing
    if re.fullmatch(r"what(?:'s| is) (?:this |the )?(?:playing|song|track|music)(?: called)?(?: now| right now)?|what song is this|what am i listening to|now playing", q):
        np = getattr(desk, "_np", None)
        from . import media
        if np and media.playing():
            return _say(desk, line, f"Playing: {np.get('title', 'something')}" + (f" ({np['channel']})" if np.get("channel") else "") + ".")
        if shutil.which("playerctl"):
            try:
                env = dict(os.environ, **(media.desk_env() or {}))
                st = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=5, env=env).stdout.strip()
                if st in ("Playing", "Paused"):
                    meta = subprocess.run(["playerctl", "metadata", "--format", "{{title}}|{{artist}}"], capture_output=True, text=True,
                                          timeout=5, env=env).stdout.strip()
                    title, _, artist = meta.partition("|")
                    return _say(desk, line, f"{'Playing' if st == 'Playing' else 'Paused'}: {title or 'something'}" + (f" by {artist}" if artist else "") + ".")
            except (OSError, subprocess.SubprocessError):
                pass
        return _say(desk, line, "Nothing is playing.")
    # the newest file of a kind: "open the last screenshot", "show my latest photo"
    m = re.fullmatch(r"(?:open|show(?: me)?|view|play) (?:the |my )?(?:last|latest|newest|most recent|recent) (?P<k>screenshot|photo|picture|image|download|pdf|document|video|song|recording)s?", q)
    if m:
        base, name_rx, exts = _KINDS[m.group("k")]
        best = None
        for root, dirs, fs in os.walk(tools._path(base)):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in fs:
                if f.startswith(".") or (name_rx and not re.search(name_rx, f, re.I)) or (exts and not f.lower().endswith(exts)):
                    continue
                p = os.path.join(root, f)
                try:
                    if best is None or os.path.getmtime(p) > os.path.getmtime(best):
                        best = p
                except OSError:
                    pass
        if not best:
            return _say(desk, line, f"There's no {m.group('k')} yet.")
        tools.open_file({"path": best}, desk.ctx)
        return _say(desk, line, f"Opened {os.path.basename(best)}.")
    return False


_WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle",
        55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
        67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "showers", 81: "showers",
        82: "heavy showers", 85: "snow showers", 86: "snow showers", 95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail"}


def _place():
    """Where the owner is, for the weather: what they told us, else the city of this computer's time zone."""
    from . import system
    p = config.Profile().get("city") or config.Profile().get("location")
    if p:
        return str(p)
    tz = system.timezone() or ""
    return tz.split("/")[-1].replace("_", " ") if "/" in tz else ""


def weather(desk, line, low):
    q = low.strip().rstrip("?.!")
    q = re.sub(r"^(?:should|do) i (?:bring|take|grab|wear|need)\s+(?:an?\s+|my\s+)?", "do i need a ", q)
    q = re.sub(r"^will i (?:need|want)\s+(?:an?\s+|my\s+)?", "do i need a ", q)
    q = re.sub(r"^do i need a (umbrella|coat|jacket|raincoat|jumper|sweater)", r"do i need an \1", q)
    m = re.fullmatch(r"(?:what(?:'s| is| will be)|how(?:'s| is| will be)) (?:the )?weather(?: like| going to be(?: like)?| be like)?(?P<w> today| tomorrow| this weekend| tonight| on \w+day| this week)?(?: in (?P<p>[a-z .,'-]+?))?(?P<w2> today| tomorrow| this weekend| tonight| this week)?"
                     r"|weather(?: today| tomorrow| forecast)?(?: in (?P<p2>[a-z .,'-]+))?|(?:the )?forecast(?: for (?P<p3>[a-z .,'-]+))?"
                     r"|(?:will|is) it (?:going to )?(?P<r>rain|snow|be (?:hot|cold|sunny|windy))(?P<w3> today| tomorrow| tonight| this weekend)?(?: in (?P<p4>[a-z .,'-]+))?"
                     r"|do i need an? (?P<u>umbrella|coat|jacket)(?P<w4> today| tomorrow)?(?: in (?P<p6>[a-z .,'-]+?))?(?P<w6> today| tomorrow)?|how (?:hot|cold|warm) (?:is it|will it be)(?P<w5> today| tomorrow)?(?: in (?P<p5>[a-z .,'-]+))?", q)
    if not m:
        return False
    if config.settings.get("internet") == "no":
        return _say(desk, line, "The internet is switched off in settings, so I can't get the forecast.")
    gd = m.groupdict()
    place = next((gd[k] for k in ("p", "p2", "p3", "p4", "p5", "p6") if gd.get(k)), None) or _place()
    when = (next((gd[k] for k in ("w", "w2", "w3", "w4", "w5", "w6") if gd.get(k)), None) or " today").strip()
    if not place:
        return _say(desk, line, "Where are you? Say “the weather in Denver” (I'll remember it if you say “I live in Denver”).")
    from . import web
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(place)
    if not _net_ok(desk, "read_webpage", {"url": geo_url}):
        return _say(desk, line, _net_no(_OFF_WEATHER))
    try:
        geo = json.loads(web.fetch(geo_url, max_bytes=100000, timeout=8)[3])
        g = (geo.get("results") or [None])[0]
        if not g:
            return _say(desk, line, f"I couldn't find a place called {place}.")
        us = g.get("country_code") in ("US", "LR", "MM")
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={g['latitude']}&longitude={g['longitude']}&timezone=auto&forecast_days=7"
               "&current=temperature_2m,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
               + ("&temperature_unit=fahrenheit" if us else ""))
        if not _net_ok(desk, "read_webpage", {"url": url}):
            return _say(desk, line, _net_no(_OFF_WEATHER))
        f = json.loads(web.fetch(url, max_bytes=200000, timeout=8)[3])
    except Exception as e:
        return _say(desk, line, f"I couldn't get the forecast just now: {_plain_err(e)}.")
    unit = "°F" if us else "°C"
    src = " (Source: Open-Meteo forecast, open-meteo.com.)"   # where the numbers come from, every time
    d = f["daily"]
    idx = 1 if "tomorrow" in when else 0
    m2 = re.match(r"on (\w+day)", when)
    if m2:
        names = [dt.date.fromisoformat(x).strftime("%A").lower() for x in d["time"]]
        idx = names.index(m2.group(1)) if m2.group(1) in names else 0
    name = g["name"] + (f", {g.get('admin1')}" if g.get("admin1") and g.get("admin1") != g["name"] else "")
    rain = d["precipitation_probability_max"][idx]
    desc = _WMO.get(d["weather_code"][idx], "mixed")
    hi, lo = round(d["temperature_2m_max"][idx]), round(d["temperature_2m_min"][idx])
    day = "Today" if idx == 0 else "Tomorrow" if idx == 1 else dt.date.fromisoformat(d["time"][idx]).strftime("%A")
    if "weekend" in when or "week" in when:
        rows = []
        for i, t in enumerate(d["time"]):
            dd = dt.date.fromisoformat(t)
            if "week" in when and "weekend" not in when or dd.weekday() >= 5:
                rows.append(f"{dd.strftime('%a')} {_WMO.get(d['weather_code'][i], 'mixed')}, {round(d['temperature_2m_max'][i])}/{round(d['temperature_2m_min'][i])}{unit}")
        return _say(desk, line, f"{name}: " + "; ".join(rows) + "." + src)
    if gd.get("r") or gd.get("u"):
        wet = rain >= 40 if rain is not None else d["weather_code"][idx] >= 51     # the chance decides; a code alone can mislead
        if gd.get("u") in ("coat", "jacket"):
            cold = lo < (50 if us else 10)
            return _say(desk, line, f"{'Yes' if cold else 'Probably not'}: {day.lower()} in {name} goes down to {lo}{unit} ({desc}).{src}")
        return _say(desk, line, f"{'Yes, likely' if wet else 'Probably not'}: {rain if rain is not None else '?'}% chance of rain {day.lower()} in {name} ({desc}, {hi}/{lo}{unit}).{src}")
    now = f" Now {round(f['current']['temperature_2m'])}{unit}." if idx == 0 and f.get("current") else ""
    return _say(desk, line, f"{day} in {name}: {desc}, high {hi}{unit}, low {lo}{unit}, {rain if rain is not None else '?'}% chance of rain.{now}{src}")


def net_and_dates(desk, line, low):
    q = low.strip().rstrip("?.!")
    if re.fullmatch(r"(?:is (?:the |my )?internet (?:working|up|down|ok|on|connected)|am i (?:online|connected(?: to the internet)?)|do i have (?:the )?internet|is (?:the )?(?:wi-?fi|network) working|is (?:the )?(?:wi-?fi|network|connection) down|are we online)", q):
        if not _net_ok(desk, "read_webpage", {"url": "https://www.google.com/generate_204"}):
            return _say(desk, line, _net_no("The internet is switched off in settings (say “turn the internet on”)."))
        t0 = time.time()
        try:
            from . import web
            web.fetch("https://www.google.com/generate_204", max_bytes=1000, timeout=6)
            return _say(desk, line, f"Yes, the internet is working (answered in {int((time.time() - t0) * 1000)} ms).")
        except Exception as e:
            try:
                import socket
                socket.create_connection(("1.1.1.1", 443), timeout=4).close()
                return _say(desk, line, "The network reaches the internet, but web pages aren't loading (names don't resolve): try again in a minute, or restart the router.")
            except OSError:
                return _say(desk, line, "No, there's no internet connection right now. Say “wifi” to check the network.")
    m = re.fullmatch(r"what day (?:of the week )?(?:is|was|will be|falls on|does)\s+(?P<x>.+?)(?:\s+(?:fall on|land on|be))?(?:\s+(?:this year|next year|in (?P<y>\d{4})))?", q)
    if m:
        today = dt.date.today()
        d, w = _date_of(m.group("x"), today if not m.group("y") else dt.date(int(m.group("y")), 1, 1))
        if "next year" in q and d:
            d = d.replace(year=d.year + 1) if d.year == today.year else d
        if d:
            if w in _HOLIDAYS:
                return _say(desk, line, f"{' '.join(x[:1].upper() + x[1:] for x in w.split())} is on a {d.strftime('%A')} ({d.strftime('%d %B %Y').lstrip('0')}).")
            return _say(desk, line, f"{d.strftime('%d %B %Y').lstrip('0')} is a {d.strftime('%A')}.")
    # "add call the bank to todo.txt": a line at the end of that file, wherever it is
    m = re.fullmatch(r"(?:add|append|write|put)\s+(?P<t>.+?)\s+(?:to|in|into|at the end of)\s+(?:my\s+|the\s+)?(?P<f>[\w .-]+\.(?:txt|md|csv|log))", q)
    if m and re.search(r"\b(?:and|save|saved|as|then|called|named)\b", m.group("f")):
        m = None        # "write a note to my neighbour and save it as thanks.txt": compose, not "append to a file"
    if m and re.match(r"(?:a|an|some|my|the)\s+(?:\w+\s+){0,4}(?:list|note|poem|story|letter|summary|paragraph|recipe|plan|"
                      r"email|message|joke|reminder|to-?do|agenda|schedule|description|bio|haiku|toast|speech)s?\b", m.group("t")):
        # "write a short shopping list into notes.txt": that describes text to write, not the words to add
        from . import tools
        name = line.strip().rstrip("?.!")[m.start("f"):m.end("f")]
        hits = [h for h in tools.find_paths(name) if os.path.basename(h).lower() == name.lower()]
        out = tools.write_document({"request": line.strip().rstrip("?.!")[m.start("t"):m.end("t")], "name": hits[0] if hits else name,
                                    "append": True}, desk.ctx if hasattr(desk, "ctx") else desk)
        return _say(desk, line, out[7:] if out.startswith("error: ") else out)
    if m:
        from . import tools
        name = line.strip().rstrip("?.!")[m.start("f"):m.end("f")]
        hits = [h for h in tools.find_paths(name) if os.path.basename(h).lower() == name.lower()]
        path = hits[0] if hits else os.path.join(config.home(), "Documents", name)
        text = line.strip().rstrip("?.!")[m.start("t"):m.end("t")].strip().strip("'\"")
        with open(path, "a", encoding="utf-8") as fh:
            if os.path.getsize(path) and not open(path, "rb").read()[-1:] == b"\n":
                fh.write("\n")
            fh.write(text + "\n")
        home = config.home().rstrip("/")
        return _say(desk, line, f"Added “{text}” to {('~' + path[len(home):]) if path.startswith(home) else path}.")
    return False


# ------------------------------------------------------------------ calendar, news, service status, mail

_STATUS_PAGES = {"github": "www.githubstatus.com", "slack": "status.slack.com", "discord": "discordstatus.com",
                 "spotify": "status.spotify.com", "zoom": "status.zoom.us", "dropbox": "status.dropbox.com", "openai": "status.openai.com",
                 "chatgpt": "status.openai.com", "cloudflare": "www.cloudflarestatus.com", "gitlab": "status.gitlab.com",
                 "notion": "status.notion.so", "reddit": "www.redditstatus.com", "netflix": "status.netflix.com", "steam": "steamstatus.io",
                 "twitch": "status.twitch.tv", "shopify": "www.shopifystatus.com", "vercel": "www.vercel-status.com", "heroku": "status.heroku.com",
                 "twilio": "status.twilio.com", "stripe": "status.stripe.com", "square": "www.issquareup.com", "venmo": "status.venmo.com",
                 "microsoft teams": "status.office.com", "teams": "status.office.com", "outlook": "status.office.com", "office": "status.office.com",
                 "onedrive": "status.office.com", "icloud": "www.apple.com/support/systemstatus", "google": "www.google.com/appsstatus/dashboard"}


def service_status(desk, line, low):
    m = re.fullmatch(r"(?:is|are) (?:the )?(?P<s>[a-z][a-z .'-]{1,30}?)(?:'s)? (?:servers? |website |site |app |service )?(?:down|up|working|broken|having (?:issues|problems|an outage)|not working|offline)(?: (?:right )?now| today)?", low)
    if not m:
        return False
    name = m.group("s").strip()
    page = _STATUS_PAGES.get(name)
    if not page:
        return False                       # an unknown service: the model looks it up on the web
    from . import web
    if not _net_ok(desk, "read_webpage", {"url": f"https://{page}/api/v2/status.json"}):
        return _say(desk, line, _net_no("The internet is switched off, so I can't look that up."))
    try:
        st = json.loads(web.fetch(f"https://{page}/api/v2/status.json", max_bytes=100000, timeout=8)[3])["status"]
    except Exception:
        return _say(desk, line, f"I couldn't reach {name}'s status page just now. Check {page} directly.")
    ok = st.get("indicator") in ("none", "") or "operational" in str(st.get("description", "")).lower()
    shown = {"github": "GitHub", "openai": "OpenAI", "chatgpt": "ChatGPT", "gitlab": "GitLab", "icloud": "iCloud", "onedrive": "OneDrive",
             "twilio": "Twilio", "heroku": "Heroku", "vercel": "Vercel", "notion": "Notion", "zoom": "Zoom", "dropbox": "Dropbox"}.get(name, name.title())
    return _say(desk, line, f"{shown}: {st.get('description', 'no answer')}" + ("" if ok else f" ({page})") + ".")


_LIVE_STATUS = re.compile(r"(?:is|are) (?P<s>(?!it\b|this\b|my\b|that\b)[a-z][a-z .'-]{1,30}?)(?:'s)? (?:servers? |website |site |app |service )?"
                          r"(?:down|broken|having (?:issues|problems|an outage))(?: right now| now| today| at the moment)?")
_LIVE_HOURS = re.compile(r"what time does (?P<s>[a-z' .-]{2,40}?) (?P<v>open|close)")
_LIVE_WON = re.compile(r"who won (?:the )?(?P<s>[a-z' .-]{2,40}?)(?: last night| yesterday| today| this week)?")
_CLOCK_TIME = re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm|a\.m\.|p\.m\.)|\b\d{1,2}:\d{2}\b", re.I)


def _first_sentences(text, n=2, cap=300):
    """The first one or two sentences of a search snippet, at most `cap` characters."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])", " ".join(str(text or "").split()))
    out = " ".join(parts[:n]).strip()
    if len(out) > cap:
        out = out[:cap].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
    return out


def live_lookup(desk, line, low):
    """A question about a live service or opening hours: a search, answered from its results in one line (no model turn)."""
    m = _LIVE_STATUS.fullmatch(low)
    h = None if m else _LIVE_HOURS.fullmatch(low)
    won = None if (m or h) else _LIVE_WON.fullmatch(low)
    if won:
        from . import web
        what = won.group("s").strip(" ")
        sport = re.search(r"\b(game|match|final|cup|series|race|fight|bout|season|league|team)\b", what)
        q = f"{what} result" + (" last night" if sport else "")
        if not _net_ok(desk, "web_search", {"query": q}):
            return _say(desk, line, _net_no("The internet is switched off in settings, so I can't look up results."))
        try:
            res = web.search(q, n=3)
        except Exception:
            return _say(desk, line, "I couldn't search for the result just now. Try again in a minute.")
        if not res:
            return _say(desk, line, "I couldn't find that result.")
        top = res[0]
        return _say(desk, line, f"From search: “{top['title']}” ({top['url']}). {top['snippet'][:200]} "
                                "Check the page for the details.")
    fact = None if (m or h or won) else next((x for x in (p.fullmatch(low) for p in _LIVE_FACTS) if x), None)
    if fact:
        # a simple fact question: the top snippet, one or two sentences, with its source (same failure replies as "who won")
        from . import web
        if not _net_ok(desk, "web_search", {"query": line.strip()}):
            return _say(desk, line, _net_no("The internet is switched off in settings, so I can't look up results."))
        try:
            res = web.search(line.strip(), n=3)
        except Exception:
            return _say(desk, line, "I couldn't search for the result just now. Try again in a minute.")
        top = res[0] if res else {}
        snippet = _first_sentences(top.get("snippet"))
        if not snippet:
            return _say(desk, line, "I couldn't find that result.")
        src = urllib.parse.urlparse(str(top.get("url") or "")).netloc.lower().removeprefix("www.") or "the web"
        return _say(desk, line, f"{snippet} (source: {src})")
    if not (m or h):
        return False
    if config.settings.get("internet") == "no":
        return _say(desk, line, "The internet is switched off in settings, so I can't check that.")
    from . import web
    name = (m or h).group("s").strip(" '")
    if m and name in _STATUS_PAGES:
        return False                  # a known status page: service_status answers it
    q = f"{name} {'status outage today' if m else 'opening hours'}"
    if not _net_ok(desk, "web_search", {"query": q}):
        return _say(desk, line, _net_no("The internet is switched off in settings, so I can't check that."))
    try:
        res = web.search(q, n=3)
    except Exception:
        return _say(desk, line, f"I couldn't search for {name} just now. Try again in a minute.")
    if not res:
        return _say(desk, line, f"I couldn't find anything about {name}.")
    top = res[0]
    if m:
        return _say(desk, line, f"I can't read {name}'s live status here. The top result is “{top['title']}” ({top['url']}). "
                                f"Check there for the current state.")
    times = [t for r in res for t in _CLOCK_TIME.findall(r["title"] + " " + r["snippet"])]
    if times:
        # "open 9am to 5:30pm": a closing question takes the later time, an opening one the earlier
        when = times[-1] if h.group("v") == "close" else times[0]
        return _say(desk, line, f"Search results give {name}'s {h.group('v')} time as {when.strip()} "
                                f"({top['url']}). Opening hours change, so check that page before you go.")
    return _say(desk, line, f"I couldn't find the {h.group('v')} time for {name} in search. The top result is “{top['title']}” "
                            f"({top['url']}).")


def news(desk, line, low):
    if not re.fullmatch(r"(?:what(?:'s| is| are) (?:the |in the |the latest |today's )?(?:news|headlines)(?: today| right now| now)?|"
                        r"(?:show|give) me (?:the |today's |the latest )?(?:news|headlines)|(?:top |latest )?headlines|the news)", low):
        return False
    import xml.etree.ElementTree as ET
    from . import web
    if not _net_ok(desk, "read_webpage", {"url": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"}):
        return _say(desk, line, _net_no("The internet is switched off in settings, so I can't get the news."))
    try:
        root = ET.fromstring(web.fetch("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en", max_bytes=400000, timeout=10)[3])
    except Exception:
        return False                       # no feed: the model tries the web itself
    items = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        src = (it.find("source").text.strip() if it.find("source") is not None and it.find("source").text else "")
        link = (it.findtext("link") or "").strip()
        if t:
            items.append((t, src, link))
        if len(items) >= 8:
            break
    if not items:
        return False
    desk.open_window({"id": "news", "replace": True, "title": "Top stories", "size": "m", "blocks": [
        {"type": "list", "items": [{"title": t.rsplit(" - ", 1)[0][:140], "subtitle": src,
                                    "actions": [{"label": "Open", "say": f"open {link} in the browser", "primary": True}]}
                                   for t, src, link in items if link]}]})
    lead = "; ".join(f"{i}. {t.rsplit(' - ', 1)[0]}" for i, (t, _, _) in enumerate(items[:3], 1))
    return _say(desk, line, f"Top stories: {lead}. The rest are on the screen.")


def calendar(desk, line, low):
    if not re.fullmatch(r"(?:what(?:'s| is| do i have| have i got)?)\s+(?:on\s+)?(?:my\s+)?(?:calendar|schedule|agenda)(?:\s+(?:today|tomorrow|this week|for today))?|"
                        r"(?:what(?:'s| is) )?(?:on )?my (?:calendar|schedule|agenda) (?:today|tomorrow|this week)|"
                        r"(?:what do i have|anything) (?:on|scheduled) (?:today|tomorrow)", low):
        return False
    from . import store
    day = dt.date.today() + (dt.timedelta(days=1) if "tomorrow" in low else dt.timedelta(0))
    mine = []
    for t in store.tasks():
        try:
            when = dt.datetime.fromtimestamp(float(t.get("next") or 0))
        except (TypeError, ValueError, OSError):
            continue
        if when.date() == day:
            mine.append(f"{when.strftime('%H:%M')} {t.get('task', '')[:60]}")
    word = "today" if day == dt.date.today() else "tomorrow"
    if mine:
        return _say(desk, line, f"No calendar is connected, so these are your reminders for {word}: " + "; ".join(sorted(mine)) + ".")
    return _say(desk, line, f"No calendar is connected, and you have no reminders for {word}. To add one, say \u201cadd dentist to my calendar on friday at 2pm\u201d.")


def open_mail(desk, line, low):
    if not re.fullmatch(r"(?:open|check|show|see|get|go to) (?:my |the )?(?:e-?mail|mail|inbox)(?: (?:app|program|account))?|(?:my )?(?:e-?mail|mail|inbox)", low):
        return False
    from . import mail, tools
    if mail.account() is None:
        desk.mail_form()
        return _say(desk, line, "Your email isn't set up yet. Enter your address and password in the window (Gmail and most others need an app password).")
    from . import agent
    out = tools.REGISTRY["mail_inbox"].fn({}, desk.ctx)
    return _say(desk, line, agent._shortcut_reply("mail_inbox", {}, out))


def free_space(desk, line, low):
    """How much space is left: the real numbers from the disk, in words (never guessed)."""
    if not re.fullmatch(_FREE_SPACE_Q + r"[?.!]?", low):
        return False
    import shutil
    try:
        u = shutil.disk_usage(config.home())
    except OSError:
        return _say(desk, line, "I couldn't read the disk just now.")
    def gb(n):
        return f"{n / 1e9:.1f} GB" if n < 1e11 else f"{n / 1e9:.0f} GB"
    pct = round(u.used / u.total * 100) if u.total else 0
    hint = " Say \"show my biggest files\" to see what's using it." if re.search(r"\bfull\b|free up", low, re.I) else ""
    return _say(desk, line, f"You have {gb(u.free)} free out of {gb(u.total)} ({pct}% used).{hint}")


def small_answers(desk, line, low):
    """Words that need no model: a 'yes' with nothing waiting, a frozen screen, a slow computer."""
    m = re.fullmatch(r"(?:turn|switch) (?P<v>on|off) (?:the |my )?bluetooth|bluetooth (?P<w>on|off)", low)
    if m:
        from . import syspanels
        ok, note = syspanels.bt_action(m.group("v") or m.group("w"))
        return _say(desk, line, note + "." if ok else note[:1].upper() + note[1:] + ".")
    if re.fullmatch(r"yes|yeah|yep|yup|sure|ok|okay", low):
        return _say(desk, line, "Nothing is waiting for a yes.")
    if re.fullmatch(r"(?:the |my )?(?:screen|computer|pc|laptop|everything) (?:has |have )?(?:froze|frozen|locked up|is stuck)", low):
        return _say(desk, line, "Give it a minute; it often comes back. If it is still stuck, press and hold the power button "
                                "for five seconds, then press it again to start. Anything not saved is lost.")
    if re.search(r"(?:computer|pc|laptop|machine) (?:is |has been |got |feels )?(?:really |very |so |quite )?slow\b", low):
        import subprocess
        try:
            out = subprocess.run(["ps", "-eo", "comm,pcpu", "--sort=-pcpu"], capture_output=True, text=True, timeout=10).stdout.split("\n")[1:4]
        except Exception:
            out = []
        busy = []
        for row in out:
            parts = row.split()
            if len(parts) == 2 and parts[1].replace(".", "", 1).isdigit():
                busy.append(f"{parts[0]} ({float(parts[1]):.0f}% CPU)")
        mem = {}
        try:
            for row in open("/proc/meminfo"):
                k, v = row.split(":", 1)
                mem[k] = int(v.split()[0])
        except (OSError, ValueError):
            pass
        if mem.get("MemTotal") and mem.get("MemAvailable", mem["MemTotal"]) < mem["MemTotal"] * 0.1:
            try:
                top = subprocess.run(["ps", "-eo", "comm,rss", "--sort=-rss"], capture_output=True, text=True, timeout=10).stdout.split("\n")[1:2]
                name, rss = top[0].split()[:2]
                hog = f"{name} ({int(rss) // 1024} MB)"
            except (IndexError, ValueError):
                hog = "the program using the most memory"
            busy.insert(0, f"memory is nearly full, and {hog} uses the most")
        if not busy:
            return _say(desk, line, "Nothing is using much processor or memory right now. Restart the program that feels slow.")
        return _say(desk, line, "Busiest now: " + ", ".join(busy) + ". Close a program you are not using to free it up.")
    return False


# ------------------------------------------------------------------ jokes

JOKES = [
    "Why did the spreadsheet see a therapist? It had too many unresolved cells.",
    "My computer asked for a vacation, so I told it to take a byte.",
    "I tried to write a joke about UDP, but I'm not sure you'd get it.",
    "My printer and I have a lot in common. We both jam when you need us most.",
    "I asked my pencil for a joke. It said it would work on a point.",
    "I asked the fridge for a joke. It said it was too cool for that.",
    "What did the mouse say to the keyboard? Let's get clicking.",
    "I wanted a job at the bakery, but they said I didn't have the dough.",
    "I bought a desk calendar. We have a very dateable relationship.",
    "Why did the stop sign get a raise? It was always holding its ground.",
    "My Wi-Fi and I have trust issues. It keeps dropping our conversations.",
    "Why did the bread stay home? It was feeling a little crumby.",
    "My alarm clock is my most reliable friend. It shows up even when I don't want it to.",
    "Why did the lamp break up with the outlet? It felt the spark was gone.",
    "Why did the golf ball go to school? It wanted to brush up on its swing.",
    "What do you call a computer that naps? A snooze button.",
    "I used to be indecisive. Now I'm not so sure.",
    "What do you call a pickle that tells jokes? A dill-arious comedian.",
    "Why did the penguin book a hotel? It heard the ice was too far away.",
    "Why did the computer go to the doctor? It had a virus and had to stay in quarantine.",
    "I asked the cloud for advice. It said it would get back to me, but it's still up in the air.",
    "I told my plant a joke. It didn't laugh, but it did grow on me.",
    "My keyboard is very cheerful. Whenever I'm stuck, it says, 'Press any key to continue.'",
    "I went to the gym to work on my abs. Now I can't feel them, so I think it worked.",
    "Why did the tortilla stop talking? It was too wrapped up in itself.",
    "Why did the coffee file a police report? It got mugged.",
    "Why did the hard drive break up with the floppy disk? Too much old baggage.",
    "Why did the clock get so good at math? It had plenty of time to practice.",
    "I changed my password to 'incorrect.' Now whenever I forget it, the computer says, 'Your password is incorrect.'",
    "Why did the battery go to the gym? It wanted to get more charged up.",
]
_recent_jokes = collections.deque(maxlen=10)  # the last 10 jokes told, so the next one is new


def jokes(desk, line, low):
    if not re.search(_JOKE_PAT, low, re.I):
        return False
    fresh = [j for j in JOKES if j not in _recent_jokes]
    joke = random.choice(fresh)
    _recent_jokes.append(joke)
    return _say(desk, line, joke)


# ------------------------------------------------------------------ the computer itself: exact facts, read from the hardware

_HW = re.compile(
    r"^(?:how much|what(?:'?s| is)(?: my| the)?) (?:battery|charge)(?: (?:level|percent(?:age)?|left|is left))?(?: do i have)?(?: left)?$|"
    r"^(?:is (?:it|the (?:laptop|computer|battery)|my (?:laptop|computer|battery))|am i) (?:charging|plugged in)$|"
    r"^(?:what|which|whats|what's)\b[^,]*\b(?:(?:graphics|video) (?:card|chip|adapter)s?|gpus?)\b|(?:graphics|video) card do i have|"
    r"(?:screen|display|monitor) (?:resolution|size)\b|^(?:what(?:'?s| is) (?:my |the )?)?resolution$|how big is (?:my |the |this )?(?:screen|display)|"
    r"^how much (?:memory|ram)\b|\bram do i have\b|^what(?:'?s| is) (?:my |the )?(?:memory|ram)$|"
    r"^what (?:computer|laptop|machine|pc|model) is (?:this|it)$|^what(?:'?s| is) (?:this|my) (?:computer|laptop|machine|pc)$|"
    r"(?:computer|laptop) model|what (?:cpu|processor)|which (?:cpu|processor)|"
    r"how fast is (?:my |the )?(?:internet|connection|wifi|wi-fi)|internet speed|speed ?test")


def _read(path):
    try:
        with open(path, errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _gpus():
    out = []
    try:
        p = subprocess.run(["lspci", "-mm"], capture_output=True, text=True, timeout=10)
        for ln in p.stdout.splitlines():
            f = re.findall(r'"([^"]*)"', ln)
            if len(f) >= 3 and re.search(r"VGA|3D|Display", f[0]):
                out.append(f"{f[1].split(' Corporation')[0]} {f[2]}".strip())
    except (OSError, subprocess.SubprocessError):
        pass
    drivers = []
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
        d = os.path.join(card, "device", "driver")
        if os.path.islink(d):
            drivers.append(os.path.basename(os.readlink(d)))
    return out, drivers


def hardware(desk, line, low):
    if not _HW.search(low):
        return False
    if re.search(r"battery|charg|plugged", low):
        base = "/sys/class/power_supply"
        for n in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            if _read(f"{base}/{n}/type") == "Battery":
                pct, st = _read(f"{base}/{n}/capacity"), _read(f"{base}/{n}/status")
                ac = any(_read(f"{base}/{m}/online") == "1" for m in os.listdir(base) if _read(f"{base}/{m}/type") == "Mains")
                how = {"Charging": "charging", "Full": "full and plugged in", "Not charging": "plugged in, not charging (it is full enough)",
                       "Discharging": "on battery"}.get(st, "plugged in" if ac else st.lower() or "on battery")
                return _say(desk, line, f"The battery is at {pct}%, {how}.")
        return _say(desk, line, "This computer has no battery: it runs from the mains.")
    if re.search(r"graphics|video (?:card|chip|adapter)|gpu", low):
        names, drivers = _gpus()
        if not names and not drivers:
            return _say(desk, line, "I can't read the graphics hardware on this computer.")
        nice = {"i915": "Intel's driver", "xe": "Intel's driver", "nouveau": "the open NVIDIA driver (nouveau)", "nvidia": "NVIDIA's own driver",
                "amdgpu": "AMD's driver", "radeon": "AMD's older driver", "virtio-pci": "a virtual machine's graphics"}
        txt = ("Graphics: " + " and ".join(names) + "." if names else "") + \
              (" In use: " + ", ".join(dict.fromkeys(nice.get(d, d) for d in drivers)) + "." if drivers else "")
        return _say(desk, line, txt.strip())
    if re.search(r"resolution|screen size|how big is", low):
        try:
            from . import media
            out = subprocess.run(["wlr-randr"], capture_output=True, text=True, timeout=10,
                                 env=dict(os.environ, **(media.desk_env() or {}))).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        cur = re.findall(r"(\d+)x(\d+) px(?:, ([\d.]+) Hz)?[^\n]*current", out)
        sc = re.findall(r"Scale: ([\d.]+)", out)
        if not cur:
            return _say(desk, line, "I can't read the screen's resolution right now.")
        parts = [f"{w} × {h}" + (f" at {float(hz):.0f} Hz" if hz else "") for w, h, hz in cur]
        return _say(desk, line, "Screen: " + "; ".join(parts) + (f", scaled {float(sc[0]):g}×" if sc and float(sc[0]) != 1 else "") + ".")
    if re.search(r"memory|ram", low):
        mi = dict(re.findall(r"^(\w+):\s+(\d+)", _read("/proc/meminfo"), re.M))
        tot, avail = int(mi.get("MemTotal", 0)) / 1048576, int(mi.get("MemAvailable", 0)) / 1048576
        return _say(desk, line, f"{tot:.1f} GB of memory (RAM); {avail:.1f} GB of it is free right now.")
    if re.search(r"how fast|speed", low):
        import time as _t
        import urllib.request as _u
        desk.emit({"t": "toast", "text": "Measuring the internet speed (about 10 seconds)…"})
        t0, got = _t.time(), 0
        try:
            r = _u.urlopen(_u.Request("https://speed.cloudflare.com/__down?bytes=50000000",
                                      headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LLM-OS"}), timeout=10)
            while _t.time() - t0 < 8:
                b = r.read(262144)
                if not b:
                    break
                got += len(b)
        except Exception as e:
            if not got:
                return _say(desk, line, f"I couldn't measure it: the test site didn't answer ({_plain_err(e)}).")
        secs = max(_t.time() - t0, 0.1)
        return _say(desk, line, f"Download speed: about {got * 8 / secs / 1e6:.0f} Mbit/s (measured for {secs:.0f} s).")
    vendor, model = _read("/sys/class/dmi/id/sys_vendor"), _read("/sys/class/dmi/id/product_name")
    cpu = re.search(r"^model name\s*:\s*(.+)$", _read("/proc/cpuinfo"), re.M)
    mi = dict(re.findall(r"^(\w+):\s+(\d+)", _read("/proc/meminfo"), re.M))
    names, _ = _gpus()
    bits = [f"{vendor} {model}".strip() or "This computer"]
    if cpu:
        bits.append(f"processor {re.sub(r'\s+', ' ', cpu.group(1)).strip()} ({os.cpu_count()} threads)")
    if mi.get("MemTotal"):
        bits.append(f"{int(mi['MemTotal']) / 1048576:.0f} GB of memory")
    if names:
        bits.append("graphics " + " and ".join(names))
    return _say(desk, line, ", ".join(bits) + ".")


def handle(desk, line):
    low = line.lower().strip().rstrip("?.!")
    for fn in (hardware, jokes, small_answers, free_space, quick, files_and_status, weather, net_and_dates, service_status, live_lookup, news, calendar, open_mail, focus, days_until, sites, work_timer, ports, web_server, health, hostname, access, sounds, autostart, vpn, discs, privacy, system_more, share_app, version_answer, model_answer, ota_updates, web_block, howto):
        try:
            if fn(desk, line, low):
                return True
        except Exception as e:  # an everyday helper must never break the desk
            desk.instant_reply(line, f"That didn't work: {_plain_err(e)}.")
            return True
    return False

MATCH = re.compile(f"(?:{MATCH.pattern})|(?:{_HW.pattern})", MATCH.flags)   # the hardware facts answer at once too
