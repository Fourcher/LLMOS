#!/usr/bin/env python3
"""The self-development loop (tools/selfdev.py) keeps its seatbelt. It parses a model's edits, applies them to the real
files ONLY while the test gate runs and always restores them (including from a journal if the process is killed),
rejects edits that don't match or that escape the OS package, stages a tested change rather than shipping it, and
does not ship on its own (applying, and shipping via OTA, are separate human steps). The light gate runs only the
tests that touch the changed modules, plus a core subset. --local-install is the owner-invoked path that installs
the tested bytes into a runtime tree and rolls them back unless a read-back matches; those cases use a mock
loopback model and a scratch install root. Does NOT run the full suite.
Run: python3 tools/test-selfdev.py"""
import ast
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import selfdev  # noqa: E402

fails = 0


def check(c, w):
    global fails
    print(("  ok   " if c else "  FAIL ") + w)
    if not c:
        fails += 1


# --- parse a model's edit blocks ---
text = ("blah\n=== FILE: src/x.py\n<<<<<<< SEARCH\nold line\n=======\nnew line\n>>>>>>> REPLACE\n"
        "=== FILE: tools/y.py\n<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n")
edits = selfdev.parse_edits(text)
check(len(edits) == 2 and edits[0]["path"] == "src/x.py" and edits[0]["search"] == "old line"
      and edits[1]["replace"] == "bar", "parses each FILE/SEARCH/REPLACE block")
check(selfdev.parse_edits("no blocks here") == [], "chatter with no blocks yields no edits")

# --- small-model replies: fences, missing markers, renamed markers, diff, whole file ---
_fenced = ("Sure, here is the edit:\n```python\n=== FILE: src/x.py\n<<<<<<< SEARCH\nold line\n=======\n"
           "new line\n>>>>>>> REPLACE\n```\n")
_fed = selfdev.parse_edits(_fenced)
check(len(_fed) == 1 and _fed[0]["path"] == "src/x.py" and _fed[0]["search"] == "old line"
      and _fed[0]["replace"] == "new line", "a fenced block still parses")
_bare = ("src/x.py\n<<<<<<< SEARCH\nold line\n=======\nnew line\n>>>>>>> REPLACE\n")
_bed = selfdev.parse_edits(_bare)
check(len(_bed) == 1 and _bed[0]["path"] == "src/x.py" and _bed[0]["replace"] == "new line",
      "a path line with no === FILE marker still parses")
_renamed = ("=== FILE: src/x.py\n<<<<<<< ORIGINAL\nold line\n=======\nnew line\n>>>>>>> UPDATED\n")
_red = selfdev.parse_edits(_renamed)
check(len(_red) == 1 and _red[0]["search"] == "old line" and _red[0]["replace"] == "new line",
      "ORIGINAL/UPDATED markers are accepted")
_words = ("FILE: src/x.py\nSEARCH:\nold line\nREPLACE:\nnew line\n")
_wed = selfdev.parse_edits(_words)
check(len(_wed) == 1 and _wed[0]["path"] == "src/x.py" and _wed[0]["search"] == "old line"
      and _wed[0]["replace"] == "new line", "SEARCH:/REPLACE: lines are accepted")
_diff = ("--- a/src/x.py\n+++ b/src/x.py\n@@ -1,3 +1,3 @@\n def fetch():\n-    return 1\n+    return 2\n     return 1\n")
_ded = selfdev.parse_edits(_diff)
check(len(_ded) == 1 and _ded[0]["path"] == "src/x.py"
      and _ded[0]["search"] == "def fetch():\n    return 1\n    return 1"
      and _ded[0]["replace"] == "def fetch():\n    return 2\n    return 1",
      "a unified diff becomes one SEARCH/REPLACE, keeping the context lines")
_whole = ("=== FILE: src/x.py\n# kept\ndef fetch():\n    return 2\n")
_hed = selfdev.parse_edits(_whole)
check(len(_hed) == 1 and _hed[0].get("whole") and _hed[0]["path"] == "src/x.py"
      and "return 2" in _hed[0]["replace"], "a whole-file reply under a FILE line is an edit")
_web = selfdev.parse_edits("=== FILE: web.py\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n")
check(len(_web) == 1 and _web[0]["path"].endswith("/llmos/web.py"),
      "a bare web.py path is the package file")
_none, _err = selfdev.explain_edits("I changed the comment already.")
check(_none == [] and "FILE" in _err and "SEARCH" in _err,
      "prose with no block returns the shape the next round is shown")
_miss, _merr = selfdev.explain_edits("=== FILE: src/x.py\n<<<<<<< SEARCH\nold line\nnew line\n>>>>>>> REPLACE\n")
check(_miss == [] and "=======" in _merr, "a block missing ======= names that missing line")
check("explain_edits(" in open(os.path.join(HERE, "selfdev.py"), encoding="utf-8").read().split("def do_task", 1)[1],
      "a format failure's exact parse error is what the next round is told")
check(selfdev.DEPLOY_FILES == ("tools/selfdev.py", "tools/test-selfdev.py", "tools/run-host-tests.sh"),
      "the laptop copy set is selfdev, its test, and the runner")
check(all(os.path.isfile(os.path.join(ROOT, r)) for r in selfdev.DEPLOY_FILES),
      "every file in the laptop copy set is in this tree")
check("llm.py" not in selfdev.DEPLOY_FILES and "config.py" not in selfdev.DEPLOY_FILES,
      "llm.py and config.py are not in the copy set")

# --- paths a patch must not be able to touch (the gate, or anywhere outside the OS package) ---
applied, probs, backups, _new = selfdev.apply_live(
    [{"path": "src/rootfs/usr/lib/llmos/llmos/../../../../etc/passwd", "search": "root", "replace": "nope"}])
check(applied == 0 and backups == {} and any("escapes" in p for p in probs),
      "a path with .. is not applied")
applied, probs, backups, _new = selfdev.apply_live([{"path": "/etc/passwd", "search": "a", "replace": "b"}])
check(applied == 0 and backups == {} and any("limited to the OS package" in p for p in probs),
      "an absolute path is not applied")
applied, probs, _b, _new = selfdev.apply_live(
    [{"path": "tools/test-selfdev.py", "search": "seatbelt", "replace": "no belt"}])
check(applied == 0 and any("test gate" in p for p in probs), "a patch cannot edit a test file")
applied, probs, _b, _new = selfdev.apply_live(
    [{"path": "tools/run-host-tests.sh", "search": "bash", "replace": "sh"}])
check(applied == 0 and any("test gate" in p for p in probs), "a patch cannot edit the test runner")
applied, probs, _b, _new = selfdev.apply_live(
    [{"path": "tools/selfdev.py", "search": "seatbelt", "replace": "no belt"}])
check(applied == 0 and any("limited to the OS package" in p for p in probs),
      "a patch cannot edit the loop itself")

# --- apply to a real package file transiently, then restore puts it back byte-for-byte ---
rel = "src/rootfs/usr/lib/llmos/llmos/_selfdev_probe.py"
full = os.path.join(ROOT, rel)
original = "alpha\nbeta\nbeta\n"
open(full, "w", encoding="utf-8").write(original)
try:
    applied, probs, backups, newtext = selfdev.apply_live([{"path": rel, "search": "alpha", "replace": "ALPHA"}])
    check(applied == 1 and open(full, encoding="utf-8").read().startswith("ALPHA"),
          "applies a matching edit to a file in the OS package")
    check(original in backups.values(), "it backs up the original first")
    check(os.path.isfile(os.path.join(selfdev.JOURNAL, "manifest.json")),
          "the original is journaled before the live file is changed")
    selfdev.restore(backups)
    check(open(full, encoding="utf-8").read() == original, "restore() puts the file back exactly as it was")
    check(not os.path.isdir(selfdev.JOURNAL), "a successful restore drops the journal")
    _, p2, _, _ = selfdev.apply_live([{"path": rel, "search": "beta", "replace": "B"}])
    selfdev.restore({rel: original})
    check(p2 and "unique" in p2[0], "rejects an edit whose SEARCH text is not unique")
    open(full, "w", encoding="utf-8").write(original)
    applied, probs, backups, _new = selfdev.apply_live(
        [{"path": rel, "whole": True, "replace": "# kept\ndef fetch():\n    return 2\n", "search": ""}])
    check(applied == 1 and "return 2" in open(full, encoding="utf-8").read(),
          "a whole-file reply replaces the package file")
    selfdev.restore(backups)
    check(open(full, encoding="utf-8").read() == original, "restore() puts a whole-file edit back")
    _, p3, _, _ = selfdev.apply_live(
        [{"path": "src/rootfs/usr/lib/llmos/llmos/_selfdev_missing.py", "search": "x", "replace": "y"}])
    check(p3 and "no such file" in p3[0], "rejects an edit to a missing file")
    # one forbidden hunk rejects the whole patch, including a hunk that would otherwise apply
    open(full, "w", encoding="utf-8").write(original)
    applied, probs, backups, _new = selfdev.apply_live([
        {"path": rel, "search": "alpha", "replace": "ALPHA"},
        {"path": "tools/test-selfdev.py", "search": "seatbelt", "replace": "no belt"}])
    check(applied == 0 and open(full, encoding="utf-8").read() == original and backups == {},
          "a test-file hunk rejects the whole patch, and the package file stays untouched")
finally:
    selfdev.journal_clear()
    selfdev._ACTIVE["backups"] = None
    if os.path.isfile(full):
        os.remove(full)

# --- the seatbelt, by static analysis of the source ---
src = open(os.path.join(HERE, "selfdev.py"), encoding="utf-8").read()
tree = ast.parse(src)
funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
do_task_src = ast.get_source_segment(src, funcs["do_task"])
check("ota" not in do_task_src and "publish" not in do_task_src, "do_task never ships (no OTA / publish in it)")
check("finally:" in do_task_src and "restore(backups)" in do_task_src,
      "do_task always restores the live source after the run (edited only transiently)")
check("if ran and not new_fails:" in do_task_src and 'json.dump' in do_task_src,
      "a change is staged only when the suite actually RAN and adds no new failures beyond baseline")
rt = ast.get_source_segment(src, funcs["run_tests"])
fs = ast.get_source_segment(src, funcs["_fail_set"])
check('l.startswith("FAIL ")' in fs and "_fail_set" in rt,
      "run_tests reports exactly which test files FAILED (for the baseline comparison)")
check(selfdev._fail_set([
    "FAIL /workspace/Support files/tools/test-a.py",
    "FAIL /workspace/Support files/tools/test-b.py",
    "host suites: 2 run, 2 failed"]) == {
        "/workspace/Support files/tools/test-a.py",
        "/workspace/Support files/tools/test-b.py"},
      "a FAIL path with spaces stays one test file, so a second failure is not hidden by the baseline")
check('host suites:' in rt and 'ran = ' in rt, "run_tests detects whether the suite ACTUALLY ran (a real N-run summary), not just absence of FAIL lines")
check('"bash"' in rt, "the suite is run with bash (its arrays break under busybox ash -> a silent no-run)")
bf = ast.get_source_segment(src, funcs["baseline_fails"])
check("if not ran:" in bf and "raise RuntimeError" in bf, "if the suite can't run at all, the loop refuses to stage anything untested")
ap_src = ast.get_source_segment(src, funcs["apply_staged"])
check("def apply_staged" in src and 'get("files"' in ap_src and "base_hashes" in ap_src and "_sha256" in ap_src,
      "writing the tested change is a separate step, and it refuses when the file changed since staging")
check("Never weaken a safety check" in src, "the model is told never to weaken a safeguard")
check("_is_live_install" in src and "REFUSING" in src and 'gate == "full" and _is_live_install()' in do_task_src,
      "the full gate still REFUSES to run on a live install; the light gate is not inside that refusal")
check("config.cloud()" in src and "cloud_chat" in src, "the loop uses the configured online coder when there is one")
check("worktree" not in src, "no leftover git-worktree path (the repo root is the parent dir; that approach was wrong)")
check(("agent" + ".py escalation") not in src and "does not escalate" in src,
      "the docstring does not claim this loop escalates on refusal")
check("TimeoutExpired" in rt, "a suite timeout is caught (it must not escape the gate)")
check('if not ran and "timed out" in tail' in do_task_src,
      "a timed-out suite stops the loop and is not staged")
check("baseline_fails(sel, limited=(gate == \"light\"))" in do_task_src
      and "run_tests(sel, limited=(gate == \"light\"))" in do_task_src,
      "the light baseline and the patched run use the same test selection")
check("journal_save" in ast.get_source_segment(src, funcs["apply_live"])
      and "journal_recover()" in ast.get_source_segment(src, funcs["main"]),
      "originals are journaled before the write, and the next start restores them")
sh = open(os.path.join(HERE, "run-host-tests.sh"), encoding="utf-8").read()
_runner_caps = "LLMOS_TEST_TIMEOUT" in sh
check(_runner_caps, "tools/run-host-tests.sh from this tree honors LLMOS_TEST_TIMEOUT; copy it with selfdev.py")


def _pkg(mod):
    """A package path. Built so this file does not contain a '<module>.py' literal the light index would treat
    as a real reference (that would make an untested module look tested)."""
    return "src/rootfs/usr/lib/llmos/llmos/" + mod + ".py"


# --- light gate: import/read mapping, core subset, refuse when the mapping cannot tell ---
selfdev._INDEX = None
sel, info = selfdev.select_light_tests([{"path": _pkg("web")}])
check(sel is not None and "tools/test-web-search.py" in sel, "the web module selects the test that imports it")
check(sel is not None and "tools/test-home-brain.py" in sel,
      "the web module also selects a test that reads the source instead of importing it")
check(sel is not None and all(t in sel for t in selfdev.CORE_TESTS), "the light gate always adds the core subset")
check(sel is not None and len(sel) < 40, "a one-module light set stays far under the full suite (%s)" % (len(sel or [])))
sel_d, _info_d = selfdev.select_light_tests([{"path": _pkg("desk")}])
check(sel_d is not None and "tools/test-desk-power.py" in sel_d,
      "the desk module selects a test that only reads the source (it needs GTK, so it is not imported)")
check(sel_d is not None and len(sel_d) < 120,
      "even the desk module's light set is well under the full suite (%s)" % (len(sel_d or [])))
sel_c, info_c = selfdev.select_light_tests([{"path": _pkg("clip")}])
check(sel_c is None and "Nothing was staged" in (info_c or "") and "clip" in (info_c or ""),
      "a module no test imports or reads is not staged")
sel_u, _info_u = selfdev.select_light_tests([{"path": _pkg("web")}, {"path": _pkg("voice")}])
check(sel_u is not None and "tools/test-web-search.py" in sel_u and "tools/test-voice.py" in sel_u,
      "a patch that edits two modules runs the union of their tests")
check(all(os.path.isfile(os.path.join(ROOT, t)) for t in selfdev.CORE_TESTS), "every core test file exists")

# --- which gate runs where (explicit, and overridable) ---
real_live, real_low = selfdev._is_live_install, selfdev._low_memory
try:
    selfdev._is_live_install = lambda: False
    selfdev._low_memory = lambda: (False, "")
    check(selfdev.resolve_gate("auto")[0] == "full", "auto on a dev machine with memory is the full suite")
    check(selfdev.resolve_gate("light")[0] == "light", "--gate light overrides auto")
    selfdev._is_live_install = lambda: True
    gate, why = selfdev.resolve_gate("auto")
    check(gate == "light" and "live" in why, "auto on a live install picks the light gate and says why")
    check(selfdev.resolve_gate("full")[0] == "full", "--gate full is still requested on a live install (do_task refuses it)")
    selfdev._is_live_install = lambda: False
    selfdev._low_memory = lambda: (True, "MemAvailable is 512 MiB, under 2048 MiB")
    gate, why = selfdev.resolve_gate("auto")
    check(gate == "light" and "512" in why, "auto picks light when memory is low, and says the number")
    prev_int, prev_term = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
    selfdev._is_live_install = lambda: True
    try:
        rc = selfdev.do_task("do not call the model", "full")
    finally:
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)
    check(rc == 2, "do_task refuses the full gate on a live install before asking a model")
finally:
    selfdev._is_live_install = real_live
    selfdev._low_memory = real_low

# --- timeout kills the whole session, instead of raising ---
t0 = time.time()
_code, timed = selfdev._run_cmd(["bash", "-c", "sleep 30"], 1, os.environ, subprocess.DEVNULL)
check(timed is True and _code is None and time.time() - t0 < 15, "a suite timeout is caught and the process group is killed")

# --- resource limits actually apply to the test process ---
lim_out = os.path.join(ROOT, "run", "selfdev-limit-out.txt")
os.makedirs(os.path.dirname(lim_out), exist_ok=True)
lim_cmd = selfdev._with_limits([sys.executable, "-c",
    "import os,resource,subprocess; print(os.nice(0)); print(resource.getrlimit(resource.RLIMIT_AS)[0]); "
    "print(subprocess.check_output(['ionice','-p',str(os.getpid())], text=True).strip())"])
with open(lim_out, "w", encoding="utf-8") as fh:
    lim_rc, lim_timed = selfdev._run_cmd(lim_cmd, 30, os.environ, fh)
lim_text = open(lim_out, encoding="utf-8").read().splitlines()
os.remove(lim_out)
check(not lim_timed and lim_rc == 0 and lim_text and lim_text[0].strip() == "19",
      "the light gate nices the suite to 19 (%s)" % (lim_text[:1],))
check(len(lim_text) >= 2 and lim_text[1].strip() == str(selfdev.DEFAULT_AS_BYTES),
      "the light gate caps address space at 1 GiB")
if selfdev._ionice_ok():
    check(any("idle" in line for line in lim_text), "the light gate puts the suite in the idle I/O class")
os.environ["LLMOS_SELFDEV_AS_BYTES"] = str(64 * 1024 * 1024)
try:
    tiny = selfdev._with_limits([sys.executable, "-c", "b=bytearray(80_000_000)"])
    tiny_rc, tiny_timed = selfdev._run_cmd(tiny, 30, dict(os.environ), subprocess.DEVNULL)
finally:
    os.environ.pop("LLMOS_SELFDEV_AS_BYTES", None)
check(tiny_rc not in (0, None) and tiny_timed is False, "a test that allocates past the cap dies instead of wedging the machine")

# --- per-test timeout in the runner ---
# The 2026-10-23 runner has no LLMOS_TEST_TIMEOUT, so this probe must not be started against it:
# the sleep runs until subprocess.run's own 20s timeout and that exception used to abort the suite.
if _runner_caps:
    sleep_py = "/tmp/llmos-selfdev-sleep-probe.py"
    open(sleep_py, "w", encoding="utf-8").write("import time\ntime.sleep(30)\n")
    try:
        env = dict(os.environ)
        env["LLMOS_TEST_TIMEOUT"] = "1"
        t0 = time.time()
        try:
            p = subprocess.run(["bash", os.path.join(HERE, "run-host-tests.sh"), sleep_py],
                               cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            p = None
        dt = time.time() - t0
        check(p is not None and p.returncode != 0 and "FAIL" in p.stdout and "1 run" in p.stdout and dt < 15,
              "LLMOS_TEST_TIMEOUT stops a stuck test (%.1fs)" % dt)
    finally:
        if os.path.isfile(sleep_py):
            os.remove(sleep_py)
else:
    check(False, "skipped the live timeout probe; copy tools/run-host-tests.sh with selfdev.py")

# --- journal survives kill -9; the next start puts the file back ---
# --- Ctrl-C restores before exiting ---
# --- --apply refuses when the file changed, and writes when the hash matches ---
# --- a symlink inside the package that points outside is not a back door ---
open(full, "w", encoding="utf-8").write("ORIGINAL\n")
ready = os.path.join(ROOT, "run", "selfdev-ready.txt")
if os.path.isfile(ready):
    os.remove(ready)
sig_child = (
    "import os, sys, time\n"
    "sys.path.insert(0, %r)\n"
    "import selfdev\n"
    "selfdev._install_signals()\n"
    "applied, probs, backups, newtext = selfdev.apply_live(["
    "{\"path\": %r, \"search\": \"ORIGINAL\", \"replace\": \"CHANGED\"}])\n"
    "open(%r, 'w').write('ready' if applied == 1 else repr(probs))\n"
    "time.sleep(60)\n"
) % (HERE, rel, ready)
kill_child = (
    "import os, sys\n"
    "sys.path.insert(0, %r)\n"
    "import selfdev\n"
    "applied, probs, backups, newtext = selfdev.apply_live(["
    "{\"path\": %r, \"search\": \"ORIGINAL\", \"replace\": \"CHANGED\"}])\n"
    "sys.exit(0 if applied == 1 else 3)\n"
) % (HERE, rel)
outside = tempfile.NamedTemporaryFile(prefix="llmos-selfdev-out-", delete=False)
outside.write(b"SAFE\n")
outside.close()
link = os.path.join(selfdev.PKG, "_selfdev_link.py")
staged_json = os.path.join(selfdev.STAGE, "staged.json")
staged_diff = os.path.join(selfdev.STAGE, "staged.diff")
saved_json = saved_diff = None
try:
    # Ctrl-C
    open(full, "w", encoding="utf-8").write("ORIGINAL\n")
    proc = subprocess.Popen([sys.executable, "-c", sig_child])
    for _i in range(50):
        if os.path.isfile(ready):
            break
        time.sleep(0.1)
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)
    check(open(full, encoding="utf-8").read() == "ORIGINAL\n", "Ctrl-C puts the live file back")
    check(not os.path.isfile(os.path.join(selfdev.JOURNAL, "manifest.json")), "Ctrl-C drops the journal after restoring")

    # kill -9: the handler never runs; the next start reads the journal
    selfdev.journal_clear()
    open(full, "w", encoding="utf-8").write("ORIGINAL\n")
    # The child must die without running its own cleanup. os._exit skips that; the parent then recovers.
    kill_child = kill_child.replace(
        "sys.exit(0 if applied == 1 else 3)\n",
        "import os as _os\n_os.kill(_os.getpid(), 9)\n")
    proc = subprocess.run([sys.executable, "-c", kill_child], capture_output=True, text=True)
    check(open(full, encoding="utf-8").read() == "CHANGED\n",
          "a killed run leaves the edit in place (stderr %s)" % (proc.stderr[-200:],))
    got = selfdev.journal_recover()
    check(open(full, encoding="utf-8").read() == "ORIGINAL\n" and any(rel in g for g in got),
          "the next start restores journaled originals (%s)" % (got,))
    check(not os.path.isdir(selfdev.JOURNAL), "recovery removes the journal")

    # symlink escape
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(outside.name, link)
    link_rel = "src/rootfs/usr/lib/llmos/llmos/_selfdev_link.py"
    applied, probs, backups, _new = selfdev.apply_live(
        [{"path": link_rel, "search": "SAFE", "replace": "PWNED"}])
    check(applied == 0 and open(outside.name, encoding="utf-8").read() == "SAFE\n",
          "a symlink that points outside the package is not written (%s)" % (probs[:1],))

    # --apply hash check. Preserve a real staged change if one is sitting in the tree.
    if os.path.isfile(staged_json):
        saved_json = open(staged_json, encoding="utf-8").read()
    if os.path.isfile(staged_diff):
        saved_diff = open(staged_diff, encoding="utf-8").read()
    os.makedirs(selfdev.STAGE, exist_ok=True)
    open(full, "w", encoding="utf-8").write("ORIGINAL\n")
    base_hash = selfdev._sha256("ORIGINAL\n")
    json.dump({"task": "probe", "when": "test", "tests": "host suites: 1 run, 0 failed", "gate": "light",
               "files": {rel: "NEW\n"}, "base_hashes": {rel: base_hash}},
              open(staged_json, "w", encoding="utf-8"))
    open(full, "w", encoding="utf-8").write("OTHER\n")
    rc = selfdev.apply_staged()
    check(rc != 0 and open(full, encoding="utf-8").read() == "OTHER\n",
          "--apply refuses when the file changed since staging")
    open(full, "w", encoding="utf-8").write("ORIGINAL\n")
    rc = selfdev.apply_staged()
    check(rc == 0 and open(full, encoding="utf-8").read() == "NEW\n",
          "--apply writes the staged file when the base hash still matches")
    json.dump({"task": "probe", "when": "test", "tests": "x", "files": {rel: "NEW\n"}},
              open(staged_json, "w", encoding="utf-8"))
    open(full, "w", encoding="utf-8").write("ORIGINAL\n")
    rc = selfdev.apply_staged()
    check(rc != 0 and open(full, encoding="utf-8").read() == "ORIGINAL\n",
          "--apply refuses a staged change that has no base hashes")
finally:
    selfdev.journal_clear()
    selfdev._ACTIVE["backups"] = None
    if os.path.isfile(full):
        os.remove(full)
    if os.path.lexists(link):
        os.remove(link)
    if os.path.isfile(outside.name):
        os.remove(outside.name)
    if os.path.isfile(ready):
        os.remove(ready)
    if saved_json is None:
        if os.path.isfile(staged_json):
            os.remove(staged_json)
    else:
        open(staged_json, "w", encoding="utf-8").write(saved_json)
    if saved_diff is None:
        if os.path.isfile(staged_diff):
            os.remove(staged_diff)
    else:
        open(staged_diff, "w", encoding="utf-8").write(saved_diff)

# --- local-only backend and owner-invoked install / verify / rollback ---
# The model is a loopback HTTP fixture. The runtime tree is a scratch directory, never /usr/lib/llmos.
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_local_saved = {
    "stage": selfdev.STAGE, "journal": selfdev.JOURNAL, "rounds": selfdev.MAX_ROUNDS,
    "baselines": dict(selfdev._BASELINES), "calls": dict(selfdev._CALLS),
    "llama": os.environ.get("LLMOS_LLAMA_URL"), "root": os.environ.get("LLMOS_SELFDEV_INSTALL_ROOT"),
}
_local_signals = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))


def _local_edit(rel):
    return ("=== FILE: " + rel + "\n<<<<<<< SEARCH\nVALUE = 1\n=======\nVALUE = 2\n>>>>>>> REPLACE\n")


class _ScriptedModel:
    """OpenAI-style SSE on 127.0.0.1. Replies are consumed in order."""

    def __init__(self):
        self.replies = []
        self.hits = []
        self.httpd = None

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                owner.hits.append(self.path)
                body = owner.replies.pop(0) if owner.replies else "no"
                chunk = json.dumps({"choices": [{"delta": {"content": body}}]})
                raw = ("data: " + chunk + "\n\ndata: [DONE]\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, fmt, *args):
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


_mod = "_selfdev_local"
_rel = "src/rootfs/usr/lib/llmos/llmos/" + _mod + ".py"
_full = os.path.join(ROOT, _rel)
_orig_checkout = "# KEEP\nVALUE = 1\n"
_prior_runtime = "OLD = 0\n"
_local_tmp = tempfile.mkdtemp(prefix="llmos-selfdev-local-")
_install_root = os.path.join(_local_tmp, "runtime")
_stage_dir = os.path.join(_local_tmp, "stage")
os.makedirs(os.path.join(_install_root, "llmos"), exist_ok=True)
os.makedirs(_stage_dir, exist_ok=True)
_runtime_file = os.path.join(_install_root, "llmos", _mod + ".py")
_sentinel = os.path.join(_install_root, "llmos", "untouched.py")
open(_sentinel, "w", encoding="utf-8").write("SENTINEL = 1\n")
_keep_fix = os.path.join(_local_tmp, "check_keep.py")
open(_keep_fix, "w", encoding="utf-8").write(
    "import ast\np = %r\ntext = open(p, encoding='utf-8').read()\nast.parse(text)\n"
    "if 'KEEP' not in text:\n    raise SystemExit('missing KEEP')\n" % _full)
_fail_fix = os.path.join(_local_tmp, "check_fail.py")
open(_fail_fix, "w", encoding="utf-8").write(
    "p = %r\ntext = open(p, encoding='utf-8').read()\n"
    "if 'VALUE = 2' in text:\n    raise SystemExit(1)\n" % _full)
_real_select = selfdev.select_light_tests
_real_run = selfdev.run_tests
_real_verify = selfdev.verify_runtime
_model = _ScriptedModel()
_llm_mod = None
_cfg_mod = None
_real_cloud = _real_cloud_chat = None
try:
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    selfdev.STAGE = _stage_dir
    selfdev.JOURNAL = os.path.join(_stage_dir, "journal")
    os.environ["LLMOS_SELFDEV_INSTALL_ROOT"] = _install_root
    selfdev.MAX_ROUNDS = 1
    selfdev._BASELINES.clear()
    selfdev._CALLS["cloud"] = 0
    selfdev._CALLS["local"] = 0

    # direct refusals: nothing is written when the stage is not a tested local artifact
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    base_hash = selfdev._sha256(_orig_checkout)
    good = "# KEEP\nVALUE = 2\n"
    good_hash = selfdev._sha256(good)
    meta_ok = {"files": {_rel: good}, "artifact_hashes": {_rel: good_hash},
               "base_hashes": {_rel: base_hash}, "ran": True, "new_fails": [], "timed_out": False,
               "backend": "local", "gate": "light", "tests": "host suites: 1 run, 0 failed"}

    def _refuse(meta, label):
        before = open(_runtime_file, encoding="utf-8").read()
        rc = selfdev.install_verified(meta, {})
        after = open(_runtime_file, encoding="utf-8").read()
        ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
        check(rc != 0 and after == before and ev.get("accepted") is False and ev.get("installed") is False, label)

    bad = dict(meta_ok)
    bad["tests"] = "host suites: 0 run, 0 failed"
    _refuse(bad, "zero tests are not installed")
    bad = dict(meta_ok)
    bad["ran"] = False
    _refuse(bad, "a stage whose suite did not run is not installed")
    bad = dict(meta_ok)
    bad["new_fails"] = ["tools/test-x.py"]
    _refuse(bad, "a stage with failing tests is not installed")
    bad = dict(meta_ok)
    bad["timed_out"] = True
    _refuse(bad, "a timed-out stage is not installed")
    bad = dict(meta_ok)
    bad["artifact_hashes"] = {_rel: "0" * 64}
    _refuse(bad, "a stage whose artifact hash does not match its bytes is not installed")
    bad = dict(meta_ok)
    bad["backend"] = "auto"
    _refuse(bad, "a stage that was not produced by the local backend is not installed")
    bad = dict(meta_ok)
    bad["base_hashes"] = {_rel: selfdev._sha256("stale\n")}
    _refuse(bad, "a stale stage whose checkout changed since the test is not installed")
    _refuse("not json", "a malformed stage is not installed")
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    problems, _hashes = selfdev.verify_runtime({_rel: good})
    check(problems and "do not match" in problems[0], "a read-back that is not the artifact fails verification")
    open(_runtime_file, "w", encoding="utf-8").write("def (\n")
    problems, hashes = selfdev.verify_runtime({_rel: "def (\n"})
    check(problems and hashes.get(_rel) == selfdev._sha256("def (\n") and "compile" in problems[0],
          "installed bytes that hash correctly but do not compile fail verification")
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)

    # unrelated file in the runtime tree is not part of the artifact
    check(open(_sentinel, encoding="utf-8").read() == "SENTINEL = 1\n", "sentinel exists before install")

    # journal: no commit means the next start puts the previous bytes back; a commit whose
    # bytes still match is left alone; a commit whose bytes were corrupted is rolled back
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    entries = {_rel: {"runtime": _prior_runtime, "checkout": _orig_checkout, "had_runtime": True}}
    selfdev.install_journal_save(entries, {_rel: good_hash})
    open(_runtime_file, "w", encoding="utf-8").write(good)
    open(_full, "w", encoding="utf-8").write(good)
    got = selfdev.install_journal_recover()
    check(open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and open(_full, encoding="utf-8").read() == _orig_checkout and _rel in got,
          "an uncommitted install journal restores runtime and checkout (%s)" % (got,))
    check(not os.path.isdir(selfdev.install_journal_dir()), "recovery removes the install journal")
    selfdev.install_journal_save(entries, {_rel: good_hash})
    open(_runtime_file, "w", encoding="utf-8").write(good)
    open(_full, "w", encoding="utf-8").write(good)
    selfdev._mark_install_commit({_rel: good_hash})
    check(selfdev.install_journal_recover() == [] and open(_runtime_file, encoding="utf-8").read() == good,
          "a committed install whose bytes match is not undone on restart")
    check(not os.path.isdir(selfdev.install_journal_dir()), "a finished install journal is dropped")
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    selfdev.install_journal_save(entries, {_rel: good_hash})
    open(_runtime_file, "w", encoding="utf-8").write(good)
    selfdev._mark_install_commit({_rel: good_hash})
    open(_runtime_file, "w", encoding="utf-8").write("OTHER = 3\n")
    got = selfdev.install_journal_recover()
    check(open(_runtime_file, encoding="utf-8").read() == _prior_runtime and _rel in got,
          "a commit whose runtime bytes no longer match is rolled back")

    # backend selection is independent of cloud config
    import llmos.config as _cfg_mod
    import llmos.llm as _llm_mod
    _real_cloud = _cfg_mod.cloud
    _real_cloud_chat = _llm_mod.cloud_chat
    _cloud_hits = []

    def _cloud_on():
        return {"provider": "x", "url": "https://example.invalid", "model": "m", "key": "k"}

    def _cloud_chat(*_a, **_k):
        _cloud_hits.append(1)
        return {"content": "CLOUD"}

    _cfg_mod.cloud = _cloud_on
    _llm_mod.cloud_chat = _cloud_chat

    class _FakeLLM:
        def __init__(self):
            self.cloud = 0
            self.local = 0

        def cloud_chat(self, *_a, **_k):
            self.cloud += 1
            return {"content": "CLOUD"}

        def chat(self, *_a, **_k):
            self.local += 1
            raise RuntimeError("local down")

    _fake = _FakeLLM()
    _real_llm = selfdev._llm
    selfdev._llm = lambda: _fake
    try:
        try:
            selfdev._chat([{"role": "user", "content": "hi"}], backend="local")
            _local_raised = False
        except RuntimeError:
            _local_raised = True
        check(_local_raised and _fake.cloud == 0 and _fake.local == 1,
              "local backend does not fall back to the online model when the on-device model fails")
        def _chat_ok(*_a, **_k):
            _fake.local += 1
            return {"content": "LOCAL"}

        _fake.chat = _chat_ok
        _auto = selfdev._chat([{"role": "user", "content": "hi"}], backend="auto")
        _loc = selfdev._chat([{"role": "user", "content": "hi"}], backend="local")
        check(_auto.get("content") == "CLOUD" and _fake.cloud == 1,
              "auto still uses the configured online model")
        check(_loc.get("content") == "LOCAL" and _fake.local == 2,
              "local ignores a configured online model and uses the on-device client")
    finally:
        selfdev._llm = _real_llm

    _url = _model.start()
    os.environ["LLMOS_LLAMA_URL"] = _url
    _local_fn = ast.get_source_segment(src, funcs["_chat_local"])
    check("cloud_chat" not in _local_fn and "config.cloud" not in _local_fn,
          "the local backend function neither reads cloud config nor calls the online model")
    check("input(" not in src, "the owner-invoked lifecycle does not ask for a confirmation")

    _called = {"propose": 0}

    def _boom_propose(*_a, **_k):
        _called["propose"] += 1
        raise AssertionError("model should not be asked")

    _real_propose = selfdev.propose
    selfdev.propose = _boom_propose
    try:
        rc = selfdev.do_task("do not generate", "full", backend="local", install=True)
    finally:
        selfdev.propose = _real_propose
    check(rc == 2 and _called["propose"] == 0, "local install refuses the full gate before asking a model")
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    check(_ev.get("accepted") is False and _ev.get("installed") is False,
          "refusing the full gate does not report an install")

    os.environ["LLMOS_SELFDEV_INSTALL_ROOT"] = os.path.realpath(selfdev.SRC)
    selfdev.propose = _boom_propose
    try:
        rc = selfdev.do_task("do not generate", "light", install=True)
    finally:
        selfdev.propose = _real_propose
        os.environ["LLMOS_SELFDEV_INSTALL_ROOT"] = _install_root
    check(rc == 2 and _called["propose"] == 0,
          "local install refuses when the install root is the dev checkout")

    def _use_select(paths):
        def _sel(_edits):
            return list(paths), "fixture"
        selfdev.select_light_tests = _sel

    def _run_lifecycle(reply, paths, install=True, gate="auto"):
        selfdev._BASELINES.clear()
        selfdev._CALLS["cloud"] = 0
        selfdev._CALLS["local"] = 0
        open(_full, "w", encoding="utf-8").write(_orig_checkout)
        open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
        open(os.path.join(_stage_dir, "staged.json"), "w", encoding="utf-8").write('{"task": "UNRELATED"}\n')
        _model.replies.append(reply)
        _use_select(paths)
        runs = []

        def _wrap(only=None, limited=False):
            runs.append((list(only) if only else None, bool(limited)))
            return _real_run(only, limited)

        selfdev.run_tests = _wrap
        rc = selfdev.do_task("edit " + _mod, gate, backend="local", install=install)
        selfdev.run_tests = _real_run
        selfdev.select_light_tests = _real_select
        return rc, runs

    rc, runs = _run_lifecycle(_local_edit(_rel), [_keep_fix], install=True, gate="auto")
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    _installed = open(_runtime_file, encoding="utf-8").read()
    check(rc == 0 and _ev.get("accepted") is True and _ev.get("ok") is True and _ev.get("installed") is True,
          "local install accepts only after runtime verification (%s)" % (_ev.get("reason"),))
    check(_ev.get("cloud_calls") == 0 and not _cloud_hits and _model.hits,
          "the install talked to the loopback model and not the online model (%s)" % (_model.hits[:1],))
    check(_installed == "# KEEP\nVALUE = 2\n" and _ev.get("runtime_hashes", {}).get(_rel) == selfdev._sha256(_installed)
          and _ev.get("artifact_hashes", {}).get(_rel) == selfdev._sha256(_installed),
          "the runtime file is the tested artifact, hash included")
    check(open(_full, encoding="utf-8").read() == _installed,
          "the checkout matches the installed artifact after verification")
    check(runs and all(limited and only == [_keep_fix] for only, limited in runs),
          "the install ran the bounded fixture, not the full suite (%s)" % (runs,))
    check("1 run" in open(os.path.join(_stage_dir, "tests.txt"), encoding="utf-8").read(),
          "the bounded test actually ran")
    check(open(_sentinel, encoding="utf-8").read() == "SENTINEL = 1\n",
          "an unrelated runtime file is left untouched")
    _prev = open(os.path.join(_stage_dir, "previous-staged.json"), encoding="utf-8").read()
    check("UNRELATED" in _prev, "the stage this install replaced is kept")
    _new_stage = json.load(open(os.path.join(_stage_dir, "staged.json"), encoding="utf-8"))
    check(_new_stage.get("backend") == "local" and _new_stage.get("gate") == "light" and _new_stage.get("ran") is True,
          "the staged record of the install names the local light run")

    rb = selfdev.rollback_installed()
    check(rb == 0 and open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and open(_full, encoding="utf-8").read() == _orig_checkout,
          "--rollback restores the previous runtime and checkout bytes")
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    check(_ev.get("phase") == "rollback" and _ev.get("accepted") is False and _ev.get("rolled_back") is True,
          "rollback evidence does not claim the artifact is still installed")
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    rb2 = selfdev.rollback_installed()
    check(rb2 != 0 and open(_runtime_file, encoding="utf-8").read() == _prior_runtime,
          "a second rollback refuses once the runtime is no longer the installed artifact")

    # failed read-back: the suite passes, then the installed bytes are not the artifact
    def _tamper(files):
        path, _err = selfdev.runtime_path(next(iter(files)))
        open(path, "w", encoding="utf-8").write(open(path, encoding="utf-8").read() + "\n# tamper\n")
        return _real_verify(files)

    selfdev.verify_runtime = _tamper
    try:
        rc, _runs = _run_lifecycle(_local_edit(_rel), [_keep_fix], install=True)
    finally:
        selfdev.verify_runtime = _real_verify
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    check(rc != 0 and _ev.get("accepted") is False and _ev.get("rolled_back") is True
          and open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and open(_full, encoding="utf-8").read() == _orig_checkout,
          "a failed runtime read-back rolls back and does not report success (%s)" % (_ev.get("reason"),))
    check(open(os.path.join(_stage_dir, "staged.json"), encoding="utf-8").read().strip().startswith("{")
          and "UNRELATED" in open(os.path.join(_stage_dir, "staged.json"), encoding="utf-8").read(),
          "a failed install puts the unrelated stage back")

    rc, _runs = _run_lifecycle(_local_edit(_rel), [_fail_fix], install=True)
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    check(rc != 0 and _ev.get("accepted") is False and open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and open(_full, encoding="utf-8").read() == _orig_checkout,
          "a failing bounded test does not install (%s)" % (_ev.get("reason"),))

    selfdev._BASELINES.clear()
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    open(os.path.join(_stage_dir, "staged.json"), "w", encoding="utf-8").write('{"task": "UNRELATED"}\n')
    _model.replies.append(_local_edit(_rel))
    _use_select([_keep_fix])
    _n = {"n": 0}

    def _rt_timeout(only=None, limited=False):
        _n["n"] += 1
        if _n["n"] == 1:
            return "host suites: 1 run, 0 failed", set(), True
        return "timed out after 5s", set(), False

    selfdev.run_tests = _rt_timeout
    rc = selfdev.do_task("edit " + _mod, "auto", backend="local", install=True)
    selfdev.run_tests = _real_run
    selfdev.select_light_tests = _real_select
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    check(rc != 0 and _ev.get("accepted") is False and open(_runtime_file, encoding="utf-8").read() == _prior_runtime,
          "a timed-out suite does not install (%s)" % (_ev.get("reason"),))
    check("UNRELATED" in open(os.path.join(_stage_dir, "staged.json"), encoding="utf-8").read(),
          "a timeout leaves the unrelated stage in place")

    selfdev._BASELINES.clear()
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    _model.replies.append(_local_edit(_rel))
    _use_select([_keep_fix])

    def _rt_zero(only=None, limited=False):
        return "host suites: 0 run, 0 failed", set(), False

    selfdev.run_tests = _rt_zero
    rc = selfdev.do_task("edit " + _mod, "auto", backend="local", install=True)
    selfdev.run_tests = _real_run
    selfdev.select_light_tests = _real_select
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    _why = (_ev.get("reason") or "").lower()
    check(rc != 0 and ("zero" in _why or "could not run" in _why or "did not run" in _why),
          "zero tests do not install (%s)" % (_ev.get("reason"),))
    check(_ev.get("accepted") is False and open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and open(_full, encoding="utf-8").read() == _orig_checkout,
          "zero tests leave runtime and checkout unchanged")

    selfdev._BASELINES.clear()
    _model.replies.append("I will not use the format")
    _use_select([_keep_fix])
    selfdev.run_tests = _real_run
    rc = selfdev.do_task("edit " + _mod, "auto", backend="local", install=True)
    selfdev.select_light_tests = _real_select
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    check(rc != 0 and _ev.get("accepted") is False and open(_runtime_file, encoding="utf-8").read() == _prior_runtime,
          "a malformed model reply does not install (%s)" % (_ev.get("reason"),))

    # stage-only local run still stops before the runtime tree
    selfdev._BASELINES.clear()
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    _model.replies.append(_local_edit(_rel))
    _use_select([_keep_fix])

    def _rt_pass(only=None, limited=False):
        return "host suites: 1 run, 0 failed", set(), True

    selfdev.run_tests = _rt_pass
    if os.path.isfile(os.path.join(_stage_dir, "evidence.json")):
        os.remove(os.path.join(_stage_dir, "evidence.json"))
    rc = selfdev.do_task("edit " + _mod, "light", backend="local", install=False)
    selfdev.run_tests = _real_run
    selfdev.select_light_tests = _real_select
    check(rc == 0 and open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and not os.path.isfile(os.path.join(_stage_dir, "evidence.json")),
          "--backend local without --install stages and does not touch the runtime tree")
    _staged_only = json.load(open(os.path.join(_stage_dir, "staged.json"), encoding="utf-8"))
    check(_staged_only.get("backend") == "local" and selfdev._CALLS.get("cloud") == 0,
          "the stage-only local run recorded the local backend and made no cloud call")

    # a module no test covers is not installed, and the full suite is not started
    selfdev._BASELINES.clear()
    _suite_calls = {"n": 0}

    def _count_run(*_a, **_k):
        _suite_calls["n"] += 1
        return "host suites: 1 run, 0 failed", set(), True

    selfdev.run_tests = _count_run
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    _clip = _pkg("clip")
    _model.replies.append("=== FILE: " + _clip + "\n<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n")
    rc = selfdev.do_task("edit clip", "auto", backend="local", install=True)
    selfdev.run_tests = _real_run
    _ev = json.load(open(os.path.join(_stage_dir, "evidence.json"), encoding="utf-8"))
    check(rc == 2 and _suite_calls["n"] == 0 and _ev.get("accepted") is False and "Nothing was staged" in (_ev.get("reason") or ""),
          "when the light gate cannot name tests, local install does not fall through to the full suite")

    # Ctrl-C and kill -9 during an install
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    _ready = os.path.join(_local_tmp, "ready.txt")
    if os.path.isfile(_ready):
        os.remove(_ready)
    _sig = (
        "import os, sys, time\n"
        "os.environ['LLMOS_SELFDEV_STAGE'] = %r\n"
        "os.environ['LLMOS_SELFDEV_INSTALL_ROOT'] = %r\n"
        "sys.path.insert(0, %r)\n"
        "import selfdev\n"
        "selfdev._install_signals()\n"
        "rel = os.environ['PROBE_REL']\n"
        "prior_rt = open(os.environ['PRIOR_RT'], encoding='utf-8').read()\n"
        "prior_co = open(os.environ['PRIOR_CO'], encoding='utf-8').read()\n"
        "selfdev.install_journal_save({rel: {'runtime': prior_rt, 'checkout': prior_co, 'had_runtime': True}}, {})\n"
        "rt, err = selfdev.runtime_path(rel)\n"
        "open(rt, 'w', encoding='utf-8').write('NEW = 9\\n')\n"
        "open(os.environ['PROBE_FULL'], 'w', encoding='utf-8').write('NEW = 9\\n')\n"
        "open(%r, 'w', encoding='utf-8').write('ready')\n"
        "time.sleep(60)\n"
    ) % (_stage_dir, _install_root, HERE, _ready)
    _prior_rt_path = os.path.join(_local_tmp, "prior-rt.py")
    _prior_co_path = os.path.join(_local_tmp, "prior-co.py")
    open(_prior_rt_path, "w", encoding="utf-8").write(_prior_runtime)
    open(_prior_co_path, "w", encoding="utf-8").write(_orig_checkout)
    _env = dict(os.environ)
    _env["PROBE_REL"] = _rel
    _env["PROBE_FULL"] = _full
    _env["PRIOR_RT"] = _prior_rt_path
    _env["PRIOR_CO"] = _prior_co_path
    _env["LLMOS_SELFDEV_STAGE"] = _stage_dir
    _env["LLMOS_SELFDEV_INSTALL_ROOT"] = _install_root
    proc = subprocess.Popen([sys.executable, "-c", _sig], env=_env)
    for _i in range(50):
        if os.path.isfile(_ready):
            break
        time.sleep(0.1)
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)
    check(open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and open(_full, encoding="utf-8").read() == _orig_checkout,
          "Ctrl-C during install restores the runtime and the checkout")

    open(_runtime_file, "w", encoding="utf-8").write(_prior_runtime)
    open(_full, "w", encoding="utf-8").write(_orig_checkout)
    _kill = (
        "import os, sys\n"
        "os.environ['LLMOS_SELFDEV_STAGE'] = %r\n"
        "os.environ['LLMOS_SELFDEV_INSTALL_ROOT'] = %r\n"
        "sys.path.insert(0, %r)\n"
        "import selfdev\n"
        "rel = os.environ['PROBE_REL']\n"
        "prior_rt = open(os.environ['PRIOR_RT'], encoding='utf-8').read()\n"
        "prior_co = open(os.environ['PRIOR_CO'], encoding='utf-8').read()\n"
        "selfdev.install_journal_save({rel: {'runtime': prior_rt, 'checkout': prior_co, 'had_runtime': True}}, {})\n"
        "rt, err = selfdev.runtime_path(rel)\n"
        "open(rt, 'w', encoding='utf-8').write('NEW = 9\\n')\n"
        "open(os.environ['PROBE_FULL'], 'w', encoding='utf-8').write('NEW = 9\\n')\n"
        "os.kill(os.getpid(), 9)\n"
    ) % (_stage_dir, _install_root, HERE)
    subprocess.run([sys.executable, "-c", _kill], env=_env, capture_output=True, text=True)
    check(open(_runtime_file, encoding="utf-8").read() == "NEW = 9\n",
          "kill -9 leaves the install in place so the next start can roll it back")
    restarted = subprocess.run([sys.executable, os.path.join(HERE, "selfdev.py")], env=_env,
                               capture_output=True, text=True)
    check(restarted.returncode != 0 and open(_runtime_file, encoding="utf-8").read() == _prior_runtime
          and open(_full, encoding="utf-8").read() == _orig_checkout,
          "the next start rolls back an install killed mid-write (rc %s)" % (restarted.returncode,))
    _ev_path = os.path.join(_stage_dir, "evidence.json")
    if os.path.isfile(_ev_path):
        _ev = json.load(open(_ev_path, encoding="utf-8"))
        check(_ev.get("accepted") is not True, "restart recovery does not report the killed install as accepted")

    help_proc = subprocess.run([sys.executable, os.path.join(HERE, "selfdev.py"), "--help"],
                               capture_output=True, text=True)
    help_text = help_proc.stdout
    check(help_proc.returncode == 0 and "--local-install" in help_text and "--backend" in help_text
          and "--rollback" in help_text, "help shows the local install lifecycle")
    bare = subprocess.run([sys.executable, os.path.join(HERE, "selfdev.py"), "--local-install"],
                          capture_output=True, text=True)
    check(bare.returncode != 0 and "does not install an existing stage" in (bare.stdout + bare.stderr),
          "--local-install without a task does not install whatever stage is sitting there")
finally:
    selfdev.select_light_tests = _real_select
    selfdev.run_tests = _real_run
    selfdev.verify_runtime = _real_verify
    selfdev.journal_clear()
    selfdev.install_journal_clear()
    selfdev.MAX_ROUNDS = _local_saved["rounds"]
    selfdev._BASELINES.clear()
    selfdev._BASELINES.update(_local_saved["baselines"])
    selfdev._CALLS.clear()
    selfdev._CALLS.update(_local_saved["calls"])
    selfdev.STAGE = _local_saved["stage"]
    selfdev.JOURNAL = _local_saved["journal"]
    selfdev._ACTIVE["backups"] = None
    if _model.httpd is not None:
        _model.stop()
    if _cfg_mod is not None and _real_cloud is not None:
        _cfg_mod.cloud = _real_cloud
    if _llm_mod is not None and _real_cloud_chat is not None:
        _llm_mod.cloud_chat = _real_cloud_chat
    if _local_saved["llama"] is None:
        os.environ.pop("LLMOS_LLAMA_URL", None)
    else:
        os.environ["LLMOS_LLAMA_URL"] = _local_saved["llama"]
    if _local_saved["root"] is None:
        os.environ.pop("LLMOS_SELFDEV_INSTALL_ROOT", None)
    else:
        os.environ["LLMOS_SELFDEV_INSTALL_ROOT"] = _local_saved["root"]
    signal.signal(signal.SIGINT, _local_signals[0])
    signal.signal(signal.SIGTERM, _local_signals[1])
    if os.path.isfile(_full):
        os.remove(_full)
    shutil_mod = __import__("shutil")
    shutil_mod.rmtree(_local_tmp, ignore_errors=True)

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
