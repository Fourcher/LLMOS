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
_miss = threading.Lock()  # one model translation at a time; a second miss gets English at once
_PH = re.compile(r"\{[^{}]*\}")
_NUM = re.compile(r"\d+")
_SYSTEM = ("You translate user-interface text. Keep it short and natural. Keep "
           "placeholders like {name} unchanged. Keep these command words in English: "
           "settings, models, tasks, memory, audit, voice, shell, clear, lock, shutdown.")  # as llm.translate_strings


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


def _keeps(text, got):
    """A translation keeps every number and every {placeholder} of the English, in the same count."""
    return (sorted(_NUM.findall(got)) == sorted(_NUM.findall(text))
            and sorted(_PH.findall(got)) == sorted(_PH.findall(text)))


def _ask(text, lang):
    """The model's wording or None. Runs in a worker thread so a hung model cannot hold the reply. The caller
    holds _miss; the worker releases it when the model call really ends, so an abandoned request still blocks
    the next miss instead of queueing behind it."""
    out = {}

    def run():
        try:
            # the same prompt as llm.translate_strings, with the output bounded to the length of the text
            user = (f"Translate every value into {lang}. Return JSON with exactly the same keys.\n\n"
                    + json.dumps([text], ensure_ascii=False))
            schema = {"type": "object", "properties": {text: {"type": "string"}}, "required": [text]}
            r = llm.complete_json(_SYSTEM, user, schema, max_tokens=max(64, 3 * len(text) // 2))
            if isinstance(r, dict):
                r = r.get(text)
            out["t"] = r
        except Exception:
            pass
        finally:
            _miss.release()

    try:
        th = threading.Thread(target=run, daemon=True)
        th.start()
    except Exception:
        _miss.release()
        return None
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
        if llm.busy():                # the owner's turn is using the model: no translation now
            return text
        if not _miss.acquire(blocking=False):   # another translation is in flight
            return text
        got = _ask(text, lang)       # releases _miss when its model call ends
        if not (isinstance(got, str) and got.strip() and _keeps(text, got)):
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
