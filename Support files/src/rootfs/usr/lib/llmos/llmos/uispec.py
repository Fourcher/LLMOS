"""The generated interface, as data.

Every screen the OS shows -- a settings panel, the inbox, a photo, a research
result, a panel the model composes -- is a small JSON "window spec" made of
typed blocks. The graphical desk renders a spec as a window; the text console
renders the same spec as a framed box. Specs are validated here so that
whatever the model or a tool produces, the renderer only ever sees known
block types with bounded sizes.

    {"title": "Inbox", "kind": "panel", "size": "m", "blocks": [
        {"type": "text", "text": "6 unread"},
        {"type": "list", "items": [{"title": "Alice", "subtitle": "Dinner?", "meta": "urgent",
                                    "actions": [{"label": "Reply", "say": "reply to Alice that ..."}]}]},
        {"type": "buttons", "items": [{"label": "Inbox zero", "say": "get me to inbox zero", "primary": true}]}
    ]}

An action is always a *request in words* ("archive email 3") that goes back
through the same path as typing -- so a button can never do more than the
owner could say, and everything it does is audited like any request.
"""
import re

SIZES = ("s", "m", "l", "xl")
KINDS = ("panel", "dialog", "image", "media", "text", "form")
BLOCK_TYPES = ("text", "kv", "stat", "list", "table", "image", "buttons", "toggle", "form",
               "quote", "code", "progress", "choices", "media", "sources", "heading", "divider", "gallery", "slider")
MAX_BLOCKS = 40
MAX_ITEMS = 60
MAX_TEXT = 12000


def _s(v, n=MAX_TEXT):
    """A string, trimmed and bounded (never None)."""
    if v is None or isinstance(v, bool):
        return "" if v is None else str(v).lower()
    if isinstance(v, (list, tuple)):
        v = "\n".join(str(x) for x in v if not isinstance(x, (dict, list, tuple)))
    if isinstance(v, dict):
        v = " ".join(f"{k}: {x}" for k, x in v.items() if isinstance(x, (str, int, float)))
    return str(v).strip()[:n]


def _list(v):
    """Always a list, whatever the model produced (a number, a dict, a string)."""
    if isinstance(v, list):
        return v
    if isinstance(v, tuple):
        return list(v)
    if isinstance(v, dict):
        return [v]
    if isinstance(v, str) and v.strip():
        return [v]
    return []


def _url(v, n=600, local_only=False):
    """Only web addresses and local files may be linked or shown; local paths may contain spaces.
    local_only: what the page loads by itself (images, thumbnails) must be a file the OS fetched,
    never a remote address the model wrote (that would be a silent network request)."""
    u = _s(v, n)
    if re.match(r"^(file:///|/)[^\n]+$", u):
        return u
    if not local_only and re.match(r"^https?://[^\s]+$", u):
        return u
    return ""


def _action(a):
    if isinstance(a, str):
        a = {"label": a, "say": a}
    if not isinstance(a, dict):
        return None
    label = _s(a.get("label") or a.get("say"), 60)
    say = _s(a.get("say") or a.get("label"), 400)
    if not label or not say:
        return None
    out = {"label": label, "say": say}
    if a.get("primary"):
        out["primary"] = True
    if a.get("danger"):
        out["danger"] = True
    return out


def _actions(v, limit=6):
    out = []
    for a in _list(v)[:limit]:
        a = _action(a)
        if a:
            out.append(a)
    return out


def _fraction(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, f))


def _block(b):
    if isinstance(b, str):
        b = {"type": "text", "text": b}
    if not isinstance(b, dict):
        return None
    t = str(b.get("type", "text")).lower()
    if t not in BLOCK_TYPES:
        # the model sometimes invents types ("paragraph", "bullet"): keep the words
        text = _s(b.get("text") or b.get("content") or b.get("value") or b.get("items"))
        return {"type": "text", "text": text} if text else None
    if t == "text":
        text = _s(b.get("text") or b.get("content"))
        return {"type": "text", "text": text, "dim": bool(b.get("dim"))} if text else None
    if t == "heading":
        text = _s(b.get("text"), 120)
        return {"type": "heading", "text": text} if text else None
    if t == "divider":
        return {"type": "divider"}
    if t == "slider":
        try:
            lo, hi = int(b.get("min", 0)), int(b.get("max", 100))
            v = max(lo, min(hi, int(b.get("value", lo))))
        except (TypeError, ValueError):
            return None
        say = _s(b.get("say"), 200)
        return {"type": "slider", "label": _s(b.get("label"), 60), "value": v, "min": lo, "max": hi, "say": say} if "{v}" in say else None
    if t == "kv":
        rows = []
        src = b.get("rows") or b.get("items") or []
        src = list(src.items()) if isinstance(src, dict) else _list(src)
        for r in src[:MAX_ITEMS]:
            if isinstance(r, dict):
                r = (r.get("label") or r.get("key") or r.get("name"), r.get("value"))
            if isinstance(r, (list, tuple)) and len(r) >= 2:
                k, v = _s(r[0], 80), _s(r[1], 300)
                if k:
                    rows.append([k, v])
        return {"type": "kv", "rows": rows} if rows else None
    if t == "stat":
        label = _s(b.get("label"), 80)
        out = {"type": "stat", "label": label, "value": _s(b.get("value"), 120)}
        f = _fraction(b.get("fraction"))
        if f is not None:
            out["fraction"] = f
        return out if label or out["value"] else None
    if t == "progress":
        return {"type": "progress", "label": _s(b.get("label"), 80), "fraction": _fraction(b.get("fraction")) or 0.0}
    if t == "list":
        items = []
        for it in _list(b.get("items"))[:MAX_ITEMS]:
            if isinstance(it, str):
                it = {"title": it}
            if not isinstance(it, dict):
                continue
            item = {"title": _s(it.get("title") or it.get("text") or it.get("name"), 200)}
            if not item["title"]:
                continue
            for k, n in (("subtitle", 300), ("meta", 40), ("id", 40), ("detail", 1200)):
                v = _s(it.get(k), n)
                if v:
                    item[k] = v
            acts = _actions(it.get("actions"))
            if acts:
                item["actions"] = acts
            if it.get("done") is not None:
                item["done"] = bool(it.get("done"))
            items.append(item)
        out = {"type": "list", "items": items}
        if b.get("numbered"):
            out["numbered"] = True
        try:
            cols = int(b.get("columns") or 1)
        except (TypeError, ValueError):
            cols = 1
        if 1 < cols <= 3:
            out["columns"] = cols
        return out if items else None
    if t == "table":
        cols = [_s(c, 60) for c in _list(b.get("columns"))[:8]]
        rows = []
        for r in _list(b.get("rows"))[:MAX_ITEMS]:
            if isinstance(r, dict):
                r = [r.get(c) for c in cols] if cols else list(r.values())
            if isinstance(r, (list, tuple)):
                rows.append([_s(c, 200) for c in r[:8]])
            elif isinstance(r, (str, int, float)):
                rows.append([_s(r, 200)])
        return {"type": "table", "columns": cols, "rows": rows} if rows else None
    if t == "image":
        src = _url(b.get("src") or b.get("path") or b.get("url"), local_only=True)   # the page loads it: local files only
        if not src:
            return None
        return {"type": "image", "src": src, "caption": _s(b.get("caption"), 300), "credit": _s(b.get("credit"), 300),
                "link": _url(b.get("link"))}
    if t == "gallery":           # photos as thumbnails: local files only, each opens when clicked
        items = []
        raw = b.get("items")
        for it in (raw if isinstance(raw, list) else [])[:MAX_ITEMS]:
            if not isinstance(it, dict):
                continue
            src = _url(it.get("src"), local_only=True)
            if src:
                acts = _actions([{"label": "Open", "say": it.get("say")}], 1) if it.get("say") else []
                items.append({"src": src, "title": _s(it.get("title"), 80), "say": acts[0]["say"] if acts else ""})
        return {"type": "gallery", "items": items} if items else None
    if t == "buttons":
        acts = _actions(b.get("items") or b.get("buttons") or b.get("actions"), 8)
        return {"type": "buttons", "items": acts} if acts else None
    if t == "choices":
        items = []
        for it in _list(b.get("items"))[:12]:
            a = _action(it)
            if a:
                a["description"] = _s(it.get("description"), 200) if isinstance(it, dict) else ""
                items.append(a)
        return {"type": "choices", "items": items, "selected": _s(b.get("selected"), 60)} if items else None
    if t == "toggle":
        label = _s(b.get("label"), 80)
        if not label:
            return None
        return {"type": "toggle", "label": label, "on": bool(b.get("on")),
                "say_on": _s(b.get("say_on"), 300), "say_off": _s(b.get("say_off"), 300)}
    if t == "form":
        fields = []
        for f in _list(b.get("fields"))[:12]:
            if not isinstance(f, dict):
                continue
            name = re.sub(r"[^a-z0-9_]", "", str(f.get("name", "")).lower())
            if not name:
                continue
            kind = _s(f.get("kind") or f.get("type") or "text", 20)
            fields.append({"name": name, "label": _s(f.get("label") or name, 80), "kind": kind,
                           "value": _s(f.get("value"), 8000 if kind == "textarea" else 300),
                           "placeholder": _s(f.get("placeholder"), 120),
                           "options": [_s(o, 80) for o in _list(f.get("options"))[:40]]})
        submit = _action(b.get("submit") if isinstance(b.get("submit"), (dict, str)) else {"label": "OK", "say": "ok"})
        post = str(b.get("submit", {}).get("post", "")) if isinstance(b.get("submit"), dict) else ""
        if submit is not None and post in ("vault.create", "cloud.setup", "connector.add", "conduct.save"):
            submit["post"] = post
        if not fields or not submit:
            return None
        return {"type": "form", "fields": fields, "submit": submit}
    if t == "quote":
        text = _s(b.get("text"), 1000).strip().strip('"\u201c\u201d\u2018\u2019\'').strip()
        src = _url(b.get("source"), 400)
        # a quotation is shown as sourced (author + "— quote marks") only with a real source URL; without one it
        # is the model's own composition, rendered as plain text so it is never mistaken for a real human quote
        return {"type": "quote", "text": text, "author": _s(b.get("author"), 120), "source": src} if (text and src) \
            else ({"type": "text", "text": text} if text else None)
    if t == "code":
        text = _s(b.get("text") or b.get("content"))
        return {"type": "code", "text": text, "lang": _s(b.get("lang"), 20)} if text else None
    if t == "media":
        return {"type": "media", "title": _s(b.get("title"), 200), "subtitle": _s(b.get("subtitle"), 200),
                "thumbnail": _url(b.get("thumbnail"), local_only=True), "state": _s(b.get("state") or "playing", 20),
                "link": _url(b.get("link"))}
    if t == "sources":
        items = []
        for it in _list(b.get("items"))[:10]:
            if isinstance(it, str):
                it = {"url": it}
            if isinstance(it, dict) and _url(it.get("url")):
                items.append({"title": _s(it.get("title") or it.get("url"), 160), "url": _url(it.get("url"))})
        return {"type": "sources", "items": items} if items else None
    return None


def normalize(spec):
    """Return a clean spec (dict) or None if nothing renderable is in it."""
    if isinstance(spec, str):
        spec = {"title": "", "blocks": [{"type": "text", "text": spec}]}
    if not isinstance(spec, dict):
        return None
    blocks = spec.get("blocks")
    if blocks is None and spec.get("lines") is not None:      # legacy: title + lines
        blocks = [{"type": "text", "text": "\n".join(str(x) for x in _list(spec.get("lines")))}]
    out_blocks = []
    for b in _list(blocks)[:MAX_BLOCKS]:
        nb = _block(b)
        if nb:
            out_blocks.append(nb)
    if not out_blocks:
        return None
    kind = str(spec.get("kind", "panel")).lower()
    size = str(spec.get("size", "")).lower()
    out = {"title": _s(spec.get("title"), 80), "kind": kind if kind in KINDS else "panel",
           "size": size if size in SIZES else "", "blocks": out_blocks}
    for k in ("id", "icon", "replace"):
        if spec.get(k):
            out[k] = _s(spec[k], 200)
    if spec.get("slot") in ("side", "cascade"):
        out["slot"] = spec["slot"]      # where the desk puts it; set by the OS, never by the model's text
    acts = _actions(spec.get("actions"))
    if acts:
        out["actions"] = acts
    return out


def to_rows(spec):
    """Flatten a spec into text rows for the console / logs / the model."""
    rows = []
    for b in spec.get("blocks", []):
        t = b["type"]
        if t in ("text", "heading"):
            rows += b["text"].splitlines()
        elif t == "divider":
            rows.append("")
        elif t == "kv":
            rows += [f"{k}: {v}" for k, v in b["rows"]]
        elif t == "stat":
            rows.append(f"{b['label']}: {b['value']}")
        elif t == "progress":
            rows.append(f"{b['label']}: {int(b['fraction'] * 100)}%")
        elif t == "list":
            for i, it in enumerate(b["items"], 1):
                head = f"{i}. " if b.get("numbered") else "· "
                idp = f"[{it['id']}] " if it.get("id") else ""
                meta = f" ({it['meta']})" if it.get("meta") else ""
                rows.append(f"{head}{idp}{it['title']}{meta}")
                if it.get("subtitle"):
                    rows.append("    " + it["subtitle"])
        elif t == "table":
            if b["columns"]:
                rows.append(" · ".join(b["columns"]))
            rows += [" · ".join(r) for r in b["rows"]]
        elif t == "gallery":
            rows.append(f"[{len(b['items'])} photos] " + ", ".join(i["title"] for i in b["items"][:6]))
        elif t == "image":
            rows.append(f"[image] {b['caption'] or b['src']}" + (f" — {b['credit']}" if b["credit"] else ""))
        elif t in ("buttons", "choices"):
            rows.append("  ".join(f"[{a['label']}]" for a in b["items"]))
        elif t == "toggle":
            rows.append(f"{b['label']}: {'on' if b['on'] else 'off'}")
        elif t == "form":
            rows += [f"{f['label']}: {f['value'] or '…'}" for f in b["fields"]]
        elif t == "quote":
            rows.append(f"“{b['text']}”" + (f" — {b['author']}" if b["author"] else ""))
            if b["source"]:
                rows.append("    " + b["source"])
        elif t == "code":
            rows += b["text"].splitlines()
        elif t == "media":
            rows.append(f"{b['state']}: {b['title']}" + (f" — {b['subtitle']}" if b["subtitle"] else ""))
        elif t == "sources":
            rows += [f"{it['title']} — {it['url']}" for it in b["items"]]
    return rows


# ---- small constructors used by the tools

def text_window(title, text, size="", kind="panel"):
    return {"title": title, "kind": kind, "size": size, "blocks": [{"type": "text", "text": text}]}


def list_window(title, items, size="m", intro="", buttons=None):
    blocks = []
    if intro:
        blocks.append({"type": "text", "text": intro, "dim": True})
    blocks.append({"type": "list", "items": items})
    if buttons:
        blocks.append({"type": "buttons", "items": buttons})
    return {"title": title, "kind": "panel", "size": size, "blocks": blocks}
