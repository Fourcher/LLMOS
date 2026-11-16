"""A bug the owner points at, fixed on this laptop, and reported upstream after they approve it.

"I found a bug, fix it" saves the active window, any screen text or screenshot the OS already has,
and a short slice of logs, then hands that to the on-device loop. The loop uses the local model.
Nothing is installed until the owner says "apply that fix". "undo that fix" drops a staged fix,
or puts the previous files back when one was installed.

The laptop signs that install with a key the owner generates here ("trust this laptop for updates").
An update source on another computer stays paired if they set one. After a kept install, the same
fix is opened as a pull request on Fourcher/LLMOS. A failed fix can be filed as an issue instead.
Neither is merged. If GitHub or the token is missing, the report waits and is tried again later.
"""
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

from . import ghreport, selfloop_ctl

RAILS_NOTE = (
    "Fix this on a staging copy with the local model only. "
    "Do not edit selfloop_ctl.py or ota.py. "
    "Do not edit tests or run-host-tests.sh. "
    "Do not restart network services, ssh, tailscale, or the model server. "
    "Do not weaken the kill switch, the daily cap, or the signature check. "
    "Run light tests only. Never run the full suite. "
    "Do not write tokens, keys, or passwords into the source."
)

_FILL = r"(?:please\s+)?(?:hey[, ]+)?"
_REPORT_SHORT = re.compile(rf"^\s*{_FILL}fix\s+(?:this|that)\s+bug\s*(?:please\s*)?[.!]?\s*$", re.I)
_REPORT = re.compile(
    rf"^\s*{_FILL}"
    r"(?:(?:i\s+found|i'?ve\s+found|there(?:'s| is)|this is|that is|something(?:'s| is))\s+(?:a\s+)?bug\b"
    r"|(?:this|that|it|something)(?:'s| is)\s+broken\b"
    r"|(?:this|that|it|something)\s+is\s+not\s+working\b"
    r"|(?:this|that|it)\s+doesn'?t\s+work\b)"
    r"[\s\S]{0,800}?"
    r"(?:,|\.|;)?\s*(?:please\s+)?fix(?:\s+(?:it|this|that))?\s*(?:please\s*)?[.!]?\s*$",
    re.I)
_APPLY = re.compile(
    rf"^\s*{_FILL}(?:yes[, ]+)?(?:go ahead and\s+)?(?:apply|install)\s+(?:that|the|this)\s+fix\s*[.!]?\s*$",
    re.I)
_UNDO = re.compile(
    rf"^\s*{_FILL}(?:undo|revert|drop|discard)\s+(?:that|the|this|the last)\s+fix\s*[.!]?\s*$",
    re.I)
_ISSUE = re.compile(
    rf"^\s*{_FILL}(?:file\s+(?:that|it|this)\s+as\s+(?:an?\s+)?(?:github\s+)?issue"
    r"|open\s+(?:an?\s+)?(?:github\s+)?issue\s+for\s+(?:that|this|the)\s+bug"
    r"|report\s+(?:that|this|the)\s+bug\s+as\s+an?\s+issue)\s*[.!]?\s*$",
    re.I)
_TRUST = re.compile(
    rf"^\s*{_FILL}(?:trust\s+this\s+(?:laptop|computer)\s+for\s+updates"
    r"|sign\s+my\s+own\s+updates"
    r"|sign\s+updates\s+on\s+this\s+(?:laptop|computer)"
    r"|(?:make|use)\s+this\s+(?:laptop|computer)\s+(?:the|as the)\s+update\s+source)\s*[.!]?\s*$",
    re.I)
_DISTRUST = re.compile(
    r"^\s*(?:please\s+)?(?:stop|don'?t)\s+sign(?:ing)?\s+(?:my\s+own\s+)?updates"
    r"(?:\s+on\s+this\s+(?:laptop|computer))?\s*[.!]?\s*$",
    re.I)
_STATUS = re.compile(
    r"^\s*(?:please\s+)?(?:what happened with that fix|what did (?:you|that fix) change|status of that fix)"
    r"\s*[?.!]?\s*$",
    re.I)
_RETRY = re.compile(
    r"^\s*(?:please\s+)?(?:try the github report again|send the pending (?:github )?report|"
    r"retry the (?:pull request|github report))\s*[.!]?\s*$",
    re.I)

_runner = None
_ship = None


def set_runner(fn):
    """Tests pass the loop starter. None restores the real one."""
    global _runner
    _runner = fn


def set_ship(fn):
    global _ship
    _ship = fn


def save_github_token(text):
    """Save the owner's fine-grained GitHub token on this computer. The value is not returned."""
    return ghreport.save_token(text)


def _plain(text):
    return str(text or "").translate({0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"', 0x2032: "'"})


def _description(text):
    t = _plain(text).strip().rstrip(".!?")
    t = re.sub(r"^(?:please\s+)?(?:hey[, ]+)+", "", t, flags=re.I).strip()
    return ghreport.redact(t)[:500]


def classify(text):
    """(action, description) when this sentence is one of the bug-fix phrases, else None."""
    raw = _plain(text).strip()
    if not raw or "\n" in raw or len(raw) > 2000:
        return None
    if _DISTRUST.match(raw):
        return ("distrust", "")
    if _TRUST.match(raw):
        return ("trust", "")
    if _APPLY.match(raw):
        return ("apply", "")
    if _UNDO.match(raw):
        return ("undo", "")
    if _ISSUE.match(raw):
        return ("issue", "")
    if _RETRY.match(raw):
        return ("retry", "")
    if _STATUS.match(raw):
        return ("status", "")
    if _REPORT_SHORT.match(raw) or _REPORT.match(raw):
        return ("report", _description(raw))
    return None


def handle_line(text):
    hit = classify(text)
    if not hit:
        return ""
    return handle_action(hit[0], hit[1])


def handle_action(action, description=""):
    action = str(action or "").strip().lower()
    if action == "report":
        return report(description)
    if action == "apply":
        return apply()
    if action == "undo":
        return undo()
    if action == "issue":
        return file_issue()
    if action == "trust":
        return trust_self()
    if action == "distrust":
        return distrust_self()
    if action == "retry":
        return ghreport.retry(force=True)
    if action == "status":
        return status_speech()
    return "Say “I found a bug, fix it”, “apply that fix”, or “undo that fix”."


def key_dir():
    return os.path.join(selfloop_ctl.state_dir(), "ota", "keys")


def _fingerprint(key):
    from . import ota
    return ota.fingerprint(key)


def _ensure_key():
    """The same on-device Ed25519 key the installer pins. A swapped private key is refused."""
    directory = key_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    priv = os.path.join(directory, "selfloop")
    pub_path = priv + ".pub"
    if not os.path.isfile(priv) or not os.path.isfile(pub_path):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "llmos-selfloop", "-f", priv],
                       check=True, stdout=subprocess.DEVNULL)
        os.chmod(priv, 0o600)
    pub = open(pub_path, encoding="utf-8").read().strip()
    pin_path = os.path.join(directory, "pinned.pub")
    if os.path.isfile(pin_path):
        pin = open(pin_path, encoding="utf-8").read().strip()
        if pin != pub:
            raise RuntimeError("pin mismatch")
    else:
        with open(pin_path, "w", encoding="utf-8") as handle:
            handle.write(pub + "\n")
        os.chmod(pin_path, 0o644)
        pin = pub
    return priv, pin


def self_trusted():
    """True when the owner has accepted the pinned on-device key."""
    try:
        pin = open(os.path.join(key_dir(), "pinned.pub"), encoding="utf-8").read().strip()
        mark = open(os.path.join(key_dir(), "trusted"), encoding="utf-8").read().strip().splitlines()
    except OSError:
        return False
    if not pin or not mark:
        return False
    return mark[0].strip() == _fingerprint(pin)


def source_clause():
    """A sentence for the updates status, empty when this laptop is not a trusted signer."""
    if not self_trusted():
        return ""
    try:
        pin = open(os.path.join(key_dir(), "pinned.pub"), encoding="utf-8").read().strip()
    except OSError:
        return ""
    return f" This laptop can also sign its own updates (key {_fingerprint(pin)})."


def trust_self():
    """Generate or reuse the on-device key, pin it, and tell the owner the key code."""
    try:
        _priv, pin = _ensure_key()
    except (OSError, subprocess.CalledProcessError, RuntimeError):
        try:
            os.remove(os.path.join(key_dir(), "trusted"))
        except OSError:
            pass
        return ("I couldn't make a signing key on this computer. Nothing was trusted, "
                "and nothing will be installed from a spoken fix.")
    fp = _fingerprint(pin)
    path = os.path.join(key_dir(), "trusted")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(fp + "\n" + str(int(time.time())) + "\n")
    os.chmod(path, 0o644)
    try:
        from . import ota
        other = ota.paired()
    except Exception:
        other = None
    if other:
        extra = f" Updates from {other.get('name') or 'your other computer'} are still on."
    else:
        extra = " You can still say “get updates from my computer” to trust another computer as well."
    return (f"This laptop can sign its own updates. The key code is {fp}. "
            "A fix still waits until you say “apply that fix”, and a failed health check puts the old files back."
            + extra)


def distrust_self():
    path = os.path.join(key_dir(), "trusted")
    try:
        os.remove(path)
    except OSError:
        pass
    return ("This laptop will no longer sign a spoken fix. The key stays on disk. "
            "Updates from another computer are unchanged.")


def _tail(path, n=40):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def capture_window():
    try:
        from . import wm
        app_id = wm.last_program() or ""
        return app_id, (wm.NAMES.get(app_id, app_id) if app_id else "")
    except Exception:
        return "", ""


def capture_screen_text():
    path = os.environ.get("LLMOS_SCREEN_TEXT", "/run/llmos/screen.txt")
    if not path:
        return ""
    try:
        if os.path.isfile(path):
            return ghreport.redact(open(path, encoding="utf-8", errors="replace").read()[:2000])
    except OSError:
        pass
    return ""


def capture_screenshot():
    env = os.environ.get("LLMOS_BUGFIX_SHOT", "").strip()
    if env and os.path.isfile(env):
        return env
    try:
        from . import config
        home = config.home()
    except Exception:
        return ""
    shots = sorted(glob.glob(os.path.join(home, "Pictures", "screenshot-*.png")))
    return shots[-1] if shots else ""


def capture_logs(window_id=""):
    chunks = []
    extra = os.environ.get("LLMOS_BUGFIX_LOG", "").strip()
    if extra:
        text = _tail(extra, 40)
        if text:
            chunks.append(text)
    results = _tail(os.path.join(selfloop_ctl.state_dir(), "results.jsonl"), 20)
    if results:
        chunks.append(results)
    if os.environ.get("LLMOS_BUGFIX_JOURNAL", "1") != "0" and shutil.which("journalctl"):
        units = ["llmos-desk", "llmos-scheduler"]
        if window_id and window_id not in units:
            units.append(window_id)
        for unit in units[:3]:
            try:
                proc = subprocess.run(["journalctl", "-n", "30", "--no-pager", "-u", unit],
                                      capture_output=True, text=True, timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                continue
            text = (proc.stdout or "").strip()
            if text and "No entries" not in text:
                chunks.append(text[-1500:])
    return ghreport.redact("\n".join(chunks))[:4000]


def capture_context():
    app_id, name = capture_window()
    return {
        "window_id": app_id, "window_name": name,
        "screen_text": capture_screen_text(), "screenshot": capture_screenshot(),
        "logs": capture_logs(app_id),
    }


def _seed():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "selfloop-backlog.json")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


def _already(description):
    for row in selfloop_ctl.load_backlog(_seed()):
        if not isinstance(row, dict) or row.get("source") != "voice":
            continue
        if row.get("status") in ("open", "queued") and row.get("description") == description:
            return True
    return False


def make_item(description, ctx):
    """One device-mode task. The rails are part of the text the model is given."""
    ctx = ctx or {}
    description = ghreport.redact(description or "a bug on the screen")[:500]
    bits = [f"The owner said: {description}"]
    if ctx.get("window_name") or ctx.get("window_id"):
        bits.append(f"Active window: {ctx.get('window_name') or ctx.get('window_id')}")
    if ctx.get("screen_text"):
        bits.append("Screen text:\n" + str(ctx.get("screen_text"))[:1500])
    if ctx.get("screenshot"):
        bits.append("Screenshot: " + str(ctx.get("screenshot"))[:300])
    if ctx.get("logs"):
        bits.append("Recent logs:\n" + str(ctx.get("logs"))[:1500])
    bits.append(RAILS_NOTE)
    detail = "\n\n".join(bits)[:4000]
    stamp = str(time.time())
    return {
        "id": "bug-" + hashlib.sha256((description + "|" + stamp).encode("utf-8")).hexdigest()[:10],
        "title": ("Fix a bug the owner found: " + description)[:140],
        "detail": detail,
        "description": description,
        "source": "voice",
        "status": "open",
        "mode": "device",
        "backend": "local",
        "context": {
            "window_id": ctx.get("window_id") or "",
            "window_name": ctx.get("window_name") or "",
            "screenshot": ctx.get("screenshot") or "",
        },
    }


def find_selfloop():
    env = os.environ.get("LLMOS_SELFLOOP_BIN", "").strip()
    candidates = [env, "/root/llmos-dev/Support files/tools/selfloop.py"]
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        candidates.append(os.path.join(d, "tools", "selfloop.py"))
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def launch_argv(script, item_id="", ship_id=""):
    """The on-device command. nice (and ionice when it exists). Never the full suite, never a service restart."""
    if ship_id:
        argv = [sys.executable, script, "--ship-one", str(ship_id)]
    else:
        argv = [sys.executable, script, "--from-voice", str(item_id)]
    if shutil.which("nice"):
        argv = ["nice", "-n", "19"] + argv
    if shutil.which("ionice"):
        argv = ["ionice", "-c", "3"] + argv
    return argv


def start_loop(item_id, popen=None):
    """Start one device-mode pass in the background. False when this machine should not start it."""
    if os.environ.get("LLMOS_BUGFIX_RUN") == "0":
        return False
    if os.environ.get("LLMOS_BUGFIX_RUN") != "1" and not os.path.isdir(os.path.join("/usr/lib/llmos", "llmos")):
        return False
    script = find_selfloop()
    if not script:
        return False
    log_path = os.path.join(selfloop_ctl.state_dir(), "voice-run.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    run = popen or subprocess.Popen
    try:
        run(launch_argv(script, item_id), stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        log.close()
        return False
    return True


def report(description, capture=None, runner=None):
    """Save the bug and start the on-device loop. The reply is what to say; nothing is installed."""
    if selfloop_ctl.killed():
        return ("The improvement loop is stopped, so I didn't start a fix. "
                "Say “resume the improvement loop” first. Nothing was changed.")
    blocked, why = selfloop_ctl.rate_limit()
    if blocked:
        return why
    description = ghreport.redact(str(description or "").strip())[:500] or "a bug on the screen"
    if _already(description):
        return "I'm already looking at that bug. Nothing new was started."
    ctx = capture() if capture else capture_context()
    item = make_item(description, ctx)
    clear_failure()
    rows = selfloop_ctl.load_backlog(_seed())
    rows.append(item)
    selfloop_ctl.save_backlog(rows)
    run = runner if runner is not None else _runner
    started = False
    try:
        if run is not None:
            run(item)
            started = True
        else:
            started = start_loop(item["id"])
    except Exception:
        started = False
    where = (ctx or {}).get("window_name") or ""
    place = f" in {where}" if where else ""
    if started:
        return (f"I'll look at that bug{place}. I'm using the local model on this computer. "
                "Nothing will be installed until you say “apply that fix”.")
    return (f"I saved that bug{place} for the loop. It hasn't started on this machine. "
            "Nothing will be installed until you say “apply that fix”.")


def spoken_for(item, outcome):
    """What to say when a fix is staged and waiting."""
    names = []
    for path in (outcome or {}).get("changed") or []:
        base = os.path.basename(str(path))
        if base and base not in names and base not in ("selfloop_ctl.py", "ota.py"):
            names.append(base)
    what = names[0] if len(names) == 1 else (", ".join(names[:5]) if names else "the staged copy")
    tests = (outcome or {}).get("tests") or []
    title = (item or {}).get("description") or (item or {}).get("title") or "the bug you found"
    return (f"I staged a fix for {title}. It changes {what}. "
            f"The light tests passed ({len(tests)}). "
            "Nothing is installed. Say “apply that fix” to install it, or “undo that fix” to drop it.")


def failed_speech(item, detail):
    title = (item or {}).get("description") or "that bug"
    why = ghreport.redact(detail or "it did not pass")[:240]
    return (f"I couldn't fix {title} ({why}). Nothing was installed. "
            "Say “file that as an issue” if you want it on GitHub.")


def failure_path():
    return os.path.join(selfloop_ctl.state_dir(), "last-failure.json")


def remember_failure(item, detail):
    _write_json(failure_path(), {
        "id": (item or {}).get("id") or "",
        "description": (item or {}).get("description") or (item or {}).get("title") or "",
        "detail": ghreport.redact(detail or "")[:1000],
        "when": int(time.time()),
    })


def clear_failure():
    try:
        os.remove(failure_path())
    except OSError:
        pass


def pending_path():
    return os.path.join(selfloop_ctl.state_dir(), "pending-speech.txt")


def write_pending(speech):
    if not speech:
        return
    path = pending_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(speech)
    os.replace(tmp, path)


def notify_owner(speech):
    try:
        from . import store
        store.notify("A fix is staged", ghreport.redact(speech)[:180], replace=True)
    except Exception:
        pass


def queued_fix():
    rows = [row for row in selfloop_ctl.load_queue()
            if isinstance(row, dict) and row.get("source") == "voice" and row.get("install") == "local"]
    return rows[-1] if rows else None


def _short(text):
    text = " ".join(str(text or "").split())
    return text[:240]


def default_ship(item):
    script = find_selfloop()
    if not script:
        return 2, "The installer isn't on this machine, so nothing was installed."
    argv = launch_argv(script, ship_id=item.get("id"))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)[:200]
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or ""))[-2000:]


def apply(ship=None):
    """Install the staged spoken fix, then report it. The first sentence is what changed."""
    if not self_trusted():
        return ("This laptop isn't trusted to sign updates yet. Say “trust this laptop for updates”. "
                "I'll show you the key code, and nothing will be installed until then.")
    item = queued_fix()
    if not item:
        return "Nothing is waiting. Say “I found a bug, fix it” first."
    speech = item.get("spoken") or spoken_for(item, {"changed": [], "tests": item.get("tests") or []})
    runner = ship or _ship or default_ship
    try:
        code, output = runner(item)
    except Exception:
        remember_failure(item, "the installer did not finish")
        return speech + " I did not install it. Say “file that as an issue” if you want this on GitHub."
    output = ghreport.redact(output or "")
    if code != 0:
        remember_failure(item, _short(output) or "the install did not succeed")
        return (speech + " I did not install it. " + (_short(output) + " " if output.strip() else "")
                + "Say “file that as an issue” if you want this on GitHub.")
    extra = ""
    low = output.lower()
    if os.environ.get("LLMOS_BUGFIX_REPORT") != "0" and "pull request" not in low and "github" not in low:
        try:
            extra = " " + finish_installed(item)
        except Exception:
            extra = " I saved the GitHub report to try later. It is not merged."
    tail = (" " + output.strip()) if output.strip() else ""
    return speech + " Installed, and the health check passed." + tail + extra


def _under(path, root):
    path = os.path.realpath(path)
    root = os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _safe_drop(path):
    if not path or not os.path.isdir(path):
        return
    root = os.path.realpath(selfloop_ctl.state_dir())
    dest = os.path.realpath(path)
    if dest == root or not dest.startswith(root + os.sep):
        return
    shutil.rmtree(dest, ignore_errors=True)


def undo():
    """Drop a staged spoken fix, or put back the files from the last one that was installed."""
    item = queued_fix()
    if item:
        kept = [row for row in selfloop_ctl.load_queue() if str(row.get("id")) != str(item.get("id"))]
        selfloop_ctl.save_queue(kept)
        _safe_drop(item.get("staging") or "")
        if item.get("support") and item.get("support") != item.get("staging"):
            _safe_drop(item.get("support"))
        ghreport.drop_pending(item.get("id"), "pr")
        return (f"I dropped that fix ({item.get('description') or item.get('title') or 'the staged change'}). "
                "Nothing was installed.")
    try:
        rec = rollback_installed()
    except Exception:
        return "I couldn't put the previous files back. Nothing else was changed."
    if not rec:
        return "There's no fix to undo."
    n = len(rec.get("names") or [])
    return (f"I put the previous files back ({n} files). "
            "If a pull request was opened, it is still open and I will not merge it.")


def receipt_file():
    return os.path.join(selfloop_ctl.state_dir(), "ota", "last-install.json")


def _read_json(path):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    os.replace(tmp, path)


def _read_receipt():
    for path in (receipt_file(), os.path.join(selfloop_ctl.state_dir(), "last-install.json")):
        data = _read_json(path)
        if data and data.get("backup") and not data.get("undone"):
            return data
    return None


def rollback_installed():
    """Restore the backup from the last kept install. Does not restart services."""
    rec = _read_receipt()
    if not rec:
        return None
    backup = rec.get("backup") or ""
    if not backup or not os.path.isfile(backup) or not _under(backup, selfloop_ctl.state_dir()):
        raise RuntimeError("refusing to restore from outside the loop's files")
    from . import ota
    old = ota.ROOT
    ota.ROOT = rec.get("root") or "/"
    try:
        ota.rollback({"backup": backup, "new": rec.get("new") or []})
    finally:
        ota.ROOT = old
    updated = dict(rec, undone=True)
    _write_json(receipt_file(), updated)
    ghreport.drop_pending(rec.get("item") or "", "pr")
    return updated


def _unified(name, old, new, limit=8000):
    try:
        old_s = old.decode("utf-8")
        new_s = new.decode("utf-8")
    except UnicodeDecodeError:
        return f"--- {name}\n(binary, {len(old)} bytes to {len(new)} bytes)\n"
    lines = list(difflib.unified_diff(old_s.splitlines(), new_s.splitlines(),
                                      fromfile="a/" + name, tofile="b/" + name, lineterm=""))
    text = "\n".join(lines)
    if len(text) > limit:
        text = text[:limit] + "\n…\n"
    return text


def diff_text(receipt, limit=20000):
    backup = (receipt or {}).get("backup") or ""
    root = (receipt or {}).get("root") or "/"
    names = (receipt or {}).get("names") or []
    if not backup or not os.path.isfile(backup):
        return "(no diff was recorded)"
    olds = {}
    try:
        with tarfile.open(backup) as bundle:
            for member in bundle.getmembers():
                if not member.isfile():
                    continue
                handle = bundle.extractfile(member)
                olds[member.name] = handle.read() if handle else b""
    except (OSError, tarfile.TarError):
        return "(no diff was recorded)"
    parts = []
    for name in names:
        if os.path.basename(str(name)) in ("selfloop_ctl.py", "ota.py"):
            continue
        try:
            new = open(os.path.join(root, name), "rb").read()
        except OSError:
            new = b""
        parts.append(_unified(str(name), olds.get(name, b""), new))
        if sum(len(part) for part in parts) >= limit:
            break
    text = "\n".join(part for part in parts if part)
    if len(text) > limit:
        text = text[:limit] + "\n…\n"
    return text or "(no diff was recorded)"


def files_from_receipt(receipt):
    root = (receipt or {}).get("root") or "/"
    out = []
    for name in (receipt or {}).get("names") or []:
        path = ghreport.repo_path(name)
        if not path:
            continue
        try:
            data = open(os.path.join(root, name), "rb").read()
        except OSError:
            continue
        if b"\0" in data[:1024]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        out.append({"path": path, "content": text})
    return out


def _test_line(item):
    tests = (item or {}).get("tests") or []
    summary = (item or {}).get("summary") or "light gate passed"
    names = ", ".join(str(t) for t in tests) if tests else "(none recorded)"
    return f"{names}; {summary}; passed again before install"


def finish_installed(item, transport=None):
    """After a kept install, open the pull request or queue it. The health check has already passed."""
    clear_failure()
    receipt = _read_receipt()
    if not receipt:
        return "The fix is installed. I don't have a record of the files, so I didn't open a pull request."
    receipt = dict(receipt)
    receipt["item"] = (item or {}).get("id") or ""
    receipt["description"] = (item or {}).get("description") or (item or {}).get("title") or ""
    receipt["tests"] = list((item or {}).get("tests") or [])
    receipt["gate"] = _test_line(item)
    _write_json(receipt_file(), receipt)
    _write_json(os.path.join(selfloop_ctl.state_dir(), "last-install.json"), receipt)
    return ghreport.submit_pr({
        "item": receipt["item"],
        "description": receipt["description"],
        "diff": diff_text(receipt),
        "tests": receipt["gate"],
        "health": receipt.get("health") or "ok",
        "files": files_from_receipt(receipt),
    }, transport=transport)


def file_issue(transport=None):
    data = _read_json(failure_path())
    if not data:
        return "I don't have a failed fix to file. Say “I found a bug, fix it” if something is still wrong."
    return ghreport.submit_issue({
        "item": data.get("id") or "issue",
        "description": data.get("description") or "a bug on the laptop",
        "detail": data.get("detail") or "",
    }, transport=transport)


def status_speech():
    item = queued_fix()
    if item and item.get("spoken"):
        return item["spoken"]
    try:
        pending = open(pending_path(), encoding="utf-8").read().strip()
    except OSError:
        pending = ""
    if pending:
        return pending
    failed = _read_json(failure_path())
    if failed:
        return failed_speech(failed, failed.get("detail") or "")
    return "I haven't staged a fix yet. Say “I found a bug, fix it”."
