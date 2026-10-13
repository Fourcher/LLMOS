#!/usr/bin/env python3
"""Host-side test for meaning.fetch under the internet setting. yes: the search model downloads. ask: it does not
download unless the owner asked (allowed=True); it raises the plain one-time-download message with the 310 MB size.
no: unchanged message, no download. The downloader (subprocess.Popen in meaning) is replaced by a recorder, so no
network is used and nothing is written outside a temporary folder.
Run: python3 tools/test-meaning-ask.py  (no VM needed). Exit status 0 = pass."""
import os
import shutil
import sys
import tempfile
import types

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import meaning, config  # noqa: E402

failures = []
downloads = []
ASK_MSG = "Searching by meaning needs a one-time download of 310 MB. Say “download the search model” to get it."
NO_MSG = "the internet is switched off, so the search model can't be downloaded"


def check(label, cond):
    if cond:
        print(f"ok {label}")
    else:
        print(f"FAIL {label}")
        failures.append(label)


class Stop(Exception):
    """Raised by the recording downloader so no real transfer runs."""


def fake_popen(cmd, **kw):
    downloads.append(cmd)
    raise Stop()


class FakeSettings:
    def __init__(self, internet):
        self.d = {"internet": internet}

    def get(self, key, default=None):
        return self.d.get(key, default)


def run_fetch(internet, **kw):
    """Returns (outcome, message). outcome: 'download' (downloader reached), 'raised' (fetch refused), 'other'."""
    del downloads[:]
    tmp = tempfile.mkdtemp(prefix="meaning-ask-")
    real_settings, real_dir = config.settings, meaning._dir
    real_popen, real_disk = meaning.subprocess, meaning.models.free_disk_gb
    config.settings = FakeSettings(internet)
    meaning._dir = lambda: tmp
    meaning.subprocess = types.SimpleNamespace(Popen=fake_popen, PIPE=None, DEVNULL=None)
    meaning.models.free_disk_gb = lambda path=None: 100.0
    try:
        meaning.fetch(**kw)
        return "other", ""
    except Stop:
        return "download", ""
    except RuntimeError as e:
        return "raised", str(e)
    finally:
        config.settings, meaning._dir = real_settings, real_dir
        meaning.subprocess, meaning.models.free_disk_gb = real_popen, real_disk
        shutil.rmtree(tmp, ignore_errors=True)


out, _ = run_fetch("yes")
check("yes -> download", out == "download" and len(downloads) == 1)

out, msg = run_fetch("ask")
check("ask -> no download", out == "raised" and downloads == [])
check("ask -> plain message with 310 MB", msg == ASK_MSG and "310 MB" in msg)

out, _ = run_fetch("ask", allowed=True)
check("ask + allowed=True -> download", out == "download" and len(downloads) == 1)

out, msg = run_fetch("no")
check("no -> unchanged message", out == "raised" and msg == NO_MSG and downloads == [])

# find_by_meaning: the model is missing and internet is "ask" -> the owner is asked first (ctx.confirm_network)
from llmos import tools  # noqa: E402

DECLINED = "you declined internet access for this. Continue without it."


class FindCtx:
    def __init__(self, answer=True, headless=False, has_confirm=True):
        self.events, self.confirms, self.statuses, self.shown = [], [], [], []
        self.answer, self.headless = answer, headless
        self.current_request = ""
        if has_confirm:
            self.confirm_network = self._confirm

    def _confirm(self, name, args):
        self.events.append("confirm")
        self.confirms.append((name, args))
        return self.answer

    def status(self, text):
        self.events.append("status")
        self.statuses.append(text)

    def show_ui(self, spec):
        self.shown.append(spec)


def run_find(internet, vision=False, model_present=False, **ctx_kw):
    """Runs find_by_meaning with the model check, fetch, index and search replaced. Returns (ctx, fetch_calls, reply)."""
    ctx = FindCtx(**ctx_kw)
    fetch_calls = []

    def fake_fetch(vision=False, progress=None, allowed=False):
        fetch_calls.append({"vision": vision, "allowed": allowed})
        ctx.events.append("fetch")
        if internet == "ask" and not allowed:
            raise RuntimeError(ASK_MSG)   # the real fetch refuses under "ask" without allowed=True

    saved = (config.settings, meaning.ready, meaning.fetch, meaning.index, meaning.search, meaning._candidates, meaning.available)
    config.settings = FakeSettings(internet)
    meaning.available = lambda: True   # meaning search is installed here; the model itself may be missing
    meaning.ready = lambda vision=False: model_present
    meaning.fetch = fake_fetch
    meaning.index = lambda *a, **k: None
    meaning.search = lambda *a, **k: []
    meaning._candidates = lambda kinds: ([("image", "/x.jpg")] if vision else [])
    try:
        reply = tools.find_by_meaning({"query": "dog on the beach", "kind": "any"}, ctx)
    finally:
        config.settings, meaning.ready, meaning.fetch, meaning.index, meaning.search, meaning._candidates, meaning.available = saved
    return ctx, fetch_calls, reply


ctx, calls, reply = run_find("ask", vision=False)
check("find ask+approve -> one fetch with allowed=True", len(calls) == 1 and calls[0]["allowed"] is True)
check("find ask+approve -> confirm asked once for find_by_meaning", len(ctx.confirms) == 1 and ctx.confirms[0][0] == "find_by_meaning")
url = ctx.confirms[0][1].get("url", "") if ctx.confirms else ""
check("find ask+approve -> confirm text has MB and is <= 60 chars", "MB" in url and len(url) <= 60)
check("find ask+approve -> asked before the status and fetch", ctx.events[:3] == ["confirm", "status", "fetch"])
check("find ask+approve -> existing status shown after approval", any("getting the search model once" in s for s in ctx.statuses))

ctx, calls, reply = run_find("ask", vision=True)
url = ctx.confirms[0][1].get("url", "") if ctx.confirms else ""
check("find ask+approve pictures -> confirm text says 865 MB", "865 MB" in url and len(url) <= 60)

ctx, calls, reply = run_find("ask", answer=False)
check("find ask+decline -> no fetch", calls == [])
check("find ask+decline -> no status shown", ctx.statuses == [])
check("find ask+decline -> declined text returned", reply == DECLINED)

ctx, calls, reply = run_find("ask", headless=True)
check("find headless ask -> no confirm", ctx.confirms == [])
check("find headless ask -> no approved fetch", not any(c["allowed"] for c in calls))
check("find headless ask -> refusal returned", ASK_MSG in reply and reply.startswith("error:"))

ctx, calls, reply = run_find("ask", has_confirm=False)
check("find ask no confirm_network -> refusal, no download", not any(c["allowed"] for c in calls) and ASK_MSG in reply)

ctx, calls, reply = run_find("ask", model_present=True)
check("find model present -> no confirm", ctx.confirms == [])
check("find model present -> no fetch", calls == [])

ctx, calls, reply = run_find("yes")
check("find yes -> fetch with allowed=False, no confirm", len(calls) == 1 and calls[0]["allowed"] is False and ctx.confirms == [])

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
