#!/usr/bin/env python3
"""The self-development loop (tools/selfdev.py) keeps its seatbelt. It parses a model's edits, applies them to the real
files ONLY while the test gate runs and always restores them (including from a journal if the process is killed),
rejects edits that don't match or that escape the OS package, stages a tested change rather than shipping it, and
NEVER ships on its own (applying, and shipping via OTA, are separate human steps). The light gate runs only the
tests that touch the changed modules, plus a core subset. Does NOT run the full suite (do_task does).
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
check("LLMOS_TEST_TIMEOUT" in sh, "the runner honors a per-test timeout from the environment")


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
sleep_py = "/tmp/llmos-selfdev-sleep-probe.py"
open(sleep_py, "w", encoding="utf-8").write("import time\ntime.sleep(30)\n")
try:
    env = dict(os.environ)
    env["LLMOS_TEST_TIMEOUT"] = "1"
    t0 = time.time()
    p = subprocess.run(["bash", os.path.join(HERE, "run-host-tests.sh"), sleep_py],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    dt = time.time() - t0
    check(p.returncode != 0 and "FAIL" in p.stdout and "1 run" in p.stdout and dt < 15,
          "LLMOS_TEST_TIMEOUT stops a stuck test (%.1fs)" % dt)
finally:
    if os.path.isfile(sleep_py):
        os.remove(sleep_py)

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

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all good")
