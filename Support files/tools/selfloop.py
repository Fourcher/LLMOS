#!/usr/bin/env python3
"""The self-improvement loop, on a dev machine.

    tools/selfloop.py --once              # one improvement: checkout, light gate, queue or discard
    tools/selfloop.py --status
    tools/selfloop.py --stop              # kill switch
    tools/selfloop.py --resume
    tools/selfloop.py --ship-approved     # the owner says yes: tests > log && ota publish

Dev-machine mode is the setup this is for. The loop checks out a separate branch, asks the
existing selfdev loop to implement there, and runs the light gate (tests that touch the
changed modules, plus the core subset). The running tree is not edited. A live install is
refused outright: ship the result to it with OTA, do not run the loop on it.

A passing gate is queued. It is published only when require_approval is false, or when the
owner runs --ship-approved. Publishing is the host tests, output redirected to a file, then
&&, then tools/ota.py publish. A pipe is refused. The full suite is not what this loop runs;
it froze a 16 GB machine. A light-queued change still wants the full suite on a dev machine
before you rely on it.

The kill switch (tools/selfloop.py --stop, or LLMOS_SELFLOOP=off, or /etc/llmos/selfloop-stop)
and the rate limit refuse a run before any checkout is created.
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


def run_light_gate(support, tests):
    """Run the light set in the checkout. Output goes to a file. The return code is the suite's."""
    log = os.path.join(support, "run", "selfloop", "gate.txt")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    cmd = ["bash", os.path.join(support, "tools", "run-host-tests.sh"), *tests]
    with open(log, "w", encoding="utf-8") as handle:
        proc = subprocess.run(cmd, cwd=support, stdout=handle, stderr=subprocess.STDOUT)
    try:
        text = open(log, encoding="utf-8", errors="replace").read()
    except OSError:
        text = ""
    fails = [ln for ln in text.splitlines() if ln.startswith("FAIL ")]
    import re
    m = re.search(r"host suites:\s*(\d+)\s*run", text)
    ran = bool(m) and int(m.group(1)) > 0
    return proc.returncode == 0 and ran and not fails, (text[-400:] or "no output")


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


def run_once(live=None, repo=None, backlog=None, log_text="", implement=None, select=None, gate=None,
             ship=None, now=None, cfg=None, dest_parent=None):
    """One pass. Returns a result dict and never publishes when the gate did not pass."""
    live = live or ROOT
    cfg = cfg or selfloop_ctl.load_config()
    now = time.time() if now is None else now
    result = {"when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), "mode": cfg["mode"],
              "require_approval": cfg["require_approval"], "action": "refused", "detail": ""}
    if selfdev._is_live_install():
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
    item, rows = selfloop_ctl.pick_item(backlog if backlog is not None else _load_backlog(), log_text)
    if item is None:
        result["detail"] = "the backlog is empty and the logs have no failing test to work from"
        selfloop_ctl.record(result)
        return result
    selfloop_ctl.note_run(now)
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
        changed = (implement or default_implement)(support, item)
        paths = list((changed or {}).get("changed") or [])
        sel, info = (select or tests_for_changes)(paths)
        if not sel:
            result.update(action="discarded", detail=info or "no tests", item=item.get("id"))
            discard_checkout(dest, kind, top, branch)
            _save_backlog(_mark(rows, item, "discarded"))
            selfloop_ctl.record(result)
            return result
        passed, summary = (gate or run_light_gate)(support, sel)
        result.update(item=item.get("id"), tests=sel, gate="light", summary=str(summary)[:400])
        if not passed:
            result.update(action="discarded", detail="the light gate did not pass")
            discard_checkout(dest, kind, top, branch)
            _save_backlog(_mark(rows, item, "discarded"))
            selfloop_ctl.record(result)
            return result
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


def ship_approved():
    """The owner approving the oldest queued change. The stored command re-runs the light gate with &&."""
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
    code = run_ship(shell, support)
    selfloop_ctl.record({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "action": "shipped" if code == 0 else "held",
                         "item": item.get("id"), "detail": "owner approval" if code == 0 else "publish gate failed"})
    if code == 0:
        selfloop_ctl.save_queue(rows[1:])
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
    ap.add_argument("--ship-approved", action="store_true", help="publish the queued change, tests && ota")
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
    if not args.once:
        ap.print_help()
        return 2
    cfg = selfloop_ctl.load_config()
    print(f"[selfloop] mode: {cfg['mode']}. Separate checkout, light gate, OTA only after tests, "
          f"approval {'required' if cfg['require_approval'] else 'not required'}.", flush=True)
    result = run_once(cfg=cfg)
    print(f"[selfloop] {result['action']}: {result['detail']}", flush=True)
    if result["action"] == "queued":
        print("[selfloop] Review it, then: tools/selfloop.py --ship-approved", flush=True)
        print("[selfloop] The full host suite is still the right check on a dev machine before you rely on it.",
              flush=True)
        return 0
    if result["action"] == "shipped":
        return 0
    if result["action"] == "refused":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
