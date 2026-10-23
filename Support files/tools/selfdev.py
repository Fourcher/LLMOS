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


EDIT_FORMAT = """Return ONLY changes, in this exact format, nothing else:

=== FILE: relative/path/from/repo/root.py
<<<<<<< SEARCH
(the exact lines to find, copied verbatim)
=======
(the lines to replace them with)
>>>>>>> REPLACE

Repeat the FILE/SEARCH/REPLACE block for each change. The SEARCH text must match the file exactly, including
indentation. Keep each change small. Do not explain. Do not output anything outside the blocks."""

_BLOCK = re.compile(r"===\s*FILE:\s*(?P<path>\S+)\s*\n<<<<<<<\s*SEARCH\s*\n(?P<search>.*?)\n=======\s*\n"
                    r"(?P<replace>.*?)\n>>>>>>>\s*REPLACE", re.S)


def gather_context(task, limit=6000):
    """The files most likely relevant to the task: ranked by how many of the task's words they contain."""
    words = {w for w in re.findall(r"[a-z_]{4,}", task.lower())}
    scored = []
    for name in sorted(os.listdir(PKG)):
        if not name.endswith(".py"):
            continue
        try:
            text = open(os.path.join(PKG, name), encoding="utf-8").read()
        except OSError:
            continue
        score = sum(text.lower().count(w) for w in words)
        scored.append((score, name, text))
    scored.sort(reverse=True)
    out, used = [], 0
    for score, name, text in scored[:3]:
        if score == 0:
            break
        excerpt = text[:limit]
        out.append(f"=== src/rootfs/usr/lib/llmos/llmos/{name} (first {len(excerpt)} chars) ===\n{excerpt}")
        used += len(excerpt)
        if used > limit * 2:
            break
    return "\n\n".join(out) or "(no obviously related file found; ask for the path)"


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
    r = _chat([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}], max_tokens=2000, temperature=0.2)
    return (r.get("content") or "").strip()


def parse_edits(text):
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
    subprocess.run(["sh", os.path.join(ROOT, "tools", "run-host-tests.sh")], cwd=ROOT,
                   stdout=open(out, "w"), stderr=subprocess.STDOUT, env=env, timeout=1800)
    lines = open(out, encoding="utf-8").read().splitlines()
    tail = next((l for l in reversed(lines) if "host suites:" in l), lines[-1] if lines else "")
    fails = {l.split()[1] for l in lines if l.startswith("FAIL ")}
    return tail.strip(), fails


_BASELINE = None


def baseline_fails():
    """Which tests fail on the UNCHANGED tree (0 on a full dev machine; a few on a bare deploy without git/venv).
    Computed once; a real change is judged only by the failures it ADDS."""
    global _BASELINE
    if _BASELINE is None:
        print("[selfdev] measuring the baseline (which tests fail before any change)…", flush=True)
        _, _BASELINE = run_tests()
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


def do_task(task):
    os.makedirs(STAGE, exist_ok=True)
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
            tail, fails = run_tests()
            new_fails = fails - base
            d = _unified(backups, newtext)
        finally:
            restore(backups)                     # the real source is edited ONLY during the run, always put back
        if not new_fails:
            open(os.path.join(STAGE, "staged.diff"), "w").write(d)
            json.dump({"task": task, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "tests": tail, "round": rnd,
                       "files": newtext}, open(os.path.join(STAGE, "staged.json"), "w"))
            print(f"\n[selfdev] TESTS PASS ({tail}). The change is staged, NOT shipped. The live source is back as it was.\n"
                  f"[selfdev] A person reviews it:  tools/selfdev.py --show   then  --apply  (or --discard).\n", flush=True)
            return 0
        note = f"the change broke tests that pass without it: {', '.join(sorted(new_fails))} ({tail})"
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
