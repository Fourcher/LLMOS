"""HTML to readable text, stdlib only."""
import html
import re
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe", "template", "button", "select"}
BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "blockquote", "pre", "table", "ul", "ol", "dd", "dt", "figcaption"}


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.title, self.in_title = [], 0, "", False
        self.links = []
        self._href = None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag in BLOCK:
            self.out.append("\n")
            if tag.startswith("h") and len(tag) == 2:
                self.out.append("## ")
            if tag == "li":
                self.out.append("- ")
        if tag == "img" and not self.skip:
            a = dict(attrs)
            if a.get("src") and (a.get("alt") or "").strip():
                self.links.append(("img", a["src"], a.get("alt", "")))

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        elif tag == "title":
            self.in_title = False
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)


def text(markup):
    p = _P()
    try:
        p.feed(markup)
    except Exception:
        pass
    t = "".join(p.out)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    lines = [l.strip() for l in t.split("\n")]
    # Drop short menu-like lines that surround the article.
    keep = [l for l in lines if len(l) > 40 or l.startswith("## ") or (l and l[-1:] in ".:!?")]
    return p.title.strip(), "\n".join(keep).strip(), p.links


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()
