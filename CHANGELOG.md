# LLM OS changelog

Versions are in `VERSION`; every image and ISO carries its version in
`/etc/llmos-release` (`llmos version` prints it, Settings shows it) and
`dist/RELEASE.json` lists what a release contains with checksums.

## 1.4.0 — 2026-10-04
- System-wide dictation, free and on the machine: press **Super+D** anywhere,
  speak, pause, and the words are typed where the cursor is — a field on the
  desk, the command bar, a terminal, a browser, any program. It records with the
  same push-to-talk path as the microphone button (the mic is open only while
  you talk), transcribes with whisper.cpp, and types through the compositor's
  virtual keyboard (`wtype`, now in the image). A chime marks start and end; the
  desk shows "Dictating…" without taking focus. `llmos dictate` runs it too.
- Choosable speech-to-text models, like the language models: Whisper Tiny,
  Base (ships with the OS), Small, and **Whisper large-v3-turbo** — near
  large-v3 accuracy at several times the speed, 99+ languages, about 0.6 GB —
  the best free local dictation model for laptops. The Models screen has a Voice
  section with each one's accuracy, speed, size, memory, strengths and
  drawbacks, and Use / Download / Remove; or say "download the turbo voice
  model", "use the turbo voice model". Base stays pinned by SHA-256; downloaded
  models are verified against the SHA-256 Hugging Face publishes for the exact
  file before they are ever used, and the shipped Base is the fallback.
- Dictated text is cleaned of whisper's non-speech tags (`[BLANK_AUDIO]`,
  `[MUSIC]`, `(silence)`…).
- Tests: `tools/test-voice.py` (catalogue, names, fallback, cleanup); in the VM,
  `tools/dictate-smoke.sh` speaks a sentence into the OS's own recording path
  through `tools/fake-mic-bridge.py` and checks it is typed into a focused
  terminal.
- Fixed: `llmos desk-ctl launch` (and the new dictation indicator) referred to
  a variable that did not exist, so the command failed; both use the
  command's argument now.
- Fixed: only the ISOs carried `/etc/llmos-release`; the disk images had none
  (`llmos version` fell back to the bare version number) and Settings never
  showed it. The image build now stamps every image (`MEDIUM=disk`), the
  installer marks an installed system as running from a disk rather than the
  live medium, and Settings (desk and console) shows the version line.

### Getting started, before the OS (the folder you share)
- **"1 - START HERE"** launchers for Mac, Windows and Linux sit at the top of
  the folder and open **LLM OS Setup** (formerly "the Exporter", now in
  `dist/setup/`). They find a working Python and, when there is none, say so
  in plain words and offer the free fix: Apple's Command Line Tools on a Mac,
  `winget` or python.org on Windows.
- LLM OS Setup now opens with a **Welcome** card: it recognises the computer
  (Mac with Apple Silicon or Intel, Windows, Linux; its memory) and recommends
  the way in — try it in a window, make a USB stick, install, or save the ISO
  — preselecting the ISO that computer needs. **Try it in a window** starts
  the built-in launcher on an Apple Silicon Mac with QEMU, and otherwise guides
  to the free app for this computer (UTM on a Mac, VirtualBox on Windows,
  GNOME Boxes on Linux) with buttons to its download page, the right ISO, and
  step-by-step settings.
- **"2 - Set up with AI.md"**: a prompt to hand to any AI assistant (Claude,
  ChatGPT, …) — "Read this and help me set up LLM OS". It walks a non-technical
  person from an unzipped folder to their first conversation: recognising the
  computer, choosing a path, opening Setup, UTM / VirtualBox / USB / install
  steps, checking fingerprints, planning the first-start choices, and
  troubleshooting. Its ground rules keep the assistant from writing disks by
  hand (only Setup's **Write** button, which hides internal disks) and make it
  ask before anything changes the computer.
- The user guide (`dist/README.md`) and the project README now open with
  **Start here**, including what to do about the first-run warnings (macOS
  "cannot be opened", Windows SmartScreen, a missing Python).
- Fixed: every Mac was sent to the Intel-Mac steps (write a USB stick, restart
  holding Option), which cannot work on Apple Silicon; and the steps told Mac
  users to double-click `run-llmos.sh`, which Finder opens in a text editor.
- Tests: `tools/test-setup-csrf.py` (renamed) also checks the recognition and
  recommendations for Apple Silicon, Intel Mac, Windows and Linux, and the
  launchers.

## Exporter CSRF hardening — 2026-10-04 (dist tooling; the OS disk images are unchanged)
- The Exporter is a local web app on 127.0.0.1 that can write USB sticks and
  run programs, so a web page the owner happens to have open must not be able to
  drive it. Its HTTP API is now hardened against CSRF: the per-launch token is
  required on **every** `/api` endpoint (the read-only ones — status, drives,
  progress, instructions — too, not just save/write), and compared in constant
  time; any request whose `Host` is not the loopback address (DNS rebinding) or
  whose `Origin`/`Referer` is another site is refused; CORS preflights get a
  bare 403 with no `Access-Control-Allow-*`, so a cross-origin call that needs
  one is blocked by the browser; and every response carries anti-framing
  (`X-Frame-Options: DENY` + CSP `frame-ancestors 'none'`), `nosniff` and
  `no-store`. The Exporter is standalone tooling in `dist/`, not part of the OS
  image, so no image or ISO changes. Covered by `tools/test-exporter-csrf.py`.

## 1.3.1 — 2026-10-03
- "Under the hood": the owner can edit the conduct section of the assistant's
  own system prompt — the part that says how it treats the owner's requests and
  the one boundary (never help harm other people). Settings → Conduct has Edit
  (a text editor on screen) and Reset to default; "edit the conduct" or "pop
  the hood" open it in words; the file is `/etc/llmos/conduct.txt`, plain text,
  editable from a terminal too. The OS ships two built-in defaults (picked by
  the guidance setting) and never edits this text itself — only the owner does,
  deliberately. The assistant can open or show the conduct but cannot rewrite
  its own rules; the default keeps the no-harm-to-others boundary. This is the
  owner-controlled answer to tuning the obedience behaviour: the end user makes
  the choice, on their own machine.
- Form fields can be multi-line (textarea), used by the conduct editor.

## 1.3.0 — 2026-10-03
- Set-up is a quiz: six sliders (how much it asks, internet, where it thinks,
  on-device model size, guidance, screen) choose the autonomy level, the
  firewall, the brain setting, the model (the biggest that fits the memory;
  only installed ones when offline), the guidance prompt and the animations.
  A line under the sliders names the model implied; the last page lists the
  choices. Everything can be changed later in words.
- An optional online model: Claude (Anthropic's Messages API) or any
  OpenAI-compatible service, added at set-up or from Settings with an API key
  that is checked with one tiny request and kept inside the vault. "Where it
  thinks" is local (the default: nothing leaves the computer), ask (here;
  before a big request goes online you are asked, and the service gets the
  request and conversation, not your memory or name) or cloud (the online
  model answers everything, this computer when it can't be reached).
  "ask claude: …" / "here: …" route one request. Every request that goes
  online is in the audit log; the orb turns blue and the reply card names the
  model that answered. With the internet off, nothing goes online.
- Guidance: owner (does what you ask on your own machine, no lectures; the
  default) or standard (the model's own caution), a slider and a setting.
- Routines: a short request the model handled in one tool step is remembered
  with its tool calls when they are safe to repeat as-is (not destructive, no
  memory writes, every long value quoted from the request). The next time the
  same words come, the calls run straight away under the same confirmation
  policy and only the answer is written; a routine that stops working is
  forgotten. Shown in the activity line and the audit log.
- Time estimates: the reply card shows how long it has been thinking and how
  long that usually takes on this machine, from the model's own speed figures
  (nothing extra is measured); downloads show the time left; the console says
  so for anything over twenty seconds.
- Desk layouts: "I want a Windows 7 desktop" (taskbar, start menu, open
  windows listed), "make it look like a Mac" (menu bar, dock, traffic
  lights), "give me a clean desk" (the default); also in Settings.
- Unattended tasks follow the owner's autonomy level instead of a flat ban on
  destructive actions: under hands-off they do what was scheduled; under
  balanced or hands-on, anything that would have asked is left undone and
  reported.
- The fixes from the 1.2 code review (15 findings) and security review:
  form-field spoofing, lock-screen keybinds, console lock crash, relative
  paths, "check …" phrases, auto-lock closing programs, live-ISO boot, the
  model missing from stick installs, the passphrase form, idle-screen
  buttons, vault holders at lock, stale checksums, the calculator, system
  windows; remote images are never auto-loaded in generated windows.
- A model manager (the Models screen), UI-driven for both on-device and online
  models: each model shows its maker, size, memory, licence, speed, what it is
  good at and its drawbacks, with one-tap Use / Download / Remove, and the
  online section lists the provider's models with Use, plus Set up / Change /
  Forget. Every button is a spoken command, so it can never do more than words.
- An agentic model refresh: because new models come out constantly, a "Check
  for new models" button (and "check for new models" / "refresh the models")
  searches Hugging Face for newer GGUF releases from the makers the OS already
  trusts and lists what is not in the catalogue yet. "add the model
  owner/repo" adds one, pinned to the exact file's SHA-256 read from Hugging
  Face, so owner-added models stay hash-verified like the built-in ones.
- Switching the online model keeps the key: "use the online model
  claude-opus-5-5", or the Use buttons in the manager.
- Connectors — the apps of this OS. A connector is an external tool provider
  following the Model Context Protocol (MCP): a local command (stdio, stays on
  this machine) or a URL (http). Its tools are discovered and join the agent
  beside the built-in ones, under the same autonomy policy and audit log; a
  tool's risk comes from its MCP annotations (read-only / destructive), and an
  http connector's calls follow the internet setting. Add, enable, disable and
  remove from the Connectors screen or in words ("add a connector named files
  that runs …"); a desk form takes the details. A local MCP server
  (`tools/fake-mcp-server.py`) ships for testing. Dependency-free client in
  `mcp.py`.
- Host tests: `tools/test-cloud.py` (the online-model client against fake
  services, no network), `tools/test-routines.py`, `tools/test-models.py` (the
  manager, refresh and add-model against a mocked Hugging Face),
  `tools/test-connectors.py` (a real stdio MCP server end to end);
  `tools/brain-smoke.sh` drives the quiz, routing and layouts in the VM with
  `tools/fake-cloud.py` as the service.

## 1.2.0 — 2026-10-03
- Bootable live ISO for PCs (BIOS + UEFI) and arm64 UEFI machines: runs LLM OS
  from a USB stick, installs to the internal disk from the running desk.
- The Exporter app (`dist/exporter`): one click on macOS, Windows or Linux to
  save the ISO, write it to a USB stick, or read the install / dual-boot steps.
- Version tracking (this file, `VERSION`, `RELEASE.json`, `/etc/llmos-release`).
- Desk: system windows share one slot on the right; overlapping windows go
  solid; a reply that opened a window folds at once; two-column "Try saying";
  plain activity names; keyboard focus rings; relative times on notes.

## 1.1.0 — 2026-10-01
- Lists and notes, timers and reminders (delivered word for word, with a chime),
  auto-lock, trash restore / empty, "set up a passphrase" after first boot,
  brightness and volume by voice, Super+Left/Right snapping.
- Hardening: supervised model and scheduler services, no RAM prompt cache,
  long requests clipped and retried, the lock really unmounts the vault
  (ephemeral WebKit session, caches outside the vault, programs closed first,
  passphrase verified against the header), VM lifetime guards in the tooling.

## 1.0.0 — 2026-09-28
- Graphical desk with the presence orb, animations (Full / Reduced / Off),
  first-run wizard, windows generated from specs, files and screenshots,
  host-GPU mode, installers (alongside / whole disk), x86-64 and arm64 images.
