#!/usr/bin/env python3
"""Host-side test: the 'keep the password somewhere safe' sentence on folder lock is shown once, not on every lock.
desk.py needs GTK, so the helper and the folder form are read from its source and run against a dict-backed settings
fake (config.settings) and a fake window. Run: python3 tools/test-lock-advice-once.py"""
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
src = open(SRC, encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class FakeSettings:
    """Dict-backed stand-in for config.settings with the same dotted-key get/set as config.py."""

    def __init__(self, broken=False):
        self.data = {}
        self.broken = broken

    def get(self, key, default=None):
        cur = self.data
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, key, value):
        if self.broken:
            raise OSError("settings store is read-only")
        node = self.data
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value


class FakeConfig:
    def __init__(self, settings):
        self.settings = settings

    def home(self):
        return "/home/llm"


class FakeDesk:
    """Collects what folder_form would open."""

    def __init__(self):
        self.windows = []

    def open_window(self, spec):
        self.windows.append(spec)


def load(settings):
    """Run desk.py's helper and folder_form with config bound to the fake settings store."""
    ns = {"re": re, "os": os, "sys": sys, "config": FakeConfig(settings)}
    exec(src[src.index("def _lock_tip_take"):src.index("def _wallpaper")], ns)
    class_ns = {"re": re, "os": os, "sys": sys, "config": ns["config"], "_lock_tip_take": ns["_lock_tip_take"]}
    exec("class X:\n" + src[src.index("    def folder_form"):src.index("    def mail_form")], class_ns)
    return ns["_lock_tip_take"], class_ns["X"].folder_form


def form_text(folder_form, kind):
    d = FakeDesk()
    d.folder_nonce = None
    folder_form(d, kind, "/home/llm/Taxes")
    return d.windows[-1]["blocks"][0]["text"]


SENTENCE = "Without the password the files can't be got back"
LOCK_SUCCESS = "Keep the password somewhere safe: without it the files can't be got back."

print("shown once")
settings = FakeSettings()
take, folder_form = load(settings)
first = form_text(folder_form, "lock")
check(SENTENCE in first, f"first lock form shows the sentence: {first!r}")
check(settings.get("tips.lock_password_shown") is True, "first show stores tips.lock_password_shown = True")
second = form_text(folder_form, "lock")
check(SENTENCE not in second, f"second lock form omits the sentence: {second!r}")
check(second.startswith("~/Taxes becomes one locked file") and second.endswith("with 7-Zip."),
      "second lock form keeps the rest of its text")
check(take() is False, "the success message (second spot) does not show the sentence after the first")
check(form_text(folder_form, "lock") == second, "form text stays identical on later locks")

print("the success message uses the same flag")
settings2 = FakeSettings()
take2, _ = load(settings2)
check(take2() is True, "first success message takes the sentence")
check(take2() is False, "second success message does not")
check(settings2.get("tips.lock_password_shown") is True, "flag stored under tips.lock_password_shown")

print("unlock form unchanged")
settings3 = FakeSettings()
_, folder_form3 = load(settings3)
unlock = form_text(folder_form3, "unlock")
check(unlock == "The password ~/Taxes was locked with.", f"unlock text unchanged: {unlock!r}")
check(settings3.get("tips.lock_password_shown") is None, "unlock does not use up the flag")

print("settings store unwritable")
broken = FakeSettings(broken=True)
take4, folder_form4 = load(broken)
try:
    txt = form_text(folder_form4, "lock")
    check(SENTENCE in txt, "lock form still opens and shows the sentence when set raises")
    check(take4() is True, "success message still gets the sentence when set raises (may repeat next time)")
except Exception as e:
    check(False, f"no crash when set raises: {e!r}")

print("desk.py wiring")
check(src.count(LOCK_SUCCESS) == 1, "the success sentence appears once in desk.py")
check(src.count("tip = _lock_tip_take()") == 2, "both lock spots call _lock_tip_take()")

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
