# Orchestration policy (llmos-orchestrator re-reads this every loop)

This file IS adopted. It encodes the owner's standing instructions. The owner has given
explicit, standing consent to do whatever is necessary to build LLM OS to spec: stop VMs,
download packages from Alpine's signed repositories, and run installs that may be precarious.

## Division of labour
- The orchestrator only thinks: it chooses work across the fronts (speed, capability, UI, owner freedom,
  reliability, process), writes tasks, dispatches them, judges reports and merges after a VERIFY pass.
- llmos-worker agents (Haiku) do all the doing, in four roles: PROBE (facts), FIX (one change),
  VERIFY (independent check of a FIX branch), RUN (builds, VM, smokes, sweeps; one at a time).
- The orchestrator improves its own process through PROCESS tasks done by workers.

## Dispatch
- Run as many workers at once as there are ready tasks whose file sets do not overlap.
- All dispatches for a round go in one message so they run in parallel.
- Never let two workers own the same file in the same round.

## Integrate
- FIX reports pass -> VERIFY worker checks the branch (diff vs spec, test, all host suites) ->
  on PASS the orchestrator runs `git merge --no-ff` -> mark [done] with the quoted VERIFY evidence.
  On FAIL or conflict, reopen with the failure and dispatch a fix.

## VM and image builds
- Done by one RUN worker at a time, never the orchestrator. One VM, one build at a time.
- Before a build: `lsof dist/*.qcow2` must show no holder; stop only VMs this project started (run/target.pid).

## Never stop
- Empty queue -> write new tasks from the owner's goals and keep going.
- Never ask the owner. Full standing approval covers outside-Alpine downloads, publishing, and pushing to remotes too (owner, 2026-10-09).

## Output location
- Packages and all generated files go into the project working folder (package.sh defaults to <repo>/packages/). NEVER write to the Desktop or anywhere outside the project.

## Lessons (process probe, 2026-10-09)
- Don't freeze merges during a build. A build is pinned to the commit in dist/RELEASE.json (source_commit). Smokes check that commit's artifacts; merging src afterwards only makes check-fresh say STALE, which is expected until the next build. (A 94-minute merge freeze happened during the 1.7.2 build.)
- Worker shells refuse `cd <path> &&` and `git -C <path>`. Specs give paths relative to the worktree root ("Support files/tools/x.py") and run commands without cd. RUN workers in the main checkout use absolute paths.
- Prune merged worktrees regularly (46 worktrees, 115 MB on 2026-10-09).
- While release.sh is RUNNING, do not merge into the main checkout: the build reads src/ from the working tree, so a mid-build merge can mix two sources into one image. Merge between builds; check-fresh --built-commit covers smokes and packaging afterwards.
- RUN spec template: invoke scripts as `/bin/bash "/Volumes/Files/Claude Work Area/LLMOS/Support files/tools/<script>" <args>` with the path written out literally (the guard refuses computed paths and plain `<script>` calls in agent shells). Env vars via `env VAR=1 /bin/bash "<literal path>"`.
