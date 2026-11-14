#!/usr/bin/env python3
"""The self-improvement loop.

    tools/selfloop.py --once              # one improvement, then queue or discard
    tools/selfloop.py --status
    tools/selfloop.py --stop              # kill switch
    tools/selfloop.py --resume
    tools/selfloop.py --ship-approved     # the owner says yes: tests > log && install
    tools/selfloop.py --install-local ID  # on-device: install one queued change (used after &&)

Dev-machine mode (mode "dev", the default) checks out a separate branch, asks a model to
implement there, and runs the light gate. The running tree is not edited. A live install is
refused in this mode: ship the result to it with OTA.

On-device mode (mode "device") is the laptop. It copies /usr/lib/llmos to a staging directory,
asks the local model (loopback llama-server, or llama-cli on a local file — never a cloud API),
runs only a light capped test subset under nice, then installs through a signed update with the
same verify / backup / rollback path as OTA. A failed health check puts the previous files back.
It does not restart network services, and it does not restart the model server.

The model backend is selectable. "configured" keeps today's selfdev choice. "cloud" and "llama"
are those two existing clients. "local" is the loopback-only backend. On-device mode accepts
only "local".

A passing gate is queued while require_approval is true (the default). Publishing or installing
is the host tests, output redirected to a file, then &&, then the installer. A pipe is refused.
The full suite is not what this loop runs; it froze a 16 GB machine. Iterations are capped.

The kill switch (tools/selfloop.py --stop, or LLMOS_SELFLOOP=off, or /etc/llmos/selfloop-stop)
and the rate limit refuse a run before any checkout or staging copy is created.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                          # Support files/
SRC = os.path.join(ROOT, "src/rootfs/usr/lib/llmos")
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import selfdev  # noqa: E402
import selfloop_local  # noqa: E402
from llmos import selfloop_ctl  # noqa: E402


def assert_separate(dest, live):
    """The checkout must not be the tree that is running, and must not be the installed package."""
    dest_r = os.path.realpath(dest)
    live_r = os.path.realpath(live)
    if dest_r == live_r or dest_r.startswith(live_r + os.sep) or live_r.startswith(dest_r + os.sep):
        raise RuntimeError("refusing to edit the running tree; the checkout has to be a separate directory")
    if dest_r == "/usr/lib/llmos" or dest_r.startswith("/usr/lib/llmos/"):
        raise RuntimeError("refusing to edit the running install")
    return dest_r


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=check)


def make_checkout(repo, dest, branch, live):
    """A separate git checkout on its own branch. Returns (support_dir, kind)."""
    assert_separate(dest, live)
    if os.path.exists(dest):
        raise RuntimeError("the checkout path already exists")
    probe = _git(repo, "rev-parse", "--show-toplevel", check=False)
    if probe.returncode == 0:
        top = probe.stdout.strip()
        add = _git(top, "worktree", "add", "-b", branch, dest, "HEAD", check=False)
        if add.returncode != 0:
            raise RuntimeError("could not make a separate checkout: " + (add.stderr or add.stdout)[-300:])
        support = os.path.join(dest, "Support files") if os.path.isdir(os.path.join(dest, "Support files")) else dest
        if not os.path.isdir(os.path.join(support, "tools")):
            raise RuntimeError("the checkout has no tools directory")
        return support, "git", top
    # No git history: copy the tree. Still a different directory than the one that is running.
    shutil.copytree(live, dest, ignore=shutil.ignore_patterns("run", ".git", "__pycache__"))
    return dest, "copy", repo


def discard_checkout(dest, kind, repo, branch):
    if kind == "git" and repo:
        _git(repo, "worktree", "remove", "--force", dest, check=False)
        _git(repo, "branch", "-D", branch, check=False)
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
    elif dest and os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)


def commit_checkout(dest, message):
    _git(dest, "-c", "user.email=llmos-selfloop@localhost", "-c", "user.name=LLMOS selfloop", "add", "-A")
    status = _git(dest, "status", "--porcelain", check=False)
    if not status.stdout.strip():
        return False
    _git(dest, "-c", "user.email=llmos-selfloop@localhost", "-c", "user.name=LLMOS selfloop",
         "commit", "-m", message)
    return True


def tests_mentioning(basename):
    hits = []
    if not basename.endswith(".py"):
        return hits
    for name in sorted(os.listdir(selfdev.HERE)):
        if not (name.startswith("test-") and name.endswith(".py")):
            continue
        try:
            text = open(os.path.join(selfdev.HERE, name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if basename in text:
            hits.append("tools/" + name)
    return hits


def tests_for_changes(paths):
    """Light gate: tests that touch the changed package modules, plus the core subset.
    A tools-only change still runs the core and any test that names that file.
    Returns (paths, message) or (None, reason) when the mapping cannot tell."""
    pkg, extra = [], set()
    for raw in paths or []:
        norm = str(raw).replace("\\", "/")
        base = os.path.basename(norm)
        if "/llmos/" in "/" + norm and norm.endswith(".py") and not base.startswith("test-"):
            pkg.append(norm)
        extra.update(tests_mentioning(base))
    if pkg:
        sel, info = selfdev.select_light_tests([{"path": p} for p in pkg])
        if sel is None:
            return None, info
        chosen = set(sel)
    elif extra:
        chosen = set(selfdev.CORE_TESTS)
        info = "core tests plus tests that name the changed file"
    else:
        return None, "no host test reads these files, so the light gate cannot tell what would break. Nothing was queued."
    chosen.update(extra)
    missing = [t for t in sorted(chosen) if not os.path.isfile(os.path.join(selfdev.ROOT, t))]
    if missing:
        return None, "the light gate is missing " + ", ".join(missing) + ". Nothing was queued."
    return sorted(chosen), info


def gate_command(support, tests):
    """The light gate, niced. An empty list is refused: run-host-tests.sh with no arguments runs every suite,
    and that full run is what froze the 16 GB laptop."""
    if not tests:
        raise RuntimeError("refusing to run the full suite; the light gate needs an explicit test list")
    cmd = ["bash", os.path.join(support, "tools", "run-host-tests.sh"), *list(tests)]
    return selfdev._with_limits(cmd)


def run_light_gate(support, tests, timeout=None):
    """Run the light set under nice. Output goes to a file. The return code is the suite's."""
    try:
        cmd = gate_command(support, tests)
    except RuntimeError as e:
        return False, str(e)
    log = os.path.join(support, "run", "selfloop", "gate.txt")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    env = dict(os.environ)
    env["LLMOS_TEST_TIMEOUT"] = str(selfdev.LIGHT_TEST_TIMEOUT)
    limit = selfdev.LIGHT_TIMEOUT if timeout is None else timeout
    with open(log, "w", encoding="utf-8") as handle:
        proc = subprocess.Popen(cmd, cwd=support, stdout=handle, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
        try:
            proc.wait(timeout=limit)
            code, timed = proc.returncode, False
        except subprocess.TimeoutExpired:
            selfdev._kill_group(proc)
            code, timed = 1, True
    try:
        text = open(log, encoding="utf-8", errors="replace").read()
    except OSError:
        text = ""
    if timed:
        return False, f"timed out after {limit}s"
    fails = [ln for ln in text.splitlines() if ln.startswith("FAIL ")]
    import re
    m = re.search(r"host suites:\s*(\d+)\s*run", text)
    ran = bool(m) and int(m.group(1)) > 0
    return code == 0 and ran and not fails, (text[-400:] or "no output")


def default_implement(support, item):
    """selfdev, pointed at the checkout, so the running tree is never the one being edited."""
    cmd = [sys.executable, os.path.join(support, "tools", "selfdev.py"), "--gate", "light", item.get("title") or ""]
    proc = subprocess.run(cmd, cwd=support, capture_output=True, text=True)
    staged = os.path.join(support, "run", "selfdev", "staged.json")
    if proc.returncode != 0 or not os.path.isfile(staged):
        tail = (proc.stdout or proc.stderr or "no change was staged")[-500:]
        raise RuntimeError(tail)
    meta = json.load(open(staged, encoding="utf-8"))
    applied = subprocess.run([sys.executable, os.path.join(support, "tools", "selfdev.py"), "--apply"],
                             cwd=support, capture_output=True, text=True)
    if applied.returncode != 0:
        raise RuntimeError((applied.stdout or applied.stderr or "could not apply")[-400:])
    return {"changed": list((meta.get("files") or {})), "note": meta.get("tests", "")}


def run_ship(shell, support):
    selfloop_ctl.assert_gated(shell)
    proc = subprocess.run(["bash", "-c", shell], cwd=support)
    return proc.returncode


def _repo_of(live):
    probe = _git(live, "rev-parse", "--show-toplevel", check=False)
    if probe.returncode == 0:
        return probe.stdout.strip()
    parent = os.path.dirname(os.path.realpath(live))
    probe = _git(parent, "rev-parse", "--show-toplevel", check=False)
    return probe.stdout.strip() if probe.returncode == 0 else live


def _version_of(support):
    path = os.path.join(support, "src/rootfs/usr/lib/llmos/llmos/__init__.py")
    try:
        for line in open(path, encoding="utf-8"):
            if line.startswith('VERSION = "'):
                return line.split('"', 2)[1]
    except OSError:
        pass
    return "0"


def _iterations(cfg, enabled):
    """How many propose-and-test rounds this pass may take. One, unless a local/cloud/llama backend is driving."""
    if not enabled:
        return 1
    n = (cfg or {}).get("max_iterations", 3)
    if not isinstance(n, int) or isinstance(n, bool):
        return 3
    return min(8, max(1, n))


def resolve_worker(cfg, implement):
    """(worker, rounds). A passed-in worker is one round, so tests and the old path stay single-shot.
    configured keeps default_implement (selfdev). local, cloud, and llama use the bounded loop."""
    backend = (cfg or {}).get("backend") or "configured"
    if implement is not None:
        return implement, 1
    if backend in ("local", "cloud", "llama"):
        return None, _iterations(cfg, True)
    return default_implement, 1


def complete_existing(backend, messages):
    """The two clients selfdev already used. local is not here: that path refuses anything but loopback."""
    from llmos import config
    from llmos import llm
    kw = {"max_tokens": 800, "temperature": 0.1}
    if backend == "cloud":
        if not config.cloud():
            raise RuntimeError("no online model is configured")
        reply = llm.cloud_chat(messages, **kw)
    elif backend == "llama":
        reply = llm.chat(messages, **kw)
    else:
        raise RuntimeError("unknown model backend " + str(backend))
    return (reply.get("content") or "").strip()


def implement_once(support, item, cfg, note=""):
    """One edit from the selected backend, applied only inside the staging or checkout package."""
    pkg = os.path.join(support, "src", "rootfs", "usr", "lib", "llmos")
    messages = selfloop_local.prompt_messages(pkg, item, note)
    backend = "local" if cfg.get("mode") == "device" else (cfg.get("backend") or "local")
    if backend == "local":
        text = selfloop_local.complete(cfg, messages)
    else:
        text = complete_existing(backend, messages)
    applied, problems, changed = selfloop_local.apply_edits(pkg, selfdev.parse_edits(text))
    if not applied:
        raise RuntimeError("; ".join(problems)[:400] or "no edit could be applied")
    return {"changed": changed}


def cap_light(chosen, priority, cap):
    """Core tests first, then the tests that name the changed module, then the rest, up to cap.
    The full suite is not a fallback: anything past the cap is left out."""
    chosen = list(dict.fromkeys(chosen))
    core_set = set(selfdev.CORE_TESTS)
    core = [t for t in selfdev.CORE_TESTS if t in set(chosen)]
    rest = [t for t in chosen if t not in core_set]
    prio = set(priority or [])
    rest.sort(key=lambda name: (0 if name in prio else 1, name))
    room = max(0, int(cap) - len(core))
    return core + rest[:room], rest[room:]


def tests_for_package(paths, cap, support):
    """Light gate for an on-device change: tests that touch the changed modules, plus the core, capped."""
    index = selfdev._test_index()
    modules, priority = [], []
    for raw in paths or []:
        base = os.path.basename(str(raw))
        if not base.endswith(".py"):
            continue
        mod = base[:-3]
        if mod not in index or not index[mod]:
            return None, (f"no host test imports or reads llmos/{mod}.py, so the light gate cannot tell what "
                          "this change would break. Nothing was queued.")
        modules.append(mod)
        for test in sorted(index[mod]):
            if mod in os.path.basename(test):
                priority.append(test)
    if not modules:
        return None, ("no host test reads these files, so the light gate cannot tell what would break. "
                      "Nothing was queued.")
    affected = set()
    for mod in modules:
        affected.update(index[mod])
    kept, dropped = cap_light(sorted(affected | set(selfdev.CORE_TESTS)), priority, cap)
    missing = [t for t in kept if not os.path.isfile(os.path.join(support, t))]
    if missing:
        return None, "the light gate is missing " + ", ".join(missing) + ". Nothing was queued."
    names = ", ".join("llmos/" + m + ".py" for m in sorted(set(modules)))
    extra = " The rest is left for a dev machine." if dropped else ""
    return kept, f"{len(kept)} tests for {names}, capped for this machine.{extra}"


def stage_tree(dest, package_src, tools_src):
    """Copy the installed package into a support-shaped tree. tools_src is copied only when tests will run there."""
    if os.path.exists(dest):
        raise RuntimeError("the staging path already exists")
    pkg_dest = os.path.join(dest, "src", "rootfs", "usr", "lib", "llmos")
    shutil.copytree(package_src, pkg_dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if tools_src:
        shutil.copytree(tools_src, os.path.join(dest, "tools"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "run"))
    return pkg_dest


def _drop(dest):
    if dest and os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)


def develop_loop(support, item, cfg, implement, select, gate, rounds):
    """Propose and run the light gate, up to rounds times. Does not install and does not delete the tree."""
    note = ""
    last = "the light gate did not pass"
    saw_gate = False
    for _attempt in range(max(1, rounds)):
        if selfloop_ctl.killed():
            return {"passed": False, "stopped": True, "detail": killed_reason()}
        try:
            if implement is not None:
                current = item if not note else dict(item, detail=((item.get("detail") or "") + "\n" + note).strip())
                changed = implement(support, current)
            else:
                changed = implement_once(support, item, cfg, note)
        except Exception as e:
            last = str(e)[:400]
            note = last
            continue
        paths = list((changed or {}).get("changed") or [])
        sel, info = select(paths)
        if not sel:
            return {"passed": False, "detail": info or "no tests", "unmapped": True}
        passed, summary = gate(support, sel)
        saw_gate = True
        if passed:
            return {"passed": True, "tests": list(sel), "summary": summary, "changed": paths}
        last = str(summary)[:400]
        note = last
    # A round that never reached the gate should say why, not that the tests failed.
    return {"passed": False, "detail": last, "error": not saw_gate}


def _device_refused(cfg, package_src, install):
    """Why on-device mode will not start, or '' when it may. Checked before a staging copy is made."""
    backend = cfg.get("backend") or "local"
    if backend != "local":
        return ("on-device mode only uses the local model, which does not call a cloud API. "
                "Nothing was changed.")
    target = package_src or ("/usr/lib/llmos" if os.path.isdir(os.path.join("/usr/lib/llmos", "llmos")) else "")
    if install is None and not target:
        return ("on-device mode installs into /usr/lib/llmos, and that directory is not on this machine. "
                "Nothing was changed.")
    if install is None and selfloop_local.is_source_tree(target):
        return "on-device mode installs into /usr/lib/llmos, not the source tree. Nothing was changed."
    return ""


def _install_result(install, support, package_src):
    """An injected installer, or the signed local install. (ok, detail)."""
    if install is not None:
        value = install(support, package_src)
        if isinstance(value, tuple):
            return bool(value[0]), str(value[1] if len(value) > 1 else "")
        return value in (0, True), ""
    pkg = os.path.join(support, "src", "rootfs", "usr", "lib", "llmos")
    state = os.path.join(selfloop_ctl.state_dir(), "ota")
    return selfloop_local.install_local(package_src, pkg, state)


def run_device(result, item, rows, cfg, now, implement, select, gate, install, package_src, tools_src, dest_parent):
    """Staging copy, light gate, then queue or a signed local install. The live package is not the work tree."""
    package_src = package_src or "/usr/lib/llmos"
    parent = dest_parent or os.path.join(selfloop_ctl.state_dir(), "staging")
    os.makedirs(parent, exist_ok=True)
    leaf = _branch_id(item.get("id") or "item") + "-" + time.strftime("%H%M%S", time.localtime(now))
    dest = os.path.join(parent, leaf)
    tools = tools_src if tools_src is not None else (None if gate is not None or implement is not None else HERE)
    # A real run copies the tests so they import the staging package. An injected gate does not need them.
    if gate is None and tools is None:
        tools = HERE
    try:
        assert_separate(dest, package_src)
        stage_tree(dest, package_src, tools)
        cap = cfg.get("max_light_tests") or 24
        selector = select or (lambda paths: tests_for_package(paths, cap, dest))
        outcome = develop_loop(dest, item, cfg, implement, selector, gate or run_light_gate, _iterations(cfg, True))
        if outcome.get("stopped"):
            result.update(action="refused", detail=outcome.get("detail") or killed_reason(), item=item.get("id"))
            _drop(dest)
            selfloop_ctl.record(result)
            return result
        if not outcome.get("passed"):
            if outcome.get("unmapped") or outcome.get("error"):
                detail = outcome.get("detail") or "no tests"
            else:
                detail = "the light gate did not pass"
            result.update(action="discarded", detail=detail, item=item.get("id"))
            _drop(dest)
            _save_backlog(_mark(rows, item, "discarded"))
            selfloop_ctl.record(result)
            return result
        sel, summary = outcome["tests"], outcome["summary"]
        result.update(item=item.get("id"), tests=sel, gate="light", summary=str(summary)[:400])
        log_path = os.path.join(dest, "run", "selfloop", "ship-gate.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        shell = selfloop_ctl.device_ship_shell(dest, sel, log_path, item.get("id"),
                                              installer=os.path.abspath(__file__))
        queued = {"id": item.get("id"), "title": item.get("title"), "when": result["when"],
                  "support": dest, "staging": dest, "package": package_src, "kind": "device",
                  "tests": sel, "ship": shell, "install": "local", "require_approval": cfg["require_approval"],
                  "backend": "local"}
        if cfg["require_approval"]:
            selfloop_ctl.enqueue(queued)
            result.update(action="queued", detail="gate passed; waiting for approval. Not installed.", ship=shell)
            _save_backlog(_mark(rows, item, "queued"))
            selfloop_ctl.record(result)
            return result
        ok, detail = _install_result(install, dest, package_src)
        if not ok:
            result.update(action="discarded", detail=detail or "the install did not succeed, so nothing was kept")
            _drop(dest)
            _save_backlog(_mark(rows, item, "discarded"))
            selfloop_ctl.record(result)
            return result
        result.update(action="installed", detail=detail or "signed local update installed", ship=shell)
        _drop(dest)
        _save_backlog(_mark(rows, item, "installed"))
        selfloop_ctl.record(result)
        return result
    except Exception as e:
        result.update(action="discarded", detail=str(e)[:400], item=(item or {}).get("id"))
        _drop(dest)
        selfloop_ctl.record(result)
        return result


def run_once(live=None, repo=None, backlog=None, log_text="", implement=None, select=None, gate=None,
             ship=None, now=None, cfg=None, dest_parent=None, package_src=None, tools_src=None, install=None):
    """One pass. Returns a result dict and never publishes when the gate did not pass."""
    live = live or ROOT
    cfg = cfg or selfloop_ctl.load_config()
    now = time.time() if now is None else now
    result = {"when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), "mode": cfg.get("mode") or "dev",
              "require_approval": cfg.get("require_approval", True), "action": "refused", "detail": "",
              "backend": cfg.get("backend") or ("local" if cfg.get("mode") == "device" else "configured")}
    if cfg.get("mode") != "device" and selfdev._is_live_install():
        result["detail"] = ("this is the running install. Dev-machine mode does this work on another machine "
                            "and ships here by OTA. Nothing was changed.")
        selfloop_ctl.record(result)
        return result
    if killed_reason():
        result["detail"] = killed_reason()
        selfloop_ctl.record(result)
        return result
    blocked, why = selfloop_ctl.rate_limit(now, cfg)
    if blocked:
        result["detail"] = why
        selfloop_ctl.record(result)
        return result
    if cfg.get("mode") == "device":
        why = _device_refused(cfg, package_src, install)
        if why:
            result["detail"] = why
            selfloop_ctl.record(result)
            return result
    item, rows = selfloop_ctl.pick_item(backlog if backlog is not None else _load_backlog(), log_text)
    if item is None:
        result["detail"] = "the backlog is empty and the logs have no failing test to work from"
        selfloop_ctl.record(result)
        return result
    selfloop_ctl.note_run(now)
    if cfg.get("mode") == "device":
        return run_device(result, item, rows, cfg, now, implement, select, gate, install,
                          package_src, tools_src, dest_parent)
    repo = repo or _repo_of(live)
    # Outside the running tree. A checkout nested in it would be the tree we promised not to edit.
    outside = os.path.dirname(os.path.realpath(repo or live))
    parent = dest_parent or os.path.join(outside, ".llmos-selfloop-checkouts")
    os.makedirs(parent, exist_ok=True)
    leaf = _branch_id(item.get("id") or "item") + "-" + time.strftime("%H%M%S", time.localtime(now))
    branch = "llmos-selfloop/" + leaf
    dest = os.path.join(parent, leaf)
    support = kind = top = None
    try:
        support, kind, top = make_checkout(repo, dest, branch, live)
        worker, rounds = resolve_worker(cfg, implement)
        outcome = develop_loop(support, item, cfg, worker, select or tests_for_changes,
                               gate or run_light_gate, rounds)
        if outcome.get("stopped"):
            result.update(action="refused", detail=outcome.get("detail") or killed_reason(), item=item.get("id"))
            discard_checkout(dest, kind, top, branch)
            selfloop_ctl.record(result)
            return result
        if not outcome.get("passed"):
            if outcome.get("unmapped") or outcome.get("error"):
                detail = outcome.get("detail") or "no tests"
            else:
                detail = "the light gate did not pass"
            result.update(action="discarded", detail=detail, item=item.get("id"))
            discard_checkout(dest, kind, top, branch)
            _save_backlog(_mark(rows, item, "discarded"))
            selfloop_ctl.record(result)
            return result
        sel, summary = outcome["tests"], outcome["summary"]
        result.update(item=item.get("id"), tests=sel, gate="light", summary=str(summary)[:400])
        if kind == "git":
            try:
                commit_checkout(dest, "selfloop: " + str(item.get("title") or item.get("id"))[:120])
            except subprocess.CalledProcessError as e:
                result["commit"] = "not committed: " + str(e)[-160:]
        log_path = os.path.join(support, "run", "selfloop", "ship-gate.txt")
        shell = selfloop_ctl.ship_shell(support, sel, _version_of(support),
                                        "selfloop " + str(item.get("id") or "") + ": " + str(item.get("title") or ""),
                                        log_path)
        queued = {"id": item.get("id"), "title": item.get("title"), "when": result["when"],
                  "support": support, "checkout": dest, "branch": branch, "kind": kind, "repo": top,
                  "tests": sel, "ship": shell, "require_approval": cfg["require_approval"]}
        if cfg["require_approval"]:
            selfloop_ctl.enqueue(queued)
            result.update(action="queued", detail="gate passed; waiting for approval. Not published.", ship=shell)
            _save_backlog(_mark(rows, item, "queued"))
            selfloop_ctl.record(result)
            return result
        code = (ship or run_ship)(shell, support)
        if code != 0:
            result.update(action="discarded", detail="the publish gate failed, so nothing was published")
            selfloop_ctl.record(result)
            return result
        result.update(action="shipped", detail="light gate passed and the update was published with &&", ship=shell)
        _save_backlog(_mark(rows, item, "shipped"))
        selfloop_ctl.record(result)
        return result
    except Exception as e:
        result.update(action="discarded", detail=str(e)[:400], item=(item or {}).get("id"))
        if dest and kind:
            discard_checkout(dest, kind, top, branch)
        selfloop_ctl.record(result)
        return result


def killed_reason():
    if not selfloop_ctl.killed():
        return ""
    return "the kill switch is on. Nothing was changed. Resume it before the loop will run again."


def _branch_id(text):
    import re
    cleaned = re.sub(r"[^a-z0-9.-]+", "-", str(text).lower()).strip("-.")
    return (cleaned or "item")[:40]


def _backlog_path():
    return os.path.join(selfloop_ctl.state_dir(), "backlog.json")


def _load_backlog():
    path = _backlog_path()
    try:
        data = json.load(open(path, encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, ValueError):
        pass
    seed = os.path.join(ROOT, "selfloop-backlog.json")
    try:
        data = json.load(open(seed, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _save_backlog(rows):
    os.makedirs(selfloop_ctl.state_dir(), exist_ok=True)
    tmp = _backlog_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _backlog_path())


def _mark(rows, item, status):
    out = []
    for row in rows:
        if isinstance(row, dict) and row.get("id") == item.get("id"):
            row = dict(row, status=status)
        out.append(row)
    return out


def install_queued(item_id):
    """Install one queued on-device change. The test gate has already passed in this process, or on the left of &&."""
    if killed_reason():
        print(killed_reason(), flush=True)
        return 2
    rows = selfloop_ctl.load_queue()
    item = next((row for row in rows if str(row.get("id")) == str(item_id)), None)
    if item is None:
        print("That change is not waiting. Nothing was installed.", flush=True)
        return 1
    if item.get("install") != "local":
        print("That change is not an on-device install. Nothing was installed.", flush=True)
        return 2
    try:
        selfloop_ctl.assert_gated(item.get("ship") or "")
    except RuntimeError as e:
        print(str(e), flush=True)
        return 2
    package = item.get("package") or ""
    support = item.get("support") or ""
    pkg = os.path.join(support, "src", "rootfs", "usr", "lib", "llmos")
    if not os.path.isdir(pkg) or not os.path.isdir(os.path.join(package, "llmos")):
        print("The staging copy is gone. Nothing was installed.", flush=True)
        return 2
    if selfloop_local.is_source_tree(package):
        print("Refusing to install into the source tree. Nothing was installed.", flush=True)
        return 2
    ok, detail = selfloop_local.install_local(package, pkg, os.path.join(selfloop_ctl.state_dir(), "ota"))
    selfloop_ctl.record({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "action": "installed" if ok else "held",
                         "item": item.get("id"), "detail": detail})
    if not ok:
        print(detail, flush=True)
        return 1
    selfloop_ctl.save_queue([row for row in rows if str(row.get("id")) != str(item_id)])
    print(detail, flush=True)
    return 0


def ship_approved():
    """The owner approving the oldest queued change. The test gate runs again before anything is installed."""
    if killed_reason():
        print(killed_reason(), flush=True)
        return 2
    rows = selfloop_ctl.load_queue()
    if not rows:
        print("Nothing is waiting for approval.", flush=True)
        return 1
    item = rows[0]
    shell = item.get("ship") or ""
    support = item.get("support") or ""
    try:
        selfloop_ctl.assert_gated(shell)
    except RuntimeError as e:
        print(str(e), flush=True)
        return 2
    if not os.path.isdir(support):
        print("The checkout for that change is gone. Nothing was published.", flush=True)
        return 2
    if item.get("install") == "local":
        tests = item.get("tests") or []
        if not tests:
            print("Refusing to install without a test list.", flush=True)
            return 2
        passed, _summary = run_light_gate(support, tests)
        selfloop_ctl.record({"when": time.strftime("%Y-%m-%d %H:%M:%S"),
                             "action": "checking" if passed else "held", "item": item.get("id"),
                             "detail": "owner approval, light gate" if passed else "the light gate did not pass"})
        if not passed:
            print("The test gate failed, so the update was not installed.", flush=True)
            return 1
        return install_queued(item.get("id"))
    code = run_ship(shell, support)
    selfloop_ctl.record({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "action": "shipped" if code == 0 else "held",
                         "item": item.get("id"), "detail": "owner approval" if code == 0 else "publish gate failed"})
    if code == 0:
        # --install-local, if the shell ran it, has already taken its own row off the queue.
        fresh = selfloop_ctl.load_queue()
        if fresh and fresh[0].get("id") == item.get("id"):
            selfloop_ctl.save_queue(fresh[1:])
        print(f"Published {item.get('id')}. The test gate passed and the update was signed.", flush=True)
        return 0
    print("The test gate failed, so the update was not published.", flush=True)
    return code or 1


def status_text():
    lines = [selfloop_ctl.summary(), "Mode file: " + (selfloop_ctl.config_path() or "(defaults)")]
    for row in selfloop_ctl.results(5):
        lines.append(f"{row.get('when', '')}  {row.get('action', '')}: {row.get('detail', '')[:160]}")
    if not selfloop_ctl.results(1):
        lines.append("No loop runs recorded.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="take one backlog item on a separate checkout")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true", help="kill switch: refuse every later run")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--ship-approved", action="store_true", help="install or publish the queued change, tests && installer")
    ap.add_argument("--install-local", metavar="ID", help="install one queued on-device change after its test gate")
    args = ap.parse_args(argv)
    if args.status:
        print(status_text())
        return 0
    if args.stop:
        print(selfloop_ctl.set_killed(True))
        return 0
    if args.resume:
        print(selfloop_ctl.set_killed(False))
        return 0
    if args.ship_approved:
        return ship_approved()
    if args.install_local:
        return install_queued(args.install_local)
    if not args.once:
        ap.print_help()
        return 2
    cfg = selfloop_ctl.load_config()
    where = "staging copy of the install" if cfg["mode"] == "device" else "separate checkout"
    print(f"[selfloop] mode: {cfg['mode']}. backend: {cfg.get('backend')}. {where}, light gate, "
          f"install only after tests, approval {'required' if cfg['require_approval'] else 'not required'}.",
          flush=True)
    result = run_once(cfg=cfg)
    print(f"[selfloop] {result['action']}: {result['detail']}", flush=True)
    if result["action"] == "queued":
        print("[selfloop] Review it, then: tools/selfloop.py --ship-approved", flush=True)
        if cfg["mode"] == "device":
            print("[selfloop] Approval signs a local update, installs it, and rolls it back if the health check fails. "
                  "Network services are not restarted.", flush=True)
        print("[selfloop] The full host suite is still the right check on a dev machine before you rely on it.",
              flush=True)
        return 0
    if result["action"] in ("shipped", "installed"):
        return 0
    if result["action"] == "refused":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
