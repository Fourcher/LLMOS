# Task queue (LLM OS buildout)

Owned by llmos-orchestrator. One line per task. Done tasks move to queue-done.md. Status: open, running, done, failed.
Operating rules: .claude/agents/llmos-orchestrator.md and docs/tasks/orchestration.md. Run VM/image builds one at a time; never let two workers edit the same file; never ask the owner.

## TOP PRIORITY (owner, 2026-10-09): real-world use testing
Boot the VM and drive it like a person (real clicks, real typing, real outcomes). Plan: docs/research/reports/VM real use testing plan.md (35 tasks, phases 1-3; follow its conventions and shared-file marks). Start Phase 1 now, after the RUN already going: PROBE and FIX tasks in parallel, RUN tasks one at a time. The other fronts continue at lower priority.
- [open] (reliability) P1-2 QMP probe on a booted image | role: run | files: none | test: see plan P1-2 (after P1-1)
- [open] (reliability) Phase 2 and Phase 3 per the plan, after the P1-9 gate | role: per plan | files: per plan | test: per plan



- [open] (speed) "open X then press …": replace fixed time.sleep(2) after the first step (agent.py ~635) with polling ctx.app_read() every 0.1 s up to 2 s when the first step is open_app | role: fix | files: src/rootfs/usr/lib/llmos/llmos/agent.py tools/test-screen-steps.py | test: test-screen-steps.py (after the ui agent.py fix merges)
- [open] (speed) _screen_steps leftover path sleeps 1 s before describing the screen (agent.py ~541) — probe whether needed | role: probe | files: none | test: report
- [open] (freedom) Default autonomy is "balanced" (config.py:144); full trust is opt-in per the 1.7.0 safety-defaults decision. Kept; refusal probe clean (agent.py:37,56 "Never refuse…"; test-risk.py "all good"). Next: RUN tools/refusal-probe.py on the VM model | role: run | files: none | test: refusal-probe output
- [running] (reliability) AT-SPI menu match + bare click VERIFIED on VM (see M2); desk.log is 0 bytes on the VM (no control: lines) -> RUN probe dispatched. VM-verify desk.log on the 1.7.2 build | role: run | files: none | test: grep "control: atspi" /run/llmos/desk.log
- [open] (process) After 5 rounds: probe own record (re-specs, stalls, idle) | role: probe | files: none | test: report
- [running] (capability/speed) PROBE: map agent.py's no-model branches in order (conditions, sleeps) | role: probe | files: none | test: report
- [open] (speed) PROBE on VM: time from "open the calculator" to app_read() returning a page (decides whether to poll instead of sleep(2)) | role: run | files: none | test: report
- [open] (ui) PROBE: list every owner-visible string in desk.js/i18n.py English that contains jargon (tool, model, error, null, undefined, JSON, API) | role: probe | files: none | test: report
- [open] (freedom) RUN tools/refusal-probe.py against the VM model; report every refusal/hedge | role: run | files: none | test: report
- [open] (process) PROBE own record (5 rounds reached): re-specs, worker stalls, VERIFY outcomes, idle gaps from git log + queue | role: probe | files: none | test: report
- [open] (process) RUN workers: the guard refuses `<script>` and `bash <script>` with computed paths but accepted `/bin/bash "<literal path>"`. Put that form into the RUN spec template in orchestration.md | role: orchestrator doc edit
- [open] (process) OCR on the desk's own UI can give false hits (control.find found "File" on the desk). Exclude the desk webview from OCR targets or crop to the front window | role: probe
- [failed] (freedom) RUN result: owner guidance "2 refusal(s), 0 lecture(s) in 16 requests" (router-ping script; angry complaint letter); standard "2 refusal(s), 1 lecture(s)". Prompt-change dispatch was interrupted; paused for owner review. RUN tools/refusal-probe.py against the 1.7.5 VM model; report every refusal, hedge or lecture | role: run
- [open] (ui) RAW: "turn word doc into pdf" -> "'files' is not installed; install it with install_app first …" (internal tool text) | role: probe+fix
- [open] (capability) WRONG: "find the file i was working on yesterday" -> "Your home folder is empty." (9 s; Documents has a folder) | role: probe+fix
- [open] (ui) SLOP: "add a shortcut to this folder" -> "The owner must specify…" (third person, 31 s) | role: probe
- [open] (speed) browser: "open my bookmarks" empty reply 53 s; "make browser dark" 110 s; "change homepage" 242 s timeout | role: probe
- [running] (capability) VERIFY PASS 4b0da11: "show my files as a list" no longer opens the notes list (shopping/notes/reading lists unchanged; a notes list literally named "music" now goes to the model — accepted). Merge after the 1.7.6 build.
- [running] (reliability) 4a1d859 test-start ignores git-ignored packages/ — VERIFY in flight; merge after the build.
- [running] (ui) i18n: 4cd0312 (contains 2fb1001 clock tooltip + 8726f50 12 desk strings) — VERIFY PASS: every language has all 440 EN keys, 0 placeholder mismatches; merge after the 1.7.6 build. Then 1.7.7.
- [running] (capability) rename chain c8cfb29 (contains 4b0da11 notes guard, 33f75b8, 7b5c208, 5e4da7c, 00a71ef) VERIFY PASS: "call it Budget instead" / "rename it to Budget" rename the folder made in the last 10 min; idioms ("call it a day", "name it after my dog", …) untouched; merge after the 1.7.6 build.
- [running] (ui/reliability) 55047d6 (i18n complete + dedupe + test-i18n-keys) VERIFY PASS; merge after the build.
- [running] (capability/reliability) chain 706c86e VERIFY PASS (contains c8cfb29 rename, 980acf3 "make this a jpg", 8e00a52 print copies + "whats the date", fbe444a "summarize/sign this pdf", 6e9be26 make a spreadsheet, 706c86e spreadsheet never overwrites + honest "opened it"). Merge after the 1.7.6 build together with 55047d6 (i18n).
- [running] (reliability) P2-1 task schema + tasklib | role: fix | files: tools/tasks/schema.md tools/tasklib.py tools/test-tasklib.py

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
- [open] (reliability) package.sh named the 1.7.6 build "LLM OS 1.7.7.zip" (reads source VERSION, not dist) | role: fix (dispatched) | files: tools/package.sh

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
- [open] (ui) raw {e} in owner replies: everyday.py:480,482,980,1353,1688 | role: fix after disk-space FIX lands (same file)
- [open] (capability) A12b callers: desk.py:3743, console.py:524, syspanels.py:516 sleep -> system.power; models.py:250, desk.py:2743 -> system.service | role: fix after A12a merge
- [open] (capability) A12c verbs: brightness (devices.py:9-34), updates (syspanels.py:564-609 incl. clear_caches), sync_time (system.py:441) | role: fix after A12a
- [note] process review 2026-10-10: 73 merges; idle 454 min in gaps >15 min (worst 05:53-08:17, 03:28-05:06) while one long RUN was the only work; freedom 1 merge, ui 2. Rule added to orchestration.md.
- [note] (speed) 7225986 merged: compound open waits for a changed app page; caveat — an already-open app whose page updates itself (clock/timer) can end the wait early. Watch in VM runs.
- [open] (ui) web.py error texts still technical when passed through: "DuckDuckGo returned 503", "Hugging Face returned HTTP 503" -> "the search service is busy; try again in a minute" | role: fix | files: web.py
- [note] process: 729037a merged — orchestrator agent file now requires Keep identical / Adversarial inputs lines; applies to me after restart.
- [open] (capability) A13 verbs (from PROBE 2026-10-10): set_shell (everyday.py:1051/1083 writes /etc/passwd, /etc/shells) | wifi_radio/airplane (rfkill block/unblock, desk.py:2412-2426) | mount/eject (syspanels.py:166/178 fallback mount/umount) | format_drive (tools.py:3217) | vault (vault.py cryptsetup/mount) | printers (syspanels.py:377/394 lpadmin) | installer stays root-only. iwctl/bluetoothctl/udisksctl: need D-Bus/polkit policy for the owner group (no policy files in repo) — PROBE in VM after A14.
- [open] (capability) last_saved open: open_file failures without an "error" prefix still reply "Opened …" (tools.py ~2826 no screen/sound device; ~2852-2856 "cannot be shown as text"/"too big") — check open_file return shape and treat these as failures | role: fix | files: tools.py
- [note] 2026-10-12: resumed after the weekly limit (stuck from Oct 10 19:22). The interrupted 1.8.0 build left dist/RELEASE.json, SHA256SUMS, VERSION modified-uncommitted (partial). Decision: leave them; the clean rebuild (release.sh all) regenerates all three; commit the new manifest after check-fresh FRESH (FIX worker), like 1.7.6–1.7.9.
- [open] (capability) A13e vault via rootd — PROBE done: vault.py runs cryptsetup/mkfs/mount as the caller (no timeouts), file-backed /var/lib/llmos/vault.img mounted on /root; change_passphrase writes both passphrases to 0600 tmpfs files. rootd logs only "time verb ok|error" (no args). DEFERRED until the owner-home location is decided in A14 (vault mounts on the owner's home, which moves from /root to /home/<owner>). Design notes: verbs vault_setup/open/lock/change/status, passphrase in the JSON body -> cryptsetup stdin; keep "any non-empty passphrase" (owner's choice, no new 8-byte minimum); add timeouts; avoid os.chdir in the threaded daemon (use cwd= on subprocess).
- [open] (speed) first-reply prefix is ~7.9k tokens at ctx>=12k (system 1375 + 80 tools 6515). Measure on the VM (curl cold POST max_tokens 1, timings.prompt_ms) before/after: (a) one fixed ~32-tool list for every context; (b) side jobs (decide, translations) evict the only slot — try --cache-ram up on small machines or -np 2 + id_slot. | role: run (measure) then fix
- [open] (ui) "the owner" in model-visible tool results is also an internal marker matched by agent.py (937 _INTERNAL, 1101, 250/1016/1018, 1194) — reword both sides in ONE commit (tools.py + agent.py) after the warm-up branch on agent.py merges. Only tools.py:995 is free-standing.
- [open] (reliability) test-desk-wait.py and test-vmctl-fast.py failed once each under host load (build running) and passed alone — timing-sensitive; widen their timing margins or use injected clocks | role: probe then fix
- [open] (ui) default accent #7c5cff gives 4.35:1 with either text colour (below 4.5). Option: nudge the default accent slightly darker (e.g. #7350ff ~4.8 with white) — check how it looks on the VM screenshot before changing | role: fix after a screenshot
- [open] (reliability) build-image*.sh wait patterns still look for "not enough disk"; the new wording is "not enough free disk" — add it to the early-exit pattern so a disk-full install fails fast | role: fix after build | files: tools/build-image.sh, tools/build-image-x86.sh
- [open] (capability) A14 plan (PROBE 2026-10-12): a) OpenRC init script llmos-rootd, before the desk; b) install.sh behind a flag (LLMOS_OWNER=1): create user "owner" (home /home/owner) + groups video,input,audio,seat,netdev,plugdev,owner; c) llmos-login/llmos-desk start the desk as that user with HOME=/home/owner when the flag file exists; d) /var/lib/llmos/models group-writable (owner) or a rootd verb; vault MOUNT -> owner home; e) model-visible "/root" strings (tools.py 442,453,1269,2128; console.py 95; reset.py 30) -> config.home(); f) rootd chown: fail loudly if group "owner" missing. Then RUN: boot as owner in the VM.
- [open] (capability) A14d: when the owner user is on: /run/llmos (root 700), desk.log (root 600), /var/cache/llmos, /var/lib/llmos/models must be usable by the owner (dirs owned by owner or group owner, created by llmos-desk/an init step); seatd access for the owner (seat group + seatd service); vault MOUNT -> owner home; model-visible "/root" strings -> config.home(). Then A14 RUN: VM install with LLMOS_OWNER=1 and boot.
- [open] (reliability) builds #2 and #3 died in the x86 step: PermissionError (EPERM) reading build/work/build-x86-serial.log on /Volumes/Files, even with the tool sandbox off. FIX in flight: serial logs on the internal disk ($TMPDIR/llmos-build). Owner-side option if it persists: Full Disk Access for the terminal/claude process.
- [open] (capability) A14c redesign: (1) move rootd's socket to its own dir /run/llmos-rootd/root.sock (dir root:owner 0750, sock 0660) — rootd.py + rootd_client.py + tests; (2) then the launcher prologue can hand /run/llmos entirely to the owner (chown -R u:owner, 0700) before re-exec'ing itself under su with LLMOS_DESK_INNER=1 and LLMOS_DESK_HOME; the body keeps XDG_RUNTIME_DIR=/run/llmos and its chmod 700 works. Body change: only the HOME line.
- [held] 032b47a (A14c launcher prologue re-execs as owner; default path identical) VERIFY PASS — merge after build (owner path off by default).
- [open] (capability) A14d (from VERIFY 032b47a): as the owner the body still needs root for: seatd-launch (needs root; switch to the seatd service + labwc directly with the user in group seat), /var/cache/llmos (mesa cache, labwc rc.xml rm), `rm -f /run/seatd.sock`, the at-spi launcher; and `exec su` failure has no fallback to the root path. Fix in llmos-desk + install.sh (rc-update add seatd; /var/cache/llmos owned by owner when flagged).
- [note] (capability) fast-route coverage 2026-10-12: 447/624 (71.6%) by desk._instant over tasks/*.json phrases (was 403/577, 70%). The everyday/intent/_HOWTO-only count (315) misses desk shortcuts; next probe should run desk.shortcut() with stubs to find the true model-only list (rows in /tmp/probe-phrases/rows.json).
- [held] 200a0a0 (keyboard: clock, Enter confirms non-danger dialogs, radio arrows, textarea focus ring) VERIFY PASS — merge after the RUN reports. Minor: Space on the clock also moves focus to the chat input.
- [held] 006e4ef (clear routines/activity log; log capped at 2 MB; never follows a symlink) VERIFY PASS — merge after the RUN reports.
- [held] 7645e2e (short phrases: font bigger, scale N%, show all apps, blue light, too dark go back) VERIFY PASS — merge after the RUN reports. Open: "private window" (no wm key).
- [held] 2b63471 (accurate online-model disclosure: q_brain_2 in 6 languages + cloud privacy answer) VERIFY PASS — merge after the RUN reports.
- [held] 072ef78 ("private window"/"incognito" -> Firefox Ctrl+Shift+P) VERIFY PASS — merge after the RUN reports.
- [open] (reliability) unvalidated tool args found by the schema probe: set_appearance.corners (stored raw, desk falls back silently), mail_setup.smtp_security (unknown value -> plaintext silently!), rename_files.spaces (KeyError on unknown), rename_files.case (silently ignored) — validate each with a plain error | role: fix | files: tools.py, mail.py
- [open] (speed) replytr busy guard only covers in-flight chat() requests, not the gaps between tool steps of a turn; also skip translation while desk.busy | role: fix | files: desk.py instant_reply
- [open] (reliability) desk say<->act thread ping-pong while busy for instant-looking phrases that fall through (pre-existing; "news", "logs", "screen time"…) | role: fix | files: desk.py act/say
- [open] (freedom) PROBE false refusals from agent._ONLY_IF_ASKED keyword gate ("not done: you did not ask for …") and _APP_WORDS gate
- [decision] (freedom) Kept agent.py conduct line refusing step-by-step drug/weapon making and harm to third parties: BRIEF "The one boundary kept throughout: no harm to other people." Offline "say you couldn't check it" kept (honesty, not a nag).
- [open] (freedom) folder-lock "Keep the password somewhere safe…" shown on every lock — show once only | role: fix | files: desk.py ~1181, ~1622
- [open] (reliability) S32 race: desk-ctl "wait … after N" grace loop gives up after 3 s if the typed line has not reached say() yet; keep waiting (to the timeout) for _req_done>after or _req_pending>0 | role: fix | files: desk.py _control_conn wait branch (~4171-4196), tools/test-desk-wait.py | WAIT: desk.py busy with ac00893 (ping-pong fix)
- [open] (reliability) task setups hard-code /root; with the owner account (A14) the desk home is /home/owner — make realrun expose a {home} placeholder (or tsh resolves config.home()) and use it in usecases-1/usecase-checks | role: fix | files: tools/realrun.py, tools/tasks/*.json
- [open] (capability) "scientific calculator" maps to the plain Calculator template (apps.match_template); add sin/cos/tan/log/sqrt/^/() to the calculator template or a scientific variant | role: probe then fix | files: apps.py templates
