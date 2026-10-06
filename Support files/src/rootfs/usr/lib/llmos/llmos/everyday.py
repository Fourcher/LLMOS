"""Everyday requests the OS answers or does itself, at once, without the model (found by the use-case runs):
days until a date, a work-hours timer, what is using a port (and stopping it), a local web server / HTML preview,
temperatures, battery and disk health, parcel tracking, typing and language practice, the computer's name, and a
focus mode that blocks distracting sites for a while.

handle(desk, line) -> True when it answered. MATCH is a quick test the desk uses to decide the request is instant."""
import datetime as dt
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import urllib.parse

from . import config

MATCH = re.compile(
    r"\b(?:days? (?:until|till|to|left)|countdown|how long (?:until|till)|work timer|clock (?:in|out)|track(?:ing)? (?:my )?(?:hours|time)|"
    r"hours (?:did i|have i) work|port \d+|on \d{2,5}\b|web ?server|serve (?:this|the)|preview (?:this|the|my)|temperature|"
    r"(?:too |so |very |running |getting )?hot\b|overheat|battery (?:health|dying|dead|draining|drains|life|is draining)|"
    r"drive health|disk health|hard ?drive (?:health|failing|dying|ok)|ssd health|smart status|track (?:my )?(?:parcel|package|order|delivery)|"
    r"order status|where is my (?:parcel|package|order)|typing (?:practice|tutor|lessons?|test)|teach me to type|learn (?:to type|\w+ish|french|spanish|german|"
    r"italian|japanese|chinese|korean|portuguese|arabic|russian|hindi|dutch)|computer(?:'?s)? name|hostname|name (?:this|the) computer|"
    r"call this computer|rename (?:this|the) computer|focus mode|block (?:youtube|facebook|instagram|tiktok|reddit|twitter|social media|"
    r"distracting|websites|sites)|stop focus|end focus)\b", re.I)


def _say(desk, line, text):
    desk.instant_reply(line, text)
    return True


def _open(desk, url):
    from . import agent
    agent.execute(desk.ctx, "browse", {"site": url})


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
             "new year": lambda y: dt.date(y, 1, 1), "new years": lambda y: dt.date(y, 1, 1), "new year's": lambda y: dt.date(y, 1, 1),
             "new year's eve": lambda y: dt.date(y, 12, 31), "new years eve": lambda y: dt.date(y, 12, 31), "halloween": lambda y: dt.date(y, 10, 31),
             "valentine's day": lambda y: dt.date(y, 2, 14), "valentines day": lambda y: dt.date(y, 2, 14), "valentines": lambda y: dt.date(y, 2, 14),
             "the fourth of july": lambda y: dt.date(y, 7, 4), "fourth of july": lambda y: dt.date(y, 7, 4), "independence day": lambda y: dt.date(y, 7, 4),
             "thanksgiving": _thanksgiving, "easter": _easter, "st patrick's day": lambda y: dt.date(y, 3, 17), "st patricks day": lambda y: dt.date(y, 3, 17)}
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                       "november", "december"], 1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9


def _date_of(words, today):
    w = words.strip().lower().rstrip("?.! ").removeprefix("the ")
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
    if re.search(r"\b(?:start|begin|resume)(?:ing)? (?:the |my |a )?(?:work )?timer|clock in|start tracking|track(?:ing)? (?:my )?(?:hours|time)$|^track my hours", low):
        if lg["running"]:
            return _say(desk, line, f"The work timer is already running, since {time.strftime('%H:%M', time.localtime(lg['running']))} "
                                    f"({_hm(time.time() - lg['running'])} so far). Say “stop the work timer” to stop it.")
        lg["running"] = time.time()
        _save_log(lg)
        return _say(desk, line, f"Work timer started at {time.strftime('%H:%M')}. Say “stop the work timer” when you stop; "
                                f"today so far: {_hm(_total(lg, midnight))}.")
    if re.search(r"\b(?:stop|end|pause|finish)(?:ing)? (?:the |my )?(?:work )?timer|clock out|stop tracking", low):
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
            return _say(desk, line, f"Nothing is listening on port {port}.")
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
            return _say(desk, line, f"Nothing is listening on port {port}.")
        return _say(desk, line, f"Port {port}: {', '.join(f'{n} (process {p})' for p, n in who)}. Say “kill whatever's on {port}” to stop it.")
    return False


# ------------------------------------------------------------------ local web server

_SERVER = {}


def web_server(desk, line, low):
    from . import tools
    if re.search(r"(?:stop|end|close|kill) (?:the |my )?(?:local )?web ?server|stop serving", low):
        p = _SERVER.pop("p", None)
        if p and p.poll() is None:
            p.terminate()
            return _say(desk, line, "The web server is stopped.")
        return _say(desk, line, "No web server was running.")
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
    return _say(desk, line, f"Serving {shown} at {url} (this computer only); it's open in the browser. Say “stop the web server” to end it.")


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
    if re.search(r"drive|disk|ssd|smart", low):
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
            with open("/etc/hostname", "w") as f:
                f.write(n + "\n")
            subprocess.run(["hostname", n], capture_output=True, timeout=5)
            hosts = open("/etc/hosts").read()
            hosts = re.sub(rf"\b{re.escape(old)}\b", n, hosts)
            with open("/etc/hosts", "w") as f:
                f.write(hosts)
        except OSError as e:
            return _say(desk, line, f"Couldn't rename it: {e}.")
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


def _hosts_block(sites):
    try:
        lines = [ln for ln in open("/etc/hosts").read().splitlines() if _MARK not in ln]
        lines += [f"0.0.0.0 {s} {_MARK}" for s in sites]
        with open("/etc/hosts", "w") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass
    try:   # Firefox may look names up itself (DNS over HTTPS): its own block list too, read when it next starts
        pol = json.load(open(_POLICY))
        if sites:
            pol["policies"]["WebsiteFilter"] = {"Block": [f"*://{s}/*" for s in sites] + [f"*://*.{s}/*" for s in sites if not s.startswith("www.")]}
        else:
            pol["policies"].pop("WebsiteFilter", None)
        with open(_POLICY, "w") as f:
            json.dump(pol, f, indent=2)
    except (OSError, ValueError, KeyError):
        pass


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
    if not m:
        return False
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


def handle(desk, line):
    low = line.lower().strip().rstrip("?.!")
    for fn in (focus, days_until, sites, work_timer, ports, web_server, health, hostname):
        try:
            if fn(desk, line, low):
                return True
        except Exception as e:  # an everyday helper must never break the desk
            desk.instant_reply(line, f"That didn't work: {e}")
            return True
    return False
