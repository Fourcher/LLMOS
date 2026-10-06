"""Email with nothing but the standard library: IMAP for reading and moving,
SMTP for sending. The account (including its password) lives in the vault
(~/.llmos/mail.json) and nothing is read or sent unless the owner asks or
scheduled it. There is no provider integration and no OAuth: use an app
password where the provider requires one (Gmail, Outlook, Yahoo, iCloud)."""
import email
import os
import email.header
import email.utils
import html
import imaplib
import json
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

from . import config

PROVIDERS = {
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com"), "googlemail.com": ("imap.gmail.com", "smtp.gmail.com"),
    "outlook.com": ("outlook.office365.com", "smtp.office365.com"), "hotmail.com": ("outlook.office365.com", "smtp.office365.com"),
    "live.com": ("outlook.office365.com", "smtp.office365.com"), "msn.com": ("outlook.office365.com", "smtp.office365.com"),
    "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com"), "icloud.com": ("imap.mail.me.com", "smtp.mail.me.com"),
    "me.com": ("imap.mail.me.com", "smtp.mail.me.com"), "fastmail.com": ("imap.fastmail.com", "smtp.fastmail.com"),
    "proton.me": ("127.0.0.1", "127.0.0.1"), "protonmail.com": ("127.0.0.1", "127.0.0.1"),  # needs Proton Bridge
    "aol.com": ("imap.aol.com", "smtp.aol.com"), "gmx.com": ("imap.gmx.com", "mail.gmx.com"),
    "zoho.com": ("imap.zoho.com", "smtp.zoho.com"), "posteo.de": ("posteo.de", "posteo.de"),
}


class MailError(Exception):
    pass


def account():
    return config.load_json(config.data("mail.json"), None)


def _guess(address):
    domain = address.rsplit("@", 1)[-1].lower()
    if domain in PROVIDERS:
        return PROVIDERS[domain]
    return "imap." + domain, "smtp." + domain


def setup(address, password, imap_host="", smtp_host="", imap_port=0, smtp_port=0,
          imap_ssl=None, smtp_security="", name=""):
    """Save an account after checking that IMAP login works."""
    address = address.strip()
    if "@" not in address:
        raise MailError("that doesn't look like an email address")
    gi, gs = _guess(address)
    acct = {
        "address": address, "password": password, "name": name.strip(),
        "imap_host": imap_host.strip() or gi, "smtp_host": smtp_host.strip() or gs,
        "imap_port": int(imap_port) or (993 if imap_ssl is not False else 143),
        "smtp_port": int(smtp_port) or 587,
        "imap_ssl": True if imap_ssl is None else bool(imap_ssl),
        "smtp_security": smtp_security or "starttls",   # starttls | ssl | none
    }
    if acct["imap_host"] == "127.0.0.1" and not imap_host:
        raise MailError("Proton Mail needs Proton Bridge running on this machine; give me its IMAP/SMTP host and ports")
    conn = _imap(acct)
    conn.logout()
    _smtp_check(acct)
    config.save_json(config.data("mail.json"), acct)
    return acct


def _smtp_check(acct):
    """Connect to the SMTP server (and log in where it takes credentials) so a
    wrong host is caught at setup, not at the first send."""
    if config.settings.get("tor"):
        raise MailError(_TOR_BLOCKS)
    sec = acct.get("smtp_security", "starttls")
    try:
        if sec == "ssl":
            s = smtplib.SMTP_SSL(acct["smtp_host"], acct["smtp_port"], timeout=20, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(acct["smtp_host"], acct["smtp_port"], timeout=20)
            s.ehlo()
            if sec == "starttls":
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
        if s.has_extn("auth"):
            s.login(acct["address"], acct["password"])
        s.quit()
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise MailError(f"IMAP is fine but SMTP at {acct['smtp_host']}:{acct['smtp_port']} failed: {e}")


_TOR_BLOCKS = ("Tor is on, and email cannot be carried through it, so it is blocked to keep this computer's address "
               "private. Turn Tor off to use email.")


def _q(name):
    """A mailbox name or search text as an IMAP quoted string: "[Gmail]/All Mail" has a space and brackets, and a
    quote in the text must not end the command."""
    return '"' + str(name).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _imap(acct=None):
    acct = acct or account()
    if not acct:
        raise MailError("no email account is set up yet")
    if config.settings.get("tor"):
        raise MailError(_TOR_BLOCKS)
    try:
        if acct["imap_ssl"]:
            conn = imaplib.IMAP4_SSL(acct["imap_host"], acct["imap_port"], ssl_context=ssl.create_default_context(), timeout=30)
        else:
            conn = imaplib.IMAP4(acct["imap_host"], acct["imap_port"], timeout=30)
        conn.login(acct["address"], acct["password"])
    except (imaplib.IMAP4.error, OSError, ssl.SSLError) as e:
        raise MailError(f"IMAP login to {acct['imap_host']} failed: {e}")
    return conn


def _decode(value):
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", "replace"))
        else:
            out.append(text)
    return " ".join(" ".join(out).split())


def _body_text(msg, limit=4000):
    """Plain text of a message: text/plain first, else HTML stripped."""
    text, htmlpart = "", ""
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        chunk = payload.decode(charset, "replace")
        if part.get_content_type() == "text/plain" and not text:
            text = chunk
        elif part.get_content_type() == "text/html" and not htmlpart:
            htmlpart = chunk
    if not text and htmlpart:
        h = re.sub(r"<(script|style)\b.*?</\1>", " ", htmlpart, flags=re.S | re.I)
        h = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", h, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", h))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    attachments = [p.get_filename() for p in msg.walk() if p.get_filename()]
    if attachments:
        text += "\n\n(attachments: " + ", ".join(attachments) + ")"
    return text[:limit]


def _folder_name(conn, kind):
    """Find the provider's folder for 'archive' or 'trash'."""
    typ, data = conn.list()
    names = []
    for line in data or []:
        if isinstance(line, bytes):
            m = re.search(r'"([^"]+)"\s*$|(\S+)\s*$', line.decode("utf-8", "replace"))
            if m:
                names.append((line.decode("utf-8", "replace").lower(), (m.group(1) or m.group(2))))
    wanted = {"archive": ("\\all", "all mail", "archive"), "trash": ("\\trash", "trash", "deleted", "bin")}[kind]
    for low, name in names:
        if any(w in low for w in wanted):
            return name
    if kind == "archive":
        conn.create(_q("Archive"))
        return "Archive"
    conn.create(_q("Trash"))
    return "Trash"


def unread(limit=20, folder="INBOX"):
    conn = _imap()
    try:
        conn.select(_q(folder), readonly=True)
        typ, data = conn.uid("search", None, "UNSEEN")
        uids = (data[0].split() if data and data[0] else [])[-limit:]
        out = []
        for uid in reversed(uids):
            typ, d = conn.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] BODY.PEEK[TEXT]<0.600>)")
            hdr, snippet = b"", b""
            for item in d or []:
                if isinstance(item, tuple):
                    if b"HEADER" in item[0]:
                        hdr = item[1]
                    elif b"TEXT" in item[0]:
                        snippet = item[1]
            msg = email.message_from_bytes(hdr)
            snip = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", snippet.decode("utf-8", "replace")))).strip()
            snip = re.sub(r"^(--[^ ]+|Content-[^ ]+:.*?)\s", "", snip)
            out.append({"uid": uid.decode(), "from": _decode(msg.get("From")), "subject": _decode(msg.get("Subject")),
                        "date": _decode(msg.get("Date"))[:31], "snippet": snip[:160]})
        return out
    finally:
        conn.logout()


def count_unread(folder="INBOX"):
    conn = _imap()
    try:
        conn.select(_q(folder), readonly=True)
        typ, data = conn.uid("search", None, "UNSEEN")
        return len(data[0].split()) if data and data[0] else 0
    finally:
        conn.logout()


def read(uid, folder="INBOX", mark_seen=True):
    conn = _imap()
    try:
        conn.select(_q(folder), readonly=not mark_seen)
        typ, d = conn.uid("fetch", str(uid), "(RFC822)")
        raw = next((item[1] for item in d or [] if isinstance(item, tuple)), None)
        if not raw:
            raise MailError(f"no message with id {uid}")
        msg = email.message_from_bytes(raw)
        return {"uid": str(uid), "from": _decode(msg.get("From")), "to": _decode(msg.get("To")),
                "subject": _decode(msg.get("Subject")), "date": _decode(msg.get("Date")),
                "message_id": msg.get("Message-ID", ""), "text": _body_text(msg)}
    finally:
        conn.logout()


def move(uids, kind="archive", folder="INBOX"):
    conn = _imap()
    try:
        conn.select(_q(folder))
        dest = _folder_name(conn, kind)
        done = []
        for uid in uids:
            uid = str(uid)
            typ, _ = conn.uid("copy", uid, _q(dest))
            if typ == "OK":
                conn.uid("store", uid, "+FLAGS", "(\\Deleted)")
                done.append(uid)
        conn.expunge()
        return done, dest
    except imaplib.IMAP4.error as e:
        raise MailError(f"the mail server refused: {e}")
    finally:
        conn.logout()


def send(to, subject, body, in_reply_to=None, references=None, attachments=None):
    acct = account()
    if not acct:
        raise MailError("no email account is set up yet")
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((acct.get("name") or acct["address"].split("@")[0], acct["address"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references or in_reply_to)
    msg.set_content(body)
    import mimetypes
    for path in attachments or []:              # files go along as attachments, under their own names
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(path))
    if config.settings.get("tor"):
        raise MailError(_TOR_BLOCKS)
    sec = acct.get("smtp_security", "starttls")
    try:
        if sec == "ssl":
            s = smtplib.SMTP_SSL(acct["smtp_host"], acct["smtp_port"], timeout=30, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(acct["smtp_host"], acct["smtp_port"], timeout=30)
            s.ehlo()
            if sec == "starttls":
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
        if sec != "none" or acct.get("smtp_auth", True):
            try:
                s.login(acct["address"], acct["password"])
            except smtplib.SMTPException:
                if sec != "none":
                    raise
        s.send_message(msg)
        s.quit()
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise MailError(f"sending via {acct['smtp_host']} failed: {e}")
    return msg["Message-ID"]


def reply(uid, body, folder="INBOX"):
    m = read(uid, folder, mark_seen=True)
    to = email.utils.parseaddr(m["from"])[1] or m["from"]
    subject = m["subject"] if m["subject"].lower().startswith("re:") else "Re: " + m["subject"]
    quoted = "\n".join("> " + ln for ln in m["text"].splitlines()[:40])
    full = body.rstrip() + f"\n\nOn {m['date']}, {m['from']} wrote:\n{quoted}\n"
    send(to, subject, full, in_reply_to=m["message_id"], references=m["message_id"])
    return to, subject


def format_list(items):
    if not items:
        return "no unread mail"
    return "\n".join(f"[{m['uid']}] {m['date'][:16]} | {m['from'][:40]} | {m['subject'][:70]}\n      {m['snippet'][:140]}"
                     for m in items)


def find(query, limit=5):
    """Resolve a name/subject fragment to messages: newest first, INBOX then
    the archive. Returns [{uid, folder, from, subject, date}]."""
    q = str(query).strip().strip("[]")
    conn = _imap()
    try:
        out = []
        folders = ["INBOX"]
        try:
            folders.append(_folder_name(conn, "archive"))
        except Exception:
            pass
        for folder in folders:
            typ, _ = conn.select(_q(folder), readonly=True)
            if typ != "OK":
                continue
            crit = f"(OR FROM {_q(q)} SUBJECT {_q(q)})"
            typ, data = conn.uid("search", None, crit)
            uids = data[0].split() if typ == "OK" and data and data[0] else []
            for uid in reversed(uids[-limit:]):
                typ, d = conn.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                hdr = next((item[1] for item in d or [] if isinstance(item, tuple)), b"")
                msg = email.message_from_bytes(hdr)
                out.append({"uid": uid.decode(), "folder": folder, "from": _decode(msg.get("From")),
                            "subject": _decode(msg.get("Subject")), "date": _decode(msg.get("Date"))[:31]})
            if out:
                break
        return out
    except imaplib.IMAP4.error as e:
        raise MailError(f"the mail server refused the search: {e}")
    finally:
        conn.logout()


def resolve(ref):
    """A numeric id -> ('INBOX', id); anything else -> the newest matching
    message by sender or subject, or None."""
    r = str(ref).strip().strip("[] ")
    if r.isdigit():
        return "INBOX", r
    hits = find(r, limit=1)
    return (hits[0]["folder"], hits[0]["uid"]) if hits else None
