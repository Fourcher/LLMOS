import hashlib
import json
import os
import re
import urllib.parse

from .. import config, textify
from . import tool, ToolError, s, i, R, N


def _ddg_html(ctx, q, n):
    body = ctx.net.get("https://html.duckduckgo.com/html/", data={"q": q}).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', body, re.S):
        href, title, rest = m.groups()
        u = urllib.parse.urlparse(href.replace("&amp;", "&"))
        real = urllib.parse.parse_qs(u.query).get("uddg", [href])[0]
        if "duckduckgo.com/y.js" in real:
            continue  # ads
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        out.append((textify.strip_tags(title), real, textify.strip_tags(sn.group(1) if sn else "")))
        if len(out) >= n:
            break
    return out


def _ddg_lite(ctx, q, n):
    body = ctx.net.get("https://lite.duckduckgo.com/lite/", data={"q": q}).decode("utf-8", "replace")
    out = []
    links = re.findall(r"<a[^>]+href=\"([^\"]+)\"[^>]+class=['\"]result-link['\"][^>]*>(.*?)</a>", body, re.S)
    snips = re.findall(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", body, re.S)
    for k, (href, title) in enumerate(links[:n]):
        u = urllib.parse.urlparse(href.replace("&amp;", "&"))
        real = urllib.parse.parse_qs(u.query).get("uddg", [href])[0]
        out.append((textify.strip_tags(title), real, textify.strip_tags(snips[k]) if k < len(snips) else ""))
    return out


def _mojeek(ctx, q, n):
    body = ctx.net.get("https://www.mojeek.com/search?q=" + urllib.parse.quote(q)).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<a class="ob" href="([^"]+)"[^>]*>.*?<h2><a[^>]*>(.*?)</a></h2>.*?<p class="s">(.*?)</p>', body, re.S):
        out.append((textify.strip_tags(m.group(2)), m.group(1), textify.strip_tags(m.group(3))))
        if len(out) >= n:
            break
    return out


def _bing(ctx, q, n):
    body = ctx.net.get("https://www.bing.com/search?q=" + urllib.parse.quote(q) + "&setlang=en").decode("utf-8", "replace")
    out = []
    for blk in re.findall(r'<li class="b_algo"(.*?)</li>', body, re.S):
        a = re.search(r'<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not a:
            continue
        sn = re.search(r"<p[^>]*>(.*?)</p>", blk, re.S)
        href = a.group(1).replace("&amp;", "&")
        if "bing.com/ck/a" in href:
            m = re.search(r"[?&]u=a1([^&]+)", href)
            if m:
                import base64
                try:
                    href = base64.urlsafe_b64decode(m.group(1) + "==").decode()
                except Exception:
                    pass
        out.append((textify.strip_tags(a.group(2)), href, textify.strip_tags(sn.group(1)) if sn else ""))
        if len(out) >= n:
            break
    return out


ENGINES = {"duckduckgo": _ddg_html, "duckduckgo-lite": _ddg_lite, "mojeek": _mojeek, "bing": _bing}
ORDER = ["duckduckgo", "duckduckgo-lite", "mojeek", "bing"]


@tool("web_search", "Search the web. Returns titles, URLs and snippets. Use this instead of guessing facts.",
      {"query": s(), "n": i(minimum=1, maximum=10)}, ["query"], klass=N)
def web_search(ctx, query, n=5):
    ctx.require_network()
    pref = (ctx.memory.pref("search_engine") or "").lower()
    order = ([pref] if pref in ENGINES else []) + [e for e in ORDER if e != pref]
    errors = []
    for name in order:
        try:
            res = ENGINES[name](ctx, query, n)
        except Exception as e:
            errors.append("%s: %s" % (name, str(e)[:80]))
            continue
        if res:
            ctx.last_search = res
            return "\n".join("[%d] %s | %s | %s" % (k + 1, t, u, sn[:220]) for k, (t, u, sn) in enumerate(res))
        errors.append(name + ": no results")
    raise ToolError("search failed: " + "; ".join(errors))


@tool("fetch_page", "Read a web page as plain text.", {"url": s(), "max_chars": i(minimum=200, maximum=20000)}, ["url"], klass=N)
def fetch_page(ctx, url, max_chars=4000):
    ctx.require_network()
    if not re.match(r"https?://", url):
        url = "https://" + url
    body = ctx.net.get(url, timeout=30)
    if body[:5] == b"%PDF-":
        path = config.rpath("page.pdf")
        open(path, "wb").write(body)
        return "PDF saved to %s (%d bytes)" % (path, len(body))
    try:
        j = json.loads(body)
        return json.dumps(j, ensure_ascii=False)[:max_chars]
    except ValueError:
        pass
    title, txt, _ = textify.text(body.decode("utf-8", "replace"))
    if len(txt) > max_chars:
        txt = txt[:max_chars] + " [... %d more chars]" % (len(txt) - max_chars)
    return "%s\n%s\n\n%s" % (title, url, txt or "(no readable text)")


IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp")


def _find_image(ctx, query):
    """A real photo for a subject: Wikipedia/Wikimedia first (free, sourced)."""
    api = ("https://en.wikipedia.org/w/api.php?action=query&format=json&prop=pageimages|info&inprop=url"
           "&piprop=original&generator=search&gsrlimit=3&gsrsearch=" + urllib.parse.quote(query))
    j = json.loads(ctx.net.get(api))
    pages = sorted((j.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        src = (p.get("original") or {}).get("source")
        if src:
            return src, p.get("fullurl", "")
    raise ToolError("no real image found for %r" % query)


@tool("show_image", "Show a real image on screen. Give an image URL, or a subject to find a real photo on Wikipedia. Never generated images.",
      {"url_or_subject": s(), "caption": s()}, ["url_or_subject"], klass=N)
def show_image(ctx, url_or_subject, caption=""):
    ctx.require_network()
    src, page = url_or_subject, ""
    if not re.match(r"https?://", src):
        src, page = _find_image(ctx, url_or_subject)
    elif not src.lower().split("?")[0].endswith(IMG_EXT):
        # A page: use its og:image.
        body = ctx.net.get(src).decode("utf-8", "replace")
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', body)
        if not m:
            raise ToolError("no image on that page")
        page, src = src, urllib.parse.urljoin(src, m.group(1))
    os.makedirs(config.rpath("img"), exist_ok=True)
    path = config.rpath("img", hashlib.sha1(src.encode()).hexdigest()[:16])
    ctx.net.get(src, timeout=40, out_file=path, max_bytes=30_000_000)
    ctx.emit({"type": "image", "path": path, "caption": caption, "source": page or src})
    return "shown %s" % (page or src)
