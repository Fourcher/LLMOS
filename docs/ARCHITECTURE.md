# LLMOS Architecture and Build Plan

Status: final for v0.1. Scope: one engineer, one to two days, fewer moving parts.
Every decision below is binding unless a later doc supersedes it.

## 0. Summary of the design in five sentences

LLMOS is an Alpine Linux edge live system (read-only squashfs, tmpfs overlay) whose
only user-facing program is a Python agent shell running fullscreen in a foot terminal
under the cage Wayland kiosk. All inference is local through llama-server bound to
127.0.0.1 with JSON-schema constrained output, so even a 0.8B model always yields a
valid action. User state (preferences, memory, mail credentials, scheduled tasks,
downloaded models) lives on a LUKS2 volume unlocked by passphrase at boot. Network
egress is denied by nftables until the user consents at onboarding, and every tool
call passes a permission gate implemented in Python according to the chosen profile,
never by the model. The build runs entirely in Docker with apk --root and produces a
hybrid BIOS+UEFI ISO tested under QEMU TCG through the serial console.

## 1. Final decisions

### 1.1 Base system
- Alpine Linux edge, OpenRC, musl, busybox. Rationale: everything we need (llama-server,
  cage, foot, mpv, yt-dlp, chafa, tor, cryptsetup) is in edge/community, the rootfs is
  small (about 350 MB uncompressed without model) and apk --root works inside Docker.
- Kernel: linux-lts from Alpine plus linux-firmware-i915, linux-firmware-amdgpu,
  linux-firmware-other packages trimmed to intel/amd/iwlwifi/rtw. Rationale: older
  laptops need firmware for GPU modesetting and Wi-Fi.
- No pip dependencies at all. The agent uses the Python stdlib only (urllib, sqlite3,
  json, html.parser, subprocess, curses not needed). Rationale: musl wheels and pypi
  availability are a build-time risk; stdlib is enough.
- Audio through ALSA directly (alsa-utils, mpv --ao=alsa). PipeWire is dropped.
  Rationale: one root session, one audio client at a time; PipeWire adds a user session
  daemon, dbus and wireplumber for no benefit here.

### 1.2 Boot and image layout
- Output: llmos.iso, hybrid BIOS+UEFI via grub-mkrescue (xorriso), dd-able to USB.
- ISO content:
  - /boot/vmlinuz-lts, /boot/initramfs-llmos (custom busybox init, see 4.3)
  - /llmos/system.squashfs (xz, the whole rootfs)
  - /llmos/models/<file>.gguf stored uncompressed outside the squashfs so llama-server
    can mmap it directly from the ISO or USB without decompression.
  - /llmos/version
- Runtime: squashfs mounted read-only, tmpfs overlay upper, switch_root. The system is
  immutable; apk installs requested by the agent go to the overlay (lost on reboot)
  unless the user asks to persist them, in which case the package list is stored on
  /data and reinstalled at boot by the llmos-persist service.
- GRUB menu: "LLMOS", "LLMOS (safe: text console, no GPU)", "LLMOS (serial console)".
  The serial entry appends console=ttyS0,115200 llmos.console=serial and is what the
  QEMU tests use.

### 1.3 Partitioning and encryption
- Live USB mode: system on the ISO, persistent state on a LUKS2 partition created at
  onboarding on a disk the user picks (internal disk or a second USB).
- Installed mode (llmos-install <disk>): GPT with three partitions:
  1. ESP 256 MB (FAT32): grub EFI + BIOS boot via a 1 MB bios_grub partition
  2. LLMOS_SYS 4 GB (ext4, mounted ro): vmlinuz, initramfs, system.squashfs, models/
  3. LLMOS_DATA rest (LUKS2 argon2id, ext4 inside, label llmos-data)
- LUKS2 with a single passphrase keyslot, argon2id (cryptsetup defaults), no recovery
  key, no TPM, no escrow. Losing the passphrase loses the data; onboarding says so
  twice and requires typing the passphrase twice.
- Unlock happens after the kernel boots, in the OpenRC service llmos-data (before
  llmos-agent): it prompts on the active console, runs cryptsetup open, mounts /data.
  Rationale: no need for an initramfs cryptsetup and the system itself is public code.
  Threat model note: an attacker with physical access could tamper with the unencrypted
  system partition (evil maid). Accepted for v0.1; documented in the onboarding text.
- The bundled model on the ISO is public and stays unencrypted. Models downloaded
  later go to /data/models and are therefore encrypted.
- Optional zram swap (zram-init, 2 GB) enabled when RAM <= 8 GB so the 4B model tier
  does not OOM on prompt processing spikes.

### 1.4 Display stack
- cage (Wayland kiosk, seatd) starts the wrapper /usr/lib/llmos/session.sh, which
  loops: foot --config /run/llmos/foot.ini --fullscreen llmos-shell. If the shell exits
  with code 75 (restart requested by a theme change), foot is relaunched immediately
  with the regenerated config and the shell reprints the last screen from the
  transcript log. Any other exit code restarts the shell after 1 s.
- cage shows the newest toplevel window fullscreen, so mpv (video) simply appears on
  top and focus returns to foot when it quits. No window manager logic needed.
- Images: chafa --format=sixel (foot supports sixel), width capped to the terminal.
- No display / no GPU / safe mode: the same llmos-shell runs on tty1 (agetty replaced
  by a direct OpenRC service) or ttyS0. Images fall back to chafa symbols, video to
  mpv --vo=tct (or refuses with a message on serial).
- Font: DejaVu Sans Mono default plus Noto Sans CJK for zh/ja/ko rendering in foot
  (font=DejaVu Sans Mono:size=12, Noto Sans CJK SC:size=12 fallback).

### 1.5 Inference
- llama-server (Alpine package llama-cpp or llama-server, whichever edge ships today) as
  OpenRC service llmos-llm: --host 127.0.0.1 --port 8080 -m <model> -c 4096 -np 1
  --threads <ncpu> --threads-batch <ncpu> --jinja --cache-reuse 256 --slot-save-path
  /run/llmos/slots --no-webui. Prompt caching (cache_prompt) is on by default in the
  server; we rely on one slot and an unchanging prefix (see 2.4).
- API used: POST /v1/chat/completions with json_schema in response_format and
  chat_template_kwargs {"enable_thinking": false} for Qwen3.5 models (thinking is off
  for latency; the agent loop is the reasoning).
- Model catalog and RAM tiers (files verified on Hugging Face 2026-09):

  | tier | RAM | repo | file | size |
  |---|---|---|---|---|
  | tiny | 4 GB | bartowski/Qwen_Qwen3.5-0.8B-GGUF | Qwen_Qwen3.5-0.8B-Q4_0.gguf | 538 MB |
  | small (default) | 8 GB | unsloth/Qwen3.5-2B-GGUF | Qwen3.5-2B-Q4_K_M.gguf | 1281 MB |
  | small alt | 8 GB | LiquidAI/LFM2.5-1.2B-Instruct-GGUF | LFM2.5-1.2B-Instruct-Q4_K_M.gguf | 731 MB |
  | small alt | 8 GB | openbmb/MiniCPM5-2B-GGUF | MiniCPM5-2B-Q4_K_M.gguf | 1561 MB |
  | medium | 12 GB+ | unsloth/Qwen3.5-4B-GGUF | Qwen3.5-4B-Q4_K_M.gguf | 2741 MB |

  Exact file names are re-verified by build/fetch-model.sh against the HF API
  (https://huggingface.co/api/models/<repo>/tree/main) at build time; the table is the
  source of truth in llmos/models.py and the script fails loudly if a name drifts.
- Default bundled model on the ISO: Qwen3.5-2B Q4_K_M. Rationale: best instruction
  following per byte in the 8 GB tier, native tool/JSON habits, about 8 to 12 tok/s on
  a 4-core 2015 laptop, ISO stays under 1.8 GB. The CI ISO variant bundles the 0.8B
  Q4_0 model so QEMU TCG tests finish in minutes.
- Ternary-Bonsai-2-27B is out: needs a fork for PQ2_0/PTQ1_0 quant types and 6 to 7 GB
  of RAM; listed in the catalog as "experimental, not offered" so it is not forgotten.
- Model switching: tool set_model downloads from HF with consent (egress), verifies
  size and sha256 from the HF tree API, writes /data/llmos/model.json, restarts
  neutral description; the OS does not editorialize.

### 1.6 Agent protocol
- One JSON object per model turn: {say, actions[], done}. Constrained by a json_schema
  with a oneOf per tool so args are validated by the grammar (details in section 2).
- Maximum 8 model calls per user request, 400 output tokens per call.

### 1.7 Tool list (exact names and args)
Permission class in brackets: R read-only, C reversible change, D destructive or
irreversible, E egress of personal data, N plain network use (not personal data).

- shell(cmd: str, timeout_s: int = 60) [C by default; D if the command matches the
  destructive list: rm -r, mkfs, dd, cryptsetup, fdisk, sgdisk, parted, wipefs,
  shutdown, reboot, poweroff, apk del, > /data; N if it names curl, wget, ssh, nc, git]
- set_brightness(percent: int 0..100) [C]
- set_volume(percent: int 0..100, mute: bool = false) [C]
- set_theme(patch: object) [C] partial merge into theme.json, see 1.11
- remember(key: str, value: str) [C] preference or fact, upserts
- forget(key: str) [C]
- recall(query: str) [R] full-text search in memory (facts and transcripts)
- web_search(query: str, n: int = 5) [N] DuckDuckGo HTML endpoint, returns
  [{title,url,snippet}]
- fetch_page(url: str, max_chars: int = 4000) [N] w3m -dump readable text
- show_image(url: str, caption: str = "") [N] downloads and renders with chafa; only
  real images from URLs, never generated
- play_video(query_or_url: str) [N] yt-dlp resolves a single video, mpv plays it
  fullscreen; if a query is given, the first result plays, nothing else is shown
- play_audio(url_or_path: str) [N or R]
- stop_media() [R]
- files.list(path: str) [R], files.read(path: str, max_chars: int = 4000) [R],
  files.write(path: str, content: str, append: bool = false) [C; D if overwriting a
  non-empty file outside /data/llmos/scratch], files.delete(path: str) [D]
- email.setup(imap_host, imap_port, smtp_host, smtp_port, user, password) [C; the
  password is stored on /data only]
- email.list(folder: str = "INBOX", n: int = 20, unread_only: bool = true) [N]
- email.read(uid: int) [N]
- email.archive(uids: [int]) [C, N], email.delete(uids: [int]) [D, N]
- email.send(to: str, subject: str, body: str, reply_to_uid: int = null) [E]
- schedule.add(when: str (ISO 8601 or "in 20m" or cron "0 9 * * 1-5"), request: str)
  [C], schedule.list() [R], schedule.remove(id: int) [C]
- notify(text: str) [R] appends to the notification list shown at the next prompt
- install_package(names: [str], persist: bool = false) [C, N] apk add
- network.status() [R]
- network.wifi_scan() [R], network.wifi_connect(ssid: str, psk: str) [C]
- network.set_mode(mode: "off"|"direct"|"tor") [C] applies the nftables policy
- model.list() [R], model.set(id: str) [C, N when download needed]
- ask_user(question: str, choices: [str] = []) [R] ends the turn and waits
- system.power(action: "shutdown"|"reboot"|"lock") [D for shutdown/reboot, C lock]
- system.locale(section: str, lang: str) [C] shorthand for a theme language patch

The model never executes anything directly; every tool is a Python function in
llmos/tools/*.py with a signature that mirrors the schema.

### 1.8 Permission model
- Profiles, chosen at onboarding, stored in /data/llmos/profile.json, changeable by
  saying "switch to careful mode" (goes through set_profile which is always class C):
  - autonomous: never asks. Classes R C D E N all auto-approved.
  - balanced (default suggestion): asks for D and E. R C N auto-approved.
  - careful: asks for C D E N. Only R auto-approved.
- The gate lives in llmos/permissions.py and wraps every tool call. It does not consult
  the model. When a tool needs consent the shell prints a one-line prompt
  "[allow] <tool> <summary>  y/n/always" and the answer "always" stores a per-tool
  grant in profile.json (auto grants are listed by "show my permissions").
- No moralizing or refusal layer in the OS. The system prompt tells the model it is the
  user's own computer and that requests are to be carried out. Model-side refusals are
  none.
- The agent runs as root. Rationale: it is the operating system; a permission profile
  is the control, not Unix users.

### 1.9 Memory
- SQLite at /data/llmos/memory.db with tables:
  - prefs(key TEXT PRIMARY KEY, value TEXT, updated_at)
  - facts(id, text, created_at) with an FTS5 virtual table facts_fts
  - transcript(id, ts, role, text) with FTS5, last 30 days kept
  - tasks(id, next_run, cron, request, last_run, last_result, enabled)
  - grants(tool, class, granted_at)
- Injected into the system prompt: all prefs (capped at 40 lines, 80 chars each) as
  "key: value" lines, and the top 5 facts matching the current request by FTS.
- The model must call remember() for anything the user states as a lasting preference
  ("I prefer metric", "my name is Ana", "never show thumbnails"). The system prompt
  lists this rule once.

### 1.10 Scheduler
- A thread inside llmos-agent polls tasks every 30 s. A due task runs the stored
  request through the same agent loop in background mode: ask_user is disabled and
  anything that would prompt is auto-denied and reported. Results append to
  notifications; the shell shows "1 scheduled task finished (type: tasks)" above the
  next prompt. No popups, no sounds.
- cron syntax via a 40-line parser (minute hour dom month dow), plus "in Nm/Nh/Nd"
  and ISO timestamps. Times are local (timezone chosen at onboarding, stored in
  /data/llmos/tz and written to /etc/localtime through the overlay at boot).

### 1.11 Theming and i18n model
- /data/llmos/theme.json (defaults in llmos/theme.py):
  {
    "palette": {"bg": "#101010", "fg": "#e6e6e6", "accent": "#7aa2f7",
                "muted": "#8a8a8a", "error": "#f7768e", "ok": "#9ece6a"},
    "corners": "rounded",         // rounded | square | none
    "font": "DejaVu Sans Mono", "font_size": 12, "padding": 12,
    "density": "normal",          // compact | normal | roomy
    "lang": {"default": "en", "sections": {"settings": "en", "system": "en",
             "answers": "en", "errors": "en", "prompts": "en"}}
  }
- set_theme(patch) merges, validates (colors are #rrggbb, corners in the enum,
  font_size 8..32) and applies:
  - palette: immediately through OSC 10/11/4 escape sequences to foot, no restart
  - font, font_size, padding: regenerate /run/llmos/foot.ini and exit 75 to restart
    foot (under 500 ms; transcript is reprinted)
  - corners, density: renderer settings in the shell, immediate
  - lang: renderer static strings switch per section; the system prompt tells the
    model which language to answer in per section
- "make everything purple" becomes {"palette": {"accent": "#9b59b6", "bg": "#1a1023",
  "fg": "#eee6ff"}}; the model produces the patch, the shell owns the rendering. The
  model is told the current theme so it can make relative changes ("a bit bigger").
- Sections: settings (onboarding, profile, permissions, theme messages), system
  (status lines, notifications), answers (model answers), errors, prompts (the input
  prompt and consent questions). Static strings live in llmos/i18n.py for en, zh, es,
  fr, de, ja (about 40 strings). Any other language is translated once by the model at
  set time and cached in /data/llmos/i18n-cache.json.
- "Generated UI": the model can attach ui blocks (section 2.1) and the renderer draws
  them with the theme (box characters chosen by corners, colors from palette). There is
  no other UI.

### 1.12 Anti-slop and anti-addiction rules (enforced in code where possible)
- Answers are short: n_predict 400 and a system prompt rule "answer in as few words as
  the request needs; no preamble, no summary of what you just did".
- Sources: web_search and fetch_page results carry URLs; the renderer prints the URL
  under any quoted text. show_image only renders downloaded images.
- No feeds, no recommendations, no autoplay: play_video plays exactly one video via
  mpv with --ytdl-raw-options=no-playlist= and --loop=no, then returns to the shell.
  web_search returns the requested n results and nothing else. There is no "related"
  tool.
- No engagement notifications: only scheduled tasks and explicit notify() calls appear,
  and only at the next prompt.
- No infinite scroll: the transcript pager is a plain scrollback (foot native).
- The system prompt forbids follow-up suggestions ("would you also like...") unless
  the user asked for options.

### 1.13 Privacy hardening and egress consent
- nftables policy (rootfs-overlay/etc/nftables.d/llmos.nft), loaded before networking:
  - inet filter output: policy drop; accept oif lo; accept ct state established,related
    (only meaningful once something is allowed out); mode chains:
    - mode off: nothing else. Default at first boot and after every boot until
      /data/llmos/network.json says otherwise (the llmos-net service applies the
      stored mode after /data is unlocked).
    - mode direct: accept udp dport 53, tcp dport {53, 80, 443, 993, 587, 465, 22}
      plus any ports the user allowed by name; everything else dropped and logged to
      the notifications ring (not to disk).
    - mode tor: accept only meta skuid tor to tcp dport {443, 9001, 9030}; all agent
      HTTP goes through socks5h://127.0.0.1:9050 (urllib via a tiny SOCKS5 wrapper in
      llmos/net.py, yt-dlp --proxy, mpv --ytdl-raw-options=proxy=). DNS never leaves
      except through Tor. MAC randomization via macchanger on link up in this mode.
  - inet filter input: policy drop; accept lo, established; no listening services
    except llama-server on 127.0.0.1 and nothing else. sshd is not installed.
- Consent flow: onboarding asks "Internet access: off / direct / through Tor". Later
  requests that need the network while mode is off trigger ask_user("This needs the
  internet. Enable direct access, use Tor, or cancel?") regardless of profile, because
  first egress is a consent decision, not a permission class.
- Egress of personal data (class E): email.send, files uploads via shell (curl -T,
  scp are matched to E), and model downloads are N. Balanced asks for E every time
  unless "always" was granted.
- No telemetry, no crash reporting, no update checks. Updates are manual: "check for
  a new LLMOS" fetches a version file only when the user asks.
- Logs: journald is absent (OpenRC, busybox syslog disabled). llmos-agent writes only
  to /data/llmos/transcript in the SQLite db; nothing to the system partition.
- Time sync: chrony disabled by default; the user can ask to sync time (N).

### 1.14 Onboarding (first boot, or /data missing)
1. Language for the whole UI (default en).
2. Keyboard layout.
3. Profile: autonomous / balanced / careful with one-line descriptions.
4. Internet: off / direct / tor.
5. Persistent storage: pick a disk from lsblk (or "none, run from RAM"), passphrase
   twice, the warning about no recovery, cryptsetup luksFormat, mkfs.ext4, mount.
6. Model: keep bundled (Qwen3.5-2B) or pick from the catalog (needs internet).
7. Name to call the user (optional), timezone.
Everything after step 5 is stored on /data. Onboarding is a plain Python script
(llmos/onboarding.py) with numbered choices, not driven by the model.

## 2. Agent action protocol

### 2.1 Model output JSON schema (llmos/schema.py)

{
  "type": "object",
  "properties": {
    "say": {"type": "string", "maxLength": 1200},
    "ui": {"type": "array", "maxItems": 4, "items": {"oneOf": [
      {"type":"object","properties":{"type":{"const":"table"},"headers":{"type":"array","items":{"type":"string"}},"rows":{"type":"array","items":{"type":"array","items":{"type":"string"}}}},"required":["type","headers","rows"]},
      {"type":"object","properties":{"type":{"const":"list"},"items":{"type":"array","items":{"type":"string"}}},"required":["type","items"]},
      {"type":"object","properties":{"type":{"const":"choice"},"question":{"type":"string"},"options":{"type":"array","items":{"type":"string"}}},"required":["type","question","options"]},
      {"type":"object","properties":{"type":{"const":"quote"},"text":{"type":"string"},"source":{"type":"string"}},"required":["type","text","source"]}
    ]}},
    "actions": {"type": "array", "maxItems": 4, "items": {"oneOf": [
      {"type":"object","properties":{"tool":{"const":"shell"},"args":{"type":"object","properties":{"cmd":{"type":"string"},"timeout_s":{"type":"integer"}},"required":["cmd"]}},"required":["tool","args"]},
      {"type":"object","properties":{"tool":{"const":"set_brightness"},"args":{"type":"object","properties":{"percent":{"type":"integer","minimum":0,"maximum":100}},"required":["percent"]}},"required":["tool","args"]},
      {"type":"object","properties":{"tool":{"const":"set_volume"},"args":{"type":"object","properties":{"percent":{"type":"integer","minimum":0,"maximum":100},"mute":{"type":"boolean"}},"required":["percent"]}},"required":["tool","args"]},
      {"type":"object","properties":{"tool":{"const":"set_theme"},"args":{"type":"object","properties":{"patch":{"type":"object"}},"required":["patch"]}},"required":["tool","args"]},
      ... one entry per tool in 1.7, generated from the tool registry ...
    ]}},
    "done": {"type": "boolean"}
  },
  "required": ["say", "actions", "done"]
}

- The schema is generated at startup from the tool registry (each tool declares its
  args schema in a decorator), so the grammar and the Python validator never drift.
- llama.cpp compiles the schema to a GBNF grammar. With oneOf per tool the model
  cannot invent tool names or omit required args. Free-form fields (shell cmd, theme
  patch object) stay open because they must be.
- Tool subsetting per turn: to keep the grammar small and the model focused, the
  registry exposes all tools but the system prompt lists them in one compact line
  each (name(args): purpose). The schema stays complete; the prompt is the guide.

### 2.2 System prompt outline (llmos/prompt.py), about 550 tokens of static prefix

1. Identity: "You are LLMOS, the operating system of this computer. The user owns
   this machine; carry out requests concisely. Reply with one JSON object."
2. Output rules: say is what the user sees (short, no preamble, no suggestions unless
   asked, cite URLs when quoting the web). done=true when nothing more is needed.
   done=false when you need tool results first. Use ask_user only when the request
   is genuinely ambiguous.
3. Tool catalog: one line per tool, generated from the registry.
4. Behavior rules: prefer real sources (web_search then fetch_page) to guessing; never
   autoplay or recommend; remember() lasting preferences; no follow-up offers.
5. Dynamic section (after the static prefix, so the prefix stays cached):
   - date/time and timezone, network mode, profile name, current theme (compact)
   - languages per section
   - preferences (from memory.db)
   - top facts matching the request
6. Then the conversation: last 6 user/assistant exchanges truncated to 2000 tokens,
   the current user message, and tool results as they come.

### 2.3 Loop (llmos/agent.py)

  run(request):
    fast = fastpath.match(request)          # optional deterministic handling
    if fast: execute and return
    messages = build(request)
    for step in range(8):
      out = llm.chat(messages, schema, n_predict=400, temperature=0.3, top_p=0.9)
      render(out.say, out.ui)
      if not out.actions or out.done and not out.actions: return
      results = []
      for a in out.actions[:4]:
        decision = permissions.check(a)     # allow / ask / deny
        if decision == ask: answer = shell.consent(a); if no: results.append(denied); break
        r = tools.run(a, timeout)           # each result is a dict {ok, output, error}
        results.append(r)
        if a.tool == "ask_user": return    # turn ends; the answer arrives as the next request
        if not r.ok: break                  # let the model see the failure before continuing
      messages.append(assistant=json.dumps(out))
      messages.append(user="TOOL RESULTS\n" + format(results))   # role user, not tool, for template safety
      if out.done and all ok: return
    render(error "stopped after 8 steps")

- Tool results are truncated to 1500 characters each, with "[truncated, N more chars]"
  and the original saved to /data/llmos/scratch/last-<tool>.txt so the model can
  fetch more with files.read if needed.
- Streaming: say is streamed as tokens arrive by parsing the partial JSON string of
  the say field (a small incremental scanner on the "say":" prefix), so the user sees
  text within the first second even on CPU. Actions run after the object completes.
- Temperature 0.3 for the action loop; 0.7 when the request is classified as creative
  writing by a keyword table (poem, story, joke). Keep it that simple.

### 2.4 Keeping latency low on CPU
- Context 4096, one slot, cache_prompt true (server default). The static prefix (about
  550 tokens) is identical every call so prompt processing per turn is only the
  dynamic part (150 to 400 tokens) plus history.
- --cache-reuse 256 lets llama-server shift the KV cache when only the middle changes
  (memory lines change rarely).
- n_predict 400 hard cap, and the grammar ends the object early when done=true and
  actions is empty, typically 40 to 120 tokens for a simple answer.
- Thinking disabled (chat_template_kwargs enable_thinking=false).
- Fast paths (llmos/fastpath.py), regex, no model: "volume N", "mute", "brightness N",
  "play <url>", "stop", "quit", "help", "settings", "show permissions". They render
  the same way as agent actions and take about 50 ms. Everything else goes to the
  model. The user can disable fast paths with a preference.
- History budget 2000 tokens; older turns are dropped, not summarized (summaries cost
  a model call).
- llama-server warm-up: the llmos-llm service sends one 1-token request at start so
  the first user request does not pay for model page-in.
- Expected on a 4-core 2015 laptop with the 2B Q4_K_M: prompt 60 to 90 tok/s, gen 8 to
  12 tok/s, so a simple command completes in 3 to 5 s and a web-research answer in
  20 to 40 s.

### 2.5 Tool result feedback format

  TOOL RESULTS
  1. web_search ok
  [1] Title | https://... | snippet
  [2] ...
  2. fetch_page ok
  <text, max 1500 chars>
  3. shell error (exit 1)
  <stderr tail>

Deterministic, numbered, easy for a small model to reference.

## 3. Repository layout

  LLMOS/
    docs/ARCHITECTURE.md             this file
    Makefile                         make iso | make ci-iso | make test | make qemu
    build/
      Dockerfile                     alpine:edge with xorriso, grub, squashfs-tools, mtools
      build.sh                       orchestrates the steps below inside the container
      mkrootfs.sh                    apk --root, overlay copy, services, cleanup
      packages.txt                   the apk package list (one per line)
      mkinitramfs.sh                 busybox static init + needed modules
      init.sh                        the initramfs /init script
      fetch-model.sh                 HF download with size and sha256 check, cache in build/cache
      mkiso.sh                       squashfs + grub-mkrescue
      grub.cfg
      install.sh                     becomes /usr/bin/llmos-install in the rootfs
    rootfs-overlay/                  copied verbatim over the apk root
      etc/inittab                    tty1 and ttyS0 run llmos-session, no getty
      etc/init.d/llmos-data          LUKS unlock and mount /data (prompt on console)
      etc/init.d/llmos-net           nftables policy, network mode, iwd, tor
      etc/init.d/llmos-llm           llama-server
      etc/init.d/llmos-agent         agent daemon (scheduler, tools, unix socket)
      etc/init.d/llmos-persist       reinstall persisted apk packages
      etc/nftables.d/llmos.nft
      etc/tor/torrc
      etc/mpv/mpv.conf               no config from ytdl, no playlist, vo auto, ao alsa
      usr/lib/llmos/session.sh       cage or tty launcher and the foot restart loop
      usr/lib/llmos/foot.ini.tmpl
      usr/bin/llmos-shell            python3 -m llmos.shell
      usr/bin/llmos-install
      usr/lib/python3.12/site-packages/llmos -> installed from ./llmos
    llmos/                           the Python package (stdlib only)
      __init__.py, shell.py, agent.py, llm.py, prompt.py, schema.py, permissions.py,
      memory.py, scheduler.py, theme.py, i18n.py, render.py, fastpath.py, net.py,
      models.py, onboarding.py, hw.py (brightness/volume with fake mode),
      tools/__init__.py (registry and decorator), tools/system.py, tools/web.py,
      tools/media.py, tools/files.py, tools/email.py, tools/network.py,
      tools/memory.py, tools/schedule.py, tools/model.py
    tests/
      unit/                          pytest (from Alpine package py3-pytest) for schema,
                                     permissions, theme merge, cron parser, fastpath,
                                     render, tool arg validation, nft file generation
      integration/                   runs inside the Alpine build container with a real
                                     llama-server and the 0.8B model: agent loop end to end
                                     with a fake hw backend, DDG search mocked by a local
                                     HTTP server
      qemu/run.sh                    boot the ISO under TCG with serial console
      qemu/driver.py                 talks to the serial console, drives onboarding,
                                     asserts outputs, takes QMP screendumps
      qemu/expectations.md           the acceptance checklist in 5.3
    scripts/dev-shell.sh             run llmos.shell on the host in text mode against a
                                     local llama-server for quick iteration

## 4. Build pipeline

### 4.1 Steps (make iso runs all inside docker)
1. build/Dockerfile: FROM alpine:edge; apk add alpine-conf xorriso grub grub-bios
   grub-efi mtools squashfs-tools cpio python3 py3-pytest curl. Build host tools are
   only used to run docker and QEMU.
2. mkrootfs.sh:
   - apk --root /work/rootfs --arch x86_64 --initdb -X <edge main> -X <edge community>
     -U --allow-untrusted add $(cat packages.txt)
   - packages.txt: alpine-base openrc linux-lts linux-firmware-i915
     linux-firmware-amdgpu linux-firmware-iwlwifi linux-firmware-rtw88 mesa-dri-gallium
     seatd cage foot foot-terminfo mpv yt-dlp chafa brightnessctl wlr-randr font-dejavu
     font-noto-cjk alsa-utils alsa-ucm-conf llama-cpp (or llama-server, verify the
     name at build) python3 sqlite tor nftables cryptsetup e2fsprogs iwd macchanger
     w3m curl ca-certificates tzdata zram-init util-linux sgdisk dosfstools eudev
     kbd bkeymaps
   - copy rootfs-overlay, install ./llmos into site-packages, python3 -m compileall
   - rc-update add for: devfs sysfs procfs udev seatd llmos-data llmos-net llmos-llm
     llmos-agent llmos-persist; runlevel default
   - remove /var/cache/apk/*, man pages, docs, locale data except en, zh, es, fr, de, ja
   - write /etc/llmos/version and a /etc/llmos/packages.sha256 manifest
3. fetch-model.sh: MODEL_ID=${MODEL_ID:-qwen3.5-2b}; resolves repo and file from
   llmos/models.py, GETs https://huggingface.co/api/models/<repo>/tree/main to confirm
   the file and its lfs sha256, downloads with curl -C - into build/cache, verifies.
4. mkinitramfs.sh: busybox.static, init.sh, modules resolved with modprobe -S <kver>
   --show-depends for: loop squashfs overlay isofs vfat ext4 dm-crypt dm-mod
   virtio_pci virtio_blk virtio_scsi virtio_net virtio_gpu sd_mod sr_mod ahci nvme
   usb_storage uas xhci_pci ehci_pci simpledrm i915 amdgpu; packed with cpio + gzip.
5. init.sh (initramfs): mount proc sys dev; modprobe list; wait up to 20 s for a
   device with label LLMOS (blkid loop); mount ro; losetup and mount
   /llmos/system.squashfs; mount tmpfs upper; mount overlay on /newroot; bind the ISO
   at /newroot/run/llmos/media so models/ is reachable; switch_root /newroot /sbin/init.
6. mkiso.sh: mksquashfs rootfs system.squashfs -comp xz -b 1M -noappend; assemble
   iso/ tree; grub-mkrescue -o llmos.iso iso/ -- -volid LLMOS; report size.
7. make ci-iso: same with MODEL_ID=qwen3.5-0.8b.
8. make test: docker run the build image, pytest tests/unit, then tests/integration
   with a llama-server started in the container on the 0.8B model.
9. make qemu: tests/qemu/run.sh llmos-ci.iso (see section 5).

Build time estimate on the given host: rootfs 3 to 5 min (mirror speed), squashfs xz
about 4 min on 4 cores, grub-mkrescue under 1 min, model download 1 to 5 min cached
thereafter. Disk use under 8 GB.

### 4.2 Service order at runtime
udev, seatd -> llmos-net (nftables drop-all first, then iwd if wifi) -> llmos-data
(passphrase prompt; skipped if no /data configured yet) -> llmos-llm -> llmos-agent ->
inittab respawns llmos-session on tty1 (cage) or on ttyS0 when llmos.console=serial.
The shell shows "loading model..." until llmos-llm answers /health.

### 4.3 Session launcher (usr/lib/llmos/session.sh)
- If a DRM device exists and kernel cmdline lacks llmos.console: exec cage -- session
  loop with foot. Otherwise run the loop directly on the tty with TERM=linux and
  render.py in "plain" mode (no sixel, ASCII boxes).
- Loop: python3 -m llmos.theme --emit-foot-ini > /run/llmos/foot.ini; foot ... ;
  exit code 75 -> loop again; anything else -> sleep 1 and loop.

## 5. QEMU test plan

### 5.1 Invocation (tests/qemu/run.sh)
  qemu-system-x86_64 -accel tcg,thread=multi -smp 4 -m 4096 -cpu max
    -cdrom llmos-ci.iso -boot d
    -drive file=blank.qcow2,if=virtio,format=qcow2  (2 GB, created fresh)
    -display none -vga virtio
    -serial mon:stdio or -chardev socket for the driver
    -qmp unix:/tmp/qmp.sock,server,nowait
    -netdev user,id=n0,restrict=on -device virtio-net-pci,netdev=n0
  restrict=on makes the guest network dead, which is what we want for the egress test;
  a second run uses restrict=off with a local HTTP server on the host reachable via
  10.0.2.2 to test consented direct mode.
- Boot menu: the driver sends the keys to pick the "serial console" GRUB entry, or the
  CI ISO defaults to it via grub env (simpler: ci-iso sets default=2).
- UEFI variant: same command with -bios /usr/share/OVMF/OVMF_CODE.fd, boot only.

### 5.2 Driver (tests/qemu/driver.py)
pexpect-free: a small stdlib socket reader with expect(pattern, timeout). Timeouts are
generous for TCG: boot 6 min, model answer 5 min, other steps 60 s.

### 5.3 Acceptance criteria (each is a driver step with a pass/fail line)
1. BIOS boot reaches "LLMOS onboarding" on the serial console within 6 minutes.
   UEFI boot (OVMF) reaches the same prompt (boot only, no further steps).
2. Onboarding: choose en, us keyboard, profile balanced, network off, disk vda,
   passphrase "test-pass-1" twice; the driver then checks lsblk output shows
   vda1 as crypto_LUKS and /data mounted (via the hidden debug command ":sh lsblk -f").
3. Model answers: send "say hello in three words"; expect a non-empty answer line from
   a valid JSON turn within 5 minutes; the driver also queries ":sh curl -s
   127.0.0.1:8080/health" to see {"status":"ok"}.
4. Theme change: send "make everything purple and no rounded corners"; expect the
   agent to call set_theme; verify /data/llmos/theme.json has corners=square and a
   palette whose accent differs from default; in text mode the renderer prints the
   ASCII box style change (the driver sees "+--" instead of round markers). A QMP
   screendump is taken in the graphical run for humans to inspect; not asserted.
5. Brightness and volume: send "set brightness to 40%" and "volume 30"; the fake hw
   backend (enabled by kernel cmdline llmos.fakehw=1 on the CI ISO) writes
   /run/llmos/hw.json; the driver asserts brightness=40 and volume=30 and that the
   fast path handled "volume 30" in under 2 s, while the brightness sentence went
   through the model.
6. Network blocked until consent: ":sh nft list ruleset" shows output policy drop
   and no accept for dport 443; ":sh curl -m 5 http://10.0.2.2:8000/" fails.
   Send "search the web for alpine linux"; expect the consent question about
   enabling internet; answer "direct"; ruleset now accepts 443; curl to the host
   fixture succeeds (restrict=off run).
7. Memory persists: send "remember that I prefer metric units", reboot the VM
   (system.power reboot is class D, the driver approves), unlock with the passphrase,
   ask "what units do I prefer" and expect "metric" in the answer.
8. Reboot without the disk still shows onboarding (no state leaked to the ISO).
9. Unit and integration suites pass in the container (make test) before any ISO build
   is attempted; the ISO build is skipped if they fail.

Criteria 1, 2, 3, 5, 6 are blocking for v0.1; 4, 7, 8 are required before calling
the day two build done.

## 6. Risks and mitigations

- Tiny model reliability (wrong tool, hallucinated args, ignoring done). Mitigations:
  grammar-constrained oneOf schema; fast paths for the most common commands; tool
  results in a numbered deterministic format; max 8 steps; the shell shows each
  action as it runs so the user can interrupt with Ctrl-C (kills the tool, ends the
  turn); default model is the 2B, with the 4B one command away for 12 GB machines.
- Qwen3.5 template quirks (thinking tags, tool-call formatting). Mitigation:
  enable_thinking false through chat_template_kwargs; we do not use native tool
  calling, only JSON output, so template tool support is irrelevant. Integration test
  covers a 3-step loop on the 0.8B model.
- TCG slowness: 0.8B model in CI, n_predict small in tests, timeouts of minutes,
  -accel tcg,thread=multi, -cpu max for AVX2 so llama.cpp uses vector kernels under
  emulation. If the answer step still exceeds 5 minutes, the CI ISO builds llama.cpp
  flags -c 1024 and the test sends a 5-token request.
- No GPU in the VM: -vga virtio gives virtio-gpu DRM so cage can start; the serial
  path tests everything functional anyway, and the graphical run is smoke-only
  (screendump not asserted).
- Alpine edge package churn (package name for llama-server, cage versions). Mitigation:
  mkrootfs.sh pins the edge snapshot by writing the mirror URL and recording the
  installed versions to /etc/llmos/packages.sha256; if a package is missing the
  build fails at step 2, not at boot.
- github.com blocked on the build host: no dependency is fetched from GitHub; llama.cpp,
  yt-dlp and everything else come from Alpine, models from HF. yt-dlp updates are
  through apk only.
- DuckDuckGo HTML endpoint changes or rate limits. Mitigation: parser kept in one
  function with a fixture test; fallback to the lite endpoint (lite.duckduckgo.com)
  and clear error to the user. No API keys anywhere.
- YouTube breakage (yt-dlp needs frequent updates). Mitigation: install_package
  yt-dlp upgrade path; play_video reports the yt-dlp error verbatim instead of retrying.
- Foot restart on font changes loses live scrollback. Mitigation: the shell reprints
  the last 200 transcript lines from memory.db; colors do not need a restart.
- LUKS on the live USB: users may pick the wrong disk. Mitigation: onboarding shows
  model, size and existing partitions for each disk and requires typing the disk name
  and "ERASE" once; the installer does the same.
- 8 GB RAM headroom: 2B model 1.3 GB + KV 0.3 GB + rootfs overlay in RAM 0.4 GB +
  mpv 0.3 GB fits comfortably; the 4B tier is refused with a clear message below
  10 GB RAM; zram swap enabled below 8 GB.
- Root agent plus shell tool: a wrong command can break the running system. The
  system is immutable, so a reboot restores it; /data is the only thing at risk and
  destructive patterns are class D (balanced asks). Careful mode asks for every change.
- Tor mode DNS leaks. Mitigation: nftables drops all UDP 53 in tor mode; urllib
  requests use socks5h so names resolve inside Tor; yt-dlp and mpv get the proxy flag;
  the test asserts the ruleset in tor mode (unit test on the generated nft file).
- Email tool complexity for inbox zero. Mitigation: v0.1 ships IMAP list/read/archive/
  delete and SMTP send with plain imaplib and smtplib; no OAuth (Gmail users need an
  app password); the model loops through unread mail in batches of 20 with the user
  approving archive/delete per batch in balanced mode.
- Voice: out of scope for v0.1 (whisper.cpp not in Alpine). Placeholder tool
  voice.setup explains it will use whisper.cpp from apk when packaged; piper and
  espeak-ng from Alpine give optional TTS through say-aloud preference later.

## 7. Build order for the engineer (two days)

Day 1
1. Repo skeleton, tool registry, schema generation, permissions, theme, i18n, render,
   memory, fastpath with unit tests (about 3 hours).
2. llm.py client and agent loop; run against a host llama-server with the 0.8B model
   through scripts/dev-shell.sh; integration test for a 3-step loop (2 hours).
3. Tools: system, web, media, files, memory, schedule, network, model (3 hours).
4. Docker build: rootfs, initramfs, iso; first boot under QEMU to the shell (3 hours).

Day 2
5. Onboarding, llmos-data (LUKS), llmos-net (nftables and modes), llmos-install (3 h).
6. cage and foot session, theme apply via OSC and restart, sixel images, mpv path,
   test on real hardware from USB if available (2 h).
7. Email tool and scheduler (2 h).
8. QEMU driver with the acceptance checklist, fix what fails, write README (3 h).

Out of scope for v0.1: voice input, OAuth mail, model fine-tuning, multi-user,
secure boot, encrypted system partition, GPU offload (llama-server Vulkan build could
be added later as an apk variant).
