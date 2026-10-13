"""Replies the OS gives at once (desk.instant_reply) in the owner's language.

The English wording is the source. For any other language the sentence is translated by the on-device model once
and kept in a small cache, so the same reply costs nothing the next time. Never blocks longer than TIMEOUT_S and
never raises: when the model is down, slow or wrong, the English text is shown. English owners get the text back
at once, with no thread and no cache file touched."""
import json
import os
import re
import tempfile
import threading

from . import config, i18n, llm

TIMEOUT_S = 4.0          # the longest a reply waits for the model
MAX_CHARS = 2000         # longer text is not translated (shown in English)
MAX_ENTRIES = 2000       # the cache keeps this many replies; the oldest are dropped first
_lock = threading.Lock()  # one reply file is read and written by one thread at a time
_PH = re.compile(r"\{[^{}]*\}")


def _path(code):
    return os.path.join(config.home(), ".llmos", "cache", "replies-%s.json" % code)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, d):
    folder = os.path.dirname(path)
    os.makedirs(os.path.dirname(folder), mode=0o700, exist_ok=True)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".replies-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _translatable(text):
    """Only text with letters in it, short enough; a number or an emoji alone reads the same everywhere."""
    return 0 < len(text) <= MAX_CHARS and re.search(r"[^\W\d_]", text) is not None


def _ask(text, lang):
    """The model's wording or None. Runs in a worker thread so a hung model cannot hold the reply."""
    out = {}

    def run():
        try:
            r = llm.translate_strings([text], lang)
            if isinstance(r, dict):
                r = r.get(text)
            out["t"] = r
        except Exception:
            pass

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(TIMEOUT_S)
    return None if th.is_alive() else out.get("t")


def translate(text, lang):
    """text in the owner's language (lang is the language name, e.g. 'Spanish'); English text when unsure."""
    try:
        code = i18n.lang_code(lang)
        if code == "en" or not isinstance(text, str) or not _translatable(text):
            return text
        path = _path(code)
        with _lock:
            hit = _read(path).get(text)
        if isinstance(hit, str) and hit.strip():
            return hit
        got = _ask(text, lang)
        if not (isinstance(got, str) and got.strip()
                and sorted(_PH.findall(got)) == sorted(_PH.findall(text))):
            return text
        with _lock:
            cache = _read(path)
            cache.pop(text, None)
            cache[text] = got
            while len(cache) > MAX_ENTRIES:
                cache.pop(next(iter(cache)))
            try:
                _write(path, cache)
            except OSError:
                pass
        return got
    except Exception:
        return text
