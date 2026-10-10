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
    pass


def _curl_base(timeout):
    cmd = ["curl", "-sS", "-L", "--compressed", "--max-time", str(timeout),
           "--max-redirs", "5", "-A", UA, "-H", "Accept-Language: en;q=0.9,*;q=0.5",
           "--proto", "=http,https"]
    if config.settings.get("tor"):
        cmd += ["--socks5-hostname", TOR_PROXY]
    return cmd


def fetch(url, max_bytes=3_000_000, timeout=15,data=None, dest=None):
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
        raise WebError(f"DuckDuckGo returned {status}")
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
        out.append({"title": _text(m.group(2)), "url": href, "snippet": _text(sn.group(1)) if sn else ""})
    return out


def _search_brave(query):
    url = "https://search.brave.com/search?" + urllib.parse.urlencode({"q": query, "source": "web"})
    status, _, _, body = fetch(url, timeout=10)
    page = body.decode("utf-8", "replace")
    if status != 200:
        raise WebError(f"Brave returned {status}")
    out = []
    for block in page.split('data-type="web"')[1:]:
        block = block[:6000]
        m = re.search(r'<a href="(https?://[^"]+)"[^>]*class="[^"]*\bl1\b', block)
        t = re.search(r'class="title[^"]*"[^>]*title="([^"]+)"', block)
        if not m or not t:
            continue
        rest = block[t.end():]
        desc = _text(re.sub(r"<cite.*?</cite>", "", rest))[:300]
        out.append({"title": html.unescape(t.group(1)), "url": m.group(1), "snippet": desc})
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
            if isinstance(e, (WebError, OSError)):
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
    if finished < len(engines):
        raise WebError("the search took too long")
    raise WebError("; ".join(errors[i] for i in sorted(errors)) or "no results")


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
        raise WebError(f"HTTP {status} from {final}")
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
        raise WebError(f"Wikimedia returned {status}")
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
