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
    r"distracting|websites|sites)|stop focus|end focus|double[- ]?clicks?|sticky keys|hands? (?:shake|shaking|tremor)|tremor|"
    r"(?:startup|start-up|boot|notification|clicking|click|system|alert) sounds?|the chime|chime (?:on|off)|"
    r"when i (?:log ?in|sign in|start (?:up|the computer))|automatically|autostart|start(?:s)? (?:up )?with the computer|startup (?:programs|apps)|"
    r"vpn|wireguard|openvpn|proxy|"
    r"\bcd\b|\bdvd\b|blu-?ray|disc drive|"
    r"on (?:my |the )?tv|chromecast|cast (?:to|this|my)|airplay|"
    r"colou?r ?blind|colou?r filter|deuteranop|protanop|tritanop|profile (?:picture|photo|pic)|avatar|screen ?saver|clock when idle|"
    r"\.exe\b|windows (?:program|app|software|game)s?|\.deb\b|appimage|"
    r"(?:keep|stay|put) (?:this |it |the window )?(?:always )?on top|always on top|picture[- ]in[- ]picture|\bpip\b)", re.I)


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
        r = subprocess.run(["apk", "add", "-q", need], capture_output=True, text=True, timeout=600)
        desk.emit({"t": "toast", "text": "", "sticky": "vpn"})
        if r.returncode != 0:
            return _say(desk, line, f"Couldn't get the VPN program ({need}): {(r.stderr or r.stdout).strip()[-150:]}")
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
        r = subprocess.run(["openvpn", "--config", f, "--daemon", "llmos-vpn"], capture_output=True, text=True, timeout=60)
        time.sleep(6)
        ok = r.returncode == 0 and subprocess.run(["pgrep", "-x", "openvpn"], capture_output=True).returncode == 0
        err = [(r.stderr or r.stdout).strip()[-150:]] if not ok else []
    if not ok:
        return _say(desk, line, f"The VPN from {os.path.basename(f)} didn't connect: {' '.join(err) or 'no answer from its server'}.")
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
    (r"(?:keep|stay|put|make) (?:this |it |that |the \w+ )?(?:window )?(?:always )?on top|always on top|picture[- ]in[- ]picture|\bpip\b",
     "Click the window, then press Super+T: it stays above the others (Super+T again to undo). For a video in Firefox, hover over it and click the "
     "picture-in-picture button: it floats in a small window that stays on top while you work."),
]


def howto(desk, line, low):
    for rx, text in HOWTO:
        if re.search(rx, low):
            return _say(desk, line, text)
    return False


def handle(desk, line):
    low = line.lower().strip().rstrip("?.!")
    for fn in (focus, days_until, sites, work_timer, ports, web_server, health, hostname, access, sounds, autostart, vpn, discs, howto):
        try:
            if fn(desk, line, low):
                return True
        except Exception as e:  # an everyday helper must never break the desk
            desk.instant_reply(line, f"That didn't work: {e}")
            return True
    return False
