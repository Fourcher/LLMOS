# LLM OS changelog

Versions are in `VERSION`; every image and ISO carries its version in
`/etc/llmos-release` (`llmos version` prints it, Settings shows it) and
`dist/RELEASE.json` lists what a release contains with checksums.

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
