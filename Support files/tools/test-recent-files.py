#!/usr/bin/env python3
"""Host-side test of the last_saved tool's periods (no VM): a temp home whose files have set mtimes.
Run: python3 tools/test-recent-files.py"""
import os
import sys
import tempfile
import time
import datetime as dt

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import config, tools  # noqa: E402

NOW = time.time()
MIDNIGHT = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
YEST_15 = (dt.datetime.combine(dt.date.today() - dt.timedelta(days=1), dt.time()) + dt.timedelta(hours=15)).timestamp()

FIXTURE = {
    "recent30.txt": (NOW - 30 * 60, "Documents"),
    "yesterday15.txt": (YEST_15, "Documents"),
    "threedays.txt": (NOW - 3 * 86400, "Downloads"),
    "tendays.txt": (NOW - 10 * 86400, "Downloads"),
}


def make_home(files, hidden=()):
    home = tempfile.mkdtemp(prefix="llmos-recent-")
    for name, (when, folder) in files.items():
        d = os.path.join(home, folder)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        open(p, "w").write("x")
        os.utime(p, (when, when))
    for rel, when in hidden:
        p = os.path.join(home, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write("x")
        os.utime(p, (when, when))
    return home


def run(home, args):
    real = config.home
    config.home = lambda: home
    try:
        return tools.last_saved(args, None)
    finally:
        config.home = real


def names(out):
    return [line.split(" in ")[0][2:] for line in out.splitlines() if line.startswith("- ")]


bad = 0
# a real open_file success reply (launched in an app)
OK_REPLY = "opened new.txt in Mousepad. Done: if the request asked for more, do the next step now; otherwise tell the owner in one sentence."


def check(label, got, want):
    global bad
    if got != want:
        bad += 1
        print(f"FAIL {label}: got {got!r} wanted {want!r}")
    else:
        print(f"ok {label}: {got}")


home = make_home(FIXTURE, hidden=[(".secret.txt", NOW - 600), (".cache/cached.txt", NOW - 600),
                                  (".local/share/lo.txt", NOW - 600)])
# a symlink to a recent file must not be listed
os.symlink(os.path.join(home, "Documents", "recent30.txt"), os.path.join(home, "Documents", "link.txt"))

# the default (no since): newest in the last two hours
check("default", run(home, {}).startswith("It's ~/Documents/recent30.txt (saved 30 minutes ago)"), True)

# hour: only the 30-minute-old file
check("hour", names(run(home, {"since": "hour"})), ["recent30.txt"])

# today: 30 minutes ago counts only if it is after today's midnight (it is, except within the first 30 minutes of the day)
today_want = ["recent30.txt"] if NOW - 30 * 60 >= MIDNIGHT else []
check("today", names(run(home, {"since": "today"})), today_want)

# yesterday: yesterday 15:00, plus recent30 when the clock is within its first 30 minutes (recent30 is then yesterday's file).
# The product takes "yesterday" from datetime.date.today() (not patchable), so the expectation is derived from the same clock.
yest_recent = NOW - 30 * 60 < MIDNIGHT
newest_yest = "recent30.txt" if yest_recent else "yesterday15.txt"
check("yesterday", names(run(home, {"since": "yesterday"})),
      ["recent30.txt", "yesterday15.txt"] if yest_recent else ["yesterday15.txt"])

# yesterday, early in the day: a file saved yesterday at 00:01 is yesterday's (a 24 h window drops it once the clock passes 00:01);
# a file saved today at 00:01 is not yesterday's (a 24 h window keeps it). Own home, so the checks above are unchanged.
YEST_MIDNIGHT = dt.datetime.combine(dt.date.today() - dt.timedelta(days=1), dt.time()).timestamp()
early = {"yesterday_early.txt": (YEST_MIDNIGHT + 60, "Documents")}
if NOW >= MIDNIGHT + 120:
    early["today_early.txt"] = (MIDNIGHT + 60, "Documents")
else:
    print("skip A (too close to midnight)")
home5 = make_home(early)
check("yesterday early", names(run(home5, {"since": "yesterday"})), ["yesterday_early.txt"])

# week: the last 7 days, newest first (3 days ago is in, 10 days ago is out)
check("week order", names(run(home, {"since": "week"})), ["recent30.txt", "yesterday15.txt", "threedays.txt"])

# hidden files, hidden folders and symlinks never appear
everything = run(home, {"since": "week"}) + run(home, {})
check("hidden skipped", [n for n in ("secret", "cached", "lo.txt", "link.txt") if n in everything], [])

# the result line carries folder and time
line = [l for l in run(home, {"since": "yesterday"}).splitlines() if l.startswith("- yesterday15.txt ")][0]
check("yesterday line", line.endswith("in ~/Documents (yesterday 15:00)"), True)

# an unknown period is an error, not a scan
check("bad since", run(home, {"since": "decade"}), "error: since must be hour, today, yesterday or week")

# max 10, newest first, even when more files match
many = {f"f{i:02d}.txt": (NOW - i * 60, "Documents") for i in range(1, 13)}
home2 = make_home(many)
got = names(run(home2, {"since": "week"}))
check("max 10 newest first", got, [f"f{i:02d}.txt" for i in range(1, 11)])

# the 20000-file cap: with the cap at 3 the scan stops early
real_cap = tools._RECENT_CAP
tools._RECENT_CAP = 3
try:
    got = names(run(home2, {"since": "hour"}))
    check("cap stops the scan", len(got) <= 3 and len(got) > 0, True)
finally:
    tools._RECENT_CAP = real_cap

# open=True: the open tool (tools.open_file) is called with the newest file and nothing else is opened
opened = []
real_open = tools.open_file
tools.open_file = lambda a, ctx: opened.append(a["path"]) or OK_REPLY
try:
    home3 = make_home({"old.txt": (NOW - 3600, "Documents"), "new.txt": (NOW - 600, "Documents")})
    out = run(home3, {"open": True})
    check("open newest", (opened, out), ([os.path.join(home3, "Documents", "new.txt")], "Opened new.txt (saved 10 minutes ago)."))
    opened.clear()
    out = run(home, {"since": "yesterday", "open": True})
    check("open yesterday", (opened, out.startswith(f"Opened {newest_yest} (saved yesterday ")),
          ([os.path.join(home, "Documents", newest_yest)], True))
    opened.clear()
    home4 = make_home({})
    check("open nothing", (run(home4, {"open": True}), opened),
          ("Nothing new was saved in the last two hours.", []))
    check("open nothing since", (run(home4, {"since": "week", "open": True}), opened),
          ("No files were saved in the last 7 days.", []))
    opened.clear()
    # open fails: the failure text is the reply, not "Opened ..."
    tools.open_file = lambda a, ctx: opened.append(a["path"]) or "error: there is no file " + a["path"]
    out = run(home3, {"open": True})
    check("open failed", (opened, out), ([os.path.join(home3, "Documents", "new.txt")], "error: there is no file " + os.path.join(home3, "Documents", "new.txt")))
    tools.open_file = lambda a, ctx: opened.append(a["path"]) or OK_REPLY
    opened.clear()
    # open_file replies that are NOT successes come back unchanged, never "Opened ..."
    not_success = [
        ("newest is a PDF", "report.pdf", "report.pdf is a PDF, 12 KB; it cannot be shown as text (say 'install mupdf' to get a PDF viewer)"),
        ("mp3 with no sound", "song.mp3", "there is no screen or sound device to play it on"),
        ("5 MB text", "big.txt", "big.txt is 5.0 MB of text, too big to show whole; read_file can take part of it"),
        ("error reply", "report.pdf", "error: there is no file /elsewhere/report.pdf"),
        ("file named opened...", "opened.pdf", "opened.pdf is a PDF, 12 KB; it cannot be shown as text"),
    ]
    for label, fname, reply in not_success:
        h5 = make_home({fname: (NOW - 300, "Documents")})
        p5 = os.path.join(h5, "Documents", fname)
        tools.open_file = lambda a, ctx, reply=reply: opened.append(a["path"]) or reply
        opened.clear()
        out = run(h5, {"open": True})
        check(f"not success: {label}", (opened, out), ([p5], reply))
    h5 = make_home({"report.pdf": (NOW - 300, "Documents")})
    p5 = os.path.join(h5, "Documents", "report.pdf")
    # the success reply, with a real success text from open_file
    tools.open_file = lambda a, ctx: opened.append(a["path"]) or "opened report.pdf in Firefox. Done: say one sentence."
    opened.clear()
    check("success: PDF opened", (opened, run(h5, {"open": True})), ([p5], "Opened report.pdf (saved 5 minutes ago)."))
    tools.open_file = lambda a, ctx: opened.append(a["path"]) or OK_REPLY
    opened.clear()
    # no open flag: the same replies, and no open call
    check("no open flag", (run(home3, {}).startswith("It's ~/Documents/new.txt"), opened), (True, []))
finally:
    tools.open_file = real_open

if bad:
    print(f"{bad} FAILED")
    sys.exit(1)
print("all good")
