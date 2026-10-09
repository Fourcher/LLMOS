# Orchestration policy (llmos-orchestrator re-reads this every loop)

This file IS adopted. It encodes the owner's standing instructions. The owner has given
explicit, standing consent to do whatever is necessary to build LLM OS to spec: stop VMs,
download packages from Alpine's signed repositories, and run installs that may be precarious.

## Division of labour
- The orchestrator plans, dispatches, integrates, verifies. It never edits a source file.
- llmos-worker agents do every code change, each in its own git worktree, on its own branch.

## Dispatch
- Run as many workers at once as there are ready tasks whose file sets do not overlap.
- All dispatches for a round go in one message so they run in parallel.
- Never let two workers own the same file in the same round.

## Integrate
- A worker reports a passing test -> merge its branch with `git merge --no-ff` -> run all host
  suites (`for t in "Support files"/tools/test-*.py; do python3 "$t"; done`) -> mark [done]
  with the quoted evidence. On conflict or suite failure, reopen with the failure and dispatch a fix.

## VM and image builds
- Serial and orchestrator-only. One VM, one build at a time.
- Before a build: `lsof dist/*.qcow2` must show no holder; stop only VMs this project started (run/target.pid).

## Never stop
- Empty queue -> write new tasks from the owner's goals and keep going.
- Ask the owner only before: an outside-Alpine download, a publish, or a push to a shared remote.
