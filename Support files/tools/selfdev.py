#!/usr/bin/env python3
"""LLM OS working on its own code, with a seatbelt.

A model proposes a change to LLM OS's own source. The change is written into the real files ONLY while a host
test gate runs against it, then the files are put back exactly as they were (the edit is transient; the live source
is never left changed). If that gate passes, the change is staged for a human yes. It never ships on its own. A
passing gate proves the code isn't broken; it does NOT prove an uncensored model didn't quietly weaken a safeguard
-- so a person sees the diff before anything is written for real. That gate is the whole point; don't remove it.

The model is whatever is configured (an online model when one is set, otherwise the on-device model). This loop
does not escalate to another model when the reply is a refusal. A round is simply tried again, up to 3 times, when
the reply is not a usable edit or the gate fails.

Two gates, chosen with --gate:

  full    the whole host suite. This is the default on a dev machine. Refused on a live install: that suite
          applies the real firewall and stops real services.
  light   only the tests that import or read the modules the patch edits, plus a small core (CORE_TESTS).
          This is what runs on the laptop. It is not a substitute for the full suite before an update is shipped.
  auto    full on a dev machine with free memory; light on a live install, or when MemAvailable is under 2 GiB.
          Printed on every run, and overridable with --gate full or --gate light.

    tools/selfdev.py "add a 'dark mode at sunset' setting"     # propose, test, stage -- stops before shipping
    tools/selfdev.py --gate light "the change"                 # laptop-sized gate
    tools/selfdev.py --show                                    # show the staged change and its test result
    tools/selfdev.py --apply                                   # a HUMAN applies the staged, tested change
    tools/selfdev.py --discard
    tools/selfdev.py --backend local "the change"              # on-device model only; still stops before install
    tools/selfdev.py --local-install "the change"              # owner-invoked: test, install, verify, or roll back
    tools/selfdev.py --rollback                                # put the previous runtime bytes back

--backend local never reads the online-model config and never calls it. --local-install is that backend plus
the bounded light gate, then an install of the tested bytes into the runtime tree (not only the dev checkout).
Exit 0 only when a read-back of those runtime bytes hashes to the tested artifact. A staged diff alone is not
success. Zero tests, a timeout, a failed test, a stale stage, a malformed edit, an interruption, or a failed
read-back exits non-zero and leaves the previous runtime bytes in place. The command does not ask for a second
confirmation. A run without --local-install still stops at the staged diff; shipping that one is still a
separate, deliberate `tools/ota.py publish` a human runs after --apply.

A checkout that is still the 2026-10-23 tree needs these three files copied together. The light gate's
per-test cap is in the runner; copying only selfdev.py leaves that cap unset and makes test-selfdev.py's
timeout probe fail:
    tools/selfdev.py
    tools/test-selfdev.py
    tools/run-host-tests.sh
llmos/llm.py and llmos/config.py also differ from that date. They are not part of this copy: the local
backend calls llm.chat, which is unchanged, and those diffs change the online catalog and settings defaults.
Run the loop on a dev machine when you can, and ship the result to the laptop afterwards. --gate light exists so
a run on the laptop does not have to execute all 200+ suites."""
import argparse
import ast
import atexit
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src/rootfs/usr/lib/llmos")       # parent of the llmos package (for `import llmos`)
PKG = os.path.join(SRC, "llmos")                          # the package itself: web.py, agent.py, … live here
STAGE = os.path.join(ROOT, "run", "selfdev")
# Tests point this at a scratch directory. Unset, the stage stays next to the checkout.
_stage_env = os.environ.get("LLMOS_SELFDEV_STAGE", "").strip()
if _stage_env:
    STAGE = os.path.realpath(_stage_env)
JOURNAL = os.path.join(STAGE, "journal")
TESTS = os.path.join(HERE, "run-host-tests.sh")
MAX_ROUNDS = 3

# full suite: historical ceiling. light: a desk-sized selection is tens of tests, each capped below.
FULL_TIMEOUT = 1800
LIGHT_TIMEOUT = 600
LIGHT_TEST_TIMEOUT = 120
# 1 GiB address space per test process. The core tests plus a couple of heavier ones pass under 512 MiB here;
# 1 GiB is headroom, still far under the 16 GB laptop. LLMOS_SELFDEV_AS_BYTES=0 turns the cap off.
DEFAULT_AS_BYTES = 1 << 30
# auto picks light below this much MemAvailable, so a cramped machine is not handed the full suite.
LOW_MEM_KIB = 2 * 1024 * 1024

# Always run with the affected-module tests. Each one guards a promise the model is told not to weaken, each one
# passes on a clean tree, and together they take about a second. The affected-module set already covers the file
# that changed; this is the cross-check:
#   test-selfdev.py      this loop still restores edits, stages only when the suite really ran, and does not ship
#   test-risk.py         destructive commands and writes to the OS's own policy files stay classified
#   test-firewall.py     firewall rule text still matches the privacy promise (it inspects text; it does not install it)
#   test-escalate.py     a timid refusal still escalates; a genuinely harmful request still does not
#   test-guard-risk.py   turning off the web/email/file check is still a security change that asks first
#   test-ask-gate.py     an action the owner did not ask for still asks (and is still refused when unattended)
#   test-config-etc.py   settings are still written to the OS config directory, or through the root helper
# test-intent.py is not in here: a change to intent.py already selects it (about 39 tests), so the core stays
# the safeguard cross-check rather than the whole router table.
# Files that differ from the 2026-10-23 checkout (6a172ce) and have to be copied together.
# llm.py and config.py also differ; they are intentionally not here.
DEPLOY_FILES = (
    "tools/selfdev.py",
    "tools/test-selfdev.py",
    "tools/run-host-tests.sh",
)

CORE_TESTS = (
    "tools/test-selfdev.py",
    "tools/test-risk.py",
    "tools/test-firewall.py",
    "tools/test-escalate.py",
    "tools/test-guard-risk.py",
    "tools/test-ask-gate.py",
    "tools/test-config-etc.py",
)

# Named by the handoff: on a live install these are the suites that once rewrote the real firewall / touched services.
# The copies in the tree are written not to. The light gate still runs them when the patch touches their modules,
# and says so; the full suite stays refused.
LIVE_RISKY_TESTS = (
    "tools/test-firewall.py",
    "tools/test-rootd-firewall.py",
    "tools/test-rootd-power.py",
)

# the model lives in the installed system; add it to the path so this can run on the laptop too
sys.path.insert(0, "/usr/lib/llmos")
sys.path.insert(0, SRC)

_ACTIVE = {"proc": None, "backups": None}
_CALLS = {"cloud": 0, "local": 0}
_HOOKS = False
_BASELINES = {}
_INDEX = None
_IONICE = None


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def journal_save(backups):
    """Write originals and fsync them BEFORE the live files are touched. A kill -9 mid-suite is recovered
    from this journal the next time selfdev starts."""
    os.makedirs(JOURNAL, exist_ok=True)
    manifest = {}
    man = os.path.join(JOURNAL, "manifest.json")
    if os.path.isfile(man):
        try:
            manifest.update(json.load(open(man, encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    for rel, text in backups.items():
        fn = hashlib.sha256(rel.encode("utf-8")).hexdigest() + ".orig"
        dest = os.path.join(JOURNAL, fn)
        tmp = dest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
        manifest[rel] = fn
    tmp = man + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, man)
    _fsync_dir(JOURNAL)


def journal_recover():
    """Put journaled originals back. Returns the relative paths restored. No-op when there is no journal."""
    man = os.path.join(JOURNAL, "manifest.json")
    if not os.path.isfile(man):
        return []
    try:
        manifest = json.load(open(man, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("[selfdev] WARNING: the edit journal is unreadable; source files were left as they are", flush=True)
        return []
    restored = []
    for rel, fn in manifest.items():
        full, cleaned, err = _package_file(rel)
        if err or not full:
            print(f"[selfdev] WARNING: journal entry {rel} is not in the OS package; skipped", flush=True)
            continue
        src_path = os.path.join(JOURNAL, os.path.basename(fn))
        try:
            original = open(src_path, encoding="utf-8").read()
            open(full, "w", encoding="utf-8").write(original)
        except OSError as e:
            print(f"[selfdev] WARNING: could not restore {cleaned} from the journal: {e}", flush=True)
            continue
        restored.append(cleaned)
    # Drop the journal only when every entry is back. A partial restore leaves it for the next start.
    if restored and len(restored) == len(manifest):
        journal_clear()
        _ACTIVE["backups"] = None
    return restored


def journal_clear():
    if os.path.isdir(JOURNAL):
        shutil.rmtree(JOURNAL, ignore_errors=True)


def _kill_group(proc):
    if proc is None:
        return
    pid = proc.pid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            proc.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            continue


def _on_signal(signum, frame):
    """Ctrl-C / SIGTERM: stop the suite, put the source back, then exit. SIGKILL cannot be caught; the journal
    covers that on the next start."""
    proc = _ACTIVE.get("proc")
    if proc is not None and proc.poll() is None:
        _kill_group(proc)
    backups = _ACTIVE.get("backups")
    if backups:
        restore(backups)
    else:
        journal_recover()
    install_journal_recover()
    raise SystemExit(128 + (signum or 0))


def _on_exit():
    proc = _ACTIVE.get("proc")
    if proc is not None and proc.poll() is None:
        _kill_group(proc)
    journal_recover()
    install_journal_recover()


def _install_signals():
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)


def _ensure_hooks():
    global _HOOKS
    if _HOOKS:
        return
    _HOOKS = True
    _install_signals()
    atexit.register(_on_exit)


def _is_gate_name(base):
    return base == "run-host-tests.sh" or (base.startswith("test-") and base.endswith(".py"))


def _package_file(rel):
    """Resolve rel inside the OS package. Does not require the file to exist.
    Returns (full, cleaned_rel, error). error is set when the path escapes the package or names the test gate."""
    raw = (rel or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or raw.startswith("~"):
        return None, None, f"{rel}: edits are limited to the OS package"
    parts = [p for p in raw.split("/")]
    if any(p in ("", ".", "..") for p in parts):
        return None, None, f"{raw}: path escapes the OS package"
    if _is_gate_name(parts[-1]):
        return None, None, f"{raw}: a patch cannot edit the test gate"
    full = os.path.realpath(os.path.join(ROOT, *parts))
    pkg = os.path.realpath(PKG)
    root = os.path.realpath(ROOT)
    if full != pkg and not full.startswith(pkg + os.sep):
        return None, None, f"{raw}: edits are limited to the OS package"
    if not full.startswith(root + os.sep):
        return None, None, f"{raw}: edits are limited to the OS package"
    if _is_gate_name(os.path.basename(full)):
        return None, None, f"{raw}: a patch cannot edit the test gate"
    if not full.endswith(".py"):
        return None, None, f"{raw}: edits are limited to Python files in the OS package"
    cleaned = full[len(root) + 1:].replace(os.sep, "/")
    return full, cleaned, None


def edit_target(rel):
    """The live file an edit may touch, or an error. Test files and run-host-tests.sh are never editable."""
    full, cleaned, err = _package_file(rel)
    if err:
        return None, None, err
    if not os.path.isfile(full):
        return None, None, f"{cleaned}: no such file"
    return full, cleaned, None


def _pkg_modules():
    try:
        names = os.listdir(PKG)
    except OSError:
        return set()
    return {n[:-3] for n in names if n.endswith(".py")}


def _test_index():
    """module name -> host tests that import it or name its file. Built from the test sources, not by importing
    them (importing would run the tests). Direct references only: a transitive walk through config.py selects
    almost the whole suite and the light gate stops being light."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    modules = _pkg_modules()
    index = {m: set() for m in modules}
    for name in sorted(os.listdir(HERE)):
        if not (name.startswith("test-") and name.endswith(".py")):
            continue
        rel = "tools/" + name
        try:
            tree = ast.parse(open(os.path.join(HERE, name), encoding="utf-8", errors="replace").read())
        except (OSError, SyntaxError):
            continue
        touched = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "llmos":
                    for alias in node.names:
                        touched.add(alias.name if alias.name in modules else "__init__")
                elif node.module.startswith("llmos."):
                    top = node.module.split(".")[1]
                    if top in modules:
                        touched.add(top)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "llmos":
                        touched.add("__init__")
                    elif alias.name.startswith("llmos."):
                        top = alias.name.split(".")[1]
                        if top in modules:
                            touched.add(top)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for mod in modules:
                    # "web.py", "…/web.py", and "the code in web.py". Not "spiderweb.py".
                    if re.search(r"(?<![\w])" + re.escape(mod) + r"\.py", node.value):
                        touched.add(mod)
        for mod in touched:
            index.setdefault(mod, set()).add(rel)
    _INDEX = index
    return index


def select_light_tests(edits):
    """Tests for a light run: every test that touches a changed module, plus CORE_TESTS.

    Returns (paths, message). paths is None when the mapping cannot tell which tests are affected -- the caller
    must not stage. That happens when a changed module has no test that imports it or reads its file. Falling
    through to the full suite is deliberately not done: the full suite is what exhausts the laptop, and it is
    refused on a live install, so a silent fallback would reintroduce the failure this gate exists to avoid.
    Re-run with --gate full on a dev machine instead."""
    index = _test_index()
    modules = []
    for e in edits:
        full, cleaned, err = edit_target(e.get("path", ""))
        if err:
            return None, err
        mod = os.path.basename(full)[:-3]
        if mod not in index or not index[mod]:
            return None, (f"no host test imports or reads llmos/{mod}.py, so the light gate cannot tell what "
                          f"this change would break. Nothing was staged. On a dev machine, re-run with --gate full.")
        modules.append(mod)
    affected = set()
    for mod in modules:
        affected.update(index[mod])
    chosen = sorted(affected | set(CORE_TESTS))
    missing = [t for t in chosen if not os.path.isfile(os.path.join(ROOT, t))]
    if missing:
        return None, ("the light gate is missing test files (" + ", ".join(missing) + "). Nothing was staged.")
    extra = sorted(affected - set(CORE_TESTS))
    names = ", ".join("llmos/" + m + ".py" for m in sorted(set(modules)))
    msg = (f"{len(chosen)} tests for {names} "
           f"({len(extra)} that touch those modules, plus {len(CORE_TESTS)} core)")
    return chosen, msg


def _mem_available_kib():
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _low_memory():
    kib = _mem_available_kib()
    if kib is None or kib >= LOW_MEM_KIB:
        return False, ""
    return True, f"MemAvailable is {kib // 1024} MiB, under {LOW_MEM_KIB // 1024} MiB"


def resolve_gate(requested):
    """Return (gate, why). auto is explicit about which one it picked."""
    requested = (requested or "auto").lower()
    if requested == "full":
        return "full", "chosen with --gate full"
    if requested == "light":
        return "light", "chosen with --gate light"
    if _is_live_install():
        return "light", "auto: this is a live LLM OS install, so the full suite is not run here"
    low, why = _low_memory()
    if low:
        return "light", "auto: " + why
    return "full", "auto: dev machine with enough free memory for the full suite"


def _is_live_install():
    """True on an actual running LLM OS machine (not a dev checkout). The full host suite reconfigures the REAL
    firewall and stops REAL services, so running it here would knock the machine's own networking out."""
    return os.path.exists("/etc/init.d/llmos-desk") or os.path.exists("/etc/llmos/installed")


def _llm():
    from llmos import llm  # noqa: E402
    return llm


def _chat_local(messages, **kw):
    """On-device endpoint only. Does not read cloud config and does not call the online model.
    If the on-device model fails, the error propagates. There is no cloud fallback."""
    _CALLS["local"] = _CALLS.get("local", 0) + 1
    return _llm().chat(messages, **kw)


def _chat(messages, backend="auto", **kw):
    """The configured online model when one is set, otherwise the on-device model.
    backend='local' is _chat_local: cloud config is not consulted.
    This loop does not escalate to another model when the reply is a refusal."""
    if (backend or "auto").lower() == "local":
        return _chat_local(messages, **kw)
    llm = _llm()
    try:
        from llmos import config
        if config.cloud():
            _CALLS["cloud"] = _CALLS.get("cloud", 0) + 1
            return llm.cloud_chat(messages, **kw)
    except Exception:
        pass
    _CALLS["local"] = _CALLS.get("local", 0) + 1
    return llm.chat(messages, **kw)


EDIT_FORMAT = """Reply with ONLY the block below, one per change. No greeting and no explanation.
A line that is only ``` is ignored. Copy SEARCH from the file exactly, spaces included, long enough to be unique.
The path is relative to the repo root, or just the file name if it is one of the files shown (web.py).
Only Python files in src/rootfs/usr/lib/llmos/llmos/ may be edited. Do not edit tests.

=== FILE: src/rootfs/usr/lib/llmos/llmos/web.py
<<<<<<< SEARCH
_TIMEOUT = 10
=======
_TIMEOUT = 20
>>>>>>> REPLACE"""

# Angle-bracket block. The path may be "=== FILE: p", "FILE: p", or a bare p.py line.
# Markers accept the words small models substitute (ORIGINAL/OLD, UPDATED/NEW).
_ANGLE = re.compile(
    r"(?P<path>[^\s`'\"]+\.py)[ \t]*\n+[ \t]*"
    r"<<<<<<<[ \t]*(?:SEARCH|ORIGINAL|OLD)?[ \t]*\n"
    r"(?P<search>.*?)\n"
    r"=======[ \t]*\n"
    r"(?P<replace>.*?)\n"
    r">>>>>>>[ \t]*(?:REPLACE|UPDATED|NEW|END)?",
    re.S | re.I)
_WORDS = re.compile(
    r"(?P<path>[^\s`'\"]+\.py)[ \t]*\n+[ \t]*"
    r"SEARCH:[ \t]*\n"
    r"(?P<search>.*?)\n"
    r"REPLACE:[ \t]*\n"
    r"(?P<replace>.*?)(?=\n[ \t]*(?:===\s*)?(?:FILE:|SEARCH:)|\Z)",
    re.S | re.I)
_FENCE_LINE = re.compile(r"^[ \t]*(?:`{3,}|~{3,}).*$")
_FILE_HEAD = re.compile(r"(?:^|\n)(?:===\s*)?FILE:[ \t]*(?P<path>\S+)", re.I)


def gather_context(task, limit=3000):
    """The files most likely relevant to the task: ranked by how many of the task's words they contain."""
    import math
    _STOP = {"the", "that", "this", "with", "from", "into", "when", "what", "which", "your", "make", "code", "file",
             "setting", "please", "want", "need", "should", "would", "llmos", "model"}
    words = {w for w in re.findall(r"[a-z_]{4,}", task.lower()) if w not in _STOP}
    scored = []
    for name in sorted(os.listdir(PKG)):
        if not name.endswith(".py"):
            continue
        try:
            text = open(os.path.join(PKG, name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        low = text.lower()
        # density, not raw count: how much this file is ABOUT the task words (so a big file isn't picked just for size),
        # plus a strong bonus for a word in the file's own name
        score = sum(low.count(w) for w in words) / math.sqrt(max(len(text), 1))
        score += 3 * sum(1 for w in words if w in name.lower())
        scored.append((score, name, text))
    scored.sort(key=lambda t: t[0], reverse=True)
    # a file the task NAMES ("in web.py", a path) is the strongest signal -- always include it first
    named = [n for n in re.findall(r"([a-z0-9_]+\.py)", task.lower())]
    order = [t for t in scored if t[1] in named] + [t for t in scored if t[1] not in named]
    out, used = [], 0
    for score, name, text in order[:2]:
        if score == 0 and name not in named:
            break
        rel = f"src/rootfs/usr/lib/llmos/llmos/{name}"
        snip = _snippets(text, words, limit)
        out.append(f"--- {rel} ---\n{snip}")
        used += len(snip)
        if used >= limit * 2:         # ~2 files max; a big prompt makes the free endpoint truncate its reply
            break
    return "\n\n".join(out) or "(no obviously related file found; ask for the path)"


def _snippets(text, words, limit, pad=5):
    """The parts of a file ACTUALLY about the task words -- the lines that mention them, with a few lines around each,
    merged -- so the model is shown (and must copy) the real code, not just the file's start. Falls back to the head."""
    lines = text.splitlines()
    low = [l.lower() for l in lines]
    hits = [i for i, l in enumerate(low) if any(w in l for w in words)]
    if not hits:
        return text[:limit]
    ranges, start, prev = [], hits[0], hits[0]
    for i in hits[1:]:
        if i - prev <= pad * 2:
            prev = i
        else:
            ranges.append((start, prev))
            start = prev = i
    ranges.append((start, prev))
    parts, used = [], 0
    for a, b in ranges:
        a, b = max(0, a - pad), min(len(lines), b + pad + 1)
        chunk = "\n".join(lines[a:b])        # raw lines, no line-number prefix, so SEARCH text copied from here matches the file
        if used + len(chunk) > limit * 2:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n   …\n".join(parts)


def propose(task, note="", backend="auto"):
    """Ask the model for a set of edits. Returns the raw text."""
    ctx = gather_context(task + " " + note)
    sysmsg = ("You edit the source code of LLM OS, an operating system, to carry out a change its owner asked for. "
              "You are given the task and excerpts of the most relevant files. Make the smallest change that does it. "
              "Never weaken a safety check, a permission prompt, the firewall or the update signature. " + EDIT_FORMAT)
    user = f"TASK: {task}\n"
    if note:
        user += f"\nThe last attempt did not work: {note}\n"
    user += f"\nRELEVANT FILES:\n{ctx}"
    r = _chat([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
              max_tokens=1200, temperature=0.1, backend=backend)
    return (r.get("content") or "").strip()


def _strip_fences(text):
    """Drop markdown fence lines. Deleting the backticks in place used to glue a language tag onto the next line."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line for line in text.split("\n") if not _FENCE_LINE.match(line))


def _clean_path(path):
    """Turn a bare name a small model prints ('web.py') into the package path when that file exists."""
    path = (path or "").strip().strip("`\"'")
    if path.startswith("./"):
        path = path[2:]
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
    path = path.replace("\\", "/")
    if "/" not in path and path.endswith(".py"):
        full = "src/rootfs/usr/lib/llmos/llmos/" + path
        if os.path.isfile(os.path.join(ROOT, full)):
            return full
    return path


def _keep_edits(edits):
    out = []
    for e in edits:
        path = _clean_path(e.get("path", ""))
        if not path:
            continue
        if e.get("whole"):
            body = e.get("replace") or ""
            if not body.strip() or body.count("\n") < 2:
                continue
            if not body.endswith("\n"):
                body += "\n"
            out.append({"path": path, "search": "", "replace": body, "whole": True})
            continue
        search, replace = e.get("search"), e.get("replace")
        if search is None:
            continue
        if search.endswith("\n"):
            search = search[:-1]
        replace = replace if replace is not None else ""
        if replace.endswith("\n"):
            replace = replace[:-1]
        if search == "" or search == replace:
            continue
        out.append({"path": path, "search": search, "replace": replace})
    return out


def _edits_from_regex(text, pattern):
    edits = []
    for m in pattern.finditer(text):
        edits.append({"path": m.group("path"), "search": m.group("search"), "replace": m.group("replace")})
    return _keep_edits(edits)


def _edits_from_diff(text):
    """One unified diff. Context lines (a leading space) are part of both SEARCH and REPLACE."""
    lines = text.split("\n")
    edits, path, search, replace, in_hunk = [], None, [], [], False

    def flush():
        nonlocal search, replace
        if path and search and "".join(search) != "".join(replace):
            edits.append({"path": path, "search": "\n".join(search), "replace": "\n".join(replace)})
        search, replace = [], []

    for line in lines:
        if line.startswith("--- ") or line.startswith("diff "):
            flush()
            in_hunk = False
            continue
        if line.startswith("+++ "):
            flush()
            raw = line[4:].strip()
            if raw.startswith("b/"):
                raw = raw[2:]
            if raw.endswith(".py"):
                path = raw.split("\t", 1)[0]
            in_hunk = True
            continue
        if line.startswith("@@"):
            flush()
            in_hunk = True
            continue
        if not in_hunk or path is None:
            continue
        if line.startswith("+"):
            replace.append(line[1:])
        elif line.startswith("-"):
            search.append(line[1:])
        elif line.startswith("\\"):
            continue
        else:
            ctx = line[1:] if line.startswith(" ") else line
            search.append(ctx)
            replace.append(ctx)
    flush()
    return _keep_edits(edits)


def _edits_from_whole_file(text):
    """A FILE line followed by the new file, which is what a small model emits when it ignores SEARCH/REPLACE."""
    marks = list(_FILE_HEAD.finditer(text))
    edits = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end].strip("\n")
        if "<<<<<<<" in body or re.search(r"(?m)^[ \t]*SEARCH:[ \t]*$", body):
            continue
        edits.append({"path": m.group("path").strip().strip("`\"'"), "replace": body, "whole": True})
    return _keep_edits(edits)


def _format_error(text):
    """The exact reason a reply produced no edit, short enough to send back on the next round."""
    if "<<<<<<<" in text and "=======" not in text:
        return ("found <<<<<<< but no ======= line. Put ======= between the old lines and the new lines, "
                "then >>>>>>> REPLACE.")
    if "<<<<<<<" in text and ">>>>>>>" not in text:
        return "found <<<<<<< and ======= but no >>>>>>> REPLACE line to close the block."
    if re.search(r"(?i)search", text) and not re.search(r"(?i)replace", text) and "<<<<<<<" not in text:
        return "found SEARCH but no REPLACE. Put the new lines after a REPLACE: line."
    if "--- " in text and "+++ " in text:
        return "a diff was found but it had no file path or no removed lines to search for."
    if ".py" in text and len(text) > 80:
        return ("no SEARCH/REPLACE block. Put === FILE: <path.py> on its own line, then the block "
                "(<<<<<<< SEARCH, =======, >>>>>>> REPLACE) or the whole new file under that line.")
    return ("no edit block. Reply with only this shape:\n"
            "=== FILE: src/rootfs/usr/lib/llmos/llmos/<name>.py\n"
            "<<<<<<< SEARCH\n<exact lines from the file>\n=======\n<changed lines>\n>>>>>>> REPLACE")


def explain_edits(text):
    """(edits, error). error is empty when at least one edit was recovered.
    Fenced blocks, missing === FILE, ORIGINAL/UPDATED words, SEARCH:/REPLACE: lines, a unified diff,
    and a whole-file reply under a FILE line are all accepted. The error is the note for the next round."""
    raw = text or ""
    cleaned = _strip_fences(raw)
    for edits in (_edits_from_regex(cleaned, _ANGLE), _edits_from_regex(cleaned, _WORDS),
                  _edits_from_diff(cleaned), _edits_from_whole_file(cleaned)):
        if edits:
            return edits, ""
    return [], _format_error(cleaned)


def parse_edits(text):
    edits, _err = explain_edits(text)
    return edits


def apply_live(edits):
    """Apply SEARCH/REPLACE edits to the REAL files, after journaling each original. Returns
    (applied, problems, backups, newtext). backups/newtext map each touched file's relative path to its original /
    edited contents. The caller MUST restore(backups) afterwards; the edit is live only while the suite runs.
    Paths outside the OS package, and any edit of a test file or of run-host-tests.sh, are rejected whole-file
    so a patch cannot weaken its own gate or write outside the tree."""
    applied, problems, backups, newtext = 0, [], {}, {}
    # A path that escapes the package, or that names the test gate, rejects the whole patch.
    # Applying the other hunks would quietly drop an attempt to weaken the gate.
    blocked = []
    for e in edits:
        _full, _cleaned, err = edit_target(e.get("path", ""))
        if err and "no such file" not in err:
            blocked.append(err)
    if blocked:
        return 0, blocked, {}, {}
    pending, originals = {}, {}
    for e in edits:
        full, cleaned, err = edit_target(e.get("path", ""))
        if err:
            problems.append(err)
            continue
        if cleaned not in pending:
            text0 = open(full, encoding="utf-8").read()
            pending[cleaned] = text0
            originals[cleaned] = text0
        text = pending[cleaned]
        if e.get("whole"):
            body = e.get("replace") or ""
            if not body.endswith("\n"):
                body += "\n"
            if body == text:
                problems.append(f"{cleaned}: the whole-file reply matches the file already")
                continue
            pending[cleaned] = body
            continue
        if e.get("search", "") not in text:
            problems.append(f"{cleaned}: the SEARCH text was not found exactly")
            continue
        if text.count(e["search"]) > 1:
            problems.append(f"{cleaned}: the SEARCH text is not unique; make it longer")
            continue
        pending[cleaned] = text.replace(e["search"], e["replace"], 1)
    changed = {rel: pending[rel] for rel in pending if pending[rel] != originals[rel]}
    if not changed:
        return 0, problems, {}, {}
    backups = {rel: originals[rel] for rel in changed}
    newtext = dict(changed)
    _ACTIVE["backups"] = backups
    journal_save(backups)                 # fsynced before any live write; a crash is undone on the next start
    for rel, text in newtext.items():
        full, _, err = edit_target(rel)
        if err or not full:
            problems.append(err or f"{rel}: no such file")
            continue
        open(full, "w", encoding="utf-8").write(text)
        applied += 1
    return applied, problems, backups, newtext


def restore(backups):
    """Put the original contents back. Called in a finally so the real source is never left edited.
    The journal is removed only after every file is back, so a crash while restoring is retried next start."""
    ok = True
    for rel, original in backups.items():
        full, cleaned, err = _package_file(rel)
        if err or not full:
            print(f"[selfdev] WARNING: could not restore {rel}: {err}", flush=True)
            ok = False
            continue
        try:
            open(full, "w", encoding="utf-8").write(original)
        except OSError as e:
            print(f"[selfdev] WARNING: could not restore {cleaned}: {e}", flush=True)
            ok = False
    if ok:
        journal_clear()
        _ACTIVE["backups"] = None
    return ok


def _as_cap():
    raw = os.environ.get("LLMOS_SELFDEV_AS_BYTES", "").strip()
    if raw == "0":
        return 0
    if raw.isdigit():
        return int(raw)
    return DEFAULT_AS_BYTES


def _suite_timeout(limited):
    raw = os.environ.get("LLMOS_SELFDEV_TIMEOUT", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return LIGHT_TIMEOUT if limited else FULL_TIMEOUT


def _ionice_ok():
    """Idle ionice needs a working ionice binary. Skip it when the probe fails (some containers)."""
    global _IONICE
    if _IONICE is None:
        if not shutil.which("ionice"):
            _IONICE = False
        else:
            probe = subprocess.run(["ionice", "-c", "3", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _IONICE = probe.returncode == 0
    return _IONICE


def _with_limits(cmd):
    """nice, idle ionice, and an address-space cap, on the suite only. The cap is bash `ulimit -v` (KiB), which
    busybox and Alpine bash both provide; it is inherited across exec, so every test process is capped."""
    cap = _as_cap()
    wrapped = list(cmd)
    if cap > 0:
        kb = max(1024, cap // 1024)
        wrapped = ["bash", "-c", 'ulimit -v "$1" || exit 97; shift; exec "$@"', "ulimit", str(kb)] + wrapped
    if shutil.which("nice"):
        wrapped = ["nice", "-n", "19"] + wrapped
    if _ionice_ok():
        wrapped = ["ionice", "-c", "3"] + wrapped
    return wrapped


def _run_cmd(cmd, timeout, env, stdout):
    """Run cmd in its own session. On timeout, kill the whole group and return timed_out=True.
    TimeoutExpired must not escape: an uncaught one used to skip the normal return path."""
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    _ACTIVE["proc"] = proc
    try:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            return None, True
        return proc.returncode, False
    finally:
        if _ACTIVE.get("proc") is proc:
            _ACTIVE["proc"] = None


def _fail_set(lines):
    """Test files that FAILED. The path is the rest of the line: this tree is 'Support files', and split()
    would collapse every failure onto the same first token, so a baseline with one failure would hide the next."""
    return {l[len("FAIL "):].strip() for l in lines if l.startswith("FAIL ") and l.strip() != "FAIL"}


def run_tests(only=None, limited=False):
    """The host suite against the real tree. only=None runs every tools/test-*.py; otherwise just those paths.
    Returns (tail, fail_set, ran). ran is true only when the summary says a real 'N run' with N > 0.
    The caller judges a change by the failures it ADDS beyond a clean-tree baseline, so a few env-specific
    failures don't block an otherwise-good change. limited=True is the laptop gate: nice/ionice, an address-space
    cap, a shorter per-test timeout, and a shorter suite timeout."""
    if only is not None and len(only) == 0:
        return "no tests selected", set(), False
    out = os.path.join(STAGE, "tests.txt")
    os.makedirs(os.path.join(ROOT, "run", "tmp"), exist_ok=True)
    os.makedirs(STAGE, exist_ok=True)
    env = dict(os.environ, TMPDIR=os.path.join(ROOT, "run", "tmp"))
    timeout = _suite_timeout(limited)
    if limited:
        env["LLMOS_TEST_TIMEOUT"] = str(LIGHT_TEST_TIMEOUT)
    sh = "bash" if shutil.which("bash") else "sh"   # run-host-tests.sh needs bash (arrays); ash silently errors
    cmd = [sh, os.path.join(ROOT, "tools", "run-host-tests.sh")]
    if only:
        cmd.extend(only)
    if limited:
        cmd = _with_limits(cmd)
    handle = open(out, "w", encoding="utf-8")
    try:
        try:
            _code, timed_out = _run_cmd(cmd, timeout, env, handle)
        except subprocess.TimeoutExpired:
            # _run_cmd already catches this; keep the net so a timeout can never skip the summary check
            _kill_group(_ACTIVE.get("proc"))
            timed_out = True
    finally:
        handle.close()
    if timed_out:
        try:
            open(out, "a", encoding="utf-8").write(f"\ntimed out after {timeout}s\n")
        except OSError:
            pass
        return f"timed out after {timeout}s", set(), False
    lines = open(out, encoding="utf-8").read().splitlines()
    summary = next((l for l in reversed(lines) if re.search(r"host suites:\s*\d+\s*run", l)), "")
    m = re.search(r"host suites:\s*(\d+)\s*run", summary)
    ran = bool(m) and int(m.group(1)) > 0           # a real summary with tests actually executed
    fails = _fail_set(lines)
    tail = summary or (lines[-1] if lines else "(the suite produced no output)")
    return tail.strip(), fails, ran


def baseline_fails(only=None, limited=False):
    """Which tests fail on the UNCHANGED tree, for THIS selection (0 on a full dev machine; a few on a bare
    deploy). A real change is judged only by the failures it ADDS. The light baseline uses the same test list
    and the same resource limits as the patched run."""
    key = (tuple(only) if only else None, bool(limited), _as_cap() if limited else None)
    if key not in _BASELINES:
        print("[selfdev] measuring the baseline (which tests fail before any change)…", flush=True)
        tail, fails, ran = run_tests(only, limited=limited)
        if not ran:
            raise RuntimeError(f"the test suite could not run here ({tail}) -- refusing to stage anything untested")
        _BASELINES[key] = fails
        print(f"[selfdev] baseline: {len(_BASELINES[key])} env-specific failure(s) to ignore: "
              f"{sorted(_BASELINES[key]) or 'none'}", flush=True)
    return _BASELINES[key]


def _unified(backups, newtext):
    import difflib
    out = []
    for rel in sorted(newtext):
        old = backups.get(rel, "").splitlines(keepends=True)
        new = newtext[rel].splitlines(keepends=True)
        out.extend(difflib.unified_diff(old, new, fromfile="a/" + rel, tofile="b/" + rel))
    return "".join(out)


def _limits_line():
    cap = _as_cap()
    cap_s = "no address-space cap" if cap <= 0 else f"address-space cap {cap // (1 << 20)} MiB"
    ion = "ionice idle" if _ionice_ok() else "ionice unavailable"
    nice = "nice 19" if shutil.which("nice") else "nice unavailable"
    return (f"{nice}, {ion}, {cap_s}, suite timeout {_suite_timeout(True)}s, "
            f"per-test timeout {LIGHT_TEST_TIMEOUT}s")


_INSTALL_PREFIX = "src/rootfs/usr/lib/llmos/"
_STAGE_NAMES = ("staged.json", "staged.diff", "tests.txt")


def install_root():
    """The runtime package directory (parent of llmos/*.py). None when it is not there.
    LLMOS_SELFDEV_INSTALL_ROOT overrides /usr/lib/llmos so tests can use a scratch tree."""
    env = os.environ.get("LLMOS_SELFDEV_INSTALL_ROOT", "").strip()
    if env:
        root = os.path.realpath(env)
        return root if os.path.isdir(root) else None
    default = "/usr/lib/llmos"
    if os.path.isdir(default):
        return os.path.realpath(default)
    return None


def _install_root_is_checkout(root):
    return bool(root) and os.path.realpath(root) == os.path.realpath(SRC)


def runtime_path(rel, root=None):
    """Map a repo path onto the runtime tree. Refuse anything that escapes that tree."""
    root = root or install_root()
    if not root:
        return None, "no runtime install root"
    raw = (rel or "").replace("\\", "/").strip()
    if not raw.startswith(_INSTALL_PREFIX):
        return None, f"{raw}: not an OS package file"
    parts = [p for p in raw[len(_INSTALL_PREFIX):].split("/")]
    if not parts or any(p in ("", ".", "..") for p in parts):
        return None, f"{raw}: path escapes the runtime install"
    full = os.path.realpath(os.path.join(root, *parts))
    root_real = os.path.realpath(root)
    if full != root_real and not full.startswith(root_real + os.sep):
        return None, f"{raw}: path escapes the runtime install"
    return full, None


def install_journal_dir():
    return os.path.join(STAGE, "install-journal")


def runtime_backup_dir():
    return os.path.join(STAGE, "runtime-backup")


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".selfdev-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(path))


def write_evidence(payload):
    """The last local-install result. accepted is true only when the runtime bytes match the tested artifact."""
    os.makedirs(STAGE, exist_ok=True)
    body = dict(payload)
    body.setdefault("when", time.strftime("%Y-%m-%d %H:%M:%S"))
    body.setdefault("ok", False)
    body.setdefault("accepted", False)
    _atomic_write(os.path.join(STAGE, "evidence.json"), json.dumps(body, indent=2, sort_keys=True) + "\n")
    return body


def _read_stage_files():
    saved = {}
    for name in _STAGE_NAMES:
        path = os.path.join(STAGE, name)
        if os.path.isfile(path):
            try:
                saved[name] = open(path, encoding="utf-8").read()
            except OSError:
                pass
    return saved


def _restore_preserved_stage(saved):
    """Put staged.json, staged.diff, and tests.txt back. A name that was absent is removed."""
    if saved is None:
        return
    os.makedirs(STAGE, exist_ok=True)
    for name in _STAGE_NAMES:
        dest = os.path.join(STAGE, name)
        if name in saved:
            _atomic_write(dest, saved[name])
        elif os.path.isfile(dest):
            os.remove(dest)


def _archive_previous_stage(saved):
    """Keep the stage this run replaced. A later failure does not delete that copy."""
    if not saved:
        return
    for name, text in saved.items():
        _atomic_write(os.path.join(STAGE, "previous-" + name), text)


def _tests_ran_count(summary):
    match = re.search(r"host suites:\s*(\d+)\s*run", summary or "")
    if not match:
        return 0
    return int(match.group(1))


def stage_acceptable(meta, check_checkout=True):
    """'' when meta is a tested local-light artifact that still matches the checkout it was tested against.
    Anything else must not be installed."""
    if not isinstance(meta, dict):
        return "staged state is malformed"
    files = meta.get("files") or {}
    arts = meta.get("artifact_hashes") or {}
    bases = meta.get("base_hashes") or {}
    if not isinstance(files, dict) or not files:
        return "nothing staged"
    if not isinstance(arts, dict) or not arts or not isinstance(bases, dict) or not bases:
        return "staged change has no artifact or base hashes"
    if meta.get("timed_out"):
        return "the test run timed out"
    if meta.get("new_fails"):
        return "the staged change has failing tests"
    if not meta.get("ran"):
        return "the test suite did not run"
    if _tests_ran_count(meta.get("tests") or "") <= 0:
        return "zero tests ran"
    if meta.get("backend") != "local":
        return "staged change was not produced by the local backend"
    if meta.get("gate") != "light":
        return "staged change was not produced by the bounded light gate"
    for rel, content in files.items():
        if not isinstance(content, str):
            return f"{rel}: staged content is malformed"
        if arts.get(rel) != _sha256(content):
            return f"{rel}: artifact hash does not match the staged bytes"
        full, cleaned, err = edit_target(rel)
        if err:
            return err
        if check_checkout:
            expect = bases.get(rel, bases.get(cleaned))
            if not expect:
                return f"{cleaned}: no base hash"
            try:
                current = open(full, encoding="utf-8").read()
            except OSError as e:
                return f"cannot read {cleaned}: {e}"
            if _sha256(current) != expect:
                return f"stale stage: {cleaned} has changed since the change was tested"
    return ""


def install_journal_save(entries, artifact_hashes=None):
    """Fsync the previous runtime and checkout bytes before either tree is changed."""
    jdir = install_journal_dir()
    os.makedirs(jdir, exist_ok=True)
    commit = os.path.join(jdir, "COMMIT")
    if os.path.isfile(commit):
        os.remove(commit)
    root = install_root()
    manifest = {"install_root": root, "artifact_hashes": artifact_hashes or {}, "files": {}}
    for rel, ent in entries.items():
        fn = hashlib.sha256(rel.encode("utf-8")).hexdigest()
        rec = {"had_runtime": bool(ent.get("had_runtime")),
               "runtime_name": fn + ".runtime", "checkout_name": fn + ".checkout"}
        if ent.get("had_runtime"):
            _atomic_write(os.path.join(jdir, rec["runtime_name"]), ent.get("runtime") or "")
        _atomic_write(os.path.join(jdir, rec["checkout_name"]), ent.get("checkout") or "")
        manifest["files"][rel] = rec
    _atomic_write(os.path.join(jdir, "manifest.json"), json.dumps(manifest))
    return manifest


def _runtime_matches(root, artifact_hashes):
    if not root or not artifact_hashes:
        return False
    for rel, digest in artifact_hashes.items():
        path, err = runtime_path(rel, root)
        if err or not path or not os.path.isfile(path):
            return False
        try:
            got = open(path, encoding="utf-8").read()
        except OSError:
            return False
        if _sha256(got) != digest:
            return False
    return True


def install_journal_recover():
    """Undo an install that did not commit. A commit whose runtime bytes still match is left in place.
    Returns the relative paths restored."""
    jdir = install_journal_dir()
    man_path = os.path.join(jdir, "manifest.json")
    commit_path = os.path.join(jdir, "COMMIT")
    if os.path.isfile(commit_path):
        try:
            info = json.loads(open(commit_path, encoding="utf-8").read())
        except (OSError, json.JSONDecodeError):
            info = {}
        root = info.get("install_root")
        arts = info.get("artifact_hashes") or {}
        if _runtime_matches(root, arts):
            shutil.rmtree(jdir, ignore_errors=True)
            return []
    if not os.path.isfile(man_path):
        return []
    try:
        manifest = json.load(open(man_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("[selfdev] WARNING: the install journal is unreadable; runtime files were left as they are",
              flush=True)
        return []
    root = manifest.get("install_root")
    if not root or not os.path.isdir(root):
        print("[selfdev] WARNING: install journal root is missing; runtime files were left as they are",
              flush=True)
        return []
    files = manifest.get("files") or {}
    restored = []
    for rel, rec in files.items():
        path, err = runtime_path(rel, root)
        if err or not path:
            print(f"[selfdev] WARNING: journal entry {rel} is not in the runtime tree; skipped", flush=True)
            continue
        full, cleaned, co_err = _package_file(rel)
        try:
            if rec.get("had_runtime"):
                name = os.path.basename(rec.get("runtime_name") or "")
                original = open(os.path.join(jdir, name), encoding="utf-8").read()
                _atomic_write(path, original)
            elif os.path.isfile(path):
                os.remove(path)
            if full and not co_err:
                name = os.path.basename(rec.get("checkout_name") or "")
                original_co = open(os.path.join(jdir, name), encoding="utf-8").read()
                _atomic_write(full, original_co)
        except OSError as e:
            print(f"[selfdev] WARNING: could not roll back {rel}: {e}", flush=True)
            continue
        restored.append(rel)
    if restored and len(restored) == len(files):
        shutil.rmtree(jdir, ignore_errors=True)
    return restored


def install_journal_clear():
    jdir = install_journal_dir()
    if os.path.isdir(jdir):
        shutil.rmtree(jdir, ignore_errors=True)


def _mark_install_commit(artifact_hashes):
    _atomic_write(os.path.join(install_journal_dir(), "COMMIT"), json.dumps({
        "install_root": install_root(), "artifact_hashes": artifact_hashes or {}}))


def save_runtime_backup(entries, artifact_hashes, runtime_hashes):
    """Previous runtime bytes kept after a successful install, so --rollback has something to restore."""
    bdir = runtime_backup_dir()
    os.makedirs(bdir, exist_ok=True)
    manifest = {"install_root": install_root(), "artifact_hashes": artifact_hashes or {},
                "runtime_hashes": runtime_hashes or {}, "files": {}}
    for rel, ent in entries.items():
        fn = hashlib.sha256(("prior:" + rel).encode("utf-8")).hexdigest()
        rec = {"had_runtime": bool(ent.get("had_runtime")),
               "runtime_name": fn + ".runtime", "checkout_name": fn + ".checkout"}
        if ent.get("had_runtime"):
            _atomic_write(os.path.join(bdir, rec["runtime_name"]), ent.get("runtime") or "")
        _atomic_write(os.path.join(bdir, rec["checkout_name"]), ent.get("checkout") or "")
        manifest["files"][rel] = rec
    _atomic_write(os.path.join(bdir, "manifest.json"), json.dumps(manifest))
    return manifest


def verify_runtime(files, root=None):
    """Read the runtime files back. Problems is empty only when every hash matches and the file compiles."""
    problems, hashes = [], {}
    for rel, content in files.items():
        path, err = runtime_path(rel, root)
        if err or not path:
            problems.append(err or f"{rel}: no runtime path")
            continue
        try:
            got = open(path, encoding="utf-8").read()
        except OSError as e:
            problems.append(f"{rel}: cannot read installed file: {e}")
            continue
        digest = _sha256(got)
        hashes[rel] = digest
        if digest != _sha256(content):
            problems.append(f"{rel}: installed bytes do not match the tested artifact")
            continue
        try:
            compile(got, path, "exec")
        except SyntaxError as e:
            problems.append(f"{rel}: installed file does not compile: {e}")
    return problems, hashes


def _not_installed(reason, phase, saved_stage=None, rolled_back=False, extra=None):
    if saved_stage is not None:
        _restore_preserved_stage(saved_stage)
    payload = {"ok": False, "accepted": False, "phase": phase, "reason": reason, "backend": "local",
               "installed": False, "rolled_back": bool(rolled_back), "cloud_calls": _CALLS.get("cloud", 0)}
    if extra:
        payload.update(extra)
    write_evidence(payload)
    print(f"[selfdev] NOT INSTALLED: {reason}", flush=True)
    return 2


def install_verified(meta, saved_stage=None):
    """Install the tested artifact into the runtime tree and the checkout.
    Returns 0 only when the runtime read-back matches that artifact. Any problem rolls the runtime
    bytes back and returns non-zero. saved_stage is the unrelated stage this run must not destroy."""
    if _CALLS.get("cloud", 0):
        return _not_installed("the online model was called", "generate", saved_stage)
    reason = stage_acceptable(meta)
    if reason:
        return _not_installed(reason, "stage", saved_stage, extra={
            "tests": meta.get("tests") if isinstance(meta, dict) else "",
            "gate": meta.get("gate") if isinstance(meta, dict) else ""})
    root = install_root()
    if not root:
        return _not_installed("no runtime install root", "install", saved_stage)
    if _install_root_is_checkout(root):
        return _not_installed("the install root is the dev checkout, not the runtime tree", "install", saved_stage)
    files = meta["files"]
    entries = {}
    for rel, content in files.items():
        path, err = runtime_path(rel)
        if err or not path:
            return _not_installed(err or f"{rel}: no runtime path", "install", saved_stage)
        had = os.path.isfile(path)
        try:
            runtime_text = open(path, encoding="utf-8").read() if had else None
        except OSError as e:
            return _not_installed(f"cannot read runtime {rel}: {e}", "install", saved_stage)
        full, cleaned, err = edit_target(rel)
        if err or not full:
            return _not_installed(err or f"{rel}: no checkout file", "install", saved_stage)
        try:
            checkout_text = open(full, encoding="utf-8").read()
        except OSError as e:
            return _not_installed(f"cannot read {cleaned}: {e}", "install", saved_stage)
        entries[rel] = {"runtime": runtime_text, "checkout": checkout_text, "had_runtime": had}
    arts = meta.get("artifact_hashes") or {}
    try:
        install_journal_save(entries, arts)
        write_evidence({"ok": False, "accepted": False, "phase": "install", "reason": "install in progress",
                        "backend": "local", "installed": False, "rolled_back": False,
                        "cloud_calls": _CALLS.get("cloud", 0), "tests": meta.get("tests"),
                        "artifact_hashes": arts, "gate": "light"})
        for rel, content in files.items():
            path, _err = runtime_path(rel)
            _atomic_write(path, content)
        problems, hashes = verify_runtime(files)
        if problems:
            raise RuntimeError("; ".join(problems))
        for rel, content in files.items():
            full, cleaned, err = edit_target(rel)
            if err or not full:
                raise RuntimeError(err or f"{rel}: no checkout file")
            _atomic_write(full, content)
            if _sha256(open(full, encoding="utf-8").read()) != _sha256(content):
                raise RuntimeError(f"{cleaned}: checkout read-back does not match the tested artifact")
        save_runtime_backup(entries, arts, hashes)
        _mark_install_commit(arts)
    except Exception as e:
        restored = install_journal_recover()
        return _not_installed(str(e), "verify", saved_stage, rolled_back=bool(restored), extra={
            "tests": meta.get("tests"), "artifact_hashes": arts, "restored": restored, "gate": "light"})
    evidence = {"ok": True, "accepted": True, "phase": "verified",
                "reason": "runtime bytes match the tested artifact", "backend": "local",
                "cloud_calls": _CALLS.get("cloud", 0), "rolled_back": False, "installed": True,
                "gate": "light", "tests": meta.get("tests"), "artifact_hashes": arts,
                "runtime_hashes": hashes, "install_root": root, "files": sorted(files)}
    if evidence["cloud_calls"]:
        rollback_installed()
        return _not_installed("the online model was called during local install", "verify", saved_stage,
                              rolled_back=True)
    try:
        write_evidence(evidence)
    except OSError as e:
        print(f"[selfdev] WARNING: installed and verified, but the evidence file could not be written: {e}",
              flush=True)
    _archive_previous_stage(saved_stage)
    install_journal_clear()
    print(f"[selfdev] INSTALLED and runtime-verified (local, light, {meta.get('tests')}).", flush=True)
    for rel, digest in hashes.items():
        print(f"[selfdev] {rel} sha256 {digest}", flush=True)
    return 0


def rollback_installed():
    """Restore the runtime bytes saved by the last successful local install.
    Refuses when the runtime is no longer that artifact, so a later edit is not overwritten."""
    bdir = runtime_backup_dir()
    man_path = os.path.join(bdir, "manifest.json")
    if not os.path.isfile(man_path):
        print("[selfdev] nothing to roll back")
        write_evidence({"ok": False, "accepted": False, "phase": "rollback", "reason": "nothing to roll back",
                        "backend": "local", "installed": False, "rolled_back": False, "cloud_calls": 0})
        return 1
    try:
        manifest = json.load(open(man_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("[selfdev] rollback backup is unreadable; nothing was changed")
        return 1
    root = manifest.get("install_root")
    files = manifest.get("files") or {}
    arts = manifest.get("runtime_hashes") or manifest.get("artifact_hashes") or {}
    if not root or not os.path.isdir(root) or not files:
        print("[selfdev] rollback backup is incomplete; nothing was changed")
        return 1
    for rel, rec in files.items():
        path, err = runtime_path(rel, root)
        if err or not path:
            print(f"[selfdev] refusing rollback: {err or rel}")
            return 1
        expect = arts.get(rel)
        try:
            current = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
        except OSError as e:
            print(f"[selfdev] refusing rollback: cannot read {rel}: {e}")
            return 1
        if expect and (current is None or _sha256(current) != expect):
            print(f"[selfdev] refusing rollback: {rel} is not the installed artifact, so it was left as it is")
            write_evidence({"ok": False, "accepted": False, "phase": "rollback",
                            "reason": f"{rel} is not the installed artifact", "backend": "local",
                            "installed": False, "rolled_back": False, "cloud_calls": 0})
            return 1
    for rel, rec in files.items():
        path, _err = runtime_path(rel, root)
        try:
            if rec.get("had_runtime"):
                text = open(os.path.join(bdir, os.path.basename(rec["runtime_name"])), encoding="utf-8").read()
                _atomic_write(path, text)
            elif os.path.isfile(path):
                os.remove(path)
            full, _cleaned, err = _package_file(rel)
            if full and not err:
                text = open(os.path.join(bdir, os.path.basename(rec["checkout_name"])), encoding="utf-8").read()
                _atomic_write(full, text)
        except OSError as e:
            print(f"[selfdev] rollback failed while writing {rel}: {e}")
            write_evidence({"ok": False, "accepted": False, "phase": "rollback", "reason": str(e),
                            "backend": "local", "installed": False, "rolled_back": False, "cloud_calls": 0})
            return 1
    for rel, rec in files.items():
        path, _err = runtime_path(rel, root)
        if rec.get("had_runtime"):
            text = open(os.path.join(bdir, os.path.basename(rec["runtime_name"])), encoding="utf-8").read()
            try:
                got = open(path, encoding="utf-8").read()
            except OSError:
                got = None
            if got != text:
                print(f"[selfdev] rollback read-back failed for {rel}")
                return 1
        elif path and os.path.exists(path):
            print(f"[selfdev] rollback left {rel} in place")
            return 1
    print("[selfdev] rolled back the runtime install to the previous bytes")
    write_evidence({"ok": True, "accepted": False, "phase": "rollback",
                    "reason": "restored the previous runtime bytes", "backend": "local",
                    "installed": False, "rolled_back": True, "cloud_calls": 0})
    return 0


def do_task(task, gate_request="auto", backend="auto", install=False):
    os.makedirs(STAGE, exist_ok=True)
    _ensure_hooks()
    _CALLS["cloud"] = 0
    _CALLS["local"] = 0
    backend = (backend or "auto").lower()
    saved_stage = _read_stage_files() if install else None

    def stop(code, phase, reason):
        if install:
            _restore_preserved_stage(saved_stage)
            write_evidence({"ok": False, "accepted": False, "phase": phase, "reason": reason,
                            "backend": "local", "installed": False, "rolled_back": False,
                            "cloud_calls": _CALLS.get("cloud", 0)})
            if code == 0:
                return 2
        return code

    if install:
        backend = "local"
        if (gate_request or "auto").lower() == "full":
            print("[selfdev] REFUSING the full gate as part of local install. This lifecycle runs the bounded "
                  "light gate only. Nothing was installed.", flush=True)
            return stop(2, "gate", "full gate refused for local install")
        root = install_root()
        if not root:
            print("[selfdev] NOT INSTALLED: no runtime install root. Nothing was changed.", flush=True)
            return stop(2, "install", "no runtime install root")
        if _install_root_is_checkout(root):
            print("[selfdev] NOT INSTALLED: the install root is the dev checkout, not the runtime tree.",
                  flush=True)
            return stop(2, "install", "install root is the dev checkout")
        gate_request = "light"
        print("[selfdev] local install: on-device model only (cloud config is ignored); bounded light gate",
              flush=True)
    gate, why = resolve_gate(gate_request)
    print(f"[selfdev] test gate: {gate} ({why})", flush=True)
    if gate == "full" and _is_live_install():
        print("[selfdev] REFUSING the full gate: this is a live LLM OS install. The full suite applies the real "
              "firewall and stops real services, and on a 16 GB machine it can wedge the box. Run the loop on a "
              "dev checkout and ship the result here afterwards. The light gate is allowed here: --gate light.",
              flush=True)
        return stop(2, "gate", "full gate refused on a live install")
    if gate == "light":
        print(f"[selfdev] light-gate limits: {_limits_line()}", flush=True)
    note = ""
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"[selfdev] round {rnd}: asking the model for a change…", flush=True)
        try:
            text = propose(task, note, backend=backend)
        except Exception as e:
            note = "the model did not answer (%s)" % e
            print(f"[selfdev] {note}", flush=True)
            continue
        edits, perr = explain_edits(text)
        if not edits:
            note = perr or "no change block was produced in the required format"
            print(f"[selfdev] {note}", flush=True)
            continue
        if gate == "light":
            sel, info = select_light_tests(edits)
            if sel is None:
                # No test touches the module: do not guess, and do not fall through to the full suite.
                if "Nothing was staged" in (info or ""):
                    print(f"[selfdev] NOT STAGING: {info}", flush=True)
                    return stop(2, "gate", info)
                note = info or "no edit could be applied"
                print(f"[selfdev] could not apply: {note}", flush=True)
                continue
            print(f"[selfdev] light gate: {info}", flush=True)
            risky = sorted(set(LIVE_RISKY_TESTS) & set(sel))
            if risky and _is_live_install():
                print("[selfdev] note: this light run includes " + ", ".join(risky)
                      + ". They are written not to touch the real firewall or power off; the normal place for "
                      "this loop is still a dev checkout.", flush=True)
        else:
            sel, info = None, "the full suite"
        try:
            base = baseline_fails(sel, limited=(gate == "light"))
        except RuntimeError as e:
            print(f"[selfdev] {e}", flush=True)
            return stop(2, "test", str(e))
        applied, problems, backups, newtext = apply_live(edits)
        if applied == 0:
            restore(backups)
            note = "; ".join(problems[:3]) or "no edit could be applied"
            print(f"[selfdev] could not apply: {note}", flush=True)
            continue
        print(f"[selfdev] applied {applied} edit(s) to the live files (put back after the run); running {info} "
              f"(this is the seatbelt)…", flush=True)
        timed_out = False
        try:
            tail, fails, ran = run_tests(sel, limited=(gate == "light"))
            new_fails = fails - base
            d = _unified(backups, newtext)
            if not ran and "timed out" in tail:
                timed_out = True
        finally:
            restore(backups)                     # the real source is edited ONLY during the run, always put back
        if timed_out:
            print(f"[selfdev] {tail}. Stopped rather than trying again. Nothing was staged.", flush=True)
            return stop(2, "test", tail)
        if ran and not new_fails:
            meta = {"task": task, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "tests": tail, "round": rnd,
                    "gate": gate, "test_files": sel or [],
                    "base_hashes": {rel: _sha256(backups[rel]) for rel in newtext},
                    "artifact_hashes": {rel: _sha256(newtext[rel]) for rel in newtext},
                    "ran": True, "new_fails": [], "timed_out": False, "backend": backend,
                    "files": newtext}
            open(os.path.join(STAGE, "staged.diff"), "w", encoding="utf-8").write(d)
            json.dump(meta, open(os.path.join(STAGE, "staged.json"), "w", encoding="utf-8"))
            if install:
                if _CALLS.get("cloud", 0):
                    print("[selfdev] NOT INSTALLED: the online model was called. Nothing was installed.",
                          flush=True)
                    return stop(2, "generate", "the online model was called")
                rc = install_verified(meta, saved_stage)
                if rc != 0:
                    _restore_preserved_stage(saved_stage)
                return rc
            print(f"\n[selfdev] TESTS PASS ({gate}, {tail}). The change is staged, NOT shipped. "
                  f"The live source is back as it was.\n"
                  f"[selfdev] A person reviews it:  tools/selfdev.py --show   then  --apply  (or --discard).\n",
                  flush=True)
            if gate == "light":
                print("[selfdev] Light gate only. Run the full suite on a dev machine before shipping.", flush=True)
            return 0
        note = (f"the test suite did not run ({tail})" if not ran
                else f"the change broke tests that pass without it: {', '.join(sorted(new_fails))} ({tail})")
        print(f"[selfdev] {note}", flush=True)
    print("[selfdev] gave up after %d rounds without a change that passes the tests." % MAX_ROUNDS, flush=True)
    return stop(1, "generate", note or "no change passed the tests")


def show():
    sj = os.path.join(STAGE, "staged.json")
    if not os.path.isfile(sj):
        print("Nothing staged.")
        return 1
    meta = json.load(open(sj, encoding="utf-8"))
    gate = meta.get("gate", "full")
    print(f"Staged {meta['when']} for task: {meta['task']}\nGate: {gate}\nTests: {meta['tests']}\n"
          f"Files: {', '.join(meta.get('files', {}))}\n")
    if gate == "light":
        names = meta.get("test_files") or []
        print(f"Light gate only: {len(names)} test file(s), not the full suite. "
              f"Run the full suite on a dev machine before shipping.\n")
    print(open(os.path.join(STAGE, "staged.diff"), encoding="utf-8").read())
    return 0


def apply_staged():
    """A HUMAN runs this to write the staged, tested change into the real source. Still not shipped.
    Refuses if a file has changed since staging (the base hash no longer matches), so a later edit is not
    overwritten by an older staged copy."""
    sj = os.path.join(STAGE, "staged.json")
    if not os.path.isfile(sj):
        print("Nothing staged.")
        return 1
    meta = json.load(open(sj, encoding="utf-8"))
    files = meta.get("files", {})
    bases = meta.get("base_hashes") or {}
    if not files:
        print("Nothing staged.")
        return 1
    if not bases:
        print("This staged change has no base hashes, so it is not safe to overwrite the files. "
              "Discard it and run the loop again.")
        return 1
    checked = []
    for rel, content in files.items():
        full, cleaned, err = edit_target(rel)
        if err:
            print(f"Refusing to apply: {err}")
            return 1
        if rel not in bases and cleaned not in bases:
            print(f"Refusing to apply: {cleaned} has no base hash.")
            return 1
        expect = bases.get(rel, bases.get(cleaned))
        try:
            current = open(full, encoding="utf-8").read()
        except OSError as e:
            print(f"Refusing to apply: cannot read {cleaned}: {e}")
            return 1
        if _sha256(current) != expect:
            print(f"Refusing to apply: {cleaned} has changed since the change was staged. "
                  f"Discard it and run the loop again.")
            return 1
        checked.append((full, content))
    for full, content in checked:
        open(full, "w", encoding="utf-8").write(content)
    print(f"Wrote the staged change into {', '.join(files)}. Review `git diff`, commit, and (separately) "
          f"`tools/ota.py publish` when you want it on the devices.")
    return 0


def main(argv=None):
    _ensure_hooks()
    recovered = journal_recover()
    if recovered:
        print("[selfdev] restored %d file(s) left edited by an interrupted run: %s"
              % (len(recovered), ", ".join(recovered)), flush=True)
    interrupted = install_journal_recover()
    if interrupted:
        print("[selfdev] rolled back %d runtime file(s) left by an interrupted install: %s"
              % (len(interrupted), ", ".join(interrupted)), flush=True)
        write_evidence({"ok": False, "accepted": False, "phase": "rollback", "backend": "local",
                        "installed": False, "rolled_back": True, "cloud_calls": 0,
                        "reason": "interrupted install was rolled back on startup", "restored": interrupted})
    ap = argparse.ArgumentParser(
        epilog="Copy onto a 2026-10-23 checkout, together: " + ", ".join(DEPLOY_FILES)
        + ". Do not copy llmos/llm.py or llmos/config.py with these files.")
    ap.add_argument("task", nargs="?", default="")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--discard", action="store_true")
    ap.add_argument("--rollback", action="store_true",
                    help="restore the runtime bytes from the last successful --local-install")
    ap.add_argument("--backend", choices=("auto", "local"), default="auto",
                    help="auto (default): online model when one is configured, otherwise on-device. "
                         "local: on-device endpoint only, never the online model.")
    ap.add_argument("--install", action="store_true",
                    help="owner-invoked local lifecycle: bounded light gate, then install the tested "
                         "artifact into the runtime tree, verify the read-back, and roll back on failure. "
                         "Does not ask for another confirmation. Implies --backend local.")
    ap.add_argument("--local-install", action="store_true",
                    help="same as --backend local --install")
    ap.add_argument("--gate", choices=("auto", "full", "light"), default="auto",
                    help="auto (default): full suite on a dev machine, light gate on a live install or when "
                         "memory is low. full is refused on a live install. light is overridable anywhere. "
                         "--install always uses the light gate and refuses --gate full.")
    a = ap.parse_args(argv)
    if a.show:
        return show()
    if a.rollback:
        return rollback_installed()
    if a.apply:
        return apply_staged()
    if a.discard:
        shutil.rmtree(STAGE, ignore_errors=True)
        print("Discarded the staged change.")
        return 0
    if a.local_install:
        a.backend = "local"
        a.install = True
    if (a.install or a.local_install) and not a.task:
        print("The local install lifecycle needs the change to make. It does not install an existing stage.")
        return 2
    if not a.task:
        ap.print_help()
        return 2
    return do_task(a.task, a.gate, backend=a.backend, install=a.install)


if __name__ == "__main__":
    sys.exit(main())
