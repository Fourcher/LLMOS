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
- Spec regexes: I have written `what\s+(?:is|'s)`, `why (?:is|'s)` and `i\s+(?:'ve…)` three times today — each needs no space before the apostrophe. Write contractions as `what(?:\s+is|'s)` / `i(?:\s+have|['’]ve)` and list one contracted example in every test.

## Rerun policy for real-use runs (plan P3-5)
- A failing task is rerun once on a fresh overlay.
- Pass then fail = flaky: file it with its signature, don't gate a merge or release on it.
- Fail twice = real: dispatch a FIX with the repro bundle.
- A failure cluster closes only after two passing reruns.

## Lesson (2026-10-10 round review): put the adversarial cases in the FIX spec
This round's VERIFY FAILs were all cases the FIX spec never named: frame size change (settle), dangerous phrases slipping a word list (P2-11), wrong state paths guessed without reading source (P2-2), action clauses swallowed by a broad regex (photo route), unquoted shell argument (realuser). Each cost one extra FIX+VERIFY cycle.
Before dispatching a FIX, add a "must also handle" line listing, as applicable:
- inputs of a different size/shape than the happy path; empty, None, unicode;
- for regex routes: 3 near-miss phrases that ask for a DIFFERENT action and must not match, plus one contraction;
- for anything built into a shell command: a quote, a space and a newline in the argument;
- for task/grader files: the real path of the state, read from source (paste file:line into the spec), never guessed;
- for word filters: phrase forms, not just single words, and a substring false positive (sudo/sudoku).

## Lesson (2026-10-10 01:38): a FIX worker booted a VM by running a new tool
A FIX worker ran its new realuser-smoke.py "to check --help"; main() ignored argv and booted the test VM from the main checkout's run/ during the 1.7.7 build (the build's x86 TCG VM survived). Rules:
- Every new tool that can boot a VM must refuse to boot unless given an explicit `--run` flag; with no args or `--help` it prints usage and exits 0.
- FIX and VERIFY specs say: never execute a VM-touching script (anything calling boot-target.sh, tsh, vmctl, qmp sockets); test only the pure functions with fakes.

## Lesson (2026-10-10): when a FIX changes a call shape, the spec owns every test that asserts it
Two FIX attempts on the bare-click change stopped because other test files asserted the old call tuple. Specs that change a function's arguments, return value or call shape must say: "grep tools/test-*.py for the old shape and update every expectation that comes from this path; list them".

## Lesson (2026-10-10 08:40 process review): list callers before the FIX starts
Review of today's 53 merges: 8 topics needed 3+ FIX attempts (testreset 5, pointer-sweep 4, web search 4, triage 4, warm-up 3, grader echo 3, typos 3, --run guard 3). Each repeat was an edge case or a caller the first spec did not name.
Rule for every FIX spec that changes existing behaviour: open with a PROBE-sourced "Callers and tests" line (file:line of every caller and every test that exercises the changed function), and the VERIFY spec repeats that list and checks each one. If the list is not known, dispatch the PROBE first; do not write the FIX from memory.

- 2026-10-10 review: 454 idle minutes came from waiting on a single long RUN with nothing else in flight. While any RUN holds the VM, keep at least 3 host-only workers (PROBE/FIX/VERIFY) running across different fronts; freedom and ui need a task every round.
- 2026-10-10: intent.match always receives the ORIGINAL typed text (desk.py:2210/2227/3451/3458, agent.py:723); the lowercased `low` (desk.py:2195) is only for everyday.MATCH and set checks. VERIFY specs must call intent.match(text) on raw text and everyday.MATCH on intent.plain(text).lower().strip(). (A false case-loss alarm came from my wrong spec.)
- 2026-10-10 follow-up review (24 merges after 10:30; 17 first-try; 9 follow-ups: 4 edge cases, 3 regressions, 2 other — none from missing files or tests). Two lines are now required in every FIX spec that replaces or wraps existing behaviour:
  * "Keep identical:" — the exact old timeouts, argv, owner-facing messages, return shapes and limits (from the PROBE), so the worker tests them.
  * "Adversarial inputs:" — symlinks, "..", option-like names, wrong types, stale/cached state, an already-open window — whatever applies, so VERIFY isn't the first to try them.
- 2026-10-12: a weekly usage limit killed every worker mid-task (Oct 10 19:22 → Oct 12 15:00). On resume: check `git status` for half-written build outputs (dist/), re-dispatch each killed task from its spec, and never trust a partial dist/ — rebuild with release.sh all.
- STANDING OWNER RULE (2026-10-12): after install there are no size or RAM limits on what the owner downloads, installs, adds or selects (models included — "If a user wants to install a 140 GB model onto their computer, that's up to them and the amount of free storage they have available."). The only refusal is "not enough free disk: need X GB, have Y GB". Bigger-than-memory is disclosed ("runs from disk, slow"), never blocked. Only the ISO and the install drive have a size budget.
- 2026-10-12: build #2 died in the x86 step with PermissionError (EPERM) reading build/work/build-x86-serial.log — a macOS file-access denial on /Volumes/Files, also seen by several workers today ("Operation not permitted" on Support files). RUN workers now run release.sh and smokes with the Bash sandbox disabled; if it recurs, check Full Disk Access for the terminal/claude process.
