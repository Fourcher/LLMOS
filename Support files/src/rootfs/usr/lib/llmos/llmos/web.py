"""Web access for research. Only runs when a request needs it and the user's
internet setting allows it. No cookies, no JavaScript, no accounts, no API
keys. With the Tor setting on, every request (DNS included) goes through Tor."""
import html
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.parse

from . import config

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
TOR_PROXY = "127.0.0.1:9050"


class WebError(Exception):
    """A plain-words message for the owner. `status` keeps the HTTP code (or None) for code that inspects it."""

    def __init__(self, message="", status=None):
        super().__init__(message)
        self.status = status


def _status_msg(service, code):
    """The owner's words for a failed HTTP request to `service`."""
    if code == 404:
        return "that page doesn't exist"
    if code == 429:
        return f"{service} is getting too many requests; try again in a minute"
    if 500 <= code <= 599:
        return f"{service} isn't answering right now; try again in a minute"
    if code in (401, 403):
        return f"{service} refused the request"
    return f"{service} didn't answer properly"


def _curl_base(timeout):
    cmd = ["curl", "-sS", "-L", "--compressed", "--max-time", str(timeout),
           "--max-redirs", "5", "-A", UA, "-H", "Accept-Language: en;q=0.9,*;q=0.5",
           "--proto", "=http,https"]
    if config.settings.get("tor"):
        cmd += ["--socks5-hostname", TOR_PROXY]
    return cmd


def fetch(url, max_bytes=3_000_000, timeout=15,data=None, dest=None, ua=None):
    """GET/POST a URL. Returns (status, content_type, final_url, body_bytes)."""
    if not re.match(r"^https?://", url or ""):
        raise WebError("only http(s) URLs are supported")
    from . import system
    if system.is_blocked(url):
        raise WebError("that site is blocked while focus mode is on; turn focus off to open it")
    if dest:
        tmp = dest
    else:
        fd, tmp = tempfile.mkstemp(prefix="llmos-web-")
        os.close(fd)
    cmd = _curl_base(timeout) + ["-o", tmp, "-w", "%{http_code}\n%{content_type}\n%{url_effective}",
                                 "--max-filesize", str(max_bytes if dest is None else 4_000_000_000)]
    if data is not None:
        cmd += ["--data", urllib.parse.urlencode(data)]
    if ua:
        cmd += ["-A", ua]                 # a later -A wins over the browser one in _curl_base
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 and not os.path.exists(tmp):
        raise WebError((p.stderr.strip() or f"curl exit {p.returncode}")[:300])
    meta = (p.stdout or "").split("\n")
    status = int(meta[0]) if meta and meta[0].isdigit() else 0
    ctype = meta[1] if len(meta) > 1 else ""
    final = meta[2] if len(meta) > 2 else url
    if dest:
        return status, ctype, final, b""
    try:
        with open(tmp, "rb") as f:
            body = f.read(max_bytes)
    except OSError:
        body = b""
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if p.returncode != 0 and not body:
        raise WebError((p.stderr.strip() or f"curl exit {p.returncode}")[:300])
    return status, ctype, final, body


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _search_ddg(query):
    status, _, _, body = fetch("https://html.duckduckgo.com/html/", data={"q": query}, timeout=10)
    page = body.decode("utf-8", "replace")
    if status != 200 or "result__a" not in page:
        raise WebError(_status_msg("DuckDuckGo", status), status)
    out = []
    for block in page.split('class="result ')[1:]:
        if "result--ad" in block[:200]:
            continue
        m = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        href = html.unescape(m.group(1))
        if href.startswith("//duckduckgo.com/l/"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse("https:" + href).query)
            href = q.get("uddg", [href])[0]
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        out.append({"title": _text(m.group(2)), "url": href, "snippet": _clean_snippet(_text(sn.group(1)), _text(m.group(2))) if sn else ""})
    return out


_AGE = re.compile(r"(?:\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago|"
                  r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4})\s+[-\u2013\u2014]\s+")


def _clean_snippet(desc, title=""):
    """A result's description alone: Brave's markup leaves the title element's tail ('>Rome - Wikipedia') and the
    age ('2 weeks ago - ') in front of it."""
    d = str(desc or "").lstrip("> \t")
    m = _AGE.search(d[:240])
    if m and (m.start() == 0 or (title and d.startswith(title[:12]) and not re.search(r"[.!?]\s", d[:m.start()]))):
        d = d[m.end():]
    elif title and d.startswith(title) and re.search(r" [-|\u2013\u2014] |: ", title):
        d = d[len(title):].lstrip(" -\u2013\u2014|:")
    return d.strip()


def _search_brave(query):
    url = "https://search.brave.com/search?" + urllib.parse.urlencode({"q": query, "source": "web"})
    status, _, _, body = fetch(url, timeout=10)
    page = body.decode("utf-8", "replace")
    if status != 200:
        raise WebError(_status_msg("Brave", status), status)
    out = []
    for block in page.split('data-type="web"')[1:]:
        block = block[:6000]
        m = re.search(r'<a href="(https?://[^"]+)"[^>]*class="[^"]*\bl1\b', block)
        t = re.search(r'class="title[^"]*"[^>]*title="([^"]+)"', block)
        if not m or not t:
            continue
        rest = block[t.end():]
        desc = _text(re.sub(r"<cite.*?</cite>", "", rest))[:300]
        title = html.unescape(t.group(1))
        out.append({"title": title, "url": m.group(1), "snippet": _clean_snippet(desc, title)})
    return out


_WIKI_UA = "LLM-OS/1.8 (personal computer assistant; https://github.com/Fourcher)"
_WIKI_LANG = {"english": "en", "chinese": "zh", "中文": "zh", "spanish": "es", "español": "es", "french": "fr", "français": "fr",
              "german": "de", "deutsch": "de", "japanese": "ja", "日本語": "ja"}


def _search_wikipedia(query, timeout=8):
    """Wikipedia's own search API: free, no key, meant for programs. The fallback when the general engines fail
    or turn a computer away (DuckDuckGo's bot check, Brave's rate limit). Each of the top four hits carries its
    article's opening sentences (its summary, fetched side by side), so they can be compared like with like."""
    try:
        from . import config
        lang = _WIKI_LANG.get(str(config.llm_language() or "English").strip().lower(), "en")
    except Exception:
        lang = "en"
    base = f"https://{lang}.wikipedia.org"
    status, _, _, body = fetch(base + "/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": query, "srlimit": 5, "format": "json", "utf8": 1}), timeout=timeout, ua=_WIKI_UA)
    if status != 200:
        raise WebError(_status_msg("Wikipedia", status), status)
    try:
        hits = json.loads(body.decode("utf-8", "replace")).get("query", {}).get("search", [])
    except ValueError:
        raise WebError("Wikipedia didn't answer properly")
    out = []
    for h in hits:
        title = str(h.get("title") or "")
        out.append({"title": f"{title} - Wikipedia", "url": base + "/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                    "snippet": _text(str(h.get("snippet") or "")) + "…", "_t": title, "fallback": True})

    def summary(r):
        try:
            st, _, _, sb = fetch(base + "/api/rest_v1/page/summary/" + urllib.parse.quote(r["_t"].replace(" ", "_"), safe=""),
                                 timeout=timeout, ua=_WIKI_UA)
            if st == 200:
                r["snippet"] = json.loads(sb.decode("utf-8", "replace")).get("extract") or r["snippet"]
        except (WebError, ValueError, OSError):
            pass

    ts = [threading.Thread(target=summary, args=(r,), daemon=True) for r in out[:4]]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout + 2)
    for r in out:
        r.pop("_t", None)
    return out


def _search_limit():
    try:
        slow = float(os.environ.get("LLMOS_SLOW", "1"))
    except ValueError:
        slow = 1.0
    return 10.0 * slow


def search(query, n=6):
    """Ask both engines at once. The first non-empty result list wins; an empty
    or failed engine does not stop the other one. Waits at most _search_limit()."""
    engines = (_search_ddg, _search_brave)
    done = queue.Queue()

    def run(idx, engine):
        try:
            done.put((idx, engine(query), None))
        except Exception as e:
            if isinstance(e, WebError):
                done.put((idx, None, e))
            elif isinstance(e, OSError):
                done.put((idx, None, str(e)))
            else:
                done.put((idx, None, f"{type(e).__name__}: {e}"))

    for idx, engine in enumerate(engines):
        threading.Thread(target=run, args=(idx, engine), daemon=True).start()

    errors = {}
    deadline = time.monotonic() + _search_limit()
    finished = 0
    while finished < len(engines):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            idx, res, err = done.get(timeout=remaining)
        except queue.Empty:
            break
        finished += 1
        if err is not None:
            errors[idx] = err
            continue
        if res:
            seen, uniq = set(), []
            for r in res:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    uniq.append(r)
            return uniq[:n]
    if finished == len(engines):          # both answered, with an error or nothing (not slow): Wikipedia's API
        try:
            res = _search_wikipedia(query)
            if res:
                return res[:n]
        except (WebError, OSError):
            pass
    if finished < len(engines):
        raise WebError("the search took too long")
    if len(errors) == len(engines) and all(isinstance(errors[i], WebError) for i in errors):
        raise WebError("the search services aren't answering right now; try again in a minute")
    raise WebError("; ".join(str(errors[i]) for i in sorted(errors)) or "no results")


_DROP = re.compile(r"<(script|style|noscript|svg|nav|footer|header|aside|form|iframe|template)\b.*?</\1\s*>", re.S | re.I)
_BLOCK = re.compile(r"<(p|h[1-6]|li|blockquote|pre|td|th|dd|dt|figcaption|article|section|div)\b[^>]*>", re.I)


def readable(page_html, limit=6000):
    """HTML -> (title, main text). Simple and dependency-free."""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.S | re.I)
    if m:
        title = _text(m.group(1))
    body = _DROP.sub(" ", page_html)
    m = re.search(r"<(article|main)\b.*?</\1>", body, re.S | re.I)
    if m and len(_text(m.group(0))) > 400:
        body = m.group(0)
    body = _BLOCK.sub("\n", body)
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    lines = []
    for ln in html.unescape(re.sub(r"<[^>]+>", " ", body)).split("\n"):
        ln = re.sub(r"[ \t\r\f\v]+", " ", ln).strip()
        if len(ln) > 2:
            lines.append(ln)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text[:limit]


def read(url, limit=6000):
    status, ctype, final, body = fetch(url)
    if status >= 400:
        raise WebError(_status_msg(urllib.parse.urlparse(final or "").netloc or "the site", status), status)
    if "html" in ctype or body.lstrip()[:1] == b"<":
        title, text = readable(body.decode("utf-8", "replace"), limit)
        return {"url": final, "title": title, "text": text}
    if ctype.startswith("text/") or "json" in ctype:
        return {"url": final, "title": "", "text": body.decode("utf-8", "replace")[:limit]}
    return {"url": final, "title": "", "text": f"(binary content: {ctype}, {len(body)} bytes)"}


def wikimedia_image(subject):
    """Find a REAL photograph of something (Wikimedia Commons), with credit
    and license, rather than generating one."""
    api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrsearch": subject + " filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 5, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime", "iiurlwidth": 1280})
    status, _, _, body = fetch(api, timeout=20)
    if status != 200:
        raise WebError(_status_msg("Wikimedia", status), status)
    pages = (json.loads(body or b"{}").get("query") or {}).get("pages") or {}
    best = sorted(pages.values(), key=lambda p: p.get("index", 99))
    for p in best:
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii.get("mime", "").startswith("image/") or ii.get("mime") == "image/svg+xml":
            continue
        meta = ii.get("extmetadata") or {}
        return {
            "title": p.get("title", "").removeprefix("File:"),
            "url": ii.get("thumburl") or ii.get("url"),
            "page": ii.get("descriptionurl", ""),
            "author": _text((meta.get("Artist") or {}).get("value", ""))[:120],
            "license": (meta.get("LicenseShortName") or {}).get("value", ""),
        }
    raise WebError("no matching photo found on Wikimedia Commons")
