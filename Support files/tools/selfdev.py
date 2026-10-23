#!/usr/bin/env python3
"""LLM OS working on its own code, with a seatbelt.

A model proposes a change to LLM OS's own source. The change is written into the real files ONLY while the FULL host
test suite runs against it, then the files are put back exactly as they were (the edit is transient; the live source
is never left changed). If the suite passes, the change is staged for a human yes. It never ships on its own. A passing
suite proves the code isn't broken; it does NOT prove an uncensored model didn't quietly weaken a safeguard -- so a
person sees the diff before anything is written for real. That gate is the whole point; don't remove it.

The model is whatever LLM OS is set to use (llmos.llm picks the best available: the home-brain or an online model when
configured, else the on-device model), and a refusal auto-switches to another model (agent.py escalation). So "use the
best coder, switch on refusal" is already how the model is chosen.

Run on the machine that has the source tree and the test harness:
    tools/selfdev.py "add a 'dark mode at sunset' setting"     # propose, test, stage -- stops before shipping
    tools/selfdev.py --show                                    # show the staged change and its test result
    tools/selfdev.py --apply                                   # a HUMAN applies the staged, tested change (commits it)
    tools/selfdev.py --discard

Shipping to devices (OTA) is still a separate, deliberate `tools/ota.py publish` a human runs after --apply."""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src/rootfs/usr/lib/llmos")       # parent of the llmos package (for `import llmos`)
PKG = os.path.join(SRC, "llmos")                          # the package itself: web.py, agent.py, … live here
STAGE = os.path.join(ROOT, "run", "selfdev")
TESTS = os.path.join(HERE, "run-host-tests.sh")
MAX_ROUNDS = 3

# the model lives in the installed system; add it to the path so this can run on the laptop too
sys.path.insert(0, "/usr/lib/llmos")
sys.path.insert(0, SRC)


def _llm():
    from llmos import llm  # noqa: E402
    return llm


def _chat(messages, **kw):
    """The best model available: the configured online coder (e.g. a free OpenRouter coder) when there is one,
    else the on-device model. A refusal is handled by the caller re-asking; coding rarely refuses."""
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
whitespace, enough lines to be unique. One block per change; repeat the whole block for more. Nothing outside blocks."""

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
    """Apply SEARCH/REPLACE edits to the REAL files, after backing up each. Returns (applied, problems, backups, newtext)
    where backups/newtext map each touched file's relative path to its original / edited contents. The caller MUST
    restore(backups) afterwards; the edit is live only while the suite runs, then put back."""
    applied, problems, backups, newtext = 0, [], {}, {}
    for e in edits:
        rel = e["path"].replace("\\", "/").lstrip("/")
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            problems.append(f"{rel}: no such file")
            continue
        text = open(full, encoding="utf-8").read()
        if e["search"] not in text:
            problems.append(f"{rel}: the SEARCH text was not found exactly")
            continue
        if text.count(e["search"]) > 1:
            problems.append(f"{rel}: the SEARCH text is not unique; make it longer")
            continue
        backups.setdefault(rel, text)            # original (first touch only)
        text = text.replace(e["search"], e["replace"], 1)
        open(full, "w", encoding="utf-8").write(text)
        newtext[rel] = text
        applied += 1
    return applied, problems, backups, newtext


def restore(backups):
    """Put the original contents back. Called in a finally so the real source is never left edited."""
    for rel, original in backups.items():
        try:
            open(os.path.join(ROOT, rel), "w", encoding="utf-8").write(original)
        except OSError as e:
            print(f"[selfdev] WARNING: could not restore {rel}: {e}", flush=True)


def run_tests():
    """The full host suite against the real tree. Returns (tail, fail_set) -- the set of test files that FAILED. The
    caller judges a change by the failures it ADDS beyond a clean-tree baseline, so a few env-specific failures (e.g.
    a git-based test on a machine without the repo history) don't block an otherwise-good change."""
    out = os.path.join(STAGE, "tests.txt")
    os.makedirs(os.path.join(ROOT, "run", "tmp"), exist_ok=True)
    env = dict(os.environ, TMPDIR=os.path.join(ROOT, "run", "tmp"))
    sh = "bash" if __import__("shutil").which("bash") else "sh"   # run-host-tests.sh needs bash (arrays); ash silently errors
    subprocess.run([sh, os.path.join(ROOT, "tools", "run-host-tests.sh")], cwd=ROOT,
                   stdout=open(out, "w"), stderr=subprocess.STDOUT, env=env, timeout=1800)
    lines = open(out, encoding="utf-8").read().splitlines()
    summary = next((l for l in reversed(lines) if re.search(r"host suites:\s*\d+\s*run", l)), "")
    m = re.search(r"host suites:\s*(\d+)\s*run", summary)
    ran = bool(m) and int(m.group(1)) > 0           # a real summary with tests actually executed
    fails = {l.split()[1] for l in lines if l.startswith("FAIL ")}
    tail = summary or (lines[-1] if lines else "(the suite produced no output)")
    return tail.strip(), fails, ran


_BASELINE = None


def baseline_fails():
    """Which tests fail on the UNCHANGED tree (0 on a full dev machine; a few on a bare deploy without git/venv).
    Computed once; a real change is judged only by the failures it ADDS."""
    global _BASELINE
    if _BASELINE is None:
        print("[selfdev] measuring the baseline (which tests fail before any change)…", flush=True)
        tail, fails, ran = run_tests()
        if not ran:
            raise RuntimeError(f"the test suite could not run here ({tail}) -- refusing to stage anything untested")
        _BASELINE = fails
        print(f"[selfdev] baseline: {len(_BASELINE)} env-specific failure(s) to ignore: {sorted(_BASELINE) or 'none'}", flush=True)
    return _BASELINE


def _unified(backups, newtext):
    import difflib
    out = []
    for rel in sorted(newtext):
        old = backups.get(rel, "").splitlines(keepends=True)
        new = newtext[rel].splitlines(keepends=True)
        out.extend(difflib.unified_diff(old, new, fromfile="a/" + rel, tofile="b/" + rel))
    return "".join(out)


def _is_live_install():
    """True on an actual running LLM OS machine (not a dev checkout). The host suite reconfigures the REAL firewall
    and stops REAL services, so running it here would knock the machine's own networking/SSH out -- which is exactly
    what happened once. The gate belongs on a dev machine or a VM, never the live install."""
    return os.path.exists("/etc/init.d/llmos-desk") or os.path.exists("/etc/llmos/installed")


def do_task(task):
    os.makedirs(STAGE, exist_ok=True)
    if _is_live_install():
        print("[selfdev] REFUSING: this is a live LLM OS install. The test gate applies the real firewall and stops "
              "real services -- running it here can cut the machine's own SSH/internet. Run the loop on a dev checkout "
              "or a VM, and ship the result to this machine via OTA.", flush=True)
        return 2
    try:
        baseline_fails()
    except RuntimeError as e:
        print(f"[selfdev] {e}", flush=True)
        return 2
    note = ""
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"[selfdev] round {rnd}: asking the model for a change…", flush=True)
        text = propose(task, note)
        edits = parse_edits(text)
        if not edits:
            note = "no change block was produced in the required format"
            print(f"[selfdev] {note}", flush=True)
            continue
        base = baseline_fails()                  # a clean-tree run, once, cached
        applied, problems, backups, newtext = apply_live(edits)
        if applied == 0:
            restore(backups)
            note = "; ".join(problems[:3]) or "no edit could be applied"
            print(f"[selfdev] could not apply: {note}", flush=True)
            continue
        print(f"[selfdev] applied {applied} edit(s) to the live files (put back after the run); running the full test suite "
              f"(this is the seatbelt)…", flush=True)
        try:
            tail, fails, ran = run_tests()
            new_fails = fails - base
            d = _unified(backups, newtext)
        finally:
            restore(backups)                     # the real source is edited ONLY during the run, always put back
        if ran and not new_fails:
            open(os.path.join(STAGE, "staged.diff"), "w").write(d)
            json.dump({"task": task, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "tests": tail, "round": rnd,
                       "files": newtext}, open(os.path.join(STAGE, "staged.json"), "w"))
            print(f"\n[selfdev] TESTS PASS ({tail}). The change is staged, NOT shipped. The live source is back as it was.\n"
                  f"[selfdev] A person reviews it:  tools/selfdev.py --show   then  --apply  (or --discard).\n", flush=True)
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
    meta = json.load(open(sj))
    print(f"Staged {meta['when']} for task: {meta['task']}\nTests: {meta['tests']}\nFiles: {', '.join(meta.get('files', {}))}\n")
    print(open(os.path.join(STAGE, "staged.diff")).read())
    return 0


def apply_staged():
    """A HUMAN runs this to write the staged, tested change into the real source. Still not shipped (OTA is separate)."""
    sj = os.path.join(STAGE, "staged.json")
    if not os.path.isfile(sj):
        print("Nothing staged.")
        return 1
    files = json.load(open(sj)).get("files", {})
    for rel, content in files.items():
        open(os.path.join(ROOT, rel), "w", encoding="utf-8").write(content)
    print(f"Wrote the staged change into {', '.join(files)}. Review `git diff`, commit, and (separately) "
          f"`tools/ota.py publish` when you want it on the devices.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="?", default="")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--discard", action="store_true")
    a = ap.parse_args()
    if a.show:
        return show()
    if a.apply:
        return apply_staged()
    if a.discard:
        import shutil
        shutil.rmtree(STAGE, ignore_errors=True)
        print("Discarded the staged change.")
        return 0
    if not a.task:
        ap.print_help()
        return 2
    return do_task(a.task)


if __name__ == "__main__":
    sys.exit(main())
