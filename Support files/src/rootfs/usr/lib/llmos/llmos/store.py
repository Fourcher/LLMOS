"""Private stores in ~/.llmos (inside the encrypted vault when enabled):
memory, audit log, notification inbox, scheduled tasks."""
import datetime as dt
import functools
import json
import os
import re
import stat
import tempfile
import time
import uuid

from . import config


def _locked(fn):
    """Each change to a data file is a read-modify-write: one at a time across the desk, the console and the
    scheduler, so that none of them overwrites what another just saved."""
    @functools.wraps(fn)
    def wrap(*a, **k):
        with config.data_lock():
            return fn(*a, **k)
    return wrap


# ------------------------------------------------------------------ memory

def facts():
    return config.load_json(config.data("memory.json"), [])


def _names():
    """The owner's name(s), so 'Jordan likes X' and 'User likes X' compare equal."""
    try:
        name = str(config.Profile().get("name", "") or "")
    except Exception:
        name = ""
    return {w.rstrip("s") for w in re.findall(r"\w{3,}", name.lower())}


@_locked
def remember(fact):
    fact = " ".join(str(fact).split())
    if not fact:
        return False
    cur = facts()
    if any(f["fact"].lower() == fact.lower() for f in cur):
        return False
    # a paraphrase of something already known is not a new fact ("User like
    # short answers" / "Jordan likes short answers"): compare stemmed words,
    # ignoring who the sentence is about
    def _words(s):
        return {w.rstrip("s") for w in re.findall(r"\w{3,}", s.lower())
                if w not in ("user", "owner", "the", "and", "that", "they", "their")} - _names()
    words = _words(fact)
    for f in cur:
        known = _words(f["fact"])
        smaller = min(len(words), len(known))
        if smaller and len(words & known) >= max(2, -(-7 * smaller // 10)):   # >= 70% of the shorter one
            return False
    cur.append({"fact": fact, "added": time.strftime("%Y-%m-%d")})
    config.save_json(config.data("memory.json"), cur)
    return True


@_locked
def forget(query):
    q = str(query).lower().strip()
    cur = facts()
    if q in ("everything", "all", "*"):
        config.save_json(config.data("memory.json"), [])
        return [f["fact"] for f in cur]
    hit = [f for f in cur if q and q in f["fact"].lower()]
    if not hit:  # fall back to word overlap
        words = set(re.findall(r"\w{3,}", q))
        scored = [(len(words & set(re.findall(r"\w{3,}", f["fact"].lower()))), f) for f in cur]
        scored = [s for s in scored if s[0] > 0]
        if scored:
            best = max(s for s, _ in scored)
            hit = [f for s, f in scored if s == best]
    keep = [f for f in cur if f not in hit]
    config.save_json(config.data("memory.json"), keep)
    return [f["fact"] for f in hit]


# ------------------------------------------------------------------ audit

AUDIT_MAX = 2 * 1024 * 1024    # the log is kept under this size
AUDIT_KEEP = 1024 * 1024       # when it is trimmed, the newest this many bytes stay


def _replace_file(path, data, mode=0o600):
    """Write bytes to a temporary file beside path, then rename it over path (as config.save_json does)."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _audit_trim(path, incoming):
    """Before an append of `incoming` bytes: if the log would pass AUDIT_MAX, keep only its newest AUDIT_KEEP bytes
    (whole lines). A symlink is never followed or rewritten: the trim is skipped."""
    try:
        st = os.lstat(path)
    except OSError:
        return
    if not stat.S_ISREG(st.st_mode) or st.st_size + incoming <= AUDIT_MAX:
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            f.seek(max(0, st.st_size - AUDIT_KEEP))
            data = f.read()
        if st.st_size > AUDIT_KEEP:  # the first bytes read may be the end of a line: drop them
            nl = data.find(b"\n")
            data = data[nl + 1:] if nl >= 0 else b""
        _replace_file(path, data)
    except OSError:
        pass


def audit(tool, args, result, allowed=True, who="agent"):
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "who": who, "tool": tool,
           "args": args, "allowed": allowed, "result": str(result)[:300]}
    path = config.data("audit.log")
    try:
        config.guard_write(path)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with config.data_lock():
            _audit_trim(path, len(line.encode("utf-8")))
            # O_NOFOLLOW: a symlinked audit.log fails with ELOOP and the entry is skipped (the outer OSError handler)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line)
    except OSError:
        pass


def clear_audit():
    """Empty the activity log ("clear the activity log"). False if it could not be cleared (a link, a locked vault)."""
    path = config.data("audit.log")
    try:
        with config.data_lock():
            try:
                st = os.lstat(path)
            except FileNotFoundError:
                return True
            if not stat.S_ISREG(st.st_mode):
                return False
            _replace_file(path, b"")
            return True
    except OSError:
        return False


def audit_tail(n=15):
    try:
        with open(config.data("audit.log"), encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
    except (OSError, ValueError):
        return []


# ------------------------------------------------------------------ routines
# What the model did for a short request it has seen before (agent._maybe_save_routine decides what is
# safe to keep). Keyed by the request's words, punctuation and case aside; the 300 most recently used stay.

def _routine_key(text):
    return " ".join(re.sub(r"[^\w\s]", " ", str(text).lower()).split())[:160]


def routines():
    r = config.load_json(config.data("routines.json"), {})
    return r if isinstance(r, dict) else {}


def routine(text):
    return routines().get(_routine_key(text))


def clear_routines():
    """Forget every routine ("forget my routines"). A missing file is already cleared. False if it could not be."""
    path = config.data("routines.json")
    try:
        with config.data_lock():
            try:
                config.guard_write(path)
                os.remove(path)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False


@_locked
def save_routine(text, calls):
    r = routines()
    key = _routine_key(text)
    if not key or not calls:
        return
    r[key] = {"request": str(text)[:160], "calls": calls, "ts": time.time(), "used": r.get(key, {}).get("used", 0)}
    if len(r) > 300:
        for k in sorted(r, key=lambda k: r[k].get("last") or r[k].get("ts") or 0)[:len(r) - 300]:
            r.pop(k, None)
    config.save_json(config.data("routines.json"), r)


@_locked
def routine_used(text, ok):
    r = routines()
    key = _routine_key(text)
    if key not in r:
        return
    if ok:
        r[key]["used"] = r[key].get("used", 0) + 1
        r[key]["last"] = time.time()
    else:
        r.pop(key)            # it no longer works: next time the model decides afresh
    config.save_json(config.data("routines.json"), r)


# ------------------------------------------------------------------ inbox

# ---- notes and lists (shopping, to-do, ideas…): plain items the owner adds in words

def notes():
    return config.load_json(config.data("notes.json"), [])


def _save_notes(ns):
    config.save_json(config.data("notes.json"), ns)


def list_name(name):
    n = re.sub(r"\s+", " ", str(name or "").strip().lower().replace("_", " "))
    n = re.sub(r"^(my|the)\s+", "", n)
    n = re.sub(r"\s+list$", "", n)
    n = {"todo": "to-do", "to do": "to-do", "todos": "to-do", "tasks": "to-do", "task": "to-do", "groceries": "shopping",
         "grocery": "shopping", "shop": "shopping", "note": "notes", "": "notes"}.get(n, n)
    return n[:40]


@_locked
def add_note(text, lst="notes"):
    n = {"id": uuid.uuid4().hex[:6], "text": " ".join(str(text).split())[:300], "list": list_name(lst),
         "added": time.strftime("%Y-%m-%d %H:%M"), "done": False}
    cur = notes()
    for c in cur:
        if c["list"] == n["list"] and c["text"].lower() == n["text"].lower() and not c["done"]:
            return c, False
    cur.append(n)
    _save_notes(cur)
    return n, True


def find_note(ref, lst=None):
    ref = " ".join(str(ref).lower().split())
    ref = re.sub(r"^item\s+", "", ref)
    cur = notes()
    # open items first: "tick off milk" means the milk still to buy, not last week's
    pool = sorted([n for n in cur if lst is None or n["list"] == lst], key=lambda n: bool(n["done"]))
    hit = [n for n in pool if n["id"] == ref] or [n for n in pool if n["text"].lower() == ref] or \
          [n for n in pool if ref and ref in n["text"].lower()]
    return hit[0] if hit else None


@_locked
def set_note_done(ref, done=True, lst=None):
    n = find_note(ref, lst)
    if not n:
        return None
    cur = notes()
    for c in cur:
        if c["id"] == n["id"]:
            c["done"] = bool(done)
    _save_notes(cur)
    return n


@_locked
def remove_note(ref, lst=None):
    """Remove one item (by id or words); ref 'all' clears the list (or every list)."""
    cur = notes()
    if str(ref).strip().lower() in ("all", "everything", "*"):
        keep = [n for n in cur if lst is not None and n["list"] != lst]
        _save_notes(keep)
        return len(cur) - len(keep)
    n = find_note(ref, lst)
    if not n:
        return 0
    _save_notes([c for c in cur if c["id"] != n["id"]])
    return 1


def lists():
    return sorted({n["list"] for n in notes()})


@_locked
def notify(title, text, alarm=False, replace=False):
    """replace: an older unseen note with the same title is superseded (one "Updated" row, not one per update)."""
    path = config.data("inbox.json")
    cur = config.load_json(path, [])
    if replace:
        for m in cur:
            if m.get("title") == title and not m.get("seen"):
                m["seen"] = True
    cur.append({"id": uuid.uuid4().hex[:8], "ts": time.time(), "title": title,
                "text": text, "seen": False, **({"alarm": True} if alarm else {})})
    config.save_json(path, cur[-200:])


def unseen():
    return [m for m in config.load_json(config.data("inbox.json"), []) if not m.get("seen")]


@_locked
def mark_seen(ids):
    path = config.data("inbox.json")
    cur = config.load_json(path, [])
    for m in cur:
        if m["id"] in ids:
            m["seen"] = True
    config.save_json(path, cur)


@_locked
def mark_rung(ids):
    """Announced (toast, chime, the reminder's own window): a restart shows the card again but does not ring again."""
    path = config.data("inbox.json")
    cur = config.load_json(path, [])
    for m in cur:
        if m["id"] in ids:
            m["rung"] = True
    config.save_json(path, cur)


# ------------------------------------------------------------------ time parsing

WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
UNITS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600,
         "day": 86400, "week": 604800}
NUMWORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
            "thirty": 30, "forty-five": 45, "few": 3, "couple": 2}
DAYPARTS = {"morning": (8, 0), "noon": (12, 0), "midday": (12, 0), "afternoon": (15, 0),
            "evening": (18, 0), "tonight": (20, 0), "night": (21, 0), "midnight": (0, 0)}


class WhenError(ValueError):
    pass


def _clock(text):
    """Find a clock time. Returns (h, m) or None."""
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", text)
    if not m:
        m = re.search(r"\b(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)", text)
        if m:
            h, mi, ap = int(m.group(1)), 0, m.group(2)
        else:
            m = re.search(r"\bat\s+(\d{1,2})\b(?!\s*(?:minutes?|hours?|days?|mins?|hrs?))", text)
            if not m:
                return None
            h, mi, ap = int(m.group(1)), 0, None
    else:
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap:
        ap = ap.replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
    elif h < 12 and any(w in text for w in ("evening", "night", "tonight", "afternoon")):
        h += 12
    elif 1 <= h <= 7 and "morning" not in text and "early" not in text:
        h += 12              # "at 3" means 3 in the afternoon; 3 in the night is said so ("3 am", "early morning")
    if not (0 <= h < 24 and 0 <= mi < 60):
        raise WhenError(f"'{h}:{mi:02d}' is not a valid time")
    return h, mi


def _daypart(text):
    for w, hm in DAYPARTS.items():
        if re.search(rf"\b{w}\b", text):
            return hm
    return None


def next_occurrence(spec, after):
    """Next run strictly after `after` (a local datetime)."""
    kind = spec["kind"]
    if kind == "interval":
        return after + dt.timedelta(seconds=spec["seconds"])
    h, mi = spec["h"], spec["m"]
    days = spec.get("days")  # None = every day
    cand = after.replace(hour=h, minute=mi, second=0, microsecond=0)
    for _ in range(9):
        if cand > after and (days is None or cand.weekday() in days):
            return cand
        cand += dt.timedelta(days=1)
    raise WhenError("could not compute the next run")


def parse_when(text, now=None):
    """Plain-language time -> (first_run: datetime, repeat_spec or None)."""
    now = now or dt.datetime.now()
    s = " " + str(text).lower().strip() + " "
    s = s.replace("everyday", "every day").replace(" each ", " every ")
    s = re.sub(r"\bdaily\b", "every day", s)
    s = re.sub(r"\bhourly\b", "every hour", s)
    s = re.sub(r"\bweekly\b", "every week", s)

    # cron: "M H * * *" or "M H * * D"
    m = re.fullmatch(r"\s*(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+([\d,*-]+)\s*", s)
    if m:
        mi, h, dow = int(m.group(1)), int(m.group(2)), m.group(3)
        days = None if dow == "*" else sorted({(int(d) - 1) % 7 for d in dow.split(",") if d.isdigit()})
        spec = {"kind": "daily", "h": h, "m": mi, "days": days}
        return next_occurrence(spec, now), spec

    repeat = " every " in s or s.startswith(" every")
    if repeat:
        # interval: "every 30 minutes", "every hour", "every 2 days" (no clock time)
        m = re.search(r"every\s+(?:(\d+)\s*|([a-z-]+)\s+)?(second|sec|minute|min|hour|hr|day|week)s?\b", s)   # ("every monday" is a weekday)
        if m and not _clock(s) and not _daypart(s):
            n = int(m.group(1)) if m.group(1) else NUMWORDS.get(m.group(2) or "", 1)
            secs = max(60, n * UNITS[m.group(3)])
            spec = {"kind": "interval", "seconds": secs}
            return now + dt.timedelta(seconds=secs), spec
        days = None
        if "weekday" in s:
            days = [0, 1, 2, 3, 4]
        elif "weekend" in s:
            days = [5, 6]
        else:
            found = sorted({d for w, d in WEEKDAYS.items() if re.search(rf"\b{w}s?\b", s)})
            if found:
                days = found
        hm = _clock(s) or _daypart(s) or (9, 0)
        if " week " in s and days is None:
            days = [now.weekday()]
        spec = {"kind": "daily", "h": hm[0], "m": hm[1], "days": days}
        return next_occurrence(spec, now - dt.timedelta(seconds=1)), spec

    # one-time, relative: "in 20 minutes", "in an hour", "in half an hour"
    if "half an hour" in s:
        return now + dt.timedelta(minutes=30), None
    m = re.search(r"\bin\s+(\d+(?:\.\d+)?|[a-z-]+)\s*(second|sec|minute|min|hour|hr|day|week)s?\b", s)
    if m:
        n = m.group(1)
        n = float(n) if re.match(r"\d", n) else NUMWORDS.get(n)
        if n is None:
            raise WhenError(f"couldn't read the number in '{text}'")
        return now + dt.timedelta(seconds=n * UNITS[m.group(2)]), None
    # "2 minutes", "for 10 minutes", "two hours from now": a length, from now (it was read as the clock time 00:02)
    m = re.fullmatch(r"\s*(?:for\s+|after\s+)?(?:a|an|\d+(?:\.\d+)?|[a-z]+)\s*(second|sec|minute|min|hour|hr|day|week)s?(?:\s+(?:from now|later|time))?\s*", s)
    if m:
        w = re.match(r"\s*(?:for\s+|after\s+)?(\S+)", s).group(1)
        n = 1 if w in ("a", "an") else float(w) if re.match(r"\d", w) else NUMWORDS.get(w)
        if n is not None:
            return now + dt.timedelta(seconds=n * UNITS[m.group(1)]), None

    # one-time, absolute
    day = None
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    elif "tomorrow" in s:
        day = now.date() + dt.timedelta(days=1)
    elif "today" in s or "tonight" in s:
        day = now.date()
    else:
        for w, d in WEEKDAYS.items():
            if re.search(rf"\b{w}\b", s):
                ahead = (d - now.weekday()) % 7
                hm0 = _clock(s) or _daypart(s) or (9, 0)
                if ahead == 0 and now.replace(hour=hm0[0], minute=hm0[1]) <= now:
                    ahead = 7
                day = now.date() + dt.timedelta(days=ahead)
                break
    hm = _clock(s) or _daypart(s)
    if day is None and hm is None:
        raise WhenError(f"I couldn't understand the time '{text}'")
    if hm is None:
        hm = (9, 0)
    if day is None:
        cand = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if cand <= now:
            cand += dt.timedelta(days=1)
        return cand, None
    return dt.datetime.combine(day, dt.time(hm[0], hm[1])), None


def describe(spec, first):
    if not spec:
        # within the hour: how long, then the clock time ("02:36" alone read as seconds away when it was a minute)
        mins = (first - dt.datetime.now()).total_seconds() / 60
        if 0 < mins < 60:
            n = max(1, round(mins))
            near = first + dt.timedelta(seconds=30)        # 04:02:45 is said as 04:03 (it rang "late" at 04:02)
            return f"in {n} minute{'s' if n != 1 else ''} ({near.strftime('%H:%M')})"
        return first.strftime("%a %d %b %H:%M")
    if spec["kind"] == "interval":
        s = spec["seconds"]
        for unit, n in (("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60)):
            if s % n == 0:
                k = s // n
                return f"every {unit}" if k == 1 else f"every {k} {unit}s"
        return f"every {s // 60} minutes"
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = spec.get("days")
    when = "every day" if days is None else "weekdays" if days == [0, 1, 2, 3, 4] else \
        "weekends" if days == [5, 6] else "every " + "/".join(names[d] for d in days)
    return f"{when} at {spec['h']:02d}:{spec['m']:02d}"


# ------------------------------------------------------------------ tasks

def tasks():
    return config.load_json(config.data("tasks.json"), [])


def _save_tasks(ts):
    config.save_json(config.data("tasks.json"), ts)


EVENTS = {"unlock": r"\b(?:every time|each time|whenever|when|after|as soon as)\b.*\b(?:unlock|log ?in|sign in|log on|come back|"
                     r"start (?:up|the computer)|turn (?:it|the computer) on|boot)|\bat (?:login|log ?in|start ?up|unlock)\b|\bon (?:unlock|login|start ?up)\b"}


def event_of(when):
    """'every time I unlock the computer' -> 'unlock' (a task that runs on that event, not at a time), else None."""
    for ev, rx in EVENTS.items():
        if re.search(rx, str(when or ""), re.I):
            return ev
    return None


@_locked
def add_task(when, task, kind="agent", approved=False):
    """kind: "agent" (the model carries the task out), "timer" (task = its length, e.g. "10 minutes"),
    "reminder" (task = the words to show); timers and reminders are delivered as they are, no model.
    A 'when' that names an event ("every time I unlock") makes a task that runs on that event instead."""
    ev = event_of(when)
    if ev:
        t = {"id": uuid.uuid4().hex[:6], "task": task.strip(), "when": when, "kind": kind if kind in ("reminder",) else "agent",
             "event": ev, "spec": None, "next": None, "created": time.time(),
             "desc": {"unlock": "every time you unlock"}[ev], "approved": bool(approved)}
        cur = tasks()
        cur.append(t)
        _save_tasks(cur)
        return t
    first, spec = parse_when(when)
    t = {"id": uuid.uuid4().hex[:6], "task": task.strip(), "when": when, "kind": kind if kind in ("timer", "reminder") else "agent",
         "spec": spec, "next": first.timestamp(), "created": time.time(),
         "desc": describe(spec, first), "approved": bool(approved)}
    cur = tasks()
    cur.append(t)
    _save_tasks(cur)
    return t


def _same_words(text):
    """'shutdown', 'shut-down' and 'shut the computer down' name the same thing: compare by the words that matter."""
    t = re.sub(r"[-_]", " ", str(text).lower())
    t = re.sub(r"\bshut (?:the |my )?(?:computer|pc|laptop|machine|it)\s*down\b", "shut down", t)
    t = re.sub(r"\bshutdown\b|\bpower off\b|\bturn (?:it |the computer |the pc |my computer )?off\b", "shut down", t)
    t = re.sub(r"\b(?:the|a|an|my|every|each|task|reminder|alarm|please|to|for|of|about)\b", " ", t)
    return " ".join(t.split())


@_locked
def cancel_task(ref):
    ref = str(ref).lower().strip()
    cur = tasks()
    hit = [t for t in cur if t["id"] == ref]
    if not hit and ref:
        want = _same_words(ref)
        words = set(want.split())
        hit = [t for t in cur if want and want in _same_words(t["task"])] or \
              [t for t in cur if ref in t["task"].lower()] or \
              [t for t in cur if words and words <= set(_same_words(t["task"]).split())]   # every word given appears, any order
    if ref in ("all", "everything"):
        hit = cur
    _save_tasks([t for t in cur if t not in hit])
    return hit


def due(now=None):
    now = now or time.time()
    return [t for t in tasks() if t.get("next") and t["next"] <= now]


def on_event(ev):
    """The tasks that run on this event ('unlock')."""
    return [t for t in tasks() if t.get("event") == ev]


@_locked
def finished(task_id, result):
    cur = tasks()
    for t in cur:
        if t["id"] != task_id:
            continue
        t["last_run"] = time.time()
        t["last_result"] = str(result)[:500]
        if t.get("event"):
            continue                      # an event task stays until it is cancelled
        if t.get("spec"):
            nxt = next_occurrence(t["spec"], dt.datetime.now())
            t["next"] = nxt.timestamp()
        else:
            t["next"] = None
    _save_tasks([t for t in cur if t.get("next") or t.get("event")])
