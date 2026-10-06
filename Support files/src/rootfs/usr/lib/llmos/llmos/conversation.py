"""One conversation that never needs clearing, and side chats beside it.

Everything said is kept (data/chats/<chat>.jsonl), but a model only ever sees what the new request is about:
the request is checked against the topic in progress -- a reference ("it", "that", "again", "the second one", a
short follow-up) or shared words continue it; anything else starts a new topic with a clean context. Older
topics come back as one-line notes only when the request is about them. A small model therefore never wades
through a long, mixed history (which is what makes it drift, repeat itself or fixate on an earlier subject), and
the same holds for the online model. No extra model calls: it is cheap on a slow computer.

A side chat is a separate conversation in its own window for a tangent; the main one is untouched.
"""
import json
import os
import re
import time

from . import config

GENERIC = {"write", "make", "open", "show", "tell", "give", "find", "get", "create", "help", "want", "need", "new", "start", "play",
           "put", "set", "use", "change", "turn", "please", "app", "apps", "can", "could", "would", "like", "something", "thing", "things", "one"}
PAST = re.compile(r"\b(again|earlier|before|yesterday|last (?:time|week|night)|you (?:said|told|wrote|suggested|mentioned)|we (?:talked|discussed|spoke)|"
                  r"remember|previous(?:ly)?|what (?:was|were|did)|the (?:one|thing) (?:you|we|i))\b", re.I)
STOP = set("""a about above after again all also am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers him his how i if in into
is it its itself just me more most my no nor not now of off on once only or other our out over own same she should so some such
than that the their them then there these they this those through to too under until up very was we were what when where which
while who whom why will with would you your yours please thanks thank okay ok yes yeah hey hi hello want need like make give show
tell get let know think much many one two thing things something anything really just now today""".split())
REF_START = re.compile(r"^\s*(?:and|also|but|so|then|now|ok(?:ay)?|yes|yeah|yep|no|nope|sure|thanks?|great|perfect|nice|cool|"
                       r"it|that|this|those|these|them|they|its|do (?:it|that|the same)|again|more|another|same|instead|undo|"
                       r"what about|how about|the (?:first|second|third|fourth|last|other|next|previous)|which one|what else|"
                       r"try again|redo|make it|change it|fix it|go on|continue|keep going|and then|after that|one more)\b", re.I)
REF_ANY = re.compile(r"\b(?:it|that|this|them|those|these|there|here|he|she|him|her|his|again|instead|too|as well|the same|previous|last one|above|earlier|"
                     r"you said|you just|you made|you did|your answer|that one)\b", re.I)
STRONG_REF = re.compile(r"\b(?:there|he|she|him|her|his|them|they|those|these|again|instead|too|as well|the same|previous|"
                        r"last one|above|earlier|you said|you just|you made|you did|your answer|that one)\b", re.I)
NEW_TOPIC = re.compile(r"^\s*(?:new (?:topic|chat|conversation|question)|(?:let'?s )?(?:start (?:over|fresh|a new)|change (?:the )?subject)|"
                       r"(?:on )?(?:a |an )?(?:different|unrelated|other) (?:note|topic|question|subject)|unrelated(?: question)?)\b[:,.!\s-]*", re.I)
GAP = 25 * 60          # a pause this long starts a new topic unless the request clearly follows on
REPLAY_MSGS = 6        # at most three exchanges of the topic in progress are replayed
REPLAY_CHARS = 5000    # and never more than this much text


def words(text):
    return {w for w in re.findall(r"[a-z][a-z0-9'-]{2,}", str(text).lower()) if w not in STOP}


def _dir():
    d = os.path.join(config.data_dir(), "chats")
    config.guard_write(d)
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


class Chat:
    def __init__(self, cid="main", title=""):
        self.id = re.sub(r"[^a-z0-9-]", "", cid.lower()) or "main"
        self.title = title
        self.msgs = []           # {"ts", "role", "content", "topic"}
        self.topics = []         # {"id", "title", "first", "last", "n", "gist"}
        self.fresh = False       # the owner asked for a fresh start: the next request opens a new topic
        self._load()

    # ---- storage
    def _path(self, ext):
        return os.path.join(_dir(), f"{self.id}.{ext}")

    def _load(self):
        try:
            with open(self._path("jsonl"), encoding="utf-8") as f:
                self.msgs = [json.loads(ln) for ln in f if ln.strip()]
        except (OSError, ValueError):
            self.msgs = []
        try:
            with open(self._path("json"), encoding="utf-8") as f:
                meta = json.load(f)
                self.topics, self.title = meta.get("topics", []), meta.get("title", self.title)
        except (OSError, ValueError):
            self.topics = []

    def _save_meta(self):
        p = self._path("json")
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"title": self.title, "topics": self.topics[-500:]}, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)

    def _append(self, m):
        self.msgs.append(m)
        with open(self._path("jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    # ---- topics
    def current(self):
        return self.topics[-1] if self.topics else None

    def topic_msgs(self, tid):
        return [m for m in self.msgs if m.get("topic") == tid]

    def continues(self, request):
        """Does this request follow on from the topic in progress?"""
        t = self.current()
        if not t or self.fresh:
            return False
        if NEW_TOPIC.match(request):
            return False
        recent = self.topic_msgs(t["id"])[-4:]
        if not recent:
            return False
        if REF_START.match(request):
            return True
        if time.time() - t["last"] > GAP:
            return False
        req = words(request)
        if not req:                                   # "why?", "go on", "what can I do about it"
            return len(request.split()) <= 3 or bool(REF_ANY.search(request))
        seen = set()
        for m in recent:
            seen |= words(m["content"])
        shared = req & seen
        # about an earlier topic and not this one ("what was the capital of australia again"): a new topic, recalled
        older = max((len(req & words(o["title"] + " " + o.get("gist", ""))) for o in self.topics[:-1]), default=0)
        if not shared and older >= 2:
            return False
        if len(request.split()) <= 8 and REF_ANY.search(request):
            # "there", "them", "again", "instead" always point back; "this"/"it"/"that" often mean the computer itself
            # ("install this on my computer"), so they continue only a thin request or one that shares a word
            if STRONG_REF.search(request) or len(req) <= 1 or shared:
                return True
        return len(shared) >= 2 or (len(shared) == 1 and len(req) <= 3)

    def context(self, request):
        """(messages to replay, a note about earlier topics) for the model, for this request."""
        if self.continues(request):
            t = self.current()
            out, size = [], 0
            for m in reversed(self.topic_msgs(t["id"])):
                size += len(m["content"])
                if len(out) >= REPLAY_MSGS or size > REPLAY_CHARS:
                    break
                out.append({"role": m["role"], "content": m["content"]})
            out.reverse()
            while out and out[0]["role"] != "user":
                out.pop(0)
            return out, ""
        return [], self.recall(request)

    def recall(self, request, limit=2):
        """One-line notes of earlier topics this request is about (so 'what did you say about X yesterday' works).
        Only when the request points back ("again", "earlier", "what was…") or shares two real subject words with
        the topic: a new request that merely shares a verb ("write a letter" after "write an email to my landlord")
        must start clean, or a small model weaves the old topic into it."""
        req = words(request) - GENERIC
        if not req:
            return ""
        back = bool(PAST.search(request))
        scored = []
        for t in self.topics[:-1] if not self.fresh else self.topics:
            sc = len(req & words(t["title"] + " " + t.get("gist", "")))
            if (back and sc >= 1) or sc >= 3 or (sc >= 2 and len(req) <= 3):
                scored.append((sc, t["last"], t))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        notes = [f"- {time.strftime('%b %d', time.localtime(t['last']))}: asked \"{t['title']}\"; answered: {t.get('gist', '')}"
                 for _, _, t in scored[:limit]]
        return ("Earlier conversations that may be relevant (use only if they help):\n" + "\n".join(notes)) if notes else ""

    def record(self, request, reply, continued):
        """Keep the exchange, in the topic in progress or a new one."""
        now = time.time()
        if not continued or not self.current():
            title = NEW_TOPIC.sub("", request).strip() or request.strip()
            n = len(self.topics)
            self.topics.append({"id": f"t{int(now * 1000):x}{n:x}", "title": title[:70] + ("…" if len(title) > 70 else ""),
                                "first": now, "last": now, "n": 0, "gist": ""})
        t = self.current()
        self._append({"ts": now, "role": "user", "content": request, "topic": t["id"]})
        self._append({"ts": now, "role": "assistant", "content": reply or "(done)", "topic": t["id"]})
        t["last"], t["n"] = now, t["n"] + 1
        gist = re.sub(r"\s+", " ", re.sub(r"[*`#>_]", "", reply or "")).strip()
        gist = gist[:110] + ("…" if len(gist) > 110 else "")
        if not t.get("gist0"):
            t["gist0"] = gist                   # the topic's first answer, and its latest
        t["gist"] = gist if gist == t["gist0"] else f"{t['gist0']} … {gist}"
        self.fresh = False
        self._save_meta()

    def new_topic(self):
        self.fresh = True

    def resume(self, tid):
        """Make an earlier topic the one in progress (it moves to the end; its messages are kept)."""
        for i, t in enumerate(self.topics):
            if t["id"] == tid:
                self.topics.append(self.topics.pop(i))
                self.topics[-1]["last"] = time.time()
                self.fresh = False
                self._save_meta()
                return self.topics[-1]
        return None

    def forget_topic(self, tid):
        self.topics = [t for t in self.topics if t["id"] != tid]
        self.msgs = [m for m in self.msgs if m.get("topic") != tid]
        with open(self._path("jsonl") + ".tmp", "w", encoding="utf-8") as f:
            for m in self.msgs:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        os.replace(self._path("jsonl") + ".tmp", self._path("jsonl"))
        self._save_meta()

    def transcript(self, limit=60):
        return [{"role": m["role"], "content": m["content"], "ts": m["ts"]} for m in self.msgs[-limit:]]


def side_chats():
    """[{id, title, last}] newest first."""
    out = []
    try:
        names = os.listdir(_dir())
    except OSError:
        return out
    for n in names:
        if n.startswith("side-") and n.endswith(".json"):
            c = Chat(n[:-5])
            last = c.msgs[-1]["ts"] if c.msgs else os.path.getmtime(os.path.join(_dir(), n))
            out.append({"id": c.id, "title": c.title or "Side chat", "last": last})
    return sorted(out, key=lambda x: -x["last"])


def new_side(title=""):
    c = Chat(f"side-{int(time.time() * 1000):x}", title=title.strip()[:60] or "Side chat")
    c._save_meta()
    return c


def delete(cid):
    for ext in ("jsonl", "json"):
        try:
            os.remove(os.path.join(_dir(), f"{cid}.{ext}"))
        except OSError:
            pass


def forget_all():
    """Every conversation, the main one and the side chats, gone from disk ("delete my history with you")."""
    n = 0
    try:
        names = os.listdir(_dir())
    except OSError:
        return 0
    for f in names:
        if f.endswith((".json", ".jsonl")):
            try:
                os.remove(os.path.join(_dir(), f))
                n += 1
            except OSError:
                pass
    return n
