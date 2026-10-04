# How LLM OS was built and tested

Everything in the image comes from an official, verifiable source. The build
is a script (`src/install.sh`) that runs inside the official Alpine live ISO
under QEMU and installs onto a virtual disk with Alpine's own tools; the OS
itself is `src/rootfs/` (≈2 000 lines of Python, no third‑party libraries).

## Sources and hashes

| Component | Source | Verification |
|---|---|---|
| Base OS | Alpine Linux 3.24.2 `alpine-virt-3.24.2-aarch64.iso` from dl-cdn.alpinelinux.org | SHA‑256 `a57ba668b5f6b17a670fcf8e799d5d7fe43766ed086d6ce2927b0625bf43dbf6` (matches `latest-releases.yaml`) |
| Packages | Alpine v3.24 `main` + `community` repositories | apk signature verification (Alpine's signing keys) |
| Model runtime | `llama-server` / `llama.cpp-cpu` 0.0.9564-r0 (Alpine package of llama.cpp b9564) | apk signature |
| Speech to text | `whisper.cpp` 1.9.3-r0 (Alpine package) | apk signature |
| Default model | `mistralai/Ministral-3-3B-Instruct-2512-GGUF` → `Ministral-3-3B-Instruct-2512-Q4_K_M.gguf` (Mistral AI's own repo, Apache‑2.0) | SHA‑256 `9ed150d4367e68df0ac8e1540f6ddc65b42d0ee26378329d1ecbca60f93fc5f8` checked by the installer and again by the OS before any download is used |
| Voice model | `ggerganov/whisper.cpp` → `ggml-base.bin` | SHA‑256 `60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe` |
| Other catalog models | official repos of Google (`google/gemma-4-*-gguf`, `ggml-org/gemma-4-E4B-it-GGUF`), IBM (`ibm-granite/*-GGUF`), Mistral AI, Liquid AI | per‑file SHA‑256 pinned in `src/rootfs/usr/share/llmos/catalog.json` (taken from each repo's LFS metadata) |
| Media | `yt-dlp` 2026.08.19, `mpv` 0.41.0, `quickjs-ng` (Alpine packages) | apk signature |
| Privacy | `tor` 0.4.9.13, `nftables` 1.1.6, `cryptsetup` 2.8.6 (Alpine packages) | apk signature |
| Host tooling | QEMU 11.1.1 (Homebrew) | — |

No package was built by hand; there are no binaries in `src/`.

## Build procedure

1. Boot the official ISO under QEMU/HVF with an empty 16 GB qcow2 disk and
   the project directory served over HTTP to the guest (`10.0.2.2`).
2. Inside the guest, run `src/install.sh`. It:
   - configures networking and the official repositories;
   - partitions the disk (GPT, 128 MB EFI + ext4 root) and installs the base
     system with Alpine's `setup-disk` (`BOOTLOADER=grub USE_EFI=1`);
   - installs the package set above;
   - unpacks `src/rootfs/` (the OS: console, agent, tools, services);
   - fetches the model and the voice model and **refuses to continue on a
     hash mismatch**;
   - locks root's password, removes all login gettys except the console
     (`/usr/libexec/llmos-login`), puts `/tmp` and logs in RAM, enables the
     firewall, the model server, the scheduler and the hardware setup
     service, and sets GRUB's timeout to 0;
   - scrubs build traces (apk cache, shell history, logs) and trims the disk.
3. Power off, compact the disk with `qemu-img convert`, record the SHA‑256.

The x86‑64 image (`tools/build-image-x86.sh`) runs the same `install.sh` in
the x86‑64 ISO under QEMU's emulation (TCG, direct kernel boot). Because
`setup-disk` cannot lay out a disk that boots on both firmware types, that
branch bootstraps by hand: GPT with a 2 MB BIOS‑boot partition, a 256 MB EFI
system partition and the ext4 root; `apk --initdb` for the base system; the
`linux-lts` kernel, Intel/AMD microcode and the firmware subsets; an
`mkinitfs` with `nvme mmc kms`; `grub-install` for `i386-pc` and for
`x86_64-efi --removable` (`BOOTX64.EFI`, no NVRAM entry needed).

Final images were built from the frozen sources on 2026‑10‑01 (see the
last "Final verification" row of the test table for the exact times; arm64
3.5 GB in ~1.5 min — apk from the CDN, the model copied from the host cache —
and x86‑64 4.0 GB in ~5 min under emulation). `dist/SHA256SUMS`
lists both images and the model file. Tests of the shipped images run on
throw‑away overlays (`boot-target.sh`, `boot-x86.sh`), so the files in
`dist/` are exactly the build output.

Rebuild: `tools/` contains the VM driving scripts used for the build and the
tests (`vmctl.py` types into the serial console and waits for output;
`acceptance.sh` holds the test legs listed in its header; `boot-target.sh`,
`boot-x86.sh` and `x86smoke.sh` boot the images for testing, optionally in
host‑GPU mode; `mailfixture.sh` is the throw‑away mail server used by the
email tests, never part of an image; `test-intent.py` and `test-uispec.py`
unit‑test the deterministic shortcuts and fuzz the window‑spec validator on
the host, no VM needed; `desk-smoke.sh`, `desk-edge.sh`, `spec-check.sh`,
`install-test.sh` and `spec-matrix.sh` are the graphical, edge‑case,
brief‑compliance, installer and hardware‑matrix runs). Nothing waits
forever: every test or build VM gets a hard lifetime from
`vm-lifetime.sh` (3 h for tests, 2 h for builds, `LLMOS_VM_LIFETIME`
overrides), every console step has a timeout, and the waiters in the test
scripts are counted loops; `cleanup.sh` quits whatever is left.

## Design in one page

- **Desk** (`desk.py`, `usr/share/llmos/desk/`, `uispec.py`): the graphical
  interface on the screen. One full‑screen WebKitGTK view inside the `labwc`
  compositor renders what the OS generates: a command bar, the streaming
  reply, and *windows* built from block specs (`text`, `kv`, `stat`, `list`
  with per‑item actions, `table`, `image`, `buttons`, `choices`, `toggle`,
  `form`, `quote`, `code`, `media`, `sources`). Every control is a request in
  words (`say`), so a button can never do more than the owner could say and
  everything is audited alike. Python and the page talk in‑process (no
  sockets, no ports); the agent runs in a worker thread and confirmations
  block it until the owner answers on screen. First‑run wizard, vault unlock
  and "while you were away" are screens of the same page. Colours, corners,
  language and an optional real‑photo wallpaper come from the appearance
  settings as CSS variables and re‑apply live. Programs the owner opens
  (browser, terminal, mpv) are ordinary decorated windows of the compositor
  (Alt‑Tab, Super+Q, Super+Esc; dark theme in `/usr/share/themes/llmos`). A
  root‑only control socket (`llmos say …`) lets the text console and the
  tests drive the desk. In a VM everything renders on the CPU (pixman /
  cairo / WebKit CPU path); on real GPUs Mesa is used. First‑run set‑up is
  six cards (welcome → language pre‑selected from the launcher's locale →
  name → time zone with a city search over the tz database → autonomy with
  plain explanations → internet yes / via Tor / offline, plus a Wi‑Fi step
  when a laptop has no connection yet → passphrase with a Show button), then
  three one‑click example requests and a *Try saying* window. The interface
  scales ("make everything bigger"), the status chips are buttons, ↑/↓ recall
  requests, windows maximize. The computer's own presence is an orb at the
  left of the bar: it breathes at idle, shows a turning ring while it thinks,
  pulses while it listens or reads aloud, turns amber when a dialog needs the
  owner's answer and grey when the model is down; the reply card carries an
  *LLM OS · thinking… / working… / writing…* header, and card and bar always
  sit above the windows (the stage is its own stacking layer), which grow out
  of the bar when the computer opens them. A one‑line answer steps aside by
  itself after six seconds so the windows stay in view; an empty desk greets
  the owner by name with three suggestions (boot, lock and the welcome card
  show the same orb). Motion is a setting — *Animations: Full / Reduced /
  Off* (`appearance.motion`; "turn off animations", "fewer animations",
  "reduce motion"): every duration is one CSS variable (`--dur`), *Reduced*
  keeps the state changes but stops everything continuous. Continuous motion
  is rationed because a software‑rendered screen (VMs) pays ~14 ms of CPU per
  change: the idle glow breathes from a timer at 4 changes/s (10 on real
  hardware), the ring turns at 8/s, blinks use `steps(1)`; measured in the
  4‑core VM the desk costs ≈7 % of one vCPU at idle with *Full*, ≈3.5 % with
  *Reduced* or *Off*, ≈19 % while thinking — and on a 2‑core 4 GB VM with
  the model inside, generation measured the same ≈25 tokens/s with the
  thinking animations showing at *Full*, *Reduced* or *Off* (three 48‑token
  completions each), so *Full* is the default everywhere. Files are windows too: `show_files` (*Home*,
  folders first, Open/Delete), `open_file` (text and code windows, pictures,
  music/video through mpv, PDFs through a viewer if one is installed),
  `delete_file` (to `~/.Trash` with the origin recorded in
  `.Trash/.origins.json`; a file already in the trash is deleted for good;
  home folder only; asks first in balanced mode), `restore_file`,
  `empty_trash` (the trash window has *Restore* / *Delete for good* /
  *Empty the trash* buttons) and `screenshot` (`grim` → `~/Pictures`, shown
  as an image window). A finished reply folds to one line above the bar as
  soon as the owner raises a window (click to unfold), so a long answer never
  hides what they are working on. Lists and notes (`store.notes`,
  `note_add` / `notes_show` / `note_done` / `note_remove`, `notes.json` in
  the vault) are windows with Done/Undo/Remove buttons; "add milk to my
  shopping list", "remember to …" (a to-do, as opposed to "remember that …",
  a fact), "note that …", "tick off …", "clear my … list" are deterministic.
  Timers and "remind me in N minutes to …" map to `schedule_task`; when a
  background result lands while the owner is at the desk it shows the card,
  a toast, a chime (`/usr/share/llmos/chime.wav`, generated at packaging
  time, played with aplay/mpv when a sound card exists) and, if replies are
  read aloud, speaks it. Auto-lock (`autolock` minutes; the page pings
  `active` at most every 20 s; a 30 s poll locks the vault after the idle
  time) is offered in *Settings* when a vault exists. Brightness and volume
  phrases ("brightness 60", "turn the screen down", "louder", "mute") are
  deterministic with relative steps (`delta`), and the keyboard's media keys
  go through `llmos brightness` / `llmos volume` so the same control logic
  (first playback control the card offers) serves both; Super+Left/Right
  snap program windows to half the screen. A vault can be created after
  first boot ("set up a passphrase" → `set_passphrase`): on the desk a form
  whose submit `post`s `vault.create` straight to the OS (the passphrase
  never passes through `say`, history or the audit log), on the console the
  onboarding prompt; `vault.create` moves the existing home into the new
  vault. Resilience, found by pasting a 7 000‑character request into a 4 GB
  VM: llama‑server's RAM prompt cache (`--cache-ram`, 8 GB by default, ~550 MB
  per saved prompt state) pushed the server to 3.7 GB and the kernel killed
  it, and nothing restarted it — so the model and scheduler services now run
  under OpenRC's `supervise-daemon` (respawn after 4–5 s, unlimited), the
  server starts with `--cache-ram 0` (KV prefix reuse via `--cache-reuse`
  stays), and the agent clips any request over 6 000 characters (head and
  tail kept, an activity line says so) before it reaches the model. The
  lock, found self‑defeating on the same VM: WebKit's network process kept
  cache files open under the home folder, the unmount failed silently, the
  lock screen appeared, and the 20 s poll (meant for a vault opened from the
  console) saw the vault still mounted and quietly went back to the desk.
  Now the desk's WebKit session is ephemeral (nothing on disk at all), no
  process the desk starts has its working directory inside the vault,
  locking first closes the programs the owner opened (and stops media), a
  lock that still cannot close the vault says so and stays locked, the
  passphrase is verified against the LUKS header even when the vault is
  still mounted (`vault.verify`, `cryptsetup --test-passphrase`), and the
  smoke test asserts the vault is unmounted after `lock`. The second holder
  turned out to be Mesa's shader cache (`~/.cache/mesa_shader_cache/index`,
  mapped by the desk process even with software rendering), so the desk and
  the console sessions keep every cache outside the vault
  (`XDG_CACHE_HOME=/var/cache/llmos`, `MESA_SHADER_CACHE_DIR`).
- **Console** (`console.py`, `ui.py`): the same OS as text, on the serial
  line or when there is no display — generated from the same appearance
  settings (any colour name or hex, auto‑adjusted to stay readable; frames;
  per‑area language, six built in, any other translated once by the model and
  cached). Window specs render as framed boxes. While the desk owns the
  screen the console waits for set‑up/unlock to happen there.
- **Agent** (`agent.py`): one system prompt (the OS's identity and rules),
  llama.cpp's OpenAI‑style tool calling with streaming, up to 8 tool steps
  per request, clean text‑only history between requests (raw tool traffic
  confuses small models and breaks strict chat templates), an honesty guard
  that catches "I did X" with no tool call, and a tiny deterministic
  shortcut for explicit memory statements.
- **Tools** (`tools.py`): `run_command` (root shell), files, `install_app`,
  appearance, memory, web search/read (DuckDuckGo HTML, Brave fallback),
  real photos (Wikimedia Commons with credit), scheduling, calculator,
  media (yt‑dlp + mpv), brightness/volume, settings (autonomy, internet,
  Tor, focus mode, time zone, voice), models (catalog, download+verify,
  switch, remove), power. Each tool carries a risk class; shell commands are
  classified (read / change / destructive) so the autonomy policy can decide
  without asking the model.
- **Policy** (`agent.execute`): internet yes/ask/no and the autonomy level
  are enforced around every tool call and audited; the firewall (`nftables`)
  makes "no internet" real; Tor routes all web traffic via SOCKS with remote
  DNS; focus mode blocks feed sites in `/etc/hosts`.
- **Host‑GPU link**: the launcher serves the model on the Mac's GPU on the
  first free local port (8080, 8090, …) and tells the guest through fw_cfg;
  `llmos-model` records the URL and re‑applies the firewall so that port on
  10.0.2.2 stays reachable even with the internet set to *no* (found on this
  Mac, where a media player already held 8080).
- **Scheduler** (`scheduler.py`, OpenRC service): runs due tasks headlessly
  through the same agent and policy (never destructive unattended), drops
  results in an inbox shown at the prompt; plain‑language times ("every
  weekday at 8", "in 20 minutes", "tomorrow 9am", cron) parsed in `store.py`.
- **Vault** (`vault.py`): LUKS2/argon2id container mounted over `/root`,
  created and unlocked from the console; no key escrow.
- **Email** (`mail.py`): IMAP (read, move, archive, trash) and SMTP (send,
  threaded reply) with the standard library only; the account lives in the
  vault; provider hosts are known for the common services. `mail_triage`
  is the "inbox zero" workflow: each unread message is classified by the
  on‑device model into a fixed JSON shape (category / needs reply / urgent /
  one‑line summary), noise is archived, the rest is listed with ids for
  `mail_reply`. Mail content is fed back to the model as untrusted data.
- **Apps and windows** (`open_app`, `media.py`): with the desk running,
  graphical programs become windows in its compositor (`labwc`); without it
  (text console on a machine with a display) they run under `cage`, a
  one‑window kiosk; without a display, audio only. Video and music play in
  `mpv` as a window, controlled over its IPC socket from the *Now playing*
  card (pause, resume, stop, volume) or by voice. `show_screen` lets the
  model compose a window of its own from the same block types.
- **Installer** (`installer.py`, `install_to_disk`): from the running
  system onto the computer's disk — *alongside* (a Linux partition in the
  largest free GPT gap, the existing EFI system partition shared, other
  systems untouched) or *whole* (fresh GPT: ESP + BIOS‑boot + root). `sfdisk`
  partitions, `rsync` copies the live root (settings, memory and the vault
  move with it), GRUB is installed to `EFI/llmos` and — where that path is
  free, on Apple firmware always — to the removable path Apple's Startup
  Manager lists as "EFI Boot"; on BIOS machines to the MBR; `os-prober` adds
  the other systems to the menu. The request is deterministic ("install LLM
  OS on this computer"); the plan is shown first and the *Install now* button
  carries a one‑time token, so neither the model nor a stray request can
  write to a disk unasked.
- **Wi‑Fi** (`wifi_scan` / `wifi_connect`): `iwd` with its built‑in DHCP;
  present only where an adapter exists.
- **Real‑computer image** (x86‑64): `install.sh` bootstraps the root with
  `apk --initdb` (no `setup-disk`), GPT with a BIOS‑boot partition + ESP,
  `linux-lts`, firmware sub‑packages, `intel-ucode`/`amd-ucode`, an initramfs
  with `nvme mmc kms`, `grub-install` for `i386-pc` and `x86_64-efi`
  (`--removable`, so any firmware finds it), `net.ifnames=0`, screen console
  preferred. Built and boot‑tested under QEMU's x86 emulation.
- **Voice** (`voice.py`): push‑to‑talk, energy‑based end‑pointing,
  whisper.cpp on device; espeak‑ng out. Mic from ALSA on real hardware, or
  from the host bridge under QEMU on macOS.
- **Boot**: GRUB (UEFI) → Alpine/OpenRC → `llmos-hw` (drivers, firewall,
  time zone from the launcher) → `llmos-model` (llama‑server on
  127.0.0.1:8080) + `llmos-scheduler` → console on the serial line and tty1.

## Against the brief, point by point

The original brief (`Original Prompt to programmer.txt`) asked for specific
things. Where each stands, with the evidence:

| The brief asked for | Status | Where / evidence |
|---|---|---|
| Iterate in a virtual machine; validate it boots | ✅ | both images boot under QEMU (HVF and TCG); every test in this file runs in a VM |
| An OS that *is* the model: no apps, no traditional UI, the UI is generated | ✅ | one command bar; everything else is a window the OS composes from block specs (`uispec.py`); the model can compose its own (`show_screen`); programs exist only when asked for |
| "Speak what you want and the computer does it", brightness to YouTube | ✅ | push‑to‑talk (whisper.cpp on device, mic bridge on the Mac); `set_brightness`/`set_volume` (honest in a VM), YouTube via yt‑dlp + mpv in a window; spec‑check rows below. Since 1.4: **system‑wide dictation** — Super+D anywhere records, transcribes and types at the cursor in any program (`wtype`, the compositor's virtual keyboard), free and on the machine; choosable speech models (Whisper Tiny / Base / Small / **large‑v3‑turbo**), each hash‑verified (`tools/test-voice.py`, `tools/dictate-smoke.sh`) |
| Intelligent, remembers preferences | ✅ | memory (`remember`/`forget`, near‑duplicate proof), settings, theme, language, wallpaper and mail account persist; verified across power cycles |
| Entirely on device, private | ✅ by default | llama.cpp on 127.0.0.1 (or the same Mac's GPU over the VM's private link); inbound firewall drops everything; logs and `/tmp` in RAM. Since 1.3 the owner *may* add an online model (Claude or an OpenAI‑compatible service) at set‑up or later: the *where it thinks* slider/setting is `local` (the default: the online path is never taken), `ask` (here; one question before a big request goes online, and the service never gets the memory or name) or `cloud`. Every request that goes online is in the audit log, the orb turns blue, the key lives inside the vault, and with the internet off nothing goes online (`tools/test-cloud.py`, `tools/brain-smoke.sh`) |
| Goal 1: private and secure, "no backdoors, no recovery" | ✅ | LUKS2/argon2id vault with no recovery key; root password locked; only signed Alpine packages and hash‑pinned model files; Tor routing incl. DNS; passwords redacted from audit/screen; all source in `src/` |
| Goal 2: simple, intuitive | ✅ | a bar, plain words, a 7‑question first run; the desk edge suite shows blank/odd/long input handled |
| Goal 3: a departure from addictive tech | ✅ | no feeds, no badges, no notifications except results you asked for; focus mode blocks feed sites at the hosts level; calm defaults |
| Text‑driven, very simple design; "everything purple", "no corners", "settings in Chinese, rest in English" | ✅ | live re‑theming from any colour name/hex with readability kept; corner styles; per‑area language (6 built in, others translated once on device); all deterministic |
| Less slop: real images, real quotes, research instead of guessing, listen to preferences, short answers, only what was asked | ✅ | Wikimedia photos with credit, Wikiquote quotes verbatim, web search + page read with a *Sources* window, honesty guard against narrated‑but‑not‑done actions, system prompt forbids invented numbers/dates |
| Self‑permissioning: acts as root without babysitting; profile chosen at onboarding | ✅ | hands‑off is the default and confirms nothing except loosening its own policy; balanced / hands‑on exist for those who want them; every action audited. Since 1.3 the first run is a quiz of six sliders (how much it asks, internet, where it thinks, on‑device model size, guidance, screen) that set the autonomy level, the firewall, the brain setting, the model, the guidance prompt and the animations, each changeable later in words |
| The model must run on modest hardware; the owner chooses models; no outside models | ✅ | 9 catalog models from the labs' official repos, SHA‑256 verified, chosen by RAM; measured floor 4 GB / 2 cores; no cloud connector exists; verified: "download gemma 4 e2b" (82 s, verified) → "use gemma 4 e2b" (13 s) → answers from the new model |
| Model choice as the answer to refusals/censorship | ✅ (by design) | the OS itself never adds refusals for the owner's own machine (its only rule is harm to other people); the catalog holds Mistral, Google, IBM and Liquid releases and no Chinese‑lab models; changing models is one sentence. The *guidance* slider/setting keeps that as the default (`owner`) and offers `standard` (the model's own caution) for owners who prefer it. See "Never denying the owner" below for the review |
| Never deny the owner a request about their own machine | ✅ for the OS layer; ⚠ residual: the model's own training, and any online model's provider rules | reviewed 2026‑10‑03 (below): no code path in the OS refuses an owner's request; confirmations are the owner's own autonomy/internet/brain settings asking, not denials; unattended tasks follow the same level |
| Efficient on an old laptop: don't make a small model re‑think repeated tasks | ✅ | deterministic shortcuts (`intent.py`, 175 tested phrases) answer the common requests with no model at all; routines (1.3) replay what the model did last time for the same short request, under the same policy, with only the answer written; llama‑server's prompt cache keeps the fixed prefix; the on‑device model only thinks about what is new |
| Know whether it is a five‑second or a five‑hour thing | ✅ | the reply card shows elapsed time and the usual time for this machine (from the model's own timings, nothing extra measured); downloads show the time left; the console announces anything over twenty seconds |
| "Construct a traditional desktop if you want" | ✅ (three layouts) | "I want a Windows 7 desktop" → taskbar, start menu, open windows listed; "make it look like a Mac" → menu bar, dock, traffic‑light buttons; "give me a clean desk" → the default; colours follow; also in Settings. It rearranges the same generated windows; it does not install another desktop environment |
| Owner may download tools like a browser; the OS picks tools to finish tasks | ✅ | `install_app` + windows on the desk ("install a web browser and open example.com"); the agent loop chains tools (search → read → answer) |
| Swapping models in and out is easy, UI-driven, AI-assisted; a list with features and drawbacks | ✅ | the Models screen lists on-device and online models with maker, size, memory, licence, speed, strengths and drawbacks, one-tap Use/Download/Remove and online Use/Set-up/Forget; the model can set up and switch from words. An agentic "Check for new models" searches Hugging Face for newer GGUF releases; `add_model owner/repo` adds one, pinned to its real SHA-256 (`tools/test-models.py`) |
| More agentic capability; "connectors are the new app" | ✅ (v1) | connectors follow the Model Context Protocol (MCP): a local command (stdio) or a URL (http) whose tools join the agent beside the built-ins, under the same autonomy policy and audit log; risk from MCP annotations; add/enable/disable/remove by screen or words; dependency-free client in `mcp.py` (`tools/test-connectors.py`, a real stdio MCP server end to end) |
| Agentic, unattended: "I need to get to inbox zero today" | ✅ | `mail_triage` reads every unread mail, archives noise, lists what needs you; scheduled tasks run in the background and land in *While you were away* |
| Works on real computers, dual boot on a Mac | ✅ / ⚠ | x86‑64 image with installer next to macOS/Windows (verified in QEMU with a Mac‑like disk); Apple Silicon needs an Asahi build that cannot be tested here and does not support M4 — documented, not shipped |

### Never denying the owner: the review (2026‑10‑03)

The brief's core promise is that the OS does what its owner asks on their
own machine. Every place a request can stop was read for this review:

| Where a request can stop | Is it a denial? | What it is |
|---|---|---|
| `agent.SYSTEM_PROMPT` (guidance `owner`, the default) | no | tells the model to do what is asked, never refuse a request about this machine or the owner's data, never lecture; the one boundary is harm to other people |
| guidance `standard` (opt‑in slider/setting) | no (the owner chose it) | the two obedience lines are replaced by "use your own judgement"; the model's own caution applies |
| `agent.needs_confirm` + `execute` | no | a confirmation dialog, decided by the owner's autonomy level; hands‑off (the default) asks only before loosening a security policy (more autonomy, more internet, Tor off, more online). "No" is the owner's own answer |
| internet setting `no` / `ask` | no | the owner's firewall choice; a blocked tool says so plainly and the model is told not to invent what it could not look up |
| `_ONLY_IF_ASKED` (mail send/delete, power) | guard, not denial | those tools run only when the current request mentions sending/deleting/powering; stops a model from doing what was not asked; a false negative is reported in words so the owner can rephrase |
| unattended tasks (`scheduler.HeadlessCtx`) | no (since 1.3) | they follow the autonomy level: hands‑off runs what was scheduled; balanced/hands‑on leave what would have asked undone and report it. Before 1.3 destructive actions were banned unattended regardless |
| `uispec.normalize`, `_CLAIM_RE` honesty nudge | no | input hardening and an honesty check; they never refuse a request |
| the on‑device model's own training | ⚠ residual, but the owner can tune it | a model may still refuse on its own; the catalog notes which refuse least (Ministral, the default) and which are "conservative" (Granite); changing models is one sentence. Since 1.3.1 the owner can edit the **conduct section** of the system prompt directly (Settings → Conduct, or "pop the hood"; `/etc/llmos/conduct.txt`), so they set exactly how insistent the obedience wording is — the OS ships the default and never edits this itself, and the assistant cannot rewrite its own rules. (A harness‑level re‑prompt that auto‑re‑asks a refusing model was *not* added: the development environment's classifier blocks that edit as a security change regardless of the owner's instruction. Editable conduct is the owner‑controlled alternative.) |
| owner‑editable conduct (from 1.3.1) | no (the owner's own text) | the conduct section is the one part of the prompt the owner controls; the default keeps the no‑harm‑to‑others boundary; the assistant may open or show it but only the human can change it |
| an online model (opt‑in, 1.3) | ⚠ by the provider's rules | Claude or any other service applies its provider's policy; the set‑up text says so; `local` remains the default and `here: …` keeps any one request on this computer |

Nothing in `src/rootfs` contains a refusal of its own (`grep -i "refuse\|not allowed\|can't do that"` finds only the internet‑off message and docstrings).

## Installing on real machines and Macs (dual boot)

The x86‑64 image carries the installer (`install_to_disk`, see the design
above). What was verified, and what was researched but cannot be verified
here (no physical Mac is written to; sources in the list at the end):

- **PCs and Intel Macs, alongside another system** — verified in QEMU/OVMF
  (`tools/install-test.sh x86`) with a disk laid out like an Intel Mac
  (300 MB EFI system partition holding Apple's folder, a 6 GB APFS‑typed
  partition, free space) and SMBIOS reporting Apple as the manufacturer:
  LLM OS booted from a second disk (the "USB stick"), created its partition
  in the free space (17.7 GB), shared the ESP, wrote `EFI/llmos/grubx64.efi`
  and the removable path `EFI/BOOT/BOOTX64.EFI` next to `EFI/APPLE`, left the
  APFS partition untouched (206 s under emulation), and the machine then
  booted from the first disk alone into the installed copy (`/dev/vda3`,
  `linux-lts`, desk on screen).
  Apple's Startup Manager (Option key) lists a FAT partition with
  `EFI/BOOT/BOOTX64.EFI` as "EFI Boot"; Apple firmware ignores `efibootmgr`
  NVRAM entries, so the removable path is what makes it show up. Macs with
  the T2 chip (2018–2020) additionally need Startup Security Utility set to
  *No Security* and *Allow booting from external media*; their internal
  keyboard, trackpad, audio and webcam need the out‑of‑tree `apple-bce`
  driver (not in Linux 6.18 / Alpine), Wi‑Fi needs Broadcom firmware copied
  from macOS. Pre‑T2 laptops (2015–2017) have upstream `applespi` for the
  keyboard/trackpad, which Alpine's `linux-lts` enables. macOS itself cannot
  be added to GRUB's menu (GRUB has no APFS driver, `os-prober` has no macOS
  probe on x86); the Startup Manager is the picker, or rEFInd if the owner
  installs it.
- **Whole disk** — verified on arm64 under HVF (`tools/install-test.sh
  arm64`): from the desk, "erase the whole disk and install LLM OS on it"
  showed the plan (erase /dev/vdb 21 GB; ESP 256 MB + LLM OS on the rest;
  copy; UEFI bootloader) with an *Install now* button; pressing it
  partitioned, copied and installed GRUB in 21 s (`EFI/BOOT/BOOTAA64.EFI` and
  `EFI/llmos`), and the VM then booted from the new disk alone
  (`6.18.53-0-virt`, root on `/dev/vda2`).
- **Apple Silicon (M1–M4)** — *not supported natively*, on purpose. Booting
  Linux there needs the Asahi chain (m1n1 → U‑Boot → UEFI) installed from
  macOS, an ESP per OS, and a kernel with 16 KB pages plus the Apple SoC
  drivers (NVMe over RTKit/SART, DART IOMMU, SPI‑HID keyboard/trackpad, DCP
  display, Wi‑Fi firmware extracted from Apple's IPSW). Alpine's `linux-lts`
  6.18 has `ARCH_APPLE` but 4 KB pages and no RTKit/SART/DART, so the
  internal SSD would be invisible; `linux-virt` (our VM kernel) has no Apple
  support at all. The working pieces exist only in Alpine **edge/testing**
  (`linux-asahi` 7.1) plus `m1n1`/`u-boot-asahi`/`asahi-fwextract` in
  community — and Asahi supports M1/M2 fully, M3 since 2026‑09‑06, **M4 not
  at all** (this machine is an M4). Shipping an Asahi‑based variant would
  mean a third image with a testing‑repository kernel that cannot be
  verified without an M1/M2/M3 Mac that is willingly repartitioned; it is
  documented here as the path, not built. On Apple Silicon, LLM OS runs as
  the VM with the model on the Mac's GPU.

## Hardware requirements (measured)

`tools/spec-matrix.sh` boots the shipped arm64 image under HVF with the
default model (Ministral 3 3B, Q4_K_M, 2.1 GB) running *inside* the VM and
the graphical desk up, for several RAM/CPU sizes, and asks llama‑server for
its own timings on a fixed prompt (M4 Mac mini, 2026‑09‑25):

| RAM | CPUs | boot → shell | model | free after load | prompt tok/s | generation tok/s |
|---|---|---|---|---|---|---|
| 2 GB | 2 / 4 | 11–13 s | does not load | — | — | — |
| 3 GB | 2 | 12 s | loads | 91 MB | — | OOM kills (desk + model do not fit) |
| 3 GB | 4 | 12 s | loads | 147 MB | 38.5 | 5.7 (page‑cache thrashing) |
| **4 GB** | **2** | 11 s | loads | 771 MB | 39.7 | 24.6 |
| 4 GB | 4 | 12 s | loads | 757 MB | 76.9 | 27.2 |
| 6 GB | 2 | 10 s | loads | 1746 MB | 54.4 | 25.8 |
| 6 GB | 4 | 12 s | loads | 1675 MB | 74.4 | 28.8 |

Reading: **4 GB is the floor** with the default model (below it the model
either does not load or thrashes); cores mostly buy prompt speed (2 → 4 cores
doubles it), generation is memory‑bound at ~25–29 tok/s on these Apple
cores; 6–8 GB leaves room for the browser, larger models (the catalog states
each model's RAM) and downloads. Disk: the image is 3.5 GB plus 2.1 GB of
model; 16 GB is the minimum, 64 GB comfortable. Real x86 machines: the same
rules apply (CPU inference; an older 4‑core laptop with 8 GB is the sweet
spot); a GPU is not used. Under the Mac launcher in host‑GPU mode the VM
itself needs only 3 GB because the model lives on the host.

## Performance and model choice (measured, M4 Mac mini, 2026‑09‑25)

llama-bench, Q4 models, prompt = 512 tokens, generation = 128 tokens:

| Model | VM CPU (4 cores) prompt / generate | Mac GPU (Metal) prompt / generate |
|---|---|---|
| Ministral 3 3B (default) | 46 / 27 tok/s | 453 / 33 tok/s |
| Gemma 4 E2B | 156 / 43 tok/s | 756 / 49 tok/s |

Speculative decoding with Gemma 4's own MTP draft head (4 CPU threads, same
output): 32.6 → **48.0 tok/s** (128 of 273 drafted tokens accepted). The
catalog carries the draft heads' official hashes; the OS and the launcher use
them automatically for Gemma models. A q8_0 KV cache with flash attention
was also tried on CPU and rejected: prompt processing became ~3× slower.

Why Ministral 3 3B ships as the default although Gemma 4 E2B is faster: in
the agent loop (real tools, several turns) Ministral routed 11/12 requests
correctly and stayed coherent across a shared conversation; Gemma 4 E2B,
re‑tested with the final architecture, scored 6/11 on the same multi‑turn
sequence — after a few turns it writes tool calls as plain text
(`set_brightness(percent=70)`) that never execute, and once claimed an action
it had not performed. Both refused nothing in an 8‑prompt refusal probe.
Granite 4.1 3B and LFM2.5 2.6B were also evaluated (10/12 and 8/12 tools; one
refusal each). Switching is one sentence ("use gemma 4 e2b") or
`LLMOS_MODEL=` in the launcher.

Host‑GPU mode (launcher on macOS) is the largest single speed‑up: prompt
processing ~10× (the cold first request and every web‑research request drop
from tens of seconds to a few) and generation 1.2–2×.

"Jev"‑style decision models (TypeSafe's Jev, 2026‑09‑15) were evaluated as a
fast front‑end router. Jev itself is a closed, API‑only, non‑generative model,
so it cannot be part of an offline OS. The open reproductions that appeared
this week (Laya 421 M, Kev 0.5–27 B, APUS‑OpenJev) do not run in llama.cpp:
Laya needs the `ggmlc` runtime (no arm64‑Linux build as of v0.9.5), Kev is a
PyTorch/PEFT adapter. Not integrated; with prompt caching in place the gain
for this OS would be modest. The deterministic shortcuts in `intent.py`
(memory statements, scheduling phrases) play the same "System 1" role for the
cases that matter most, in ~0 ms.

## Test results

Acceptance suites (`tools/acceptance.sh`) driven over the serial console of
the built image under QEMU/HVF, 4 GB VM unless noted. ✅ = passed as
described.

| Area | Result |
|---|---|
| Boot | ✅ UEFI/GRUB → console in ~15 s; loopback, DHCP, model server, scheduler, firewall all up |
| First‑run wizard, passphrase vault | ✅ LUKS2 vault created ("Encrypting your storage…"), banner shows 🔒 |
| Time zone from the launcher | ✅ `15:37 MST, UTC−07:00` after the fix (root read‑only at sysinit was the bug) |
| "how much disk space?" | ✅ runs `df -h`, answers |
| "make everything purple" | ✅ purple text on an auto‑darkened purple background, readable |
| Settings panel | ✅ framed panel, all fields |
| "settings in Chinese, everything else in English" | ✅ settings panel renders 设置/自主程度/联网…, rest stays English |
| Memory ("remember that…", "what do you remember?") | ✅ saved, listed, recalled; also after Moon‑fact hallucination cleanup |
| Arithmetic | ✅ `calculate` → 18,377 |
| Web research | ✅ search → read (USA Today / artemistracker.com) → 2‑sentence summary with source, after the 6 k‑context fix |
| Real photo | ✅ Eiffel Tower from Wikimedia Commons (Benh Lieu Song, public domain), rendered in the terminal |
| Media | ✅ yt‑dlp found "Best of lofi hip hop 2021 … by Lofi Girl", mpv played, "stop" stopped |
| Ordinary admin | ✅ `rm -rf /tmp/*`, `apk add htop`, folder + file creation, file read — done without lectures; service on/off needed the OpenRC hint added afterwards |
| Autonomy (hands‑on) | ✅ tightening does not ask; file creation asked `[y/N]` and proceeded on `y`; loosening asks |
| Voice (on‑device speech‑to‑text) | ✅ espeak‑ng‑synthesised "what time is it in tokyo right now" → whisper.cpp transcribed "What time is it in Tokyo right now?"; `voice` with no real mic listened and reported nothing said (the Mac needs the mic bridge; the OS now tries it first) |
| Vault lock/unlock | ✅ `lock` closes the vault; a wrong passphrase is rejected, the right one reopens it |
| Reboot persistence (host‑GPU mode) | ✅ `shutdown` powered off cleanly; after reboot the vault asked for the passphrase and reopened; banner `hands-off · host GPU · 🔒`; memory ("you are Jordan… set up LLM OS on 2026‑09‑25"), purple theme, Chinese settings panel and `America/Phoenix` all persisted; a request round‑trip took 3 s on the Mac's GPU |
| Shipped arm64 image, first boot (3 GB VM, host‑GPU) | ✅ final image (`SHA256SUMS`): no GRUB errors, "model served by the host at http://10.0.2.2:8080", wizard completed, "how much disk space?" 6 s, "make everything green with square corners" 7 s (square frames rendered), "12 times 34" 5 s, Artemis research read from nasa.gov with the source 14 s, settings panel correct; then the full email leg on the same boot (below) |
| Shipped x86‑64 image (QEMU emulation, SeaBIOS and OVMF UEFI, host‑GPU) | ✅ both firmware types: GRUB → `6.18.53-0-lts` → serial console offered in 17–18 s (screen is the preferred console), wizard completed, "how much disk space?" 6–7 s and "12 times 34" 5–6 s with the model on the Mac, settings panel; 26 services started, `/boot/efi/EFI/BOOT/BOOTX64.EFI` present, HDA sound card and `/dev/dri/card*` (virtio‑vga) detected. With the model inside the emulated VM it loads and answers `/health` but generation is too slow to time under TCG — on a real x86 machine it runs on the CPU at native speed |
| Email (Dovecot + Postfix test server inside the VM, 6 seeded messages) | ✅ `mail_setup` verified IMAP and SMTP login; "what's in my inbox?" listed all six with one‑line summaries; "get me to inbox zero" classified each message, archived the newsletter, CI notification and promo on its own, listed Alice's dinner question and Bob's invoice as needing the owner (and drew an "Inbox Zero Checklist" panel); "reply to Alice that Friday at 7 works and I'll bring dessert" resolved *Alice* to her message and sent a threaded `Re: Dinner on Friday?` (In‑Reply‑To/References, quoted original) that arrived in her mailbox. Guards added from what the tests showed: no account → the OS says so instead of the model searching the web for the person; sending/deleting/powering off only when the current request asks for it (the model once tried to "finish" an earlier failed reply on its own); tool errors tell the model to report, not to install mail software |
| Scheduler (unattended task → inbox) | ✅ "in 1 minute, tell me one real fact about the Moon" scheduled instantly (deterministic shortcut); the scheduler ran it in the background ~1 min later on the host GPU; at the next prompt a "While you were away" box showed the result — a correct, timeless fact (384,400 km, tidally locked), no invented current data |
| Video on the screen | ✅ "pull up a YouTube video of a lofi hip hop live stream and play it on the screen" → deterministic `play_media` shortcut → yt‑dlp found Lofi Girl's stream → mpv inside the Wayland kiosk (`cage`, software rendering, `--vo=wlshm`); the framebuffer dump (`tools/screendump.py`, QEMU monitor) shows the actual video frame (the Lofi Girl scene, 1280×800, 90 % non‑black), the virtual sound card reports `state: RUNNING`; "stop" ends it. Raw DRM output (`--vo=drm`) was black under virtio‑gpu, which is why video goes through the kiosk |
| Graphical programs | ✅ "open a terminal window on the screen" → `foot` in the kiosk (frame dumped and viewed); "install a web browser and open example.com in it on the screen" → `apk add firefox-esr`, Firefox in the kiosk rendering example.com (frame dumped and viewed). Needed `eudev` + `setup-devd udev` in the image (cage's libinput found no input devices under mdev) and a stale `/run/seatd.sock` cleanup |
| Graphical desk, first boot of the shipped arm64 image (4 GB VM, model inside the VM; `tools/desk-smoke.sh`, frames in `run/shot-desk-*.png`) | ✅ boots straight into the set‑up wizard on screen (language grid, name, time zone, three autonomy cards, internet, Tor, passphrase → LUKS2 vault created); then: "how much disk space do I have?" answered in the reply card; `settings` opens a window with radio choices and toggles; "make everything teal with square corners" re‑themes the whole interface live; "show me a photo of the Matterhorn" opens a real photo (Dirk Beyer, CC BY‑SA 3.0, credited); "in 1 minute, tell me one real fact about Mars" → the scheduler ran it unattended and a *While you were away* window appeared with a correct fact; `lock` shows the unlock screen, a wrong passphrase is refused, the right one returns to the desk with the theme intact. 383 MB free / 685 MB available afterwards with the 3 B model resident |
| Desk windows (test VM, `tools/dsay`) | ✅ inbox window with Read/Archive buttons and an *Inbox zero* button; a message window with the reply form and Archive/Delete; "play some lofi hip hop" → mpv plays the Lofi Girl stream in a decorated window (dark labwc title bar) with a *Now playing* card whose Pause/Resume/Stop/volume drive mpv over IPC; "open a terminal window" → `foot` as a window with a dock chip; Alt‑Tab/Super+Q/Super+Esc bound in the compositor |
| Desk edge cases (shipped arm64 image, host‑GPU mode, `tools/desk-edge.sh`, frames in `run/shot-edge-*.png`) | ✅ **hands‑on**: "create a file…" raised a *Write to ~/note.txt?* dialog with the exact arguments; *Don't* → no file, the model reported it could not; *Allow* → file created. **Loosening asks**: "switch back to hands‑off" raised *change autonomy → hands‑off*; tightening ("turn the internet off") did not ask and the reply says the firewall now blocks everything; the next web request was refused ("internet is blocked"); "allow internet use" asked again. Policy sentences, the interface language and power requests are routed by the OS, not the model (the model had mapped "ask me each time before using the internet" to nothing and "put everything in Chinese" to a Chinese *answer*). **Odd input**: an unknown colour ("blurple") got a sensible light‑purple theme; blank input is ignored; an 8× repeated request got one sentence. **Stop** cancels a running request (and declines any confirmation it raises). **Model outage**: with the model unreachable the reply card shows the "model isn't running" message and the status dot goes grey; when it is back, "12 times 34" → 408. **Many windows** cascade; `clear` closes them. **Chinese**: "put everything in Chinese" re‑labels the whole desk; `settings` opens 设置 with 自主程度/联网/通过 Tor 联网 rendered in Noto CJK; "switch everything back to English" restores it. No‑account email requests are answered by the OS; focus mode writes/removes the hosts entries; the mic button shows *Listening…* and gives up quietly without a microphone. **Persistence**: orange theme, a memory and a real‑photo wallpaper (Maloja Pass, CC BY‑SA, credited) survive a power‑off and boot of the same installation. A confirmation nobody answers counts as *no* after 10 minutes instead of stalling the desk forever (found by this test) |
| Installer, next to "macOS" (x86‑64, QEMU/OVMF with Apple in SMBIOS, `tools/install-test.sh x86`) | ✅ a disk laid out like an Intel Mac (300 MB ESP holding `EFI/APPLE`, a 6 GB APFS‑typed partition, 17.7 GB free) and LLM OS booted from a second disk: "install LLM OS on this computer" → plan (use the free space, keep macOS, share the ESP, removable path for Apple's startup manager) → *Install now* → new `/dev/vda3` (17.7 GB), system copied, `EFI/llmos/grubx64.efi` and `EFI/BOOT/BOOTX64.EFI` written next to Apple's folder, the APFS partition untouched; 206 s under emulation; reply tells the owner to hold Option and pick "EFI Boot". Powered off and booted from the Mac‑like disk alone: root on `/dev/vda3` (fstab by UUID, ESP at `/boot/efi`), kernel `6.18.53-0-lts`, the desk up on screen |
| Installer, whole disk (arm64, HVF, `tools/install-test.sh arm64`) | ✅ plan window → *Install now* (one‑time token) → GPT with ESP + root on the blank second disk, system copied, GRUB `arm64-efi` (removable + `EFI/llmos`) in 21 s; booted from the new disk alone |
| Set‑up and desk polish (2026‑09‑27; frames `run/shot-desk-wizard-*.png`, `run/shot-desk-desk-fresh.png`) | ✅ Real VM, first boot of the shipped image: welcome card → language grid with the launcher's language pre‑selected → name → time zone with a live city search (typing "tok" lists Tokyo/Vladivostok with UTC offsets; the current zone and seven big cities offered before typing) → three autonomy cards with plain explanations and a *Recommended* badge → internet as one step (*Yes* recommended / *Yes, through Tor* / *No, stay offline*) → passphrase with *Show/Hide* and a mismatch message → a *That's it* card with three one‑click example requests; the desk then opens a *Try saying* window with eight examples as buttons. The conditional Wi‑Fi step (only on a laptop with an adapter and no route yet) was exercised in the browser pane with a simulated scan: the step count becomes 7, secured networks show a lock and a password field, *Skip for now* is offered. Desk: windows maximize (▢ or double‑click the title), ↑/↓ recall earlier requests, the status chips open Models/Settings or lock, Ctrl+W closes, "make everything bigger" scales the interface (70–200 %), Settings gained language choices, colour presets and A−/A+ |
| Brief compliance pass (`tools/spec-check.sh`, shipped arm64 image, frames `run/shot-spec-*.png`) | ✅ **Security facts from inside the OS**: no listening TCP/UDP sockets at all, firewall input policy *drop*, vault active on `/root` (LUKS2), `/tmp` in RAM, 502 packages all from `dl-cdn.alpinelinux.org`; with the internet turned *off* the output policy is *drop* except the host's model/mic ports and "12 × 34" still answers (the host model on port 8081 stayed reachable). **The brief's own examples**: "set the brightness to 60" answers honestly that a VM has no backlight; "pull up a YouTube video of ocean waves and play it" plays in a window and "stop the video" stops it; "give me a real quote from Marcus Aurelius" opens a window of three verbatim Wikiquote quotes with the source link; "what's the weather in Tokyo right now" is looked up (search → page → answer with the source URL); "every weekday at 8 give me a summary of my day" scheduled; "remember that I'm vegetarian" then "what do you know about me?" recalls it and refuses a duplicate; "install htop and open it" opens it in a terminal window; "install a web browser and open example.com in it" installs Firefox and shows example.com in a window; `audit` lists it all. Two requests the 3 B model got wrong on the first pass are now routed by the OS and re‑verified: "show me my disk, memory and scheduled tasks in one panel" (it had answered in prose) opens a *This computer* window of real numbers with bars (`system_panel`, from `/proc` and `df`); "download gemma 4 e2b" (it had asked which id to use) resolves the spoken name against the catalog. **Model choice, inside the VM (6 GB)**: `models` window with Download buttons → "download gemma 4 e2b": 3.3 GB + the 59 MB draft head fetched from Google's official repo and SHA‑256‑verified in 82 s → "use gemma 4 e2b": llama‑server restarted with the new model in 13 s, the status chip reads *Gemma 4 E2B*, "12 × 34" answered by it; the choice persists in settings |
| Desk on the x86‑64 image (QEMU emulation, host‑GPU model; `run/shot-x86desk-*.png`) | ✅ same desk as arm64, CPU‑rendered under TCG: onboarding on the console then the desk on tty1; `settings` window; "make everything green with square corners" re‑themes; "show me a photo of the Eiffel Tower" opens the credited photo window; "open a terminal window" opens `foot` with a dock chip; 1.95 GB free of 2.9 GB with the model on the host |
| Window‑spec validator fuzz (`tools/test-uispec.py`, host) | ✅ 5 000 random junk specs per seed (wrong types, nesting, 5 KB strings, script/`javascript:`/`data:` URLs) never raise, sizes stay capped, only `http(s)://`, `file:///` and absolute paths are kept as image/link/source URLs; the model's usual mistakes (`paragraph`, `bullet`, a string for a list, a string fraction, dict rows) still render. Found by this test and fixed: a number where a list was expected crashed the validator (the tool wrapper would have reported an error, never the desk) and a `javascript:` image URL passed through |
| Final verification of the shipped images (2026‑09‑26 01:38/01:43 builds, `SHA256SUMS`) | ✅ **arm64**: desk first boot → wizard → requests, lock/unlock, scheduled task → *While you were away* (`tools/desk-smoke.sh`); text console first boot in host‑GPU mode ("Press Enter" on the serial line takes over set‑up from the screen): disk 7 s, "make everything green with square corners" 4 s, 12×34 6 s, Artemis research with source 14 s; email leg: account set up (login verified), Inbox · 6, inbox zero archived 4 and listed Bob's invoice and Alice's dinner as needing the owner, "reply to Alice that Friday at 7 works…" sent a threaded `Re: Dinner on Friday?` that arrived in her mailbox; whole‑disk installer 17 s and boot from the new disk; edge‑case suite (row above). **x86‑64** (re‑run on the 16:26 build): SeaBIOS boot → console in 22 s, wizard, requests 6 s / 6 s; OVMF UEFI 20 s, 6 s / 6 s; dual‑boot installer next to the Mac‑like disk: 121 s, `EFI/APPLE` kept, `EFI/llmos` + `EFI/BOOT/BOOTX64.EFI` written, booted from the installed `/dev/vda3` alone. Checksums verified after all tests (the images are never written to by the tests) |
| Files, open, trash, screenshot (2026‑09‑28, test VM, `tools/dsay`; frames `run/shot-files.png`, `run/shot-openfile.png`, `run/shot-screenshot.png`) | ✅ "show my files" → *Home* window (folders first, dates and sizes, Open/Delete buttons; *↑ Home* to go up); "open the file ~/Documents/notes.txt" → text window, `hello.py` → code window, a PNG → image window with a Delete button; "delete the file ~/Downloads/report.pdf" → moved to `~/.Trash` (hands‑off: done; balanced: *Move notes.txt to the trash?* → *Don't* → untouched, reply "Okay, I left it alone."); `/etc/passwd` refused (home folder only); a missing file → "There is no file …"; "take a screenshot" → `grim` → the screen as an image window, file in `~/Pictures` |
| Presence and animations (2026‑09‑28, test VM; frames `run/shot-anim-idle.png`, `run/shot-anim-thinking.png`, `run/shot-anim-reply.png`, `run/shot-anim-settings.png`) | ✅ orb in the bar breathes at idle, ring turns and the header reads *thinking…/working…* with the activity lines during a web look‑up, *writing…* with a caret while the answer streams; the reply card and bar stay above the windows; AI‑opened windows grow out of the bar; "turn off animations" / "fewer animations" / "turn animations on" → "Done — animations off / reduced / full." and the *Animations* choice in *Settings* follows; measured desk CPU (4‑core VM, 10 s samples): Full ≈7 %, Reduced ≈3.5 %, Off ≈3.5 % of one vCPU at idle, ≈19 % while thinking |
| Confirmation wording (2026‑09‑28) | ✅ dialogs are plain language — *Switch autonomy to hands-off?* "This lets me do more without asking first.", *Move report.pdf to the trash?* "… → ~/.Trash (it can be put back)" — never raw JSON; commands stay monospaced; a declined shortcut answers "Okay, I left it alone." |
| Final verification of the shipped images (2026‑09‑28 builds: arm64 12:53, 3.78 GB, `a657ba26…`; x86‑64 13:03, 4.35 GB, `c8ccec30…`; `SHA256SUMS` verifies) | ✅ **arm64** (`tools/desk-smoke.sh`, host‑GPU model, 4 GB VM, 12:58): wizard on screen → desk with *Try saying* → "how much disk space?" ("11.9 GB free out of 16.7 GB"), *Settings*, "make everything teal with square corners" (orb, chips and windows follow the accent), Matterhorn photo (credited), scheduled Mars fact → *While you were away* window, "show my files" → *Home* window (vault housekeeping dir hidden), "take a screenshot" → image window, "fewer animations" → setting `reduced` on disk, "turn animations on", "open the settings" → "Here it is." (deterministic), "clear" → the idle greeting with the orb and three suggestions (`run/shot-desk-hero.png`), lock → wrong passphrase rejected → unlock; 299 MB used of 3.9 GB at the end. **x86‑64** (`tools/x86smoke.sh bios`, host‑GPU, 3 GB VM, 13:05): GRUB → `6.18.54-0-lts`, serial console offered after 19 s, onboarded, "how much disk space?" 6 s, "what is 12 times 34?" 5 s (`calculate`), *Settings* box, 26 services, `BOOTX64.EFI` present |
| Lists, notes, trash, device phrases (2026‑10‑01, 2‑core 4 GB test VM with the model inside, `run/feat-test.sh`) | ✅ "add milk / eggs to my shopping list" → *Shopping* window, "remember to call Sam" → *To‑do*, "note that the plumber comes Tuesday" → *Notes*, "what's on my shopping list?" → "Here it is.", "tick off milk" → "Done." (struck through), "show my lists" → all lists, "remove eggs from my shopping list" / "clear my to‑do list" → "Removed."; "delete the file ~/old.txt" → trash, "show the trash" → *Trash* window with Restore / Delete for good / Empty buttons, "restore old.txt from the trash" → "Put old.txt back at /root/old.txt." (file present again), "empty the trash" → "The trash is empty (1 item deleted for good)."; "brightness 60" / "turn the volume up" / "mute" answer deterministically with the VM's honest hardware replies; "lock after 5 minutes" without a vault → asks to set one up first; "set up a passphrase" → the passphrase form |
| Timers, reminders, auto‑lock, the lock itself, resilience (2026‑10‑01, same VM, `run/feat-test2/3.sh`, `run/locktest*.sh`) | ✅ "set a timer for 1 minute" → "Timer set — 1 minute, it rings at 09:16."; "remind me in 1 minute to stretch" → "Reminder set for 09:17: stretch."; both landed in *While you were away* word for word ("Time's up: your 1 minute timer is done.", "Reminder: stretch") with the toast and chime path, no model involved; "lock after 1 minute of inactivity" → the desk locked by itself at the next 30 s poll after a minute without input (first run never locked: the idle clock was only set by page input — fixed to count from entering the desk and every request). **Lock, found self‑defeating and fixed**: the first lock showed the lock screen while the vault stayed mounted (WebKit cache files, then Mesa's shader cache under the home) and the poll returned to the desk unasked; after the ephemeral session, the cache relocation, no working directory inside the vault and closing the owner's programs first, "lock" with a terminal window open → the terminal closed, `/root` unmounted, `/dev/mapper/llmos-vault inactive`, a wrong passphrase rejected, the right one reopened it with the lists intact. **Edge cases**: a 7 000‑character paste at first OOM‑killed the in‑VM llama‑server (RAM prompt cache) and nothing restarted it — now the service respawns (back in 8 s), starts with `--cache-ram 0`, the agent clips over 6 000 characters and retries once more with half the text when the 6k context still overflows; "把所有东西变成紫色" → "现在界面已更新为紫色主题。" (the model did it in Chinese); two requests half a second apart → both answered in turn; Stop six seconds into a long poem → stopped |
| Final verification of the shipped images (2026‑10‑01 builds: arm64 09:59, 3.78 GB, `74046bf5…`; x86‑64 10:03, 4.35 GB, `0fed84b7…`; `SHA256SUMS` verifies) | ✅ **arm64** (`tools/desk-smoke.sh`, host‑GPU model, 4 GB VM, 10:09): wizard → desk with *Try saying* → "how much disk space?" (main filesystem and vault figures), *Settings*, "make everything teal with square corners", Matterhorn photo (credited), scheduled Mars fact, *Home* files window, screenshot window, "add milk to my shopping list" / "remember to call Sam" / "show my lists" → "Added." ×2, "Here it is.", "set a timer for 1 minute" → "Timer set — 1 minute, it rings at 10:07.", "fewer animations" → setting `reduced` on disk, "turn animations on", "open the settings" → "Here it is." (the vault‑present crash of the 09:43 build fixed), "clear", **lock → `/root` unmounted, `/dev/mapper/llmos-vault inactive`**, wrong passphrase rejected, unlock, and *While you were away* holding both the Mars fact and "Time's up: your 1 minute timer is done." **x86‑64** (`tools/x86smoke.sh bios`, host‑GPU, 3 GB VM, 10:05): GRUB → `6.18.54-0-lts`, serial console offered after 20 s, onboarded, "how much disk space?" 20 s, "what is 12 times 34?" 6 s, *Settings* box, 26 services, `BOOTX64.EFI` present |
| Model‑behaviour guards (from what the tests showed) | ✅ deterministic shortcuts for memory, scheduling, "reply to X that …", "open a terminal", "play …", and "make everything/the text/the background <colour> (with square corners)" (on one of three shipped‑image runs the model turned "everything green" into black‑on‑white with green frames — now the theme engine gets exactly the named colour; vaguer requests still go to the model); honesty guard rejects "I've set/remembered…" claims with no matching tool call; mail results shown verbatim in a box so the model cannot paraphrase amounts or invent replies; `mail_send`/`mail_reply`/`mail_delete`/`system_power` only when the current request asks for them; no‑account email requests (including "reply to Alice …") answered by the OS, not by a web search for the person or a scheduled task; a spelled‑out account ("set up my email: address …, password …, imap host …, port 993") is parsed by the OS and passed through unchanged — on the shipped image's first email test the model had silently dropped the SMTP host and port and blamed the provider; passwords in tool arguments are redacted (`•••`) on screen and in the audit log |
