#!/usr/bin/env python3
"""Remove finished agent worktrees (.claude/worktrees/agent-*).

A worktree is removed only if its branch is merged into the base branch,
its directory exists, it has no uncommitted changes, and it has been idle
for at least N minutes. Use --dry-run to list what would be removed.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print what would be removed; remove nothing")
    ap.add_argument("--base", default="llmos-1.5.0", help="base branch that must contain the worktree branch")
    ap.add_argument("--idle", type=int, default=60, help="minimum idle minutes before removal (default 60)")
    args = ap.parse_args()

    top = git("rev-parse", "--show-toplevel", cwd=HERE)
    if top.returncode != 0:
        print("error: cannot find repository root from", HERE, file=sys.stderr)
        return 1
    repo = top.stdout.strip()

    out = git("worktree", "list", "--porcelain", cwd=repo).stdout.split("\n\n")
    removed = unmerged = recent = dirty = other = 0
    for block in out:
        lines = dict(l.split(" ", 1) for l in block.strip().splitlines() if " " in l)
        path = lines.get("worktree", "")
        branch = lines.get("branch", "").replace("refs/heads/", "")
        if "/.claude/worktrees/agent-" not in path or not branch:
            continue
        name = os.path.basename(path)
        why = None
        if git("merge-base", "--is-ancestor", branch, args.base, cwd=repo).returncode != 0:
            why = "unmerged"
            unmerged += 1
        elif not os.path.isdir(path):
            why = "missing dir"
            other += 1
        elif git("status", "--porcelain", cwd=path).stdout.strip():
            why = "dirty"
            dirty += 1
        elif time.time() - os.path.getmtime(path) < args.idle * 60:
            why = "recent (<%d min, may be in use)" % args.idle
            recent += 1
        if why:
            print("skip", name, why)
            continue
        if args.dry_run:
            print("would remove", name, "(branch %s)" % branch)
            removed += 1
            continue
        r = git("worktree", "remove", path, cwd=repo)
        if r.returncode == 0:
            print("removed", name)
            removed += 1
        else:
            print("fail", name, r.stderr.strip()[:120])
            other += 1
    if not args.dry_run:
        git("worktree", "prune", cwd=repo)
    skipped = unmerged + recent + dirty + other
    print("%s %d, skipped %d (unmerged %d, recent %d, dirty %d)"
          % ("would remove" if args.dry_run else "removed", removed, skipped, unmerged, recent, dirty))
    return 0


if __name__ == "__main__":
    sys.exit(main())
