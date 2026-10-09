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
