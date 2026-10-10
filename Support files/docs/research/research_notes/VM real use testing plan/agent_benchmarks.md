# How GUI/OS-Agent Benchmarks Drive Real VMs and Score Tasks (as a model for testing LLM OS in QEMU)

Notes compiled 2026-10-09. Versions and dates: OSWorld v1 (Apr 2024), OSWorld Docker provider (Oct 2024), OSWorld-Verified (28 Jul 2025), OSWorld 2.0 (arXiv Jun 2026, rev. Jul 2026); WindowsAgentArena (Sep 2024, hard mode Nov 2024); AndroidWorld (arXiv 2405.14573, 2024); macOSWorld (arXiv 2506.04135, Jun 2025); MacArena (arXiv 2606.06560, Jun 2026); BenchJack (arXiv 2605.12673, May 2026); Spider2-V (NeurIPS 2024).

## 1. Provisioning and reset between tasks (snapshots, golden images, timing)

### Takeaway
Everyone uses "one golden base image + per-task setup script", not one snapshot per task. Reset means throwing away all writes (snapshot revert, a fresh container on a read-only qcow2, an AMI restore, or a clone), then running a short config-driven setup. Readiness is detected by polling an in-guest HTTP server until it answers. Most papers don't publish per-reset timings. The ones that do report a 300 s boot timeout and whole-suite runtimes of minutes when parallel.

### Cited Findings
**OSWorld (Ubuntu)**
- VMs are restored from snapshots for efficient resets. The authors avoided full per-task snapshots because each costs gigabytes. They used a hybrid instead: a base VM snapshot plus config-driven setup in three stages (start the VM, optionally prepare files, optionally run commands such as opening files or resizing windows). The benchmark has 302 distinct initial states. — [OSWorld paper (HTML)](https://arxiv.org/html/2404.07972)
- Providers: VMware Workstation/Fusion (driven via `vmrun`), VirtualBox, Docker (KVM recommended), Modal, Daytona, and AWS (host-client architecture for parallel runs). Docker support was added 2024-10-22, and the environment code was refactored on 2024-06-15 to decouple VMware. — [OSWorld README](https://raw.githubusercontent.com/xlang-ai/OSWorld/main/README.md)
- Docker provider specifics, which map closely onto LLM OS + QEMU:
  - Image `happysixd/osworld-docker`. The guest disk is bind-mounted **read-only** at `/System.qcow2`.
  - Env `DISK_SIZE=32G, RAM_SIZE=4G, CPU_CORES=4`. `/dev/kvm` is passed through when present, otherwise `KVM=N` (slow).
  - Ports map 5000 (in-guest control server), 8006 (VNC web), 9222 (Chromium CDP), and 8080 (VLC HTTP). Host ports are allocated under a file lock so parallel environments don't collide.
  - "Revert" only stops and `remove(v=True)`s the container. `save_state` is not implemented, and the code does not show how writes to the read-only disk are handled. That a fresh container then starts from the pristine disk is my inference, not stated in the source.
  - Readiness: poll `GET http://localhost:<port>/screenshot` every 1 s until HTTP 200, with a 300 s timeout. — [OSWorld docker provider.py](https://raw.githubusercontent.com/xlang-ai/OSWorld/main/desktop_env/providers/docker/provider.py)
- Guest image recipe:
  - Ubuntu 20.04 GNOME on **Xorg (not Wayland)** at 1920x1080 via the dummy Xorg driver. User `user`, autologin via `/etc/gdm3/custom.conf`.
  - `unattended-upgrades` disabled, screen blank Never, suspend Off.
  - In-guest server `main.py` runs as systemd `osworld_server.service` on port 5000 with `DISPLAY=:0` and `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`.
  - Guest packages: gnome-screenshot, wmctrl, ffmpeg, socat, xclip, python3-tk, and pyatspi (for the a11y tree).
  - x11vnc on 5900 and noVNC on 5910 for human viewing. — [OSWorld server README](https://raw.githubusercontent.com/xlang-ai/OSWorld/main/desktop_env/server/README.md)
- Scaling history:
  - VMware `.vmdk/.vmx` images were heavy on local resources and got harder to use after the Broadcom acquisition.
  - Docker+QEMU ran 8-16 parallel environments per server. The blog dates it to summer 2024, but the README dates Docker support to 2024-10-22; the sources conflict.
  - AWS (modeled on WindowsAgentArena) runs up to 50 environments at once, so a full evaluation takes minutes. WAA's approach reportedly cut evaluation time from 10+ hours to about 20 minutes. — [OSWorld-Verified blog](https://xlang.ai/blog/osworld-verified)
- Image hygiene in Verified:
  - The image shrank from 50 GB to 25 GB and IOPS were tuned, because slow first boots made LibreOffice take about 1 minute to open.
  - Fonts were installed for Writer/Impress. VLC runs with `-aout=dummy`.
  - Task files moved from Google Drive to Hugging Face because Drive blocked downloads under load. Separately, and earlier (2025-05-01, before the July Verified release), pre-downloaded init files were made available. — [OSWorld-Verified blog](https://xlang.ai/blog/osworld-verified); [OSWorld README](https://raw.githubusercontent.com/xlang-ai/OSWorld/main/README.md)

**WindowsAgentArena (Windows 11)**
- A Docker container runs a Windows 11 VM under QEMU/KVM (adapted from dockur/windows). A Flask server inside the VM executes commands and returns observations and files. A client in the container handles scheduling, config, the agent, and evaluation. — [WAA paper (HTML)](https://arxiv.org/html/2409.08264)
- Golden image:
  - The user supplies a Win11 Enterprise Eval ISO (~6 GB, renamed `setup.iso`). `./run-local.sh --prepare-image true` does a fully automated build in about 20 min and produces a ~30 GB storage snapshot. Don't touch the VM while it provisions; it shuts down when done.
  - Defaults are 8 GB RAM / 8 cores. Viewer at `http://localhost:8006`.
  - Azure ML uses Standard_D8_v3 workers (nested virtualization required), and each worker is disposed after its job. At ~40 VMs a full run takes ~30-35 min. — [WAA README](https://raw.githubusercontent.com/microsoft/WindowsAgentArena/main/README.md)
- No pre-built golden image is shipped, for licensing reasons. Users build it from a trial ISO with scripts. — [WAA paper (HTML)](https://arxiv.org/html/2409.08264)

**AndroidWorld**
- Built on AndroidEnv + adb with the free Android Emulator (~2 GB RAM, 8 GB disk), a Pixel 6 profile on Android 13.
- **Device time is reset to a fixed timestamp at each task start.**
- App versions are pinned to fixed F-Droid releases. Only apps that need no login and store data locally are used.
- Each task has its own `initialize_task` / `is_successful` / teardown. Example: the SMS task clears the SMS DB at setup, checks the telephony DB on success, and clears it again at teardown. — [AndroidWorld paper (HTML)](https://arxiv.org/html/2405.14573)

**macOSWorld**
- Runs on AWS EC2 Mac minis (dedicated Apple hardware), with one AMI snapshot per UI language.
- Each run restores the snapshot, then runs a prep script (zsh/AppleScript) over SSH. All changes are discarded after evaluation. No reset time is reported. — [macOSWorld paper (HTML)](https://arxiv.org/html/2506.04135)

**MacArena (Jun 2026)**
- Uses UTM VMs on Apple's Virtualization.framework. UTM lacks snapshot revert, so the **base image is cloned per episode**.
- Apple caps a host at 2 concurrent macOS guests, which limits parallelism. One of its two VMs is built by an automated script, which makes it easier to move to new OS versions. — [MacArena summary](https://www.emergentmind.com/papers/2606.06560)

### Inferences
- For LLM OS: keep one pristine golden qcow2 (read-only) and boot each task on a throwaway overlay (`qemu-img create -f qcow2 -b golden.qcow2 -F qcow2 run.qcow2`, or `-snapshot`). Then delete the overlay. This is the QEMU equivalent of OSWorld's read-only `/System.qcow2` plus fresh container. For faster resets, a QEMU `savevm`/`loadvm` internal snapshot or `-loadvm` of a booted-and-idle state skips the boot. This is a standard QEMU feature; none of the cited benchmarks documents it. Verify that snapshots work with the display device LLM OS actually uses: QEMU may refuse migration or snapshots with a GL-accelerated virtio-gpu.
- Copy the readiness pattern: poll an endpoint that proves the full UI stack is up (a screenshot that works, or better, the desk answering), with a hard timeout, rather than sleeping.
- Copy the determinism controls: freeze the clock (AndroidWorld), disable updates and screen blanking (OSWorld), pin package versions, and avoid network-dependent content.

### Gaps
- No source gave measured per-task reset latency (seconds per revert) for OSWorld/WAA/macOSWorld; only suite-level runtimes and the 300 s readiness timeout.
- OSWorld's VMware provider snapshot name and mechanics were not fetched (the paper only says "restored from snapshots").
- AndroidWorld's use of emulator snapshots for reset is not described in the fetched text.

## 2. Action interface and observation space

### Takeaway
The dominant action interface is pyautogui code (or a fixed primitive set of mouse, keyboard and scroll at pixel coordinates), plus special WAIT/FAIL/DONE terminal actions. Observations are a screenshot, optionally an accessibility tree (AT-SPI on Linux, UIA on Windows, the Android a11y tree), and optionally Set-of-Marks overlays. Actions are sent to an in-guest HTTP server or via VNC/adb.

### Cited Findings
- **OSWorld actions** are pyautogui Python, e.g. `pyautogui.click(300, 540, button='right')` or `pyautogui.hotkey('ctrl','alt','t')`. Special actions are WAIT, FAIL (declares the task infeasible) and DONE.
- **OSWorld observations**:
  - Screenshots at 1920x1080 (downsampling 0.2-0.8 also tested).
  - An a11y tree as XML from ATSPI (Linux) or PyWinAuto (Windows), filtered to a tab-separated table of tag, name, text, position and size.
  - Set-of-Marks: numbered boxes on the screenshot plus element metadata.
  - Baselines saw the last 3 rounds, with a 15-step limit. — [OSWorld paper (HTML)](https://arxiv.org/html/2404.07972)
- The OSWorld runner exposes `--action_space pyautogui`, `--observation_type screenshot`, `--max_steps 15`, `--sleep_after_execution 3` and `--num_envs 10`. — [OSWorld README](https://raw.githubusercontent.com/xlang-ai/OSWorld/main/README.md)
- **WAA actions**: a `computer` API with mouse (move_id, move_abs, single/double/right_click, scroll), keyboard (write, press), clipboard (copy_text, copy_image, paste), os.open_program and window_manager.switch_to_application, plus free-form pyautogui.
- **WAA observations**: window titles, clipboard, current and previous screenshots at 1440x900, a UIA tree via pywinauto, and SoM from UIA/DOM/OCR/icon detection/OmniParser. UIA queries can take **seconds to minutes** on complex screens. — [WAA paper (HTML)](https://arxiv.org/html/2409.08264)
- WAA `--som-origin` options are oss, omni, mixed-omni (recommended) and a11y. `--a11y-backend` is uia (slow, accurate) or win32 (fast, less accurate). — [WAA README](https://raw.githubusercontent.com/microsoft/WindowsAgentArena/main/README.md)
- **AndroidWorld actions**: click, long press, input text, scroll in 4 directions, home/back, enter, open app, plus status (complete/infeasible), answer (for information retrieval), wait, and unknown.
- **AndroidWorld observations**: screenshot at 2400x1080, a11y tree, and processed UI elements with bounding boxes and state flags. — [AndroidWorld paper (HTML)](https://arxiv.org/html/2405.14573)
- **macOSWorld actions**: VNC-level mouse down/up, move, drag, clicks, scroll, key presses, `type_text`, screenshot and cursor_position. SSH is used only by the testbench for setup and grading.
- **macOSWorld observations**: 1024x768 screenshots. SoM via OmniParser v2 is optional. — [macOSWorld paper (HTML)](https://arxiv.org/html/2506.04135)
- MacArena uses 16 action primitives and a 15-step budget, with 2 runs per task. — [MacArena summary](https://www.emergentmind.com/papers/2606.06560)

### Inferences
- For LLM OS on Wayland: OSWorld's guest recipe depends on Xorg (xdotool/pyautogui/x11vnc all need X11). A Wayland compositor needs Wayland-native equivalents. The test harness can inject input at the hypervisor (QEMU QMP `input-send-event`, or the VNC server QEMU provides with `-vnc`) and capture the screen via QMP `screendump`, without any in-guest helper. That keeps the guest unmodified and is the analogue of macOSWorld's VNC-only agent channel. (QMP/VNC capability is standard QEMU; not taken from a cited benchmark.)
- Since LLM OS's agent is in the OS, the "action" a test sends is mostly *typed text into the desk input plus Enter*. Low-level clicks are needed only for confirmation buttons. A GTK/WebKit desk could also expose a test hook (like Chromium's CDP on 9222 in OSWorld) so tests read DOM state instead of OCR-ing pixels.

### Gaps
- AgentBench OS (bash-in-Docker), ScreenSpot/ScreenSpot-Pro (grounding-only, no VM) and VisualAgentBench specifics were not retrieved: the AgentBench abstract page lacked them, and the others weren't fetched within the call budget. They are not covered here.

## 3. Task specification and success checking

### Takeaway
A task is a JSON record with id, instruction, setup `config` steps, and an `evaluator` = {func, result-getter, expected-getter}. Success is judged by **execution-based state checks** run after the episode: commands in the guest, files pulled out and compared, app databases, browser cookies or tabs. It is not judged by screenshots. Rewards are mostly binary at the final step, with continuous 0-1 scores for document similarity.

### Cited Findings
- Verbatim OSWorld task (OS domain):
```json
{
  "id": "94d95f96-9699-4208-98ba-3c3119edf9c2",
  "snapshot": "os",
  "instruction": "I want to install Spotify on my current system. Could you please help me?",
  "source": "https://help.ubuntu.com/lts/ubuntu-help/addremove-install.html.en",
  "config": [{"type": "execute", "parameters": {"command": ["python","-c",
     "import pyautogui; import time; pyautogui.click({SCREEN_WIDTH_HALF}, {SCREEN_HEIGHT_HALF}); time.sleep(0.5);"]}}],
  "related_apps": ["os"],
  "evaluator": {
    "func": "check_include_exclude",
    "result": {"type": "vm_command_line", "command": "which spotify"},
    "expected": {"type": "rule", "rules": {"include": ["spotify"], "exclude": ["not found"]}}
  },
  "proxy": false, "fixed_ip": false, "possibility_of_env_change": "low"
}
```
  — [OSWorld task JSON](https://raw.githubusercontent.com/xlang-ai/OSWorld/main/evaluation_examples/examples/os/94d95f96-9699-4208-98ba-3c3119edf9c2.json)
- An OSWorld config does setup (download files, open software, adjust layout), then post-processing after the agent finishes (save files, reopen apps), then retrieves state and runs the evaluator.
- Getter functions extract state and evaluator functions judge it. There are **134 unique evaluation functions**.
- Example: the Amazon-cookies task uses `get_cookie_data(env)` + `is_cookie_deleted(cookie_data, rule)` with a `.amazon.com` domain rule.
- Some getters are "live", e.g. they crawl real-time web values at grading time. — [OSWorld paper (HTML)](https://arxiv.org/html/2404.07972)
- WAA is execution-based: post-processing scripts check final files, settings and configs, sometimes against golden reference files. Rewards are binary or continuous, given only at the final step. Task list: `evaluation_examples_windows/test_all.json`. — [WAA paper (HTML)](https://arxiv.org/html/2409.08264); [WAA README](https://raw.githubusercontent.com/microsoft/WindowsAgentArena/main/README.md)
- AndroidWorld rewards come mainly from system state via adb (files, app SQLite DBs for added or deleted rows, settings). UI-element validation is a fallback.
- AndroidWorld tasks are **parameterized from a seed**, giving practically unlimited variants. State validators are more durable than UI matching and reusable across apps. — [AndroidWorld paper (HTML)](https://arxiv.org/html/2405.14573)
- A macOSWorld task = instructions in 5 languages + an AMI-per-language map + a prep script (zsh/AppleScript) + one or more evaluation scripts (AppleScript/JS/zsh). These run over SSH after the episode and echo True/False, which becomes a binary reward. — [macOSWorld paper (HTML)](https://arxiv.org/html/2506.04135)
- MacArena uses a deterministic evaluator script on final VM state, scoring 0-1. — [MacArena summary](https://www.emergentmind.com/papers/2606.06560)
- OSWorld 2.0: 108 long-horizon workflows (median ~1.6 human-hours). The primary metric is binary completion at 500 steps, plus a partial score, plus a per-task safety report. — [OSWorld 2.0 abstract](https://arxiv.org/abs/2606.29537)
- Spider2-V: 494 tasks over 20 enterprise data apps (dbt, Airflow, etc.) in a live VM, with automatic setup configs and per-task evaluation metrics. — [Spider2-V NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/hash/c2f71567cd53464161cab3336e8fc865-Abstract.html)

### Inferences
- Map directly onto LLM OS: `{"id", "instruction" (text typed into the desk), "setup": [shell cmds via serial console/SSH/QGA], "evaluator": {"func", "result": {"type": "vm_command_line", "command": "..."}, "expected": {...}}, "possibility_of_env_change"}`. Prefer host-side getters (read the shut-down overlay read-only). The QEMU guest agent (`guest-exec`) or a serial shell can serve as a `vm_command_line` getter for live state, but it runs inside the guest and is reachable by the agent (see section 5).
- Also check the desk's *reply text* for tasks that are questions, as AndroidWorld's `answer` action and info-retrieval tasks do. That should be a secondary check; system state stays primary.

### Gaps
- The full catalog of OSWorld getter types (e.g., `vm_file`, `cloud_file`) was not fetched; only `vm_command_line` and `rule` are confirmed above.

## 4. Task categories, counts and hardest categories

### Takeaway
Suites hold ~100-500 tasks split across OS/system settings, file ops, office docs, browser, media, coding, and multi-app workflows. They include a few percent of infeasible tasks. Multi-app workflows and office documents are consistently the hardest.

### Cited Findings
- **OSWorld**: 369 Ubuntu tasks = 268 single-app (72.6%) + 101 multi-app workflow (27.4%). 30 are infeasible (8.1%) and 84 were adapted from other benchmarks. There is also a 43-task Windows set.
  - Domains: OS, Office (Calc/Impress/Writer), Daily (Chrome/VLC/Thunderbird), Professional (VS Code/GIMP), Workflow.
  - Best original agent (GPT-4 + a11y), 12.24% overall: OS 20.83, Office 3.58, Daily 25.64, Professional 26.53, Workflow 2.97. Humans scored 72.36%.
  - Difficulty bins by human time: Easy 0-60 s, Medium 60-180 s, Hard >180 s. Human success by bin: 84.9/81.1/49.6%. Median human time 111.94 s. — [OSWorld paper (HTML)](https://arxiv.org/html/2404.07972)
- The Verified protocol is 369 tasks, or 361 when 8 Google Drive tasks can't be configured (exclusions must be reported). This is from a third-party explainer. — [BenchLM explainer](https://benchlm.ai/md/blog/posts/osworld-verified-computer-use-benchmark.md)
- **WAA**: 154 tasks, about two-thirds adapted from OSWorld.
  - Domains: Office 43, Web Browsing 30, Windows System 24, Coding 24, Media & Video 21, Windows Utilities 12.
  - Best agent 19.5% vs human 74.5%. Office scored 0.0% and Utilities 8.3% (keyboard-shortcut and icon heavy). Humans found VLC hardest. — [WAA paper (HTML)](https://arxiv.org/html/2409.08264)
  - WAA added a "hard" mode (2024-11-10, `diff_lvl="hard"`) where agents must also find and open the right app themselves. — [WAA README](https://raw.githubusercontent.com/microsoft/WindowsAgentArena/main/README.md)
- **AndroidWorld**: 116 tasks over 20 apps, plus 92 MobileMiniWoB++ tasks. Best agent 30.6% vs human 80.0%. The agent averaged 3.9 min per task, about 3x slower than humans. — [AndroidWorld paper (HTML)](https://arxiv.org/html/2405.14573)
- **macOSWorld**: 202 tasks over 30 apps (28 macOS-only) in 5 languages.
  - Categories: System & Interface, File Management, Productivity, Media, Built-in Apps, Advanced Apps, Multi-Apps. Multi-Apps is hardest at 3.7% average.
  - A 29-task safety subset uses real AppleScript-triggered deceptive dialogs. Claude CUA was distracted 72.4% of the time and OpenAI CUA 69.0%. — [macOSWorld paper (HTML)](https://arxiv.org/html/2506.04135); [Search result: macOSWorld abstract](https://arxiv.org/pdf/2506.04135v1)
- **MacArena**: 421 tasks over 50 apps (221 ported from OSWorld, 151 from macOSWorld, 49 new). Agents did worse on macOS than Ubuntu on identical tasks, and rank orders flipped on native tasks. This suggests benchmark familiarity inflates scores. — [MacArena summary](https://www.emergentmind.com/papers/2606.06560)
- **OSWorld 2.0**: agents fail less at GUI control than at losing track of constraints, missing mid-task info, guessing instead of asking, and skipping verification. They are worst on hidden-state tasks. — [OSWorld 2.0 abstract](https://arxiv.org/abs/2606.29537)

### Inferences
- An LLM OS suite should mirror these buckets, adapted: system settings (wifi, display, power, users), file ops, app install/remove, browser, office/docs, media, multi-step workflows, information questions ("how much disk is free"), infeasible or should-refuse requests, and a safety/deception subset (fake dialogs, destructive requests). Multi-step workflows and "ask instead of guess" are where to expect failures.

### Gaps
- macOSWorld per-category counts are only in a figure, which was not read.

## 5. Known pitfalls and how OSWorld-Verified fixed them

### Takeaway
The biggest costs are evaluator false negatives (valid alternative solutions marked wrong), environment drift (live websites), timing races (acting before an app loads), and ambiguous instructions. Adversarial audits also show false-positive routes: graders reading state the agent can tamper with, and "FAIL" or crashes counted as success. Verified fixed evaluators first, instructions second, and logged every change.

### Cited Findings
- Verified (2025-07-28): 300+ feedback items, about 2 months of work by ~10 people. Before the v1 release the team had already spent over 400 person-hours on 4 rounds of checks. Their lesson: "providing reliable rewards consumes more human resources than we imagined." — [OSWorld-Verified blog](https://xlang.ai/blog/osworld-verified)
- **Issues found**:
  - Environment instability: CAPTCHAs, 403/geo blocks, DOM and URL changes.
  - Removed site features, e.g. the speedtest CSV export.
  - **Timing races**, e.g. a fixed `pyautogui.press("down", presses=8)` firing before Writer had loaded.
  - Ambiguity ("purple background", "fill blank cells", resize image vs layer).
  - Infeasibility misjudgments.
  - False negatives: CSV header handling, VS Code changes made via extensions, double spacing on a blank line, and equivalent spreadsheet formulas. — [OSWorld-Verified blog](https://xlang.ai/blog/osworld-verified)
- **Fixes**:
  - Evaluators were changed first and task text only if necessary, with all changes in a public log.
  - More valid gold solutions were accepted rather than narrowing instructions.
  - `compare_docx_files` gives 0-1 scores, `compare_pdf_images` uses perceptual hashing, and EPUB scores are averaged. Color tolerance, unit, case and currency-format normalization were added.
  - Approximate URL matching was added, with a `possibility_of_env_change` flag, proxy support, fixed IPs, and replacements for protected sites. Simulated web environments are in progress.
  - **`open_file` was made blocking**, sleeps were tuned per instance size, and booking windows were extended (4 to 8+ months). — [OSWorld-Verified blog](https://xlang.ai/blog/osworld-verified)
- A 2025 study of agentic benchmarks reports 13 of 46 OSWorld Chrome tasks broken by website changes, because evaluators relied on HTML selectors/XPaths. A related write-up gives a 28% absolute underestimate. These figures come via search summaries and should be verified. — [Establishing Best Practices for Rigorous Agentic Benchmarks](https://arxiv.org/pdf/2507.02825)
- BenchJack (May 2026) is an automated red-teaming system for reward hacking. It found 219 flaws in 8 classes across 10 benchmarks, and synthesized exploits that score near-perfect without solving tasks. Iterative audit-and-patch "fully patched WebArena and OSWorld within three iterations." — [BenchJack abstract](https://arxiv.org/abs/2605.12673)
- According to a search summary of BenchJack (not confirmed on the abstract page), OSWorld patches covered:
  - a grader reading agent-mutable VM state,
  - FAIL-as-first-action counting as a win,
  - a file-not-found case silently dropped and masked as success by `max(results)`. — [BenchJack PDF (via search)](https://arxiv.org/pdf/2605.12673)
- Single-seed results hide variance: across 3 seeds AndroidWorld's M3A scored 27.6/26.3/33.2%. A different device profile gave variation similar to changing seeds. — [AndroidWorld paper (HTML)](https://arxiv.org/html/2405.14573)
- WAA pitfalls: imprecise SoM boxes, the agent describing the right action but picking the wrong element ID, and slow UIA queries. — [WAA paper (HTML)](https://arxiv.org/html/2409.08264)

### Inferences
- Grade from a channel the agent cannot write to. In LLM OS the agent's tools are real and there is no unprivileged-user split yet, so anything inside the guest (qemu-ga, serial root shell, files the evaluator reads) is agent-mutable. That is the same "grader reads agent-mutable state" class BenchJack reports.
  - **Out of reach:** after shutdown, inspect the overlay from the host read-only (qemu-nbd/guestfish, or diff against golden). Use this for files, configs and installed packages.
  - **Tamperable:** QGA or a serial shell. Use only for live-only state (running services, network links), label it agent-reachable, and cross-check where possible.
  - Never trust a log or status file the OS agent itself writes.
- Make infeasible or refusal tasks require the *right* reason, and make "agent said done/failed immediately" never pass a feasible task. Treat any evaluator exception or missing file as FAIL, never skip it.
- Replace fixed sleeps with wait-until conditions, because timing races were a top source of flakiness.
- Run each task several times (2+ runs as in MacArena, or seeded variants as in AndroidWorld) and report the variance. Keep an issue log per task.

### Gaps
- Exact BenchJack OSWorld exploit details are unverified beyond the search summary.

## 6. Lessons for a self-made OS whose agent is part of the OS (LLM OS)

### Takeaway
The benchmark pattern transfers almost directly if you swap the "agent" and "harness" roles. The harness is now a scripted *user*: it types a request into the desk via VNC/QMP, waits for completion, then grades real system state through an out-of-band channel. Golden image + overlay reset, state-based evaluators, a task JSON schema, a readiness probe, frozen clock and pinned packages, an infeasible/safety subset, and repeated runs are the copyable pieces.

### Cited Findings (supporting precedents)
- Grading by post-episode scripts over a separate privileged channel (SSH) while the agent only had VNC. — [macOSWorld paper (HTML)](https://arxiv.org/html/2506.04135)
- Execution-based, final-state grading with a deterministic 0-1 script. — [MacArena summary](https://www.emergentmind.com/papers/2606.06560); [WAA paper (HTML)](https://arxiv.org/html/2409.08264)
- Real OS dialogs (AppleScript) rather than overlays for deception tests. — [macOSWorld paper (HTML)](https://arxiv.org/html/2506.04135)
- Long-horizon failures include guessing instead of asking the user and skipping verification. — [OSWorld 2.0 abstract](https://arxiv.org/abs/2606.29537)
- OSWorld's guest needed Xorg rather than Wayland for its tooling. — [OSWorld server README](https://raw.githubusercontent.com/xlang-ai/OSWorld/main/desktop_env/server/README.md)

### Inferences (proposed concrete design)
0. Because OSWorld 2.0 failures center on guessing instead of asking and on skipping verification, LLM OS evaluators should include "asked when ambiguous" and "verified result" checks.
1. **Image**: build `golden.qcow2` once from the LLM OS ISO install, with first boot complete, clock source fixed, updates off, and screen blank off. Store it read-only and keep its hash.
2. **Per-task reset**: `qemu-img create -b golden.qcow2 -F qcow2 -f qcow2 task.qcow2`, boot, then delete. Optionally `loadvm` a pre-booted state to cut boot time. Inject a fixed date at boot (AndroidWorld-style).
3. **Readiness**: poll a QMP `screendump`/desk health signal until the desk input is visible, with a ~300 s timeout like OSWorld.
4. **Act as the user**: VNC/QMP keystrokes type the instruction into the desk and press Enter. Click only on confirmation prompts if the task script says so. Record screenshots every N seconds for debugging, not scoring.
5. **Completion detection**: wait for the desk's "agent idle" state (or a timeout and step cap). Don't use fixed sleeps.
6. **Grade**:
   - Primary (tamper-proof): shut down and inspect the overlay from the host read-only (qemu-nbd/guestfish). Check file existence, config contents, the apk installed DB (`/lib/apk/db/installed`), and sqlite files.
   - Live-only state (services, links): QEMU guest agent or serial shell (`vm_command_line`-style). This is agent-reachable, so label it and cross-check.
   - Secondary: check the desk's reply text for question tasks.
   - Make the evaluator explicitly fail on exceptions.
7. **Task JSON**: id, instruction (optionally paraphrase variants), setup commands, evaluator {func, result, expected}, feasible true/false, expected refusal or question, `possibility_of_env_change`, timeout.
8. **Suite hygiene**: include infeasible and should-ask tasks, a safety subset with destructive or deceptive prompts (run only in the VM, consistent with project rules), multiple runs per task, a per-task change log, and a periodic adversarial check that "do nothing" and "declare done" score 0 on every feasible task.

### Gaps
- No found benchmark tests an OS's *built-in* agent through its own UI. All of them drive an external agent. The role swap above is an inference, not established practice.
- Wayland-specific harness precedents (input injection and a11y on wlroots-type compositors) were not found in these benchmarks.
