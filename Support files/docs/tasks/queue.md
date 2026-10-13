# Task queue (LLM OS buildout)

Owned by llmos-orchestrator. One line per task. Done tasks move to queue-done.md. Status: open, running, done, failed.
Operating rules: .claude/agents/llmos-orchestrator.md and docs/tasks/orchestration.md. Run VM/image builds one at a time; never let two workers edit the same file; never ask the owner.

## TOP PRIORITY (owner, 2026-10-09): real-world use testing
Boot the VM and drive it like a person (real clicks, real typing, real outcomes). Plan: docs/research/reports/VM real use testing plan.md (35 tasks, phases 1-3; follow its conventions and shared-file marks). Start Phase 1 now, after the RUN already going: PROBE and FIX tasks in parallel, RUN tasks one at a time. The other fronts continue at lower priority.
- [open] (reliability) Phase 2 and Phase 3 per the plan, after the P1-9 gate | role: per plan | files: per plan | test: per plan



- [open] (speed) _screen_steps leftover path sleeps 1 s before describing the screen (agent.py ~541) — probe whether needed | role: probe | files: none | test: report
- [open] (freedom) Default autonomy is "balanced" (config.py:144); full trust is opt-in per the 1.7.0 safety-defaults decision. Kept; refusal probe clean (agent.py:37,56 "Never refuse…"; test-risk.py "all good"). Next: RUN tools/refusal-probe.py on the VM model | role: run | files: none | test: refusal-probe output
- [open] (process) After 5 rounds: probe own record (re-specs, stalls, idle) | role: probe | files: none | test: report
- [open] (speed) PROBE on VM: time from "open the calculator" to app_read() returning a page (decides whether to poll instead of sleep(2)) | role: run | files: none | test: report
- [open] (ui) PROBE: list every owner-visible string in desk.js/i18n.py English that contains jargon (tool, model, error, null, undefined, JSON, API) | role: probe | files: none | test: report
- [open] (freedom) RUN tools/refusal-probe.py against the VM model; report every refusal/hedge | role: run | files: none | test: report
- [open] (process) OCR on the desk's own UI can give false hits (control.find found "File" on the desk). Exclude the desk webview from OCR targets or crop to the front window | role: probe
- [failed] (freedom) RUN result: owner guidance "2 refusal(s), 0 lecture(s) in 16 requests" (router-ping script; angry complaint letter); standard "2 refusal(s), 1 lecture(s)". Prompt-change dispatch was interrupted; paused for owner review. RUN tools/refusal-probe.py against the 1.7.5 VM model; report every refusal, hedge or lecture | role: run
- [open] (ui) SLOP: "add a shortcut to this folder" -> "The owner must specify…" (third person, 31 s) | role: probe

Notes:
- docs/tasks/orchestration.md IS the adopted policy (rewritten 2026-10-09 to match the owner's standing consent). The orchestrator plans and dispatches; workers do all code edits in worktrees; the orchestrator owns VM/image builds and may stop VMs, download from Alpine's signed repos, and run precarious installs. Owner instruction (2026-10-09): never ask the owner; outside-Alpine downloads, publishing and pushing are pre-approved.

Session state note (2026-10-09):
- dist/ is an INCOHERENT INTERMEDIATE: arm64 qcow2 was rebuilt to 1.7.2 to test M1, but RELEASE.json/SHA256SUMS still say 1.7.1 and the x86 image is the old 1.7.1 build. check-fresh says STALE (source now fb26f07). dist/SHA256SUMS is modified-uncommitted on purpose. Do NOT ship from dist/ until a full `tools/release.sh all` regenerates a coherent 1.7.2 (after M1/M2 land). The 1.7.1 zip on ~/Desktop is the real shipped 1.7.1.
- M1 wizard experiment: do NOT dismiss onboarding by `pkill labwc` — it leaves a stale desk socket (Connection refused). Instead pre-set `onboarded:true` in the image build (or drive the wizard to completion via the desk's wizard_step) and boot fresh, then test the calculator.
- docs/tasks/orchestration.md is adopted and tracked in git.

## Post-1.7.6-build src merge list (all VERIFY PASS; merge in this order once release.sh exits)
- df416e6 (intent chain incl. 4eea691 aria, last_saved, notes guard, spreadsheet, _free_path)
- 55047d6 (i18n 6 langs × 440 keys)
- b2af87a (P1-4 rect 65b5641 + P2-14 testreset-min 6c6218f + both resets clear last_reply)
- ee5d199 (P3-2 testshell temperature 0 / seed 42)
- a943c66 (photo route "my pics from X", action-clause guard)
- d343bf1 ("skipped" toast = no answer in 10 minutes; trial-merged clean with 55047d6)
Merged tools-only this round: c9f69f8 P1-1, 8d05067 P2-1, 60395ff P2-12, 0821a15 P2-3, bb105d6 evaluator gaps, d3786d3 P2-11, 30fb221 P2-2, 71edf5f P1-5, fa75052 P1-3.
Pending VERIFY: d9947ce P1-11 realuser.py.

## 1.7.6 RUN results (2026-10-10 00:55)
- [open] (capability) slow/wrong: "how tall is mount everest" 88 s; "show as list / big icons" 149 s empty reply; "turn word doc into pdf" 73 s wrong ("Opened the office program"); "always open pdfs in X" 44 s wrong ("Install files."); "translate thank you to french" 23 s; "click File" 23 s | role: probe (dispatched) | files: read only

## Post-1.7.7-build src merge list
- b1ee0a5 (pdf route: "turn word doc into pdf" -> which_file; VERIFY PASS)
- f2b6cec (contains 65ead61 + bare-click miss skips 2nd OCR; dfae44a + owner_text plain errors on 4 display paths; c18ff22 + typo retry in intent.match and desk.turn; f11631a + open_app verb strip; b01e1ea to-do list route fix; b14adc7 + notes "as a list" fix; contains 2d76e55 set_default_app + files view list/icons tool+routes; VERIFY PASS)
- bd3a962 (files icon grid in desk.js/desk.css; VERIFY PASS)
- 059904f (web search: engines in parallel, 10 s cap, plain error text; VERIFY PASS: "search failed: DuckDuckGo returned 503; Brave returned 429")
- [open] (reliability) packages/LLM OS 1.7.7.zip actually holds the 1.7.6 build; next package.sh run after the 1.7.7 build overwrites it | role: run | files: packages/
- 769a120 (everyday: instant "15 percent of 240" answers; VERIFY PASS: "15% of 240 is 36.")

## 1.7.7 build + post-build merges (2026-10-10 02:25)
- [failed] (top) P2-5 realrun basic.json on 1.7.7: 0/50 (all at the shot step — QEMU-relative screendump path; and desk wait returned before requests ran). Fixed 8c3815d (tools) + 64c2ee3 (desk). Rerun on 1.7.8. | evidence: summary "pass": 0, "fail": 50, 848 s

## Post-1.7.8-build src merge list
- 8f4b4b5 (warm-up sends the same prefix as the first turn; None ctx cached 5 s; VERIFY PASS: hung /props two calls 3.01 s)

## Owner account (next big item) — plan, one step at a time
Facts (PROBE 10:05): no init/session file names a user; config.home() = $LLMOS_HOME or ~ (65 home-path uses); 13 root-needing lines in tools.py (apk, iwctl, nft, /etc writes, chmod/chown); no account code; installer has no user step; desk.py:3032 already tells the owner separate accounts are planned.
- [open] (capability) A12 next verb groups: wifi (iwctl scan/connect/forget, rfkill), power (poweroff/reboot/suspend), brightness, system update (apk update/upgrade, cache), restart model service, drives (mount/eject/format), printers, bluetooth, vault, install_to_disk, kiosk seat, wireguard, passwd/shells, reset erase, clock sync
- [open] (capability) A13 install.sh owner user + rootd service behind a flag; A14 RUN boot as owner; A15 flip default
- [open] (speed) poll instead of fixed sleeps: tools.py:3604 _screen_after 0.8 s (describe() changed), agent.py:560 1 s, desk.py:143 wifi scan 3 s, tools.py:3969 1.5 s, everyday.py:827 vpn 6 s | role: fix one at a time after agent.py:654 lands
- [open] (ui) i18n English wording: 'model'/'API' jargon in onboarding & settings (i18n.py:40-95, 181, 193) — decide plain terms, keep 'API key' where providers use it | role: fix
- [note] process review 2026-10-10: 73 merges; idle 454 min in gaps >15 min (worst 05:53-08:17, 03:28-05:06) while one long RUN was the only work; freedom 1 merge, ui 2. Rule added to orchestration.md.
- [note] (speed) 7225986 merged: compound open waits for a changed app page; caveat — an already-open app whose page updates itself (clock/timer) can end the wait early. Watch in VM runs.
- [note] process: 729037a merged — orchestrator agent file now requires Keep identical / Adversarial inputs lines; applies to me after restart.
- [open] (capability) A13 verbs (from PROBE 2026-10-10): set_shell (everyday.py:1051/1083 writes /etc/passwd, /etc/shells) | wifi_radio/airplane (rfkill block/unblock, desk.py:2412-2426) | mount/eject (syspanels.py:166/178 fallback mount/umount) | format_drive (tools.py:3217) | vault (vault.py cryptsetup/mount) | printers (syspanels.py:377/394 lpadmin) | installer stays root-only. iwctl/bluetoothctl/udisksctl: need D-Bus/polkit policy for the owner group (no policy files in repo) — PROBE in VM after A14.
- [note] 2026-10-12: resumed after the weekly limit (stuck from Oct 10 19:22). The interrupted 1.8.0 build left dist/RELEASE.json, SHA256SUMS, VERSION modified-uncommitted (partial). Decision: leave them; the clean rebuild (release.sh all) regenerates all three; commit the new manifest after check-fresh FRESH (FIX worker), like 1.7.6–1.7.9.
- [open] (capability) A13e vault via rootd — PROBE done: vault.py runs cryptsetup/mkfs/mount as the caller (no timeouts), file-backed /var/lib/llmos/vault.img mounted on /root; change_passphrase writes both passphrases to 0600 tmpfs files. rootd logs only "time verb ok|error" (no args). DEFERRED until the owner-home location is decided in A14 (vault mounts on the owner's home, which moves from /root to /home/<owner>). Design notes: verbs vault_setup/open/lock/change/status, passphrase in the JSON body -> cryptsetup stdin; keep "any non-empty passphrase" (owner's choice, no new 8-byte minimum); add timeouts; avoid os.chdir in the threaded daemon (use cwd= on subprocess).
- [open] (speed) first-reply prefix is ~7.9k tokens at ctx>=12k (system 1375 + 80 tools 6515). Measure on the VM (curl cold POST max_tokens 1, timings.prompt_ms) before/after: (a) one fixed ~32-tool list for every context; (b) side jobs (decide, translations) evict the only slot — try --cache-ram up on small machines or -np 2 + id_slot. | role: run (measure) then fix
- [open] (ui) "the owner" in model-visible tool results is also an internal marker matched by agent.py (937 _INTERNAL, 1101, 250/1016/1018, 1194) — reword both sides in ONE commit (tools.py + agent.py) after the warm-up branch on agent.py merges. Only tools.py:995 is free-standing.
- [open] (ui) default accent #7c5cff gives 4.35:1 with either text colour (below 4.5). Option: nudge the default accent slightly darker (e.g. #7350ff ~4.8 with white) — check how it looks on the VM screenshot before changing | role: fix after a screenshot
- [open] (reliability) build-image*.sh wait patterns still look for "not enough disk"; the new wording is "not enough free disk" — add it to the early-exit pattern so a disk-full install fails fast | role: fix after build | files: tools/build-image.sh, tools/build-image-x86.sh
- [held] 032b47a (A14c launcher prologue re-execs as owner; default path identical) VERIFY PASS — merge after build (owner path off by default).
- [note] (capability) fast-route coverage 2026-10-12: 447/624 (71.6%) by desk._instant over tasks/*.json phrases (was 403/577, 70%). The everyday/intent/_HOWTO-only count (315) misses desk shortcuts; next probe should run desk.shortcut() with stubs to find the true model-only list (rows in /tmp/probe-phrases/rows.json).
- [held] 200a0a0 (keyboard: clock, Enter confirms non-danger dialogs, radio arrows, textarea focus ring) VERIFY PASS — merge after the RUN reports. Minor: Space on the clock also moves focus to the chat input.
- [held] 006e4ef (clear routines/activity log; log capped at 2 MB; never follows a symlink) VERIFY PASS — merge after the RUN reports.
- [held] 7645e2e (short phrases: font bigger, scale N%, show all apps, blue light, too dark go back) VERIFY PASS — merge after the RUN reports. Open: "private window" (no wm key).
- [held] 2b63471 (accurate online-model disclosure: q_brain_2 in 6 languages + cloud privacy answer) VERIFY PASS — merge after the RUN reports.
- [held] 072ef78 ("private window"/"incognito" -> Firefox Ctrl+Shift+P) VERIFY PASS — merge after the RUN reports.
- [decision] (freedom) Kept agent.py conduct line refusing step-by-step drug/weapon making and harm to third parties: BRIEF "The one boundary kept throughout: no harm to other people." Offline "say you couldn't check it" kept (honesty, not a nag).
- [open] (reliability) task setups hard-code /root; with the owner account (A14) the desk home is /home/owner — make realrun expose a {home} placeholder (or tsh resolves config.home()) and use it in usecases-1/usecase-checks | role: fix | files: tools/realrun.py, tools/tasks/*.json
- [open] (capability) "scientific calculator" maps to the plain Calculator template (apps.match_template); add sin/cos/tan/log/sqrt/^/() to the calculator template or a scientific variant | role: probe then fix | files: apps.py templates
- [open] (capability) no "what did I miss" / "show my notifications" route: add one that calls desk.show_away(force=True) (works under do-not-disturb) | role: fix | files: desk.py shortcut, after ebd3776 merges
- [open] (reliability) tools/tasks/basic-convert.py:75 generator still writes /root paths; make it emit {home} | role: fix | files: tools/tasks/basic-convert.py
- [done] (freedom) Refusal probe, Ministral 3 3B (default), host llama-server --jinja: owner guidance "0 refusal(s), 0 lecture(s) in 16 requests"; standard guidance "1 refusal(s), 0 lecture(s) in 16 requests" (router ping flood 1000/s). Improved from 1.7.5 (owner 2 refusals). Standard is opt-in stricter guidance; kept.
