# LLM OS

An operating system you talk to. It boots to a desk with one bar at the
bottom; you type (or say) what you want — *"what's using my disk?"*, *"make
everything purple"*, *"every morning at 8, give me the weather"*, *"play some
lofi"*, *"get me to inbox zero"* — and the computer does it, using a language
model that runs entirely on the machine. The interface is generated: what you
ask for appears as windows the OS composes on the spot (a settings panel, your
inbox, a photo, a research result with its sources), in the colours, corners
and language you chose. No apps to find, no menus, no accounts, nothing
leaves the computer unless a request needs the internet and you allowed it.

**Images:** `llmos-arm64.qcow2` (Apple Silicon Macs, arm64 VMs) and
`llmos-x86_64.qcow2` (ordinary PCs and laptops, BIOS or UEFI, installable next
to macOS on Intel Macs or next to Windows). Checksums in `SHA256SUMS`.

## Run it (macOS, Apple Silicon)

```bash
brew install qemu llama.cpp     # llama.cpp is optional: it enables host-GPU mode
./run-llmos.sh
```

A window opens: that is the computer. Your terminal shows a spare text
console (press Enter there to use the OS as plain text instead). Quit by
saying `shutdown` in the window, or with Ctrl‑A then X in the terminal.

### Host‑GPU mode (recommended on a Mac)

A virtual machine cannot use the Mac's GPU, so by default the model would run
on the VM's four CPU cores. With `llama.cpp` installed, the launcher instead
serves the *same* verified model on the Mac's GPU (Metal) and the guest talks
to it over the VM's private link — still entirely on this computer, still no
network (the server is bound to 127.0.0.1 and the OS's firewall allows only
that link even with internet turned off). Measured on an M4 Mac mini:

| | VM CPU (4 cores) | Mac GPU (Metal) |
|---|---|---|
| reading a request (prompt tokens/s) — Ministral 3 3B | 46 | 453 |
| writing a reply (tokens/s) — Ministral 3 3B | 27 | 33 |
| reading — Gemma 4 E2B | 156 | 756 |
| writing — Gemma 4 E2B | 43 | 49 |

Reading speed is what you notice: a typical request takes 5–7 s in host‑GPU
mode, web research 15 s. The first run fetches the model file once (2.1 GB
for the default) from the lab's official repository and checks its SHA‑256
against `catalog.json`.

`LLMOS_MODEL=gemma-4-e2b ./run-llmos.sh` serves a different catalog model;
`LLMOS_HOST_GPU=0` forces the model back inside the VM. The server takes the
first free local port (8080, 8090, …; `LLMOS_MODEL_PORT` to choose) and the
OS's firewall allows exactly that port even with the internet turned off. Gemma 4 models also
get **speculative decoding** automatically (their multi‑token‑prediction draft
head, a 59 MB verified file): about 1.5× faster replies, identical output.
`LLMOS_WIDTH`/`LLMOS_HEIGHT` set the screen size (default 1440×900; the window
zooms to fit).

Optional voice input: `brew install ffmpeg`, then run `python3 mic-bridge.py`
in another terminal before starting the VM (QEMU on macOS can't capture the
microphone itself; the bridge streams it in over loopback, push‑to‑talk only).
On Linux with KVM the same script works (`./run-llmos.sh`); on anything else it
falls back to slow emulation.

## Real computers (x86‑64 PCs and laptops, Intel Macs)

`llmos-x86_64.qcow2` is the same OS built for ordinary computers: Alpine's
full `lts` kernel, firmware for the common Intel/Realtek/Qualcomm/Broadcom/
MediaTek Wi‑Fi and Intel/AMD graphics, CPU microcode, an NVMe‑capable
initramfs, Wi‑Fi via iwd, and GRUB installed for **both** BIOS and UEFI.

**Try it from a USB stick** (the stick becomes the computer; nothing on the
internal disk is touched):

```bash
qemu-img convert -O raw llmos-x86_64.qcow2 llmos-x86_64.img
sudo dd if=llmos-x86_64.img of=/dev/rdiskN bs=4m     # the whole stick is erased
```

Boot from it (PCs: the boot menu key at power‑on, usually F12/F8/Esc; Intel
Macs: hold Option and pick "EFI Boot"). The OS runs on the screen; the first
boot grows into the stick.

**Install it next to macOS or Windows** ("dual boot"): first make free space
(macOS: Disk Utility → Partition → add a partition, or shrink; Windows: Disk
Management → Shrink Volume — 20 GB or more), boot the stick, and say
*"install LLM OS on this computer"*. The OS shows the plan — which disk, how
much free space it will use, which other system it found and will keep, that
the existing EFI partition is shared — and only writes when you press *Install
now*. Everything you already set up on the stick (name, settings, memory, the
encrypted vault) moves with it. *"Erase the whole disk and install LLM OS"*
uses a whole disk instead. On a Mac, hold Option at startup and choose "EFI
Boot" to start LLM OS; on a PC pick it in the firmware boot menu (an "LLM OS"
entry is added where the firmware allows). Intel Macs with the T2 chip need
Startup Security Utility set to *No Security* + *Allow booting from external
media*; their keyboard/trackpad/audio need drivers not yet in the standard
kernel, so use an external keyboard there. Wi‑Fi on Macs with Broadcom chips
may need firmware from macOS.

**Apple Silicon Macs (M1–M4) cannot boot this natively.** They need the Asahi
Linux boot chain (m1n1 + U‑Boot) and an Apple‑specific kernel (16 K pages,
Apple NVMe/keyboard/display drivers) that only exists in Alpine's testing
repository; Asahi itself supports M1–M3 but not M4 as of September 2026. On
those Macs LLM OS runs as the virtual machine above, in host‑GPU mode.

Hardware‑specific parts (Wi‑Fi, backlight, sound) use the standard kernel
drivers and were verified in QEMU (BIOS and UEFI), not on physical machines
here. On a real machine the model runs on the CPU; see *Requirements*.

## First boot

A short set‑up on screen — six steps, each one card: language (your Mac's is
pre‑selected), your name, time zone (type a city; pre‑filled from your Mac),
how much the OS may do on its own (three choices with plain explanations;
hands‑off is recommended), internet (yes / yes through Tor / stay offline),
and an optional passphrase (with a *Show* button so you can see what you
typed). On a laptop with no connection yet, a Wi‑Fi step lists the networks
in range. The last card offers three example requests to try with one click,
and the desk opens with a *Try saying* window of more — there are no apps to
discover, so the examples are the tour. With a passphrase, everything
personal — memory, tasks, notes, files, the audit log — lives in a LUKS2
(argon2id) encrypted vault that is only opened when you type it. There is no
recovery: forget the passphrase and that data is gone, by design.

## Using it

Type what you want in the bar (or press the microphone / F1 and speak); ↑/↓
recall earlier requests. The reply appears above the bar; anything better
shown than said opens as a window you can move, resize, maximize (double‑click
its title), minimize or close (Esc or Ctrl+W closes the front one). The chips
in the top bar are live: the model chip opens *Models*, the autonomy chip
opens *Settings*, the lock chip locks. Programs you ask for — a browser, a
terminal, a video — open as ordinary windows on top. "Make everything bigger"
scales the whole interface (older eyes welcome).

The computer itself is the orb at the left of the bar: it breathes when
idle, turns a ring while it thinks, pulses while it listens or reads aloud,
goes amber when it needs your answer, and turns blue while a request is out
at an online model. Its reply always sits above the
windows: a one‑line answer steps aside by itself after a few seconds, and a
longer one folds to a single line above the bar the moment you click a window
(click the line to unfold it). An empty desk greets you with three things to
try. Everything moves — windows
grow out of the bar, replies rise, toasts drop, colours cross‑fade — and how
much is yours to set: *Settings → Animations* or "fewer animations" / "turn
off animations" / "turn animations on". Some things it does:

| You say | What happens |
|---|---|
| "how much disk space is free?" | runs the real command, tells you |
| "make everything purple" / "no sharp corners" / "settings in Chinese, rest in English" | the whole interface regenerates around your preference, live — colours are kept readable automatically |
| "settings" · "models" · "tasks" · "memory" · "audit" | the system's own windows; every control in them is a request in words, so a button can never do more than you could say |
| "remember I'm vegetarian" · "what do you know about me?" | on‑device memory, kept across reboots |
| "every weekday at 8 give me a summary of my day" · "in 20 minutes remind me to stretch" | runs later on its own; results wait in a "While you were away" window |
| "what's the latest on the Artemis program?" | searches the web, reads the page, answers with the source — the pages it read are listed in a *Sources* window |
| "show me a photo of the Eiffel Tower" · "use a photo of the Alps as my wallpaper" | a real photograph (Wikimedia Commons, credited), never a generated one |
| "play some lofi hip hop" · "pause" · "stop" | finds it (YouTube via yt‑dlp), plays it in a window, with a *Now playing* card to control it |
| "set up my email: address me@example.com, password …" · "what's in my inbox?" · "get me to inbox zero" · "reply to Alice that Friday works" | IMAP/SMTP with any provider (app password for Gmail/Outlook/Yahoo/iCloud); the inbox is a window with Read/Archive buttons and a reply form; *inbox zero* reads every unread mail, archives newsletters/notifications/junk on its own and lists what actually needs you |
| "give me a real quote from Marcus Aurelius" | verbatim, attributed quotes from Wikiquote — never invented ones |
| "show me my disk, memory and tasks in one panel" | the model composes a window (stats, lists, tables, buttons) in your style |
| "show my files" · "open my downloads folder" · "open the file ~/notes.txt" · "delete the file ~/old.txt" | a *Home* or folder window with Open/Delete buttons; text and code open as windows, pictures as images, music and video play; deleted files go to `~/.Trash`, so nothing is lost by a slip |
| "take a screenshot" | saved in `~/Pictures` and shown |
| "show the trash" · "restore report.pdf" · "empty the trash" | the trash is a window with *Restore* and *Delete for good* buttons; restored files go back where they were |
| "add milk to my shopping list" · "remember to call Sam" · "note that the plumber comes Tuesday" · "what's on my to-do list?" · "tick off milk" · "clear my shopping list" | lists and notes kept on the device, each a window with Done/Remove buttons (also behind *Lists* in the *Try saying* window) |
| "set a timer for 10 minutes" · "remind me in 20 minutes to stretch" | a chime, a toast and a *While you were away* card when it lands (spoken too if replies are read aloud) |
| "set up a passphrase" · "encrypt my data" | creates the encrypted vault later if you skipped it at first boot (a form on screen, the prompt on the console); everything already in your home moves into it |
| "lock after 10 minutes of inactivity" · "turn off auto-lock" (with a passphrase vault) | the vault closes by itself when you step away; *Settings → Auto-lock* has Never / 5 / 15 / 60 min |
| "brightness 60" · "turn the screen down" · "volume 30" · "louder" · "mute" | handled by the OS directly, no model in the loop; the keyboard's brightness and volume keys do the same |
| "turn off animations" · "fewer animations" | a calmer screen; *Full* is the default — measured on 2 cores, it costs no reply speed |
| "I want a Windows 7 desktop" · "make it look like a Mac" · "give me a clean desk" | the same windows rearranged: a taskbar with a start menu and every open window listed, or a menu bar with a dock and traffic‑light buttons, or the clean LLM OS desk; colours follow (*Settings → Desk layout*) |
| "ask claude: write me a cover letter" · "here: what time is it" | one request to the online model (if an account exists) or kept on this computer, whatever the *where it thinks* setting says |
| "use the online model for everything" · "think only on this computer" · "set up the online model" | the *where it thinks* setting and the account form (loosening it asks once, like any policy) |
| "open a terminal window" · "install a web browser and open example.com" · "open htop" | real windows on the desk (Alt‑Tab switches, Super+Q closes, Super+Esc minimizes) |
| "connect to Wi‑Fi HomeNet with password …" (real computers) | iwd; remembered for next time |
| "install htop" · "delete my old logs" · "turn off syslog" | root admin, done — it's your machine |
| "ask before deleting things" · "use Tor" · "no internet" · "focus mode for 2 hours" | policies enforced by the OS (firewall, Tor routing, hosts file), not just promised |
| "use ministral 8b" · "download gemma 12b" | switch or fetch models — official releases only, verified by SHA‑256 |
| "lock" · "shutdown" | closes the programs you opened and then the vault (passphrase to reopen) · powers off |

### The set‑up quiz

The first run asks your language, name and time zone, then shows six
sliders. Each one's meaning is written out as you move it, and the model it
implies is named underneath:

- **How much should it ask?** → hands‑off / balanced / hands‑on (below).
- **Internet** → connected / asks each time / offline (the firewall then
  blocks everything).
- **Where it thinks** → only on this computer / here, but it asks before a
  big request goes to an online model / an online model answers everything.
- **On‑device model** → fast and light / in between / the most capable this
  machine can run (downloaded after set‑up if it isn't installed).
- **Guidance** → follows your instructions on your machine, no lectures (the
  default) / keeps a standard assistant's caution.
- **Screen** → calm / reduced / lively.

If the "where it thinks" slider asks for an online model, the next page takes
the account: Claude (Anthropic; keys come from console.anthropic.com) or any
OpenAI‑compatible service (address + model name + key). The key is checked
with one tiny request and kept with your data inside the vault; usage is
billed to that account. Skip it and everything is answered on this computer
until you add one in Settings. Every slider maps to a setting you can change
later in words.

### Autonomy

Chosen at set‑up, changeable any time by asking (or in Settings):

- **hands‑off** (default): does everything without asking.
- **balanced**: asks before destructive or irreversible actions.
- **hands‑on**: asks before every change.

Every tool action is written to an audit log (`audit`) in all modes. Changing
the internet/Tor/autonomy/online‑model policy itself always asks, so a
background task can't loosen its own leash. Writing to the computer's disk
(the installer) always shows its plan first. Scheduled tasks follow the same
level: under hands‑off they do what you scheduled; under balanced or hands‑on
anything that would have asked is left undone and reported.

### Where it thinks

- **Only on this computer** (default): nothing is ever sent to an online
  model; the code path is never taken.
- **Here; asks before going online for big tasks**: short requests are
  answered here. A long or open‑ended one ("write me a cover letter…"), or one
  this computer could not finish, brings one dialog: *Ask Claude Sonnet 5
  (online)?* It says what goes — your request, the recent conversation and
  what it does on this computer while working, never your memory or name.
- **Online model for everything**: the online model answers, with your
  memory; this computer answers when it can't be reached.

"ask claude: …" sends one request online whatever the setting (if an account
exists); "here: …" keeps one on this computer. While a request is out, the orb
turns blue and the reply card says *online · Claude Sonnet 5*; the audit log
has an `online_model` line for each one. With the internet off, nothing goes
online. "forget the online model" removes the account. An online model
follows its provider's rules as well as yours.

### Time, and things it has done before

The reply card shows how long it has been thinking and how long that usually
takes on this machine (*thinking… 12 s / usually ~8 s*), from the model's own
speed figures. Downloads show the time left. A short request the model
handled before in one step ("what's the uptime", "open my downloads") is a
*routine*: the next time, the same actions run straight away under the same
confirmation rules and only the answer is written (*doing what I did last
time for this* in the activity line); one that stops working is forgotten.

### What it will and won't do

It does what its owner says on the owner's own machine — no lectures, no
disclaimers, no second‑guessing your files, your settings, your software.
The single boundary is harm to *other* people. Honesty is not negotiable: it
never claims an action it didn't perform, never invents facts, quotes or
sources, and says plainly when it can't do something (for example, no
backlight to dim in a VM).

**Under the hood: you set the conduct.** That paragraph above is not fixed. The
"conduct" section of the assistant's own instructions — how it treats your
requests, and the one boundary — is yours to edit. *Settings → Conduct* has
**Edit** (a text box with the current wording) and **Reset to default**, or say
"edit the conduct" / "pop the hood"; it is the plain‑text file
`/etc/llmos/conduct.txt`, so you can edit it from a terminal too. Change it
however you like — it is your machine. The OS ships a sensible default (the
default keeps the no‑harm‑to‑others line) and never rewrites this itself; the
assistant can show it to you but only you can change it, so it can't loosen its
own rules behind your back. The *Guidance* setting picks between two built‑in
defaults ("follows my instructions" or "standard caution") if you'd rather not
write your own.

## Models

Ships with **Ministral 3 3B** (Mistral AI, Apache‑2.0, ~2.1 GB, Q4_K_M). The
catalog (`models`) also offers Gemma 4 E2B/E4B/12B, Granite 4.1 3B/8B,
Ministral 3 8B/14B and LFM2.5 8B‑A1B — all fetched from the original labs'
official Hugging Face repos and checked against the published SHA‑256 before
they are ever loaded. Pick by what your machine can hold (`models` shows RAM).

The **Models** screen is a manager for both on‑device and online models. Each
one lists its maker, size, memory, licence, speed, what it is good at and its
drawbacks, with one‑tap **Use**, **Download** or **Remove**; the online section
lists your provider's models with **Use**, plus **Set up**, **Change** and
**Forget**. Every button is just a spoken command, so you can also say "use
Ministral 8B", "download Gemma 12B", or "use the online model Claude Opus".
Because new models come out constantly, **Check for new models** (or "check for
new models") searches Hugging Face for newer releases from the makers the OS
trusts; "add the model owner/repo" adds one, pinned to its exact SHA‑256 so it
stays verified like the built‑ins.

**Connectors** (the `connectors` screen) are the apps of this OS. A connector
is an external tool provider following the Model Context Protocol (MCP) — a
local command that stays on this machine, or a URL. Its tools become abilities
the assistant can use, under the same permission rules and audit log as
everything else. Add one from the screen's form or in words: "add a connector
named files that runs `npx -y @modelcontextprotocol/server-filesystem ~`". Turn
them on or off, or remove them, the same way. A local connector keeps data
here; an online one follows your internet setting.

Speech‑to‑text is whisper.cpp (`base` model) on device; speech out is
espeak‑ng (`"read your replies aloud"`).

## Requirements

Measured in `BUILD.md`. In short, with the default 3 B model on the machine
itself: **minimum** 2 cores, 4 GB RAM, 16 GB disk (answers at ~25 words/s,
reads requests at ~40 tokens/s; 3 GB is not enough — the model and the desk
do not fit together); **comfortable** 4+ cores, 8 GB RAM, 64 GB SSD (twice
the reading speed, room for a browser, bigger models and downloads). A GPU
is not used on real machines; on a Mac use host‑GPU mode (then the VM needs
only 3 GB).

## Privacy and security, concretely

- All inference is local (llama.cpp bound to 127.0.0.1). No cloud, no keys.
- Inbound firewall drops everything; there are no services to log in to
  (root's password is locked; the screen and the serial console are the only
  doors).
- Internet is a setting: yes / ask each time / no — "no" is an outbound
  firewall rule, not a promise. Optional Tor routing for all web traffic
  (DNS included, and the desk's own web content).
- Optional full encryption of everything personal (LUKS2, argon2id), no
  recovery key, no backdoor.
- Logs live in RAM; `/tmp` is RAM. Web fetches carry no cookies, run no
  JavaScript. Passwords you type for email are never echoed or logged.
- Built only from signed official Alpine packages and the labs' own model
  releases; hashes in `BUILD.md`.

## Limits (honest list)

- Under QEMU there is no backlight; brightness reports that. Sound works
  through the virtual sound card; the microphone needs the bridge.
- A 3 B model is capable but not brilliant. In testing it once answered "free
  memory" with the disk figure, once re‑saved a fact it already knew, and it
  needed a hint about Alpine's service commands (now built in). The most
  common requests (colours and text size, memory, scheduling, timers and
  reminders, lists and notes, files and the trash, screenshots, brightness
  and volume, animations, "reply to X that…", playing media, opening a
  terminal, the settings panels, installing to disk) are handled by the OS
  itself and never depend on the model getting them right. If a request is misread,
  say it differently — or switch to a bigger model if your machine allows.
- A pasted text longer than about 6 000 characters is shortened (beginning
  and end kept) before the model sees it; the reply says so. If the model
  ever crashes, its service restarts itself within a few seconds.
- Inside the VM (without host‑GPU mode) the first request after boot takes
  up to a minute while the model reads its instructions; later requests take
  a few seconds to a few tens of seconds. Host‑GPU mode removes most of that.
- Web search uses DuckDuckGo's HTML endpoint (Brave as fallback); it's plain
  results, not an API.
- Apple Silicon Macs run it as a VM, not natively (see above).
- One user. It's a personal computer.
