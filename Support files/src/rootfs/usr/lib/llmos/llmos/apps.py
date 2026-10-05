"""Small apps the owner asks for ("make me a calculator", "a pink timer", "an app that tracks my water").

An app is one HTML file shown in a window on the desk, inside a sandbox: its own scripts run, but it cannot reach
the network, the desk or the owner's files. It keeps what it needs (a note, a to-do list, a drawing) through the
OS (LLMOS.save / LLMOS.load), inside the owner's data. Common apps come ready-made in /usr/share/llmos/apps and
are themed to the request in an instant; anything else is written by the model.
"""
import html
import json
import os
import re
import time

from . import config, llm, ui

SHARE = os.path.join(config.SHARE, "apps")
MAX_STATE = 4 * 1024 * 1024
MAX_HTML = 400 * 1024


def apps_dir():
    d = os.path.join(config.home(), "Apps")
    config.guard_write(d)
    os.makedirs(d, exist_ok=True)
    return d


def _meta(text):
    m = re.search(r"<!--\s*llmos-app:(.*?)-->", text, re.S)
    out = {}
    if m:
        for part in m.group(1).split(";"):
            k, _, v = part.partition("=")
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def templates():
    out = []
    try:
        names = sorted(os.listdir(SHARE))
    except OSError:
        return out
    for n in names:
        if n.endswith(".html"):
            with open(os.path.join(SHARE, n), encoding="utf-8") as f:
                m = _meta(f.read(4000))
            if m.get("id"):
                m["words"] = m.get("words", "").split()
                out.append(m)
    return out


def match_template(what):
    """The ready-made app a request means ('a calculator', 'stopwatch', 'world clock'), or None."""
    w = " " + re.sub(r"[^a-z0-9 ]+", " ", str(what).lower()) + " "
    best, score = None, 0
    for t in templates():
        for word in [t["id"]] + t["words"]:
            word = re.sub(r"[^a-z0-9 ]+", " ", word.lower()).strip()
            if f" {word} " in w and len(word) > score:
                best, score = t, len(word)
    return best


def installed():
    """The owner's apps: [{id, title, size, file, made}] newest first."""
    out = []
    try:
        d = apps_dir()
    except OSError:
        return out
    for n in os.listdir(d):
        if not n.endswith(".html"):
            continue
        p = os.path.join(d, n)
        try:
            with open(p, encoding="utf-8") as f:
                m = _meta(f.read(4000))
        except OSError:
            continue
        out.append({"id": n[:-5], "title": m.get("title") or n[:-5], "size": m.get("size") or "m", "file": p,
                    "made": os.path.getmtime(p)})
    return sorted(out, key=lambda a: -a["made"])


def find(name):
    """An installed app by id or title words ('calculator', 'my pink timer')."""
    n = re.sub(r"[^a-z0-9 ]+", " ", str(name).lower()).strip()
    n = re.sub(r"\b(the|my|app|application|program|open|launch|start)\b", " ", n).strip()
    if not n:
        return None
    apps = installed()
    for a in apps:
        if n in (a["id"], a["title"].lower()):
            return a
    for a in apps:
        if all(w in (a["id"] + " " + a["title"].lower()) for w in n.split()):
            return a
    t = match_template(n)
    if t:
        for a in apps:
            if a["id"] == t["id"] or a["id"].startswith(t["id"] + "-"):
                return a
    return None


# ---- the look: words -> colours and type

PALETTES = [  # (words, bg, fg, accent, font)
    (("retro", "terminal", "hacker", "matrix", "green screen", "crt", "8-bit", "8 bit"), "#031a07", "#3cff6e", "#3cff6e", "mono"),
    (("neon", "cyberpunk", "synthwave", "vaporwave", "futuristic"), "#0d0221", "#f6e7ff", "#ff2bd6", ""),
    (("pastel", "cute", "soft", "kawaii"), "#fff4fa", "#4a3b4f", "#f08bb4", ""),
    (("ocean", "sea", "aqua", "underwater"), "#061a2b", "#dff3ff", "#2ec4f1", ""),
    (("sunset", "warm", "autumn", "fall"), "#2a1210", "#ffe8d6", "#ff7a3d", ""),
    (("forest", "nature", "earthy", "woods"), "#0f1f14", "#e3f2e1", "#5cbf73", ""),
    (("minimal", "clean", "simple", "white", "paper"), "#ffffff", "#111111", "#111111", ""),
    (("gold", "luxury", "elegant", "classy"), "#121008", "#f5ecd0", "#d4af37", "serif"),
    (("light", "bright", "day"), "#f6f6f8", "#16171d", "#5b5bd6", ""),
    (("dark", "night", "black", "midnight"), "#0e1016", "#e8e9ef", "#7c5cff", ""),
]
FONTS = {"mono": "'JetBrains Mono', monospace", "serif": "'Noto Serif', serif", "sans": "Inter, 'Noto Sans', sans-serif",
         "pixel": "Terminus, 'JetBrains Mono', monospace"}


def look(words="", desk_theme=None):
    """CSS variables for an app from the owner's words ('retro green', 'pink and big buttons', 'like a typewriter'),
    starting from the desk's own colours."""
    w = " " + str(words or "").lower() + " "
    th = desk_theme or ui.Theme()
    hx = lambda c: "#%02x%02x%02x" % tuple(int(x) for x in c)
    sysfont = (config.settings.get("appearance", {}) or {}).get("font") or "sans"
    bg, fg, acc, font = (hx(th.bg) if th.bg else "#0e1016"), (hx(th.fg) if th.fg else "#e8e9ef"), (hx(th.acc) if th.acc else "#7c5cff"), \
        (sysfont if sysfont in FONTS else "sans")
    for names, b, f, a, fo in PALETTES:
        if any(f" {n} " in w or f" {n}-" in w for n in names):
            bg, fg, acc = b, f, a
            font = fo or font
            break
    # a colour named on its own is the accent ("a pink timer", "calculator in orange")
    for word in re.findall(r"[a-z]+|#[0-9a-f]{6}", w):
        c = ui.parse_color(word)
        if c and word not in ("dark", "light", "white", "black"):
            acc = hx(c)
            if " dark " not in w and " light " not in w and acc != bg:
                pass
            break
    if any(k in w for k in ("monospace", "typewriter", "code", "coder", "programmer", "pixel")):
        font = "mono"
    elif any(k in w for k in ("serif", "classic", "book", "old-fashioned", "old fashioned", "fancy")):
        font = "serif"
    scale = 1.25 if any(k in w for k in (" big ", " large ", " huge ", "bigger", "easy to read", "elderly", "accessible")) else 1.0
    radius = "0px" if any(k in w for k in ("square", "sharp", "boxy", "brutal")) else "22px" if any(k in w for k in ("round", "bubbly", "pill")) else "12px"
    lum = lambda h: (0.2126 * int(h[1:3], 16) + 0.7152 * int(h[3:5], 16) + 0.0722 * int(h[5:7], 16)) / 255
    on = "#000000" if lum(acc) > 0.6 else "#ffffff"
    return {"--bg": bg, "--fg": fg, "--accent": acc, "--on-accent": on, "--font": FONTS[font], "--mono": FONTS["mono"],
            "--card": f"color-mix(in srgb, {fg} 8%, {bg})", "--line": f"color-mix(in srgb, {fg} 16%, {bg})",
            "--dim": f"color-mix(in srgb, {fg} 60%, {bg})", "--r": radius, "--scale": str(scale)}


# what every app gets: no network, the look, the base styles and the save/load bridge to the OS
_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
        "media-src data: blob:; font-src file:; connect-src 'none'; form-action 'none'")
_BASE = """
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--fg);font-family:var(--font);font-size:calc(16px * var(--scale));padding:16px;line-height:1.4;overflow:auto}
button,input,select,textarea{font:inherit;color:inherit}
button{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:9px 14px;cursor:pointer;transition:filter .12s,transform .06s}
button:hover{filter:brightness(1.15)}button:active{transform:scale(.97)}
button.primary{background:var(--accent);color:var(--on-accent);border-color:transparent}
input,select{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:8px 10px}
input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
h1,h2,h3{margin:.2em 0 .5em}
"""
_BRIDGE = """
window.LLMOS={_cb:null,
 load(cb){this._cb=cb;parent.postMessage({llmos:"load"},"*");setTimeout(()=>{if(this._cb){const c=this._cb;this._cb=null;c(null)}},1500)},
 save(state){try{parent.postMessage({llmos:"save",state},"*")}catch(e){}},
 export(name,data){parent.postMessage({llmos:"export",name,data},"*")}};
addEventListener("message",e=>{const m=e.data||{};if(m.llmos==="state"&&LLMOS._cb){const c=LLMOS._cb;LLMOS._cb=null;c(m.state)}});
"""


def look_label(words):
    """A short name for a look: 'Forest', 'Pink', 'Retro green' (shown in the app's title)."""
    w = re.sub(r"\b(theme|look|looking|style|styled|colou?rs?|with|and|a|an|the|mode|buttons?|big|large|font)\b", " ", str(words).lower())
    w = re.sub(r"\s+", " ", w).strip()
    return (w[:20].strip() or "custom").capitalize()


def wrap(body, title, vars_):
    """A complete, sandbox-ready document around an app's own markup."""
    root = ";".join(f"{k}:{v}" for k, v in vars_.items())
    head = (f'<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{_CSP}">'
            f"<title>{html.escape(title)}</title><style>:root{{{root}}}{_BASE}</style><script>{_BRIDGE}</script></head><body>")
    return head + body + "</body></html>"


def _strip_doc(text):
    """An app's markup without its own <html>/<head> shell (the OS supplies one) or any network-loading tags."""
    t = re.sub(r"(?is)<!doctype[^>]*>|</?html[^>]*>|</?body[^>]*>|<head[^>]*>.*?</head>", "", text)
    t = re.sub(r'(?is)<meta[^>]+http-equiv[^>]*>', "", t)
    t = re.sub(r'(?is)<script[^>]+src=[^>]*>\s*</script>|<link[^>]+>', "", t)      # no outside scripts or styles
    return t.strip()


def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return s[:40] or "app"


def _save(app_id, title, size, body, look_words):
    d = apps_dir()
    base, n = _slug(app_id), 1
    if look_words:                                  # a new look is a new app ("a pink calculator" next to the plain one)
        base = _slug(f"{app_id}-{look_label(look_words)}")
    path = os.path.join(d, base + ".html")
    while os.path.exists(path) and look_words:
        n += 1
        path = os.path.join(d, f"{base}-{n}.html")
    meta = f"<!-- llmos-app: id={os.path.basename(path)[:-5]}; title={title}; size={size}; look={look_words} -->"
    doc = meta + wrap(body, title, look(look_words))
    config.guard_write(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return {"id": os.path.basename(path)[:-5], "title": title, "size": size, "file": path, "made": time.time()}


def from_template(t, look_words="", what=""):
    with open(os.path.join(SHARE, t["id"] + ".html"), encoding="utf-8") as f:
        body = re.sub(r"<!--\s*llmos-app:.*?-->", "", f.read(), count=1, flags=re.S)
    title = t.get("title", t["id"])
    if t["id"] == "tracker" and what:
        # the tracker sets itself up from its title: "Water tracker" counts glasses, "Budget tracker" dollars
        w = re.sub(r"\b(a|an|the|my|me|app|make|create|build|for|to|please|i|want|need)\b", " ", str(what).lower())
        w = " ".join(w.split())[:30]
        if w and w != "tracker":
            title = w[:1].upper() + w[1:] + ("" if "track" in w or "log" in w else " tracker")
    app_id = t["id"] if title == t.get("title", t["id"]) else _slug(title)
    if look_words:
        title = f"{title} · {look_label(look_words)}"
    return _save(app_id, title, t.get("size", "m"), body, look_words)


GEN_SYSTEM = """You write one small, complete, working app as a single HTML fragment for a sandboxed window.
Rules:
- Output ONLY the fragment: <style>…</style> then the markup then <script>…</script>. No <html>, <head>, <body>, no markdown fences, no explanations.
- No network at all: no external scripts, fonts, images or fetch(). Draw with CSS, emoji, SVG or canvas.
- Use these CSS variables for every colour and the font: var(--bg) var(--fg) var(--accent) var(--on-accent) var(--card) var(--line) var(--dim) var(--font); var(--r) is the corner radius. The body already has padding and the base button/input styles; buttons with class "primary" use the accent.
- To keep data between uses call LLMOS.save(objectOfState) whenever it changes, and at start LLMOS.load(function(state){ ... }) (state is null the first time). Never use localStorage, cookies or IndexedDB (they are unavailable).
- It must work with mouse and keyboard, fit a 520x560 window, and be genuinely useful and polished, with clear labels.
- Plain modern JavaScript, no frameworks. Make sure there are no syntax errors."""


def generate(what, look_words="", use_cloud=None):
    """Have the model write an app. Returns (app, note) or (None, reason)."""
    user = f"Make this app: {what}\nLook: {look_words or 'match the system (use the variables)'}"
    msgs = [{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": user}]
    try:
        if use_cloud:
            r = llm.cloud_chat(msgs, max_tokens=6000, temperature=0.2)
        else:
            r = llm.chat(msgs, max_tokens=3500, temperature=0.2, think=False)
    except Exception as e:
        return None, f"the model could not write it: {e}"
    text = (r.get("content") or "").strip()
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text.strip(), flags=re.I)
    body = _strip_doc(text)
    if len(body) < 200 or "<script" not in body.lower() or len(body) > MAX_HTML:
        return None, "the model's attempt was not a working app"
    if re.search(r"(?i)\bfetch\(|XMLHttpRequest|WebSocket|localStorage|document\.cookie", body):
        body = re.sub(r"(?i)localStorage\.setItem\([^;]*\);?", "", body)
    m = re.search(r"(?i)<h1[^>]*>(.*?)</h1>", body)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip()[:40] if m else str(what).strip()[:40].capitalize()
    return _save(_slug(title), title or "App", "m", body, look_words), "written by the model"


def retheme():
    """Apps made without a look of their own follow the system's look (dark mode reaches them too)."""
    vars_ = look("")
    root = ";".join(f"{k}:{v}" for k, v in vars_.items())
    n = 0
    for a in installed():
        try:
            with open(a["file"], encoding="utf-8") as f:
                doc = f.read()
        except OSError:
            continue
        m = _meta(doc[:4000])
        if m.get("look"):
            continue
        new = re.sub(r"<style>:root\{[^}]*\}", "<style>:root{" + root + "}", doc, count=1)
        if new != doc:
            with open(a["file"], "w", encoding="utf-8") as f:
                f.write(new)
            n += 1
    return n


def state_path(app_id):
    d = os.path.join(config.data_dir(), "app-state")
    config.guard_write(d)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, _slug(app_id) + ".json")


def load_state(app_id):
    try:
        with open(state_path(app_id), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_state(app_id, state):
    data = json.dumps(state, ensure_ascii=False)
    if len(data) > MAX_STATE:
        return False
    p = state_path(app_id)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(p + ".tmp", p)
    return True


def remove(app_id):
    a = find(app_id)
    if not a:
        return None
    os.remove(a["file"])
    try:
        os.remove(state_path(a["id"]))
    except OSError:
        pass
    return a
