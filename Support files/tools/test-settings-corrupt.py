#!/usr/bin/env python3
"""Host-side test that config.Settings.set never drops the owner's other settings when settings.json is corrupt.

A good file keeps its other keys. A corrupt file after a good load keeps the last good values and leaves a
settings.json.broken-<stamp> copy. A corrupt file with no earlier good load gets only the new key, plus the copy.
A list, an empty file, or "{" alone counts as corrupt. A missing file is created normally, with no copy.
ETC is a temp dir (writable), so the direct write path is used; rootd is never called.
Run: python3 tools/test-settings-corrupt.py"""
import glob
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-settings-corrupt-home-")
os.environ.update(LLMOS_HOME=home, LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import config  # noqa: E402

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print(f"ok {name}")
    else:
        fails += 1
        print(f"FAIL {name} {detail}")


def fresh_etc(tag):
    """A new ETC dir for one case, and a fresh process state (no last-good values kept yet)."""
    d = tempfile.mkdtemp(prefix=f"llmos-settings-{tag}-")
    config.ETC = d
    config.settings.path = os.path.join(d, "settings.json")
    config._good_settings = None
    return d


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def broken_copies(d):
    return sorted(glob.glob(os.path.join(d, "settings.json.broken-*")))


GOOD = {"language": "French", "autonomy": "hands-off", "appearance": {"scale": 120, "font": "serif"}}

# (1) good file: set keeps the other keys, get sees the new value
d = fresh_etc("good")
with open(config.settings.path, "w", encoding="utf-8") as f:
    json.dump(GOOD, f)
config.settings.set("internet", "no")
got = read_json(config.settings.path)
check("good file keeps other keys",
      got.get("language") == "French" and got.get("autonomy") == "hands-off"
      and got.get("appearance") == {"scale": 120, "font": "serif"} and got.get("internet") == "no", json.dumps(got))
check("good file: get sees the new value", config.settings.get("internet") == "no")
check("good file: no broken copy", broken_copies(d) == [], str(broken_copies(d)))

# (2) corrupt after a good load: earlier good keys kept, .broken copy written
d = fresh_etc("after-good")
with open(config.settings.path, "w", encoding="utf-8") as f:
    json.dump(GOOD, f)
config.settings.all()  # the process loads the good file
corrupt_text = '{"language": "French", "autonomy": '
with open(config.settings.path, "w", encoding="utf-8") as f:
    f.write(corrupt_text)
config.settings.set("tor", True)
got = read_json(config.settings.path)
check("corrupt after good load keeps earlier good keys",
      got.get("language") == "French" and got.get("autonomy") == "hands-off"
      and got.get("appearance") == {"scale": 120, "font": "serif"} and got.get("tor") is True, json.dumps(got))
copies = broken_copies(d)
check("corrupt after good load writes a .broken copy",
      len(copies) == 1 and os.path.basename(copies[0]).startswith("settings.json.broken-")
      and open(copies[0], encoding="utf-8").read() == corrupt_text, str(copies))

# (3) corrupt from the start (no good load in this process): only the new key, plus the copy
for tag, text in (("empty", ""), ("brace", "{"), ("typo", '{"language": "French",,}')):
    d = fresh_etc("start-" + tag)
    with open(config.settings.path, "w", encoding="utf-8") as f:
        f.write(text)
    config.settings.set("tor", True)
    got = read_json(config.settings.path)
    check(f"corrupt from start ({tag}) keeps only the new key", got == {"tor": True}, json.dumps(got))
    check(f"corrupt from start ({tag}) writes a .broken copy",
          len(broken_copies(d)) == 1 and open(broken_copies(d)[0], encoding="utf-8").read() == text,
          str(broken_copies(d)))

# (4) list JSON counts as corrupt: after a good load, good keys kept and a copy written
d = fresh_etc("list")
with open(config.settings.path, "w", encoding="utf-8") as f:
    json.dump(GOOD, f)
config.settings.all()
with open(config.settings.path, "w", encoding="utf-8") as f:
    f.write('["language", "French"]')
config.settings.set("tor", True)
got = read_json(config.settings.path)
check("list JSON treated as corrupt (good keys kept)",
      got.get("language") == "French" and got.get("tor") is True and not isinstance(got, list), json.dumps(got))
check("list JSON writes a .broken copy", len(broken_copies(d)) == 1, str(broken_copies(d)))

# (5) missing file (first run): created normally, no copy
d = fresh_etc("missing")
config.settings.set("tor", True)
check("missing file is created with the new key", read_json(config.settings.path) == {"tor": True},
      str(read_json(config.settings.path)))
check("missing file: no broken copy", broken_copies(d) == [], str(broken_copies(d)))

for p in (home,):
    shutil.rmtree(p, ignore_errors=True)

if fails:
    print(f"{fails} FAIL")
    sys.exit(1)
print("all good")
