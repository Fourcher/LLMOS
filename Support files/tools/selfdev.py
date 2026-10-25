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

Shipping to devices is still a separate, deliberate `tools/ota.py publish` a human runs after --apply.
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
    raise SystemExit(128 + (signum or 0))


def _on_exit():
    proc = _ACTIVE.get("proc")
    if proc is not None and proc.poll() is None:
        _kill_group(proc)
    journal_recover()


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


def _chat(messages, **kw):
    """The configured online model when one is set, otherwise the on-device model.
    This loop does not escalate to another model when the reply is a refusal."""
    llm = _llm()
    try:
        from llmos import config
        if config.cloud():
            return llm.cloud_chat(messages, **kw)
    except Exception:
        pass
    return llm.chat(messages, **kw)


EDIT_FORMAT = """Return ONLY changes, in this EXACT format. No markdown, no ```, no +/- diff lines, no explanation.
Copy this layout literally:

=== FILE: src/rootfs/usr/lib/llmos/llmos/web.py
<<<<<<< SEARCH
_TIMEOUT = 10
=======
_TIMEOUT = 20
>>>>>>> REPLACE

Rules: the path is relative to the repo root. The SEARCH text is copied VERBATIM from the file shown to you, exact
whitespace, enough lines to be unique. One block per change; repeat the whole block for more. Nothing outside blocks.
Only Python files in the OS package (src/rootfs/usr/lib/llmos/llmos/*.py) may be edited. Do not edit tests."""

_BLOCK = re.compile(r"===\s*FILE:\s*(?P<path>\S+)\s*\n<<<<<<<\s*SEARCH\s*\n(?P<search>.*?)\n=======\s*\n"
                    r"(?P<replace>.*?)\n>>>>>>>\s*REPLACE", re.S)


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


def propose(task, note=""):
    """Ask the model for a set of edits. Returns the raw text."""
    ctx = gather_context(task + " " + note)
    sysmsg = ("You edit the source code of LLM OS, an operating system, to carry out a change its owner asked for. "
              "You are given the task and excerpts of the most relevant files. Make the smallest change that does it. "
              "Never weaken a safety check, a permission prompt, the firewall or the update signature. " + EDIT_FORMAT)
    user = f"TASK: {task}\n"
    if note:
        user += f"\nThe last attempt did not work: {note}\n"
    user += f"\nRELEVANT FILES:\n{ctx}"
    r = _chat([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}], max_tokens=1200, temperature=0.1)
    return (r.get("content") or "").strip()


def parse_edits(text):
    text = text.replace("```", "")        # the model sometimes fences the blocks; the markers below are what matter
    edits = []
    for m in _BLOCK.finditer(text):
        edits.append({"path": m.group("path").strip(), "search": m.group("search"), "replace": m.group("replace")})
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
        if e["search"] not in text:
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


def do_task(task, gate_request="auto"):
    os.makedirs(STAGE, exist_ok=True)
    _ensure_hooks()
    gate, why = resolve_gate(gate_request)
    print(f"[selfdev] test gate: {gate} ({why})", flush=True)
    if gate == "full" and _is_live_install():
        print("[selfdev] REFUSING the full gate: this is a live LLM OS install. The full suite applies the real "
              "firewall and stops real services, and on a 16 GB machine it can wedge the box. Run the loop on a "
              "dev checkout and ship the result here afterwards. The light gate is allowed here: --gate light.",
              flush=True)
        return 2
    if gate == "light":
        print(f"[selfdev] light-gate limits: {_limits_line()}", flush=True)
    note = ""
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"[selfdev] round {rnd}: asking the model for a change…", flush=True)
        text = propose(task, note)
        edits = parse_edits(text)
        if not edits:
            note = "no change block was produced in the required format"
            print(f"[selfdev] {note}", flush=True)
            continue
        if gate == "light":
            sel, info = select_light_tests(edits)
            if sel is None:
                # No test touches the module: do not guess, and do not fall through to the full suite.
                if "Nothing was staged" in (info or ""):
                    print(f"[selfdev] NOT STAGING: {info}", flush=True)
                    return 2
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
            return 2
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
            return 2
        if ran and not new_fails:
            open(os.path.join(STAGE, "staged.diff"), "w", encoding="utf-8").write(d)
            json.dump({"task": task, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "tests": tail, "round": rnd,
                       "gate": gate, "test_files": sel or [],
                       "base_hashes": {rel: _sha256(backups[rel]) for rel in newtext},
                       "files": newtext}, open(os.path.join(STAGE, "staged.json"), "w", encoding="utf-8"))
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
    return 1


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
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default="")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--discard", action="store_true")
    ap.add_argument("--gate", choices=("auto", "full", "light"), default="auto",
                    help="auto (default): full suite on a dev machine, light gate on a live install or when "
                         "memory is low. full is refused on a live install. light is overridable anywhere.")
    a = ap.parse_args(argv)
    if a.show:
        return show()
    if a.apply:
        return apply_staged()
    if a.discard:
        shutil.rmtree(STAGE, ignore_errors=True)
        print("Discarded the staged change.")
        return 0
    if not a.task:
        ap.print_help()
        return 2
    return do_task(a.task, a.gate)


if __name__ == "__main__":
    sys.exit(main())
