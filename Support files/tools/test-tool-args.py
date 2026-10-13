#!/usr/bin/env python3
"""Host-side unit test: enumerated tool arguments are checked before anything is stored or renamed.
  set_appearance.corners  rounded|square|double|heavy|none (case-insensitive; "round" -> rounded)
  rename_files.spaces     dashes|underscores|remove|keep  ("dash"/"underscore" aliases)
  rename_files.case       lower|upper|title|keep           (lowercase/uppercase/titlecase aliases)
  mail_setup.smtp_security starttls|ssl|none (case-insensitive; "tls" -> starttls); anything else is an error,
  never plaintext.
Run: python3 tools/test-tool-args.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
import tempfile

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

home = tempfile.mkdtemp()
os.environ["LLMOS_HOME"] = home

from llmos import tools, mail  # noqa: E402


class FakeCtx:
    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeSettings:
    def __init__(self):
        self.store = {}

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value):
        self.store[key] = value


ctx = FakeCtx()
settings = FakeSettings()
tools.config.settings = settings
tools._undo_push = lambda *a, **k: None
tools._settings_snapshot = lambda: {}
REG = tools.REGISTRY


def corners(v):
    return REG["set_appearance"].fn({"corners": v}, ctx)


# --- set_appearance.corners ---
for raw, want in [("rounded", "rounded"), ("square", "square"), ("double", "double"), ("heavy", "heavy"),
                  ("none", "none"), ("SQUARE", "square"), (" Heavy ", "heavy"), ("round", "rounded")]:
    settings.store.clear()
    r = corners(raw)
    assert settings.store.get("appearance.corners") == want, (raw, settings.store, r)
    assert r.startswith("corners ") or "corners" in r, r
    print(f"ok corners {raw!r} -> {want}")

for bad in ["roundd", "circle", "tsquare"]:
    settings.store.clear()
    r = corners(bad)
    assert r == "error: corners must be rounded, square, double, heavy or none", r
    assert "appearance.corners" not in settings.store, settings.store
    print(f"ok corners {bad!r} refused, nothing stored")

# --- rename_files ---
def make_tree():
    d = tempfile.mkdtemp()
    for n in ["my file.txt", "Other Doc.txt"]:
        open(os.path.join(d, n), "w").close()
    return d


def names(d):
    return sorted(os.listdir(d))


d = make_tree()
r = REG["rename_files"].fn({"folder": d, "files": [os.path.join(d, "my file.txt")], "spaces": "underscore"}, ctx)
assert names(d) == ["Other Doc.txt", "my_file.txt"], (names(d), r)
print("ok spaces underscore alias renames", r[:60])

d = make_tree()
r = REG["rename_files"].fn({"folder": d, "files": [os.path.join(d, "my file.txt")], "spaces": "DASHES"}, ctx)
assert names(d) == ["Other Doc.txt", "my-file.txt"], (names(d), r)
print("ok spaces DASHES case-insensitive renames")

d = make_tree()
r = REG["rename_files"].fn({"folder": d, "files": [os.path.join(d, "Other Doc.txt")], "case": "Lowercase"}, ctx)
assert names(d) == ["my file.txt", "other doc.txt"], (names(d), r)
print("ok case Lowercase alias renames")

for bad_args in [{"spaces": "tabs"}, {"case": "sentence"}, {"spaces": "dash_s", "case": "lower"}]:
    d = make_tree()
    a = {"folder": d, "files": [os.path.join(d, "my file.txt"), os.path.join(d, "Other Doc.txt")]}
    a.update(bad_args)
    before = names(d)
    r = REG["rename_files"].fn(a, ctx)
    assert r.startswith("error: "), r
    assert names(d) == before, (names(d), before)
    print(f"ok rename_files {bad_args} refused, nothing renamed: {r}")

# --- mail smtp_security ---
captured = {}
mail._imap = lambda acct: type("C", (), {"logout": lambda self: None})()
mail._smtp_check = lambda acct: None
mail.config.save_json = lambda path, data: captured.update(data)

for raw, want in [("starttls", "starttls"), ("ssl", "ssl"), ("none", "none"), ("SSL", "ssl"), ("TLS", "starttls")]:
    captured.clear()
    r = REG["mail_setup"].fn({"address": "a@example.com", "password": "pw", "smtp_security": raw}, ctx)
    assert captured.get("smtp_security") == want, (raw, captured, r)
    assert r.startswith("email set up"), r
    print(f"ok smtp_security {raw!r} -> {want}")

for bad in ["tsl", "plain", "nonee", "starttl"]:
    captured.clear()
    r = REG["mail_setup"].fn({"address": "a@example.com", "password": "pw", "smtp_security": bad}, ctx)
    assert r.startswith("error: smtp_security must be starttls, ssl or none"), r
    assert not captured, ("saved despite bad smtp_security", captured)
    print(f"ok smtp_security {bad!r} refused, nothing saved")

print("all good")
