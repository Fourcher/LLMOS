"""The computer's own mailbox: a real email address it makes for itself, to sign things up and read back the codes
and confirmation links they send, so the owner never copies a two-factor code again.

A laptop on a home network cannot be a mail server the internet delivers to (no domain, no public address, port 25
blocked, residential addresses are on every spam list). So the address is made through a free email service that
offers a programmatic inbox (mail.tm, with mail.gw as a stand-in if it is down): the address is real and receives
mail from anyone, and this reads it over the service's own API. It is a shared, free service meant for sign-ups and
verifications -- fine for those, and some sites turn such addresses away. For a lasting personal address the owner
brings their own (mail.py). The address and its password live in the vault with the rest of the owner's data.

Nothing but the standard library."""
import json
import re
import secrets
import time
import urllib.error
import urllib.request

from . import config

# the free inbox services, tried in order. Both speak the same API (mail.tm's), so one stands in for the other.
PROVIDERS = [("mail.tm", "https://api.mail.tm"), ("mail.gw", "https://api.mail.gw")]
_FILE = "devmail.json"
_TOKENS = {}                 # address -> (token, when): a short-lived cache so a burst of reads logs in once


class DevMailError(Exception):
    pass


def account():
    """{"address", "password", "provider", "base", "id"} or None when the computer has no mailbox yet."""
    a = config.load_json(config.data(_FILE), None)
    return a if isinstance(a, dict) and a.get("address") else None


def address():
    a = account()
    return a["address"] if a else ""


def _api(base, method, path, data=None, token=None, timeout=20):
    r = urllib.request.Request(base + path, data=(json.dumps(data).encode() if data is not None else None), method=method)
    r.add_header("Content-Type", "application/json")
    r.add_header("Accept", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            body = f.read()
            return f.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise DevMailError(f"{base.split('//')[-1]} could not be reached ({getattr(e, 'reason', e)})")


def _members(doc):
    if isinstance(doc, dict) and "hydra:member" in doc:
        return doc["hydra:member"]
    return doc if isinstance(doc, list) else []


def provision(label="llmos"):
    """Make the computer a fresh mailbox and keep it. Replaces any earlier one. Returns the new address."""
    label = re.sub(r"[^a-z0-9]+", "", str(label or "llmos").lower())[:16] or "llmos"
    last = None
    for name, base in PROVIDERS:
        try:
            st, doms = _api(base, "GET", "/domains?page=1")
            active = [d["domain"] for d in _members(doms) if d.get("isActive", True) and not d.get("isPrivate")]
            if st != 200 or not active:
                last = DevMailError(f"{name} offered no address to use")
                continue
            addr = f"{label}-{secrets.token_hex(4)}@{active[0]}"
            pw = secrets.token_urlsafe(16)
            st, acc = _api(base, "POST", "/accounts", {"address": addr, "password": pw})
            if st not in (200, 201):
                last = DevMailError(f"{name} would not make the address ({acc.get('hydra:description') or acc.get('message') or st})")
                continue
            st, tok = _api(base, "POST", "/token", {"address": addr, "password": pw})
            if st != 200 or not tok.get("token"):
                last = DevMailError(f"{name} made the address but the sign-in failed")
                continue
            a = {"address": addr, "password": pw, "provider": name, "base": base, "id": acc.get("id", "")}
            config.save_json(config.data(_FILE), a)
            _TOKENS[addr] = (tok["token"], time.time())
            return addr
        except DevMailError as e:
            last = e
    raise last or DevMailError("no free email service answered")


def _token(a):
    tok = _TOKENS.get(a["address"])
    if tok and time.time() - tok[1] < 540:        # mail.tm tokens last ~15 min; refresh well before that
        return tok[0]
    st, doc = _api(a["base"], "POST", "/token", {"address": a["address"], "password": a["password"]})
    if st != 200 or not doc.get("token"):
        raise DevMailError("the mailbox could not be opened (the free service may have dropped it; make a new one)")
    _TOKENS[a["address"]] = (doc["token"], time.time())
    return doc["token"]


def messages(limit=20):
    """The inbox, newest first: [{id, from, from_name, subject, intro, seen, at}]. Empty list when nothing is there."""
    a = account()
    if not a:
        raise DevMailError("the computer has no mailbox yet")
    st, doc = _api(a["base"], "GET", "/messages?page=1", token=_token(a))
    if st != 200:
        raise DevMailError("the inbox could not be read")
    out = []
    for m in _members(doc)[:limit]:
        frm = m.get("from") or {}
        out.append({"id": m.get("id", ""), "from": frm.get("address", ""), "from_name": frm.get("name", ""),
                    "subject": m.get("subject", ""), "intro": m.get("intro", ""), "seen": bool(m.get("seen")),
                    "at": str(m.get("createdAt", ""))})
    return out


def read(mid):
    """One message in full: {id, from, subject, text, html, at}."""
    a = account()
    if not a:
        raise DevMailError("the computer has no mailbox yet")
    st, m = _api(a["base"], "GET", "/messages/" + str(mid), token=_token(a))
    if st != 200:
        raise DevMailError("that message could not be read")
    frm = m.get("from") or {}
    html = m.get("html") or []
    return {"id": m.get("id", ""), "from": frm.get("address", ""), "subject": m.get("subject", ""),
            "text": m.get("text", "") or "", "html": "\n".join(html) if isinstance(html, list) else str(html or ""),
            "at": str(m.get("createdAt", ""))}


# ---- pulling the useful thing out of a verification email: the code, or the link to click.

_CODE_WORD = re.compile(r"\b(?:code|passcode|otp|pin)\b", re.I)
_HINT = re.compile(r"\b(code|passcode|verif\w*|otp|one[\s-]*time|2fa|pin|password|confirm\w*)\b", re.I)
_TOKEN = re.compile(r"[0-9A-Za-z]{4,8}")
_STANDALONE = re.compile(r"(?<![0-9A-Za-z])[0-9A-Za-z]{4,8}(?![0-9A-Za-z])")
_HTMLTAG = re.compile(r"<[^>]+>")
_LINK = re.compile(r"https?://[^\s\"'<>)\]]+")
_LINK_WORDS = ("verify", "confirm", "activate", "validate", "verification", "confirmation", "signup", "sign-up",
               "magic", "login", "signin", "token", "code", "auth", "activate-account", "email")


def _plain(msg):
    text = msg.get("text") or ""
    if not text and msg.get("html"):
        text = _HTMLTAG.sub(" ", msg["html"])
    return text


def _code_shape(tok):
    """A token that looks like a one-time code: 4-8 digits (not a year), or 5-8 letters-and-digits with both."""
    if re.fullmatch(r"[0-9]{4,8}", tok):
        return not (len(tok) == 4 and 1900 <= int(tok) <= 2099)
    return (bool(re.fullmatch(r"[0-9A-Za-z]{5,8}", tok)) and bool(re.search(r"[0-9]", tok)) and bool(re.search(r"[A-Za-z]", tok)))


def extract_code(msg):
    """The verification code in a message, or "". A code right after the word "code" ("your code is 123456") wins;
    otherwise, in a message that is plainly about a code, a single standalone code-shaped token. A phone number, an
    order id or a year is never taken."""
    text = _plain(msg)
    for m in _CODE_WORD.finditer(text):
        for tok in _TOKEN.findall(text[m.end():m.end() + 30]):   # the first code-shaped token just after "code"
            if _code_shape(tok):
                return tok
    if _HINT.search(text):
        toks = [t for t in _STANDALONE.findall(text) if _code_shape(t)]
        if len(set(toks)) == 1:
            return toks[0]
    return ""


def extract_links(msg):
    """The confirmation links in a message, the ones that look like a verify/confirm link first."""
    text = (msg.get("text") or "") + "\n" + (msg.get("html") or "")
    seen, links = set(), []
    for url in _LINK.findall(text):
        url = url.rstrip(".,);”\"'")
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
    links.sort(key=lambda u: 0 if any(w in u.lower() for w in _LINK_WORDS) else 1)
    return links


def wait_for_code(timeout=90, since=None):
    """Wait for a new message and return {"code", "link", "from", "subject", "id"}; {} if none comes in time. `since`
    is an id to treat as already seen (the newest message before the sign-up), so an old code is never returned."""
    seen = {since} if since else set()
    if since is None:
        try:
            seen = {m["id"] for m in messages()}     # anything already here is old
        except DevMailError:
            seen = set()
    deadline = time.time() + max(5, int(timeout))
    while time.time() < deadline:
        try:
            for m in messages():
                if m["id"] in seen:
                    continue
                full = read(m["id"])
                code = extract_code(full)
                links = extract_links(full)
                if code or links:
                    return {"code": code, "link": links[0] if links else "", "links": links,
                            "from": full["from"], "subject": full["subject"], "id": m["id"]}
                seen.add(m["id"])
        except DevMailError:
            pass
        time.sleep(4)
    return {}


def newest_id():
    try:
        ms = messages(limit=1)
        return ms[0]["id"] if ms else None
    except DevMailError:
        return None


def forget(delete=True):
    """Drop the mailbox. With delete, also remove it from the service so nothing lingers there."""
    a = account()
    if a and delete and a.get("id"):
        try:
            _api(a["base"], "DELETE", "/accounts/" + a["id"], token=_token(a))
        except DevMailError:
            pass
    _TOKENS.pop(a["address"], None) if a else None
    try:
        import os
        os.unlink(config.data(_FILE))
    except OSError:
        pass
