# LLM OS VM test harness audit (what exists, and what is missing for real clicking and typing)

All paths are relative to `Support files/` unless they start with `/`. Sources are file:line references in this repo, read on 2026-10-09 at branch llmos-1.5.0 (HEAD 4e06241). I did not start, stop or touch any VM, build or run/ socket. I read the run/ result files only.

## 1. How each harness boots QEMU, injects input, reads results and asserts

### Takeaway
Every arm64 harness boots through `tools/boot-target.sh`: hvf, `-display none`, an HMP monitor socket, and the serial console as a Unix socket that is logged to a file. x86 harnesses boot through `tools/boot-x86.sh` (TCG) or an inline command in isosmoke. Input always goes in as text on the serial line. Desk actions are then made with `llmos say` / `llmos desk-ctl` over the desk's Unix control socket. Results are read from the JSON returned by `desk-state`/`say`, plus HMP `screendump` PNGs that no harness checks automatically.

### Cited Findings
**Shared boot plumbing**
- `boot-target.sh` (arm64): `qemu-system-aarch64 -machine virt -accel hvf -cpu host -smp $CPUS -m $RAM`, edk2 pflash, virtio disk, `-nic user`, `-device virtio-gpu-pci -device virtio-keyboard-pci -device virtio-tablet-pci`, `-audiodev none` + virtio-sound, `-display none -monitor unix:run/tmon.sock`, serial chardev on `run/tser.sock` logged to `run/boot-serial.log`, `-daemonize -pidfile run/target.pid`. — [tools/boot-target.sh:38-48](tools/boot-target.sh)
- fw_cfg switches: `opt/llmos/testshell` (the serial line becomes a root shell), `model_url`/`model_id` (host-GPU mode, llama-server on the Mac at 10.0.2.2:8080), `mic`, and an extra drive. — [tools/boot-target.sh:11-20](tools/boot-target.sh)
- Before booting, the script sends HMP `quit` to whatever VM is on `run/tmon.sock` and deletes the serial log. — [tools/boot-target.sh:21-22](tools/boot-target.sh)
- `boot-x86.sh`: `qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072`, SeaBIOS or OVMF, `virtio-vga`, virtio keyboard and tablet, intel-hda with `audiodev none`, `-display none`, monitor `run/ymon.sock`, serial `run/yser.sock` → `run/x86-boot.log`. — [tools/boot-x86.sh:27-35](tools/boot-x86.sh)
- `vmctl.py`: `send` writes text into the serial socket in 16-byte chunks 20 ms apart, because "serial getty/readline can drop bytes on big bursts under TCG". `wait` polls the log file for a regex every 0.5 s, with an optional `--quiet` settle. `run` sleeps 1.2 s first because "the console flushes input while it re-arms its line editor". — [tools/vmctl.py:22-31,43-61,75-79](tools/vmctl.py)
- `tsh`: runs one shell command on the arm64 serial line with an end marker `DONE_""N`. It decides whether to prefix `!` by scraping the last prompt from the final 4000 bytes of the shared log. — [tools/tsh:9-12](tools/tsh)
- `xrun`: types one request on the x86 serial console and waits for the prompt regex `[›>] $`. — [tools/xrun:5](tools/xrun)
- `screendump.py`: HMP `screendump` to PPM, converted to PNG. It prints the non-black fraction and a distinct-colour count, but asserts nothing. — [tools/screendump.py:56-59,68-74](tools/screendump.py)
- `vm-lifetime.sh`: a detached guard kills the QEMU pid after `$LLMOS_VM_LIFETIME` or 10800 s (3 h) and logs to `run/vm-lifetime.log`. — [tools/vm-lifetime.sh:8-14](tools/vm-lifetime.sh); called at [tools/boot-target.sh:49](tools/boot-target.sh) and [tools/boot-x86.sh:36](tools/boot-x86.sh); isosmoke uses 7200 s at [tools/isosmoke.sh:11,40](tools/isosmoke.sh)

**Per harness**
| Harness | Boot | Input path | Result read | Assertions |
|---|---|---|---|---|
| `test-vm-up.sh` | boot-target.sh with LLMOS_TESTSHELL=1 ([:14](tools/test-vm-up.sh)) | `desk-ctl wizard <step>` for every wizard step ([:17-19](tools/test-vm-up.sh)); mail fixture fetched over the host http.server; email set up through `llmos say` ([:20-22](tools/test-vm-up.sh)) | prints `desk-state` | none beyond "test shell up" / "no test shell" ([:15](tools/test-vm-up.sh)) |
| `usecase-run.py` | expects a running test VM | `testreset`, then `( llmos say '…' > /tmp/uc.json & )` ([:57,65](tools/usecase-run.py)); dialogs answered with `desk-ctl dialog yes/no`, using a regex to choose "destructive" ([:80-84](tools/usecase-run.py)) | reply/windows/dialogs from JSON, screendump PNG per case ([:119-124](tools/usecase-run.py)) | **none**. It records results "for review against 'success looks like'" ([:5](tools/usecase-run.py)). Grading is by `ux-grade.py` (heuristic REFUSED etc., [tools/ux-grade.py:2-3](tools/ux-grade.py)) and by hand |
| `button-sweep.py` | expects a running test VM | `llmos desk-ctl act '<button words>'` ([:46](tools/button-sweep.py)) | windows/reply diff in `desk-state` before and after a 4 s sleep ([:47-55](tools/button-sweep.py)) | "ok" if any window changed or the reply changed; machine-changing buttons are skipped by regex ([:18-20](tools/button-sweep.py)) |
| `desk-smoke.sh` | boot-target.sh, shipped image on an overlay ([:19](tools/desk-smoke.sh)) | `desk-ctl wizard`, `desk-ctl js "…click()"`, `llmos say`, `desk-ctl lock/unlock` ([:24-57](tools/desk-smoke.sh)) | `desk-state`, screendumps `run/shot-desk-*.png` ([:13](tools/desk-smoke.sh)) | 4 hard checks only: vault unmounted after lock, WebKit page alive, wrong passphrase stays on lock, right one unlocks ([:52-58](tools/desk-smoke.sh)) |
| `calc-smoke.sh` | boot-target.sh ([:9](tools/calc-smoke.sh)) | sets `onboarded=True` through python on the serial line, then `sleep 25` ([:21](tools/calc-smoke.sh)); 6 phrases via `llmos say` ([:28-44](tools/calc-smoke.sh)) | grep of `"reply"` | reply substrings "Closed", "pressed =", "shows 9", each ≤20 s ([:58-84](tools/calc-smoke.sh)); quits the VM via HMP ([:89](tools/calc-smoke.sh)) |
| `timed-sweep.sh` | boot-target.sh ([:17](tools/timed-sweep.sh)) | same onboarded bypass ([:30](tools/timed-sweep.sh)); `testreset`, then `llmos say` per line ([:58-61](tools/timed-sweep.sh)) | reply grep → `run/timed-sweep.tsv` | none; reports counts ≤3 s and >3 s ([:85-91](tools/timed-sweep.sh)) |
| `isosmoke.sh` | inline QEMU: arm64 hvf, ISO on scsi-cd ([:17-25](tools/isosmoke.sh)); x86 TCG `-cdrom` ([:31-37](tools/isosmoke.sh)) | one serial shell command | prints cmdline/mounts/release/models/desk socket | none (prints only) ([:43](tools/isosmoke.sh)) |
| `x86smoke.sh` | boot-x86.sh in host-GPU mode ([:11](tools/x86smoke.sh)) | **keystrokes into the console's first-run wizard** over serial: `for a in "" Jordan "" 1 y n ""` ([:20](tools/x86smoke.sh)); requests via `xrun` | serial text | waits for "All set" ([:21](tools/x86smoke.sh)); otherwise prints timing only |
| `agent_smoke.py` | **no VM.** It runs `agent.run` from `src/` on the Mac against a llama-server, with a temp HOME/ETC ([:10-18](tools/agent_smoke.py)) | python call with a fake Ctx whose `confirm_network`/`confirm_action` return True ([:38-39](tools/agent_smoke.py)) | tool names called; store side effects printed | expected tool name in calls, 12 cases ([:46-75](tools/agent_smoke.py)) |
| `vm-lifetime.sh` | n/a (guard) | n/a | n/a | n/a |

Other in-VM harnesses I found but did not audit line by line: `acceptance.sh` (serial console legs onboard/basics/agentic/…, [tools/acceptance.sh:1-14](tools/acceptance.sh)), `desk-edge.sh` (desk control socket, [tools/desk-edge.sh:1-15](tools/desk-edge.sh)), `dictate-smoke.sh` (in-guest `wtype` into a terminal, [tools/dictate-smoke.sh:2-6](tools/dictate-smoke.sh)), and `final-check.sh` (chains desk-smoke, acceptance and install-test, [tools/final-check.sh:12-14](tools/final-check.sh)).

### Inferences
- Every arm64 harness uses the same fixed socket, log and pid names (`run/tser.sock`, `run/tmon.sock`, `run/boot-serial.log`, `run/target.pid`). Only one arm64 test VM can exist at a time, and any harness that boots kills the previous VM (boot-target.sh:21).
- The screenshots are evidence for a human reviewer only. No harness compares pixels, OCRs a PNG or checks the non-black fraction.

### Gaps
- `trun`, `rrun`, `brun`, `acceptance.sh` and `desk-edge.sh` were not read in full.
- The exact current state of `run/` (whether a VM is up now) was deliberately not checked.

## 2. Does any harness click with the real pointer or type real keystrokes into the desk?

### Takeaway
No. No harness sends QEMU-level pointer or keyboard events (no QMP, no `sendkey`, no `input-send-event`). Nothing types into the desk's input box or clicks a desk button with a pointer. Desk actions go through the control socket, which calls Python handlers directly (`say`, `act`, `wizard`, `dialog`) or evaluates JavaScript (`js`, which runs DOM `.click()`). The only real keystrokes are serial-console text (x86smoke into the console wizard) and in-guest `wtype` into a terminal (dictate-smoke).

### Cited Findings
- Grepping `tools/` and `src/` for `qmp|sendkey|input-send-event|mouse_move|mouse_button|xdotool|ydotool` returns nothing. `wtype` appears only in the OS's own code (wm.py, control.py, voice.py, desk.py) and in the dictation tests. — grep over tools/ src/ (no matches except [tools/dictate-smoke.sh:5](tools/dictate-smoke.sh), [tools/dictate-test.sh:6,21](tools/dictate-test.sh))
- Every QEMU invocation uses `-display none` and an HMP `-monitor unix:…`. None has `-qmp` or `-vnc`. — [tools/boot-target.sh:46](tools/boot-target.sh), [tools/boot-x86.sh:33](tools/boot-x86.sh), [tools/isosmoke.sh:23,35](tools/isosmoke.sh)
- The desk control socket handler (`_control_conn`):
  - `say` calls `self.say(arg, done)` directly. It does not touch the page's `#in` field. — [src/rootfs/usr/lib/llmos/llmos/desk.py:4049-4055](src/rootfs/usr/lib/llmos/llmos/desk.py)
  - `act`: `# press a button by its words, as the page does (tests)` → `self.act(arg)`. — [desk.py:4117-4119](src/rootfs/usr/lib/llmos/llmos/desk.py)
  - `wizard`: `self.wizard_step(step, value)`. — [desk.py:4077-4080](src/rootfs/usr/lib/llmos/llmos/desk.py)
  - `dialog`: `# answer every pending confirmation (tests)` sets the same answer on **all** pending dialogs. — [desk.py:4064-4069](src/rootfs/usr/lib/llmos/llmos/desk.py)
  - `js`: `self.emit({"t": "eval", "js": arg})`. — [desk.py:4129-4130](src/rootfs/usr/lib/llmos/llmos/desk.py)
  - `testreset` (only when fw_cfg testshell is set): `# tests drive the desk without touching the keyboard: the screen must stay on`. — [desk.py:4103-4116](src/rootfs/usr/lib/llmos/llmos/desk.py)
- `Desk.act` runs `_instant`/`shortcut`/`intent.match`, or falls back to `self.say(text)`. It is a words-to-handler path, not a click. — [desk.py:2198-2215](src/rootfs/usr/lib/llmos/llmos/desk.py)
- Synthetic DOM clicks used by a harness: `desk-ctl js "document.getElementById('wz-tz').value='tok'; …dispatchEvent(new Event('input'))"` and `desk-ctl js "document.getElementById('reply-close').click()"`. — [tools/desk-smoke.sh:27,48](tools/desk-smoke.sh)
- Pressing a button in button-sweep: `tsh(f"( llmos desk-ctl act '{q}' >/dev/null 2>&1 & )", 20)`. — [tools/button-sweep.py:46](tools/button-sweep.py)
- Real keystrokes, serial console only: `for a in "" Jordan "" 1 y n ""; do $V send $S "$a"; …` into the console wizard. — [tools/x86smoke.sh:20](tools/x86smoke.sh)
- labwc keybinds call `llmos desk-ctl act '…'` (for example Print → `act 'take a screenshot'`, Super+L → `act 'lock the screen'`), so a real key press would reach the same `act` path. No harness presses these keys. — [src/rootfs/etc/xdg/labwc/rc.xml:48-75](src/rootfs/etc/xdg/labwc/rc.xml)
- The OS has its own screen-control stack: grim + tesseract + wlrctl + wtype ([src/rootfs/usr/lib/llmos/llmos/control.py:5,36,345,366](src/rootfs/usr/lib/llmos/llmos/control.py)), with an AT-SPI path tested on the host using a fake tree ([tools/test-atspi.py:1-10](tools/test-atspi.py)). This is the *agent's* way of clicking inside programs, not a test driver of the desk.

### Inferences
- Both `virtio-tablet-pci` (absolute pointer) and `virtio-keyboard-pci` are attached (boot-target.sh:43). Injecting real pointer and keyboard events through QMP `input-send-event` (or HMP `sendkey`/`mouse_move`) is therefore technically possible with no device changes. Only a `-qmp` socket is missing.
- Because `act` sends a button's *say string*, button-sweep never exercises page click handlers that are not say-strings. Example: parity-results notes `Desk.handle('app.focus')` is `pass`, so a dock-chip click does nothing ([docs/research/parity-results.md:1294](docs/research/parity-results.md)). A pointer-driven sweep would catch this class of bug, and the current sweep cannot.
- Page-side breakage would go unseen by every harness: a broken `onclick`, focus on the wrong element, an Enter key that does not submit, an overlay covering a button, a WebKit bridge that fails between page and Python.

### Gaps
- Not found: any harness that OCRs or pixel-checks the desk to confirm what is on screen.
- Not found: any test of the desk's on-screen keyboard focus (`desk-ctl focus` exists at desk.py:4120-4127, but no harness checks the field actually takes typing).

## 3. Task lists and their latest pass/fail state

### Takeaway
There are four main task lists. The only fully hand-graded recent VM run is basic-sweep: 1.7.1 arm64, 2026-10-09, 43/50 outright, 2 real defects (S40, S48, both fixed), and the rest harness races or notes. The parity "results" document is mostly a source-reading map, not VM results. The queue's latest open failures are browser speed and timeouts, SLOP/WRONG replies, and a refusal-probe run marked failed.

### Cited Findings
- `use-cases.md`: a checklist of rows `ID | phrasings | success looks like | P`, parsed by usecase-run.py's regex. It says a row passes only when the result "is visible on screen or provable from the system". The file itself records no pass/fail. — [docs/research/use-cases.md:3,10](docs/research/use-cases.md), [tools/usecase-run.py:28-38](tools/usecase-run.py)
  - Last stored run: `run/usecases/summary.json`, 93 cases, mtime Oct 5 03:41, timeouts M05 and X07, max 203.1 s (computed from run/usecases/summary.json). Run span about 01:25→03:41 on Oct 5 (JSON mtimes).
- `parity-tasks.md`: Q01-Q60+ XFCE-equivalent requests, run with `usecase-run.py --file docs/research/parity-tasks.md --out run/parity`. — [docs/research/parity-tasks.md:3-5](docs/research/parity-tasks.md)
  - `run/parity/summary.json`: 60 cases, Oct 5 03:58→04:20, one timeout (Q60), max 156.9 s. `run/parity2` 9 cases and `run/parity-chain` 7 cases, no timeouts.
- `parity-results.md`: "Checked against the source … **No VM was run**: items marked *verify* depend on labwc/acpid defaults". Counts as mapped: YES 125, PROGRAM 102, PARTIAL 209, NO 373 of 809. Only the "Closed since this mapping (1.7.0)" table names Q-rows that were "Run in VM". — [docs/research/parity-results.md:3,7-38,44-52](docs/research/parity-results.md)
- `basic-sweep.md` results, 2026-10-09, shipped 1.7.1 arm64: "43 of 50 pass outright". Real bugs: S40 (`"No such tool 'mail_send'."`) and S48 (`"Done."` for help), fixed in a5b2257 and ff47fbf. S32 music and S35/S36 lock were judged "back-to-back start-up race", not bugs. The doc's own harness note: "`usecase-run.py` fires requests back-to-back; media/lock state needs a moment to settle". — [docs/research/basic-sweep.md:59-91](docs/research/basic-sweep.md)
  - The first-pass table called S35/S36 "lock/unlock in a serial test-shell has no real graphical lock session … likely harness artifact". The follow-up checked it by hand and found the lock works. — [docs/research/basic-sweep.md:72,84](docs/research/basic-sweep.md)
- Queue, latest open items: `[open] Re-run docs/research/basic-sweep.md on the 1.7.2 build` ([docs/tasks/queue.md:23](docs/tasks/queue.md)). Open WRONG/SLOP/speed items: "make this a jpg" took a screenshot; "turn word doc into pdf" leaks internal tool text; "find the file i was working on yesterday" → "Your home folder is empty."; "why is my disk full" SLOP; "add a shortcut to this folder" third person; browser "open my bookmarks" empty reply 53 s, "make browser dark" 110 s, "change homepage" 242 s timeout ([docs/tasks/queue.md:87-95](docs/tasks/queue.md)). The same timeout appears in `run/timed-sweep.tsv` row 54 (`242 change homepage [timeout]`).
- Queue `[failed]`: refusal-probe on 1.7.5, owner guidance "2 refusal(s), 0 lecture(s) in 16 requests"; standard "2 refusal(s), 1 lecture(s)". — [docs/tasks/queue.md:84](docs/tasks/queue.md)
- Latest build RUN evidence (1.7.5): calc-smoke "all good"; sweep "36 ≤3 s, 9 >3 s", max 11 s; read_screen 3.76 s (was 18 s). — [docs/tasks/queue.md:82](docs/tasks/queue.md)
- Open: "OCR on the desk's own UI can give false hits (control.find found 'File' on the desk)". — [docs/tasks/queue.md:81](docs/tasks/queue.md)

### Inferences
- The most recent *failures* are the browser-control timeouts and the refusal probe. The most recent *full hand-graded sweep* was on 1.7.1, so builds 1.7.2-1.7.5 have only partial VM coverage (calc-smoke plus timed-sweep).

### Gaps
- No consolidated pass/fail exists for use-cases.md or parity-tasks.md. The run JSONs hold replies, but the grading verdicts (by ux-grade.py or by hand) for those runs were not found in docs.

## 4. Known harness problems recorded in docs, queue or code

### Takeaway
The recorded problems are: the first-run wizard blocking desk actions; a mock that hid a real failure (test-screen-steps.py mocking `app_press`); back-to-back request races; timed-sweep reading a previous phrase's late reply; desk.log empty on the VM; OCR matching the desk's own UI; `pkill labwc` leaving a stale socket; and a worker that launched concurrent builds plus a self-matching waiter. Shared-serial-console corruption and vm-lifetime kills are **not recorded** in docs or the queue, though the structure allows both. Screen blanking is handled only inside `testreset`.

### Cited Findings
- **First-run wizard blocking / false positive from a mock:** "My earlier 'done' was a FALSE POSITIVE: tools/test-screen-steps.py MOCKS app_press, the very thing that is broken … DeskCtx.app_call evals window.llmosApp(...) in the desk webview while the FIRST-RUN WIZARD is up … ROOT CAUSE CONFIRMED: first-run wizard." — [docs/tasks/queue.md:15](docs/tasks/queue.md). The mock: `FakeCalculatorCtx.app_press` sets `display="9"` on `=` ([tools/test-screen-steps.py:42-55](tools/test-screen-steps.py)), and `fake_execute` routes `click` to it ([tools/test-screen-steps.py:61-75](tools/test-screen-steps.py)).
- **Wizard workaround rule:** "do NOT dismiss onboarding by `pkill labwc` — it leaves a stale desk socket (Connection refused). Instead pre-set `onboarded:true` … or drive the wizard to completion via the desk's wizard_step". — [docs/tasks/queue.md:101](docs/tasks/queue.md)
- **Late reply read by the next phrase:** "timed-sweep harness: a timeout leaves the late reply to be read by the next phrase (row 10 shows row 8's reply)", fixed in dae63d0. — [docs/tasks/queue.md:57](docs/tasks/queue.md)
- **Back-to-back races:** S32 and S35/S36 false negatives. — [docs/research/basic-sweep.md:83-91](docs/research/basic-sweep.md), [docs/tasks/queue.md:11-12](docs/tasks/queue.md)
- **Observability:** "desk.log is 0 bytes on the VM (no control: lines)". — [docs/tasks/queue.md:38](docs/tasks/queue.md); the desk stderr fix is at [docs/tasks/queue.md:28](docs/tasks/queue.md)
- **Concurrent builds and a self-matching waiter:** "recovered from a worker that launched two concurrent x86 builds + a self-matching waiter". — [docs/tasks/queue.md:6](docs/tasks/queue.md)
- **Screen blanking:** `start_idle` turns the screen off after `screen_off` minutes, default 10, via swayidle + `wlopm --off`. — [desk.py:1957-1967](src/rootfs/usr/lib/llmos/llmos/desk.py). `testreset` sets `screen_off` 0, `sleep_after` 0 and `autolock` 0, then restarts idle. — [desk.py:4106-4110](src/rootfs/usr/lib/llmos/llmos/desk.py)
- **Serial typing fragility:** byte drops under TCG, and input flushed while the line editor re-arms. — [tools/vmctl.py:26,78](tools/vmctl.py). The captured TSV shows echo contamination and line-wrap splits, e.g. row 50 reply column `llmos say "where did that download go" | grep … ; ec ho "OK""S50" "reply": …` (run/timed-sweep.tsv).
- **Prompt guessing:** tsh chooses `!` by reading the last prompt in the shared log tail. — [tools/tsh:10-11](tools/tsh)
- **Busybox quoting:** "busybox sh in the VM hates nested quotes". — `/Users/jordan/.claude/projects/-Volumes-Files-Claude-Work-Area-LLMOS/memory/llmos-project-state.md:31`
- **vm-lifetime:** `run/vm-lifetime.log` is absent or empty (tail returned nothing), so no kill has been recorded.

### Inferences
- **Shared serial corruption (structural, not recorded):** two drivers on `run/tser.sock` at once would interleave typed bytes and markers in one log. tsh's prompt guess would then pick the wrong mode, and boot-target.sh would quit the other agent's VM and delete its log (boot-target.sh:21-22).
- **Screen blanking in harnesses that skip testreset:** desk-smoke.sh, desk-edge.sh and test-vm-up.sh never call `testreset`, and the default `screen_off` is 10 min. desk-smoke includes a 75 s + 22 s wait ([tools/desk-smoke.sh:60](tools/desk-smoke.sh)). Late screendumps in a long run could come out black (not verified).
- **3 h kill:** the usecases run took about 2 h 16 min for 93 single phrasings. An `--all-phrasings` run, or a slow-model run, would likely pass the 10800 s guard and lose the VM mid-run (inference from JSON mtimes and vm-lifetime.sh:8).
- **testreset is not shipped behaviour:** it forces `autonomy balanced`, `internet yes`, `autolock 0`, `screen_off 0`, and declines dialogs (desk.py:4104-4109). Tests therefore run in a configuration no owner has.

### Gaps
- Not found: any doc or queue entry about shared-serial-console corruption between agents, or about a vm-lifetime kill happening.
- Not found: a recorded incident of screen blanking breaking a test.

## 5. Snapshotting and reset, and how long boot + test takes

### Takeaway
Each boot creates a fresh qcow2 overlay over a shipped `dist/` image, plus a fresh UEFI vars file. `LLMOS_KEEP_OVERLAY=1` reuses the overlay for a reboot leg. Nothing uses QEMU `savevm`/`loadvm` snapshots, and between cases the only reset is the in-guest `testreset`. arm64 hvf reaches the test shell in about 14 s and x86 TCG in about 24 s (ISO smokes). Per-request timings from usecase-run cannot show anything under about 9 s.

### Cited Findings
- Overlay: shipped images under `dist/` are "never booted directly"; `qemu-img create -f qcow2 -b <dist image> run/target-overlay.qcow2` unless `LLMOS_KEEP_OVERLAY=1`; `build/work` disks are booted directly so state persists across the reboot leg. — [tools/boot-target.sh:23-36](tools/boot-target.sh). x86 always recreates `run/x86-overlay.qcow2`. — [tools/boot-x86.sh:10-12](tools/boot-x86.sh). ISO VMs boot the read-only ISO with fresh vars. — [tools/isosmoke.sh:16,30](tools/isosmoke.sh)
- No `savevm`, `loadvm` or `-snapshot` in any harness (grep found none).
- Per-case reset: `testreset` closes windows, declines dialogs, resets settings, starts a new chat topic, stops recording, unlocks. — [desk.py:4103-4116](src/rootfs/usr/lib/llmos/llmos/desk.py). usecase-run also runs `pkill -x mpv; pkill -f firefox; pkill -x thunar`. — [tools/usecase-run.py:56-57](tools/usecase-run.py)
- Boot timings: arm64 ISO "test shell up after 14 s"; x86 ISO (UEFI) "test shell up after 24 s". — [docs/tasks/queue.md:6](docs/tasks/queue.md). Harness wait ceilings: 300 s (test-vm-up/desk-smoke), 400 s for the x86 serial offer (x86smoke.sh:13), 900 s for an ISO (isosmoke.sh:42).
- First request after boot is slow: "capital 5 s in sweep (58 s cold right after boot, prompt eval 3981 tokens @46 tok/s)". — [docs/tasks/queue.md:82](docs/tasks/queue.md)
- calc-smoke and timed-sweep add a fixed `sleep 25` after forcing onboarded. — [tools/calc-smoke.sh:21](tools/calc-smoke.sh), [tools/timed-sweep.sh:30](tools/timed-sweep.sh)
- Timing quantisation: in run/usecases/summary.json, 64 of 93 cases round to 9 s (min 9.2). In run/parity, 57 of 60 are about 9 s. In run/basic, 45 of 50 are about 12 s (min 11.7), summing to 699.5 s of request time. timed-sweep rows show 2 s for the same kind of instant replies (run/timed-sweep.tsv rows 50-52).
- The x86 smoke runs in host-GPU mode, "so the test is not bottlenecked by emulated inference". — [tools/x86smoke.sh:2-4](tools/x86smoke.sh)
- "x86 emulation takes 1.5-3 h" refers to *image builds*, not boots. — memory llmos-project-state.md:13

### Inferences
- The 9.2 s floor comes from usecase-run's loop: a background `say` launched through tsh (1.2 s pre-sleep + typing + 1 s quiet), then `time.sleep(4)`, then another tsh status call ([tools/usecase-run.py:65-70](tools/usecase-run.py)). Its `seconds` field cannot tell a 0.5 s reply from an 8 s one.
- A full boot + wizard + mail fixture (test-vm-up) on arm64 probably takes a few minutes, but no run log with that total was found.

### Gaps
- No recorded wall-clock time for test-vm-up.sh or desk-smoke.sh end to end, and none for x86 boot with on-device (emulated) inference.
- Disk-image (qcow2) boot time on x86 to the serial offer was not found in docs, only the ISO figure.

## 6. The 10 biggest gaps versus real-user testing (clicking and typing, then checking real outcomes)

### Takeaway
The harnesses test the OS's *words-to-handler* logic well, but they skip the layer a person actually touches: pixels, pointer, keyboard focus and the WebKit page. They also grade by reply text more than by real system outcome, and they run in a test-only configuration.

### Cited Findings (each gap, with files)
1. **No real pointer or keyboard input into the guest.** There is no `-qmp`, and no `input-send-event`/`sendkey` anywhere. Virtio tablet and keyboard are present but unused. — [tools/boot-target.sh:43-46](tools/boot-target.sh), [tools/boot-x86.sh:30-33](tools/boot-x86.sh), [tools/isosmoke.sh:20-23](tools/isosmoke.sh), [tools/vmctl.py](tools/vmctl.py)
2. **Typing into the desk is never tested.** `llmos say` calls `Desk.say` directly and bypasses `#in`, Enter handling, focus, the page→Python bridge and the reply rendering. — [desk.py:4049-4055](src/rootfs/usr/lib/llmos/llmos/desk.py), [tools/usecase-run.py:65](tools/usecase-run.py), [tools/desk-smoke.sh:15](tools/desk-smoke.sh), [tools/timed-sweep.sh:61](tools/timed-sweep.sh), [tools/calc-smoke.sh:43](tools/calc-smoke.sh)
3. **"Button presses" are words, not clicks.** `desk-ctl act` and `desk-ctl js …click()` skip hit-testing, overlays and real event handlers. Handlers that are not say-strings (for example `app.focus`, which is `pass`) are invisible to the sweep. — [tools/button-sweep.py:46](tools/button-sweep.py), [desk.py:4117-4119,4129-4130](src/rootfs/usr/lib/llmos/llmos/desk.py), [tools/desk-smoke.sh:27,48](tools/desk-smoke.sh), [docs/research/parity-results.md:1294](docs/research/parity-results.md)
4. **The first-run wizard is never completed the way a person would.** It is bypassed by `desk-ctl wizard` steps, by `onboarded=True` + `sleep 25`, or (x86) by serial console keys. The wizard UI itself (sliders, buttons, passphrase fields) has no pointer-driven test, and the wizard is known to block desk actions. — [tools/test-vm-up.sh:17-19](tools/test-vm-up.sh), [tools/desk-smoke.sh:24-32](tools/desk-smoke.sh), [tools/calc-smoke.sh:21](tools/calc-smoke.sh), [tools/timed-sweep.sh:30](tools/timed-sweep.sh), [tools/x86smoke.sh:20](tools/x86smoke.sh), [docs/tasks/queue.md:15,101](docs/tasks/queue.md)
5. **Screens are captured but never checked.** screendump PNGs have no OCR, pixel or template assertion, so a black, frozen or wrong screen still "passes". — [tools/screendump.py:56-59](tools/screendump.py), [tools/usecase-run.py:119-121](tools/usecase-run.py), [tools/desk-smoke.sh:13](tools/desk-smoke.sh)
6. **Grading is by reply text, not real outcome.** usecase-run asserts nothing. calc-smoke checks substrings like "shows 9". button-sweep counts "any window or reply changed" as ok. Few harnesses check system state (desk-smoke's vault check is the exception). The basic sweep needed hand follow-up to separate bugs from artifacts. — [tools/usecase-run.py:5](tools/usecase-run.py), [tools/calc-smoke.sh:58-74](tools/calc-smoke.sh), [tools/button-sweep.py:51-53](tools/button-sweep.py), [tools/desk-smoke.sh:52-58](tools/desk-smoke.sh), [docs/research/basic-sweep.md:79-91](docs/research/basic-sweep.md)
7. **Tests run in a test-only configuration.** `testreset` (fw_cfg-gated) forces autonomy, internet, autolock 0, screen_off 0, firewall and dialog declines. Dialogs are answered en masse by a regex through `desk-ctl dialog`, not by clicking Yes/No. Shipped behaviour (screen blanking at 10 min, autolock, real confirmation UI) goes untested. — [desk.py:4064-4069,4103-4116,1963](src/rootfs/usr/lib/llmos/llmos/desk.py), [tools/usecase-run.py:80-84](tools/usecase-run.py)
8. **Host-side mocks stand in for VM truth.** test-screen-steps.py fakes `app_press` and produced a recorded false positive. test-atspi.py uses a fake accessibility tree. test-bare-click.py fakes `agent.execute`. agent_smoke.py runs on the Mac with `confirm_* → True`. — [tools/test-screen-steps.py:42-75](tools/test-screen-steps.py), [tools/test-atspi.py:1-10](tools/test-atspi.py), [tools/test-bare-click.py:18-25](tools/test-bare-click.py), [tools/agent_smoke.py:10-18,38-39](tools/agent_smoke.py), [docs/tasks/queue.md:15](docs/tasks/queue.md)
9. **One fragile shared serial channel and fixed sockets, with no isolation.** Text is typed in chunks with sleeps, the prompt is guessed from the log tail, echo gets mixed into captured replies, and only one VM is possible because boot quits any existing VM and deletes its log. The 3 h guard can kill long runs. — [tools/vmctl.py:22-31,75-79](tools/vmctl.py), [tools/tsh:10-12](tools/tsh), [tools/boot-target.sh:21-22,49](tools/boot-target.sh), [tools/vm-lifetime.sh:8](tools/vm-lifetime.sh), run/timed-sweep.tsv row 50
10. **Timing and settle handling are too coarse to reflect what a user experiences.** usecase-run's 9.2 s floor hides latency. Back-to-back requests with no settle check caused false negatives. There is no "visible within N s on screen" measure, no audio sink (`-audiodev none`, so playback outcomes can't be heard or checked), and desk.log was empty on the VM. — [tools/usecase-run.py:65-70](tools/usecase-run.py), [docs/research/basic-sweep.md:91](docs/research/basic-sweep.md), [tools/boot-target.sh:44](tools/boot-target.sh), [docs/tasks/queue.md:38](docs/tasks/queue.md)

### Inferences
- Gaps 1-3 and 5 together mean the whole layer a person touches is untested: the page as rendered, the compositor's pointer and keyboard routing, and the WebKit bridge. Adding a QMP socket to boot-target.sh plus a screenshot-and-locate step (OCR, or AT-SPI/DOM coordinates read via `desk-ctl js`) would close most of it without new guest packages.
- Real OCR false hits on the desk's own UI ([docs/tasks/queue.md:81](docs/tasks/queue.md)) suggest that any pixel-based test oracle must crop to the target window.

### Gaps
- I did not verify whether WebKit in the guest delivers virtio-tablet absolute events correctly under labwc with `-display none`. No harness has ever tried it.
- No information was found on per-element screen coordinates being exposed anywhere (that would be needed to click by name with a real pointer).
