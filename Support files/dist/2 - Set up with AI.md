# Set up LLM OS with an AI assistant

> **If you are a person:** you don't need to read this file. Give it to your AI
> assistant — Claude, ChatGPT, or any assistant that can read files on your
> computer — and say:
>
> **"Read this file and help me set up LLM OS."**
>
> It will take it from there, one step at a time, in plain language, and it
> will always ask before doing anything that changes your computer.
>
> *No AI assistant? Double-click the **1 - START HERE** file for your computer
> instead (Mac, Windows or Linux), in this same folder.*

---

**Everything below is written for you, the AI assistant.**

## Your job

Help the person get LLM OS running, from wherever they are now to their first
conversation with it. Assume they may not be technical. LLM OS is an operating
system you talk to: its whole interface is a language model running on the
computer itself. It is free and open source (Apache-2.0).

Ways people use it, from easiest to most involved:

1. **Try it in a window** (a virtual machine) on the computer they have now.
   Nothing on their computer changes. The right first step for almost everyone.
2. **Make a bootable USB stick** and start a PC (or an Intel Mac) from it.
   Still nothing changes on that computer; LLM OS runs from the stick.
3. **Install it** onto a computer, on its own or next to Windows or macOS,
   from that USB stick.
4. **Just save the ISO file** to keep or share.

Your main instrument is **LLM OS Setup**, a small app in this folder that
opens as a page in the web browser. It recognises the computer, recommends a
path, saves and verifies the ISO, writes USB sticks safely, and shows
per-computer instructions. Prefer it over doing things by hand.

## Ground rules — follow these every time

1. **One step at a time, in plain words.** Short messages. Explain any term
   the first time (ISO, virtual machine, boot menu). After each step, check it
   worked before moving on.
2. **Ask before anything that changes the computer:** installing software,
   running commands with administrator rights, changing settings, writing a
   USB stick, resizing or erasing a disk. Say what will happen and wait for a
   clear yes.
3. **Never write to a disk yourself.** Do not run `dd`, `diskutil eraseDisk`,
   `diskpart`, `mkfs`, partitioning tools or similar. To make a USB stick, use
   the **Write** button in LLM OS Setup: it lists only removable drives, hides
   the computer's own disks, and asks for confirmation. Installing onto a
   computer happens *inside* LLM OS (from the stick), where its installer shows
   the exact plan and asks once.
4. **Protect their data.** Before anything that touches a computer's internal
   disk (installing, dual boot, shrinking a partition), make sure they have a
   backup, and on Windows, their BitLocker recovery key. If in doubt, stop and
   ask.
5. **Be honest.** If a step fails, say so and what the message said. Don't
   guess at results you can't see; ask them to tell you or show a screenshot.
6. **Adapt to what you can do.** If you can run commands, open apps or see the
   screen, do the safe parts yourself (after asking) and tell them what you
   did. If you can only chat, give one instruction at a time and ask them to
   reply with what they see.
7. **Respect their choices.** Recommend, explain trade-offs, and let them
   decide. Never pressure.

## What's in this folder

| File or folder | What it is |
|---|---|
| `1 - START HERE (Mac).command` | Opens LLM OS Setup on a Mac (double-click). |
| `1 - START HERE (Windows).bat` | Opens LLM OS Setup on Windows (double-click). |
| `1 - START HERE (Linux).sh` | Opens LLM OS Setup on Linux. |
| `2 - Set up with AI.md` | This file. |
| `README.md` | The user guide: what LLM OS does and how to use it. |
| `setup/` | LLM OS Setup itself (`llmos-setup.py`, a page, instructions). |
| `llmos-arm64.iso` | Bootable LLM OS for Apple Silicon Macs (in a window) and ARM PCs. About 2.9 GB. |
| `llmos-x86_64.iso` | Bootable LLM OS for ordinary PCs and Intel Macs. About 3.4 GB. |
| `llmos-arm64.qcow2`, `llmos-x86_64.qcow2` | Ready-made virtual-machine disks (advanced). |
| `run-llmos.sh` | Advanced launcher for Apple Silicon Macs with Homebrew QEMU. |
| `SHA256SUMS` | Fingerprints to check the files are intact. |
| `RELEASE.json`, `VERSION` | The version and contents of this release. |

If the folder is still a **.zip file**, it must be unzipped first (macOS:
double-click it; Windows: right-click → **Extract All**). On Windows, running
anything from inside the zip view fails because the other files aren't there.

If neither ISO is in the folder, this copy is incomplete: ask them to get the
full folder from wherever they got it.

## Step 1 — Find out about the computer

You need: the operating system, whether a Mac has **Apple Silicon** (M1–M4) or
an **Intel** chip, the memory (RAM), and free disk space.

If you can run commands:

- **macOS:** `sw_vers -productVersion`, `uname -m` (`arm64` = Apple Silicon,
  `x86_64` = Intel), `sysctl -n hw.memsize` (bytes), `df -h ~`.
- **Windows (PowerShell):**
  `(Get-CimInstance Win32_OperatingSystem).Caption`,
  `$env:PROCESSOR_ARCHITECTURE`,
  `[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)`,
  `Get-PSDrive C`.
- **Linux:** `uname -m`, `free -g`, `df -h ~`.

If you can only chat, ask: *"Is this a Mac or a Windows PC? If it's a Mac:
Apple menu → About This Mac — what does it say next to Chip or Processor, and
how much Memory?"* (On Windows: Settings → System → About.)

**What it means:**

| Computer | Can LLM OS run in a window? | Can it start LLM OS directly? | ISO to use |
|---|---|---|---|
| Mac, Apple Silicon (M1–M4) | Yes (best: the free app UTM) | **No**, not yet | `llmos-arm64.iso` |
| Mac, Intel | Yes (UTM) | Yes, from a USB stick | `llmos-x86_64.iso` |
| Windows PC | Yes (free VirtualBox) | Yes, from a USB stick | `llmos-x86_64.iso` |
| Linux PC | Yes (GNOME Boxes, virt-manager) | Yes, from a USB stick | `llmos-x86_64.iso` (ARM: `llmos-arm64.iso`) |

Requirements: **4 GB of memory** for LLM OS (8 GB is comfortable), so a
computer running it *in a window* is best with 8 GB or more. About 35 GB of
free disk for a virtual machine. A USB stick of **8 GB or more** (16 GB, USB
3.0, recommended).

## Step 2 — Ask what they want, and recommend

Ask in plain words, for example:

> "Do you want to (a) try LLM OS in a window on this computer — safest, nothing
> changes — (b) make a USB stick to start another computer with it, or
> (c) install it on a computer? If you're not sure, (a) is a great start."

Recommend **(a)** unless they clearly want something else, or the computer
has under 8 GB of memory (then a USB stick on a PC is smoother). On an Apple
Silicon Mac, only (a) works on that Mac itself.

## Step 3 — Open LLM OS Setup (the START HERE file)

Tell them where it is: **this folder**, the file **"1 - START HERE"** for
their computer. Names starting with "1" sort to the top.

If you can open apps or run commands, offer to start it for them (in the
folder): `python3 setup/llmos-setup.py` on Mac or Linux, `py -3
setup\llmos-setup.py` on Windows. It opens a page in their browser; a small
text window stays open while it runs.

Expect these, and explain them before they happen:

- **macOS: "cannot be opened" / "Apple could not verify…"** This is normal for
  files from the internet. Fix: right-click (Control-click) the file → **Open**
  → **Open**. Or System Settings → Privacy & Security → **Open Anyway**. If you
  have a terminal and they agree, you can clear the download flag for the whole
  folder: `xattr -dr com.apple.quarantine "<path to this folder>"`.
- **macOS: "install the command line developer tools?"** The setup needs
  Python, which Apple provides free this way. Click **Install**, wait, then
  open START HERE again.
- **macOS: the file opens in a text editor instead of running.** It lost its
  "executable" mark (common if the folder passed through Windows). With
  consent: `chmod +x "<folder>/1 - START HERE (Mac).command"`.
- **Windows: "Windows protected your PC."** Click **More info** → **Run
  anyway**. The file is plain text; you can show them its contents if they
  want to check it first.
- **Windows: no Python.** The START HERE file offers to install it with
  Windows' own package manager (winget), or opens python.org (tick "Add
  python.exe to PATH" in the installer). Then open START HERE again.
- **The browser didn't open.** The text window shows a `http://127.0.0.1:…`
  address; paste it into the browser.

The page opens with a **Welcome** card: it says what kind of computer this is
and highlights the recommended choice.

## Step 4 — Do what they chose

### (a) Try it in a window

In LLM OS Setup, click **Try it in a window**. On an Apple Silicon Mac that
already has QEMU from Homebrew, this starts LLM OS directly. Otherwise the page
explains the easy route and links to the free app. The full steps are also in
the page under *Try it in a window*:

**Mac → UTM** (free, from mac.getutm.app; open the download and drag UTM to
Applications):
1. UTM → **Create a New Virtual Machine** → **Virtualize** → **Linux**.
2. **Boot ISO Image** → **Browse** → the ISO from Step 1 (Apple Silicon:
   `llmos-arm64.iso`; Intel: `llmos-x86_64.iso`). "Show the ISO this computer
   needs" in Setup reveals the right file.
3. Memory **4096 MB** (6144 if the Mac has 16 GB or more), **4** CPU cores,
   storage **32 GB**. Skip the shared folder. **Save**, name it "LLM OS".
4. Press **▶ Play**.

**Windows → VirtualBox** (free, from virtualbox.org):
1. **New**: name "LLM OS", ISO image `llmos-x86_64.iso`, Type **Linux**,
   Version **Other Linux (64-bit)**, tick **Skip Unattended Installation**.
2. Memory **4096 MB**, **4** processors, a new **32 GB** disk.
3. **Finish**, then **Start**.

**Linux:** GNOME Boxes (**+** → choose the ISO → **Create**), virt-manager, or
`qemu-system-x86_64 -enable-kvm -m 4096 -smp 4 -cdrom llmos-x86_64.iso`.

**Faster on Apple Silicon (optional, for people comfortable with Homebrew):**
`brew install qemu llama.cpp`, then **Try it in a window** in Setup. The
language model then runs on the Mac's graphics chip (several times faster at
reading requests), still entirely on the Mac.

To keep LLM OS in the window between restarts: inside LLM OS say
**"install LLM OS"** — it installs onto the virtual machine's own virtual
disk, never onto the real computer — then remove the ISO from the virtual
machine's CD drive in its settings.

### (b) Make a USB stick

1. Plug in a stick of 8 GB or more. **Everything on it will be erased** —
   confirm they have nothing on it they need.
2. In LLM OS Setup, *Write to a USB stick*: pick the stick (only removable
   drives are listed; use **Refresh** after plugging in), pick the ISO
   (`llmos-x86_64.iso` for ordinary PCs and Intel Macs), tick "I understand
   the stick will be erased", **Write**. macOS and Windows ask for the
   computer's password or an administrator OK; that's expected.
3. If the write is refused on Windows, use Rufus (DD image mode) or
   balenaEtcher with the same ISO. Don't use other methods.
4. To start a PC from the stick: plug it in, restart, and press the boot-menu
   key while the maker's logo shows — usually **F12**, sometimes **F11**,
   **Esc**, **F8**, **F9** (HP) or **F10**; on some machines **Del/F2** opens
   the firmware where the stick is chosen under *Boot*. If the stick isn't
   offered, turn **Secure Boot off** in the firmware (LLM OS's boot loader is
   unsigned, so it will not start with Secure Boot on). On Windows, suspend
   BitLocker *before* changing Secure Boot, or Windows may demand its recovery
   key next start. On an Intel Mac: hold **Option (⌥)** while it starts and
   choose the orange **EFI Boot** (a T2 Mac needs **No Security** +
   external-media boot in Startup Security Utility first).

Starting from the stick changes nothing on that computer.

### (c) Install it on a computer

Only after they've tried it from a USB stick (b) and want to keep it.

1. **Backup first.** Check they have one. On Windows, have the BitLocker
   recovery key (account.microsoft.com/devices/recoverykey) or turn
   BitLocker off.
2. **Next to Windows:** in Windows open **Disk Management**, right-click the
   Windows partition → **Shrink Volume**, free at least **32 GB**, leave it
   unallocated. **Next to macOS (Intel Mac):** Disk Utility → Partition → add
   a partition of 32 GB+, apply, then remove that new partition so the space
   is free. Macs with a T2 chip: in **Startup Security Utility** (hold Cmd+R
   at start → Utilities) set **No Security** and allow booting from external
   media. On Windows, suspend BitLocker before any firmware change.
3. Start from the USB stick, then inside LLM OS say **"install LLM OS
   alongside Windows"** (or "alongside macOS"), or **"erase the whole disk and
   install LLM OS"** if they want only LLM OS. It shows the exact plan and asks
   once. It takes a few minutes, then offers a restart.
4. Afterwards a menu at start lets them choose LLM OS or Windows/macOS. Unplug
   the stick.

### (d) Just save the ISO

In LLM OS Setup, *Save the ISO* → **Save to Downloads**. It copies the ISO
and checks the copy against its fingerprint.

## Step 5 — Check the files are intact (recommended)

Setup checks the ISO when it saves it. To check by hand, in this folder:

- **macOS:** `shasum -a 256 llmos-x86_64.iso` (or `llmos-arm64.iso`)
- **Windows:** `Get-FileHash .\llmos-x86_64.iso -Algorithm SHA256`
- **Linux:** `sha256sum -c SHA256SUMS --ignore-missing`

The long code must match that file's line in `SHA256SUMS`. If it doesn't,
the file is damaged or altered: don't use it, get the folder again.

## Step 6 — Plan the first start together

The first time LLM OS starts, it asks a few questions. Going through them
beforehand makes it quick. Help them choose, then write their answers in a
short list they can follow.

First it asks their **language**, **name** and **time zone**. Then six
sliders (everything can be changed later just by asking):

1. **How much should it ask before acting?** Does things on its own /
   asks before risky changes / asks before any change. Most people: on its
   own or risky-only.
2. **Internet:** connected / asks each time / offline (blocks everything).
   Offline means maximum privacy but no web answers, no downloads.
3. **Where it thinks:** only on this computer (fully private, the default) /
   here, but asks before sending a big request to an online model / an online
   model answers everything. The online options need an account with a
   provider such as Anthropic (Claude, console.anthropic.com) or an
   OpenAI-compatible service, and its API key; requests then leave the
   computer and are billed to that account. Help them decide; don't push.
4. **On-device model:** fast and light / in between / the most capable this
   computer can run (bigger downloads, needs more memory). On 8 GB or less,
   fast and light.
5. **Guidance:** follows their instructions on their own machine without
   lectures (the default) / keeps a standard assistant's caution. Its exact
   wording can later be read and changed in Settings → Conduct.
6. **Screen:** calm (no animation) / reduced / lively.

Then, if needed, **Wi-Fi** (on a real computer; have the network name and
password ready), and an optional **passphrase** that encrypts their personal
data. **There is no recovery: if they forget the passphrase, that data is
gone.** Suggest they write it down somewhere safe, or skip it for a trial.

## Step 7 — First start and hand-off

When LLM OS is running, they type (or speak) what they want into the bar at
the bottom. Good first things to try:

- "what's using my disk?"
- "make everything purple"
- "every morning at 8, give me the weather"
- "show me a photo of the Alps"
- **Dictation:** press **Super+D** (the Windows key and D) anywhere, speak,
  pause — the words are typed where the cursor is. In a window on a Mac, if
  the key doesn't reach LLM OS, use the microphone button in the bar, or
  turn on keyboard capture in UTM.

Everything else — settings, models, voice, connectors, the conduct section —
is found by asking LLM OS itself ("open the settings", "show the models"),
and the full guide is `README.md` in this folder.

Before you finish, tell them in two or three sentences what they now have and
how to start LLM OS again (the UTM or VirtualBox window, the USB stick, or the
start menu on an installed computer).

## Troubleshooting

| Symptom | What to do |
|---|---|
| The window shows LLM OS starting, then stays black (UTM) | Stop the VM → Edit → Display → choose **virtio-ramfb** (or "virtio-gpu-pci") → start again. |
| Black or tiny screen (VirtualBox) | Settings → Display → Graphics Controller **VMSVGA**, Video Memory **128 MB**. |
| Very slow in a window | Give the VM more memory and cores; close other apps. On Apple Silicon, the Homebrew route uses the Mac's graphics chip. |
| "Not enough memory" or freezes | The host needs room for its own apps plus 4 GB for LLM OS; close programs or use a USB stick on a PC. |
| The PC doesn't start from the stick | Use the boot-menu key (above); turn off Secure Boot; try another USB port (a USB 2.0 port sometimes works better); write the stick again. |
| The stick doesn't appear in Setup | Plug it in, wait a few seconds, click **Refresh**. Built-in disks are deliberately never listed. |
| Write failed on Windows | Approve the administrator prompt; otherwise Rufus (DD image mode) or balenaEtcher. |
| Apple Silicon Mac won't start from the stick | Expected: these Macs can only run LLM OS in a window for now. |
| Microphone or dictation doesn't hear anything in a window | The virtual machine needs microphone access; on a real computer it works directly. The bar's text box always works. |
| Forgot the passphrase | The encrypted personal data can't be recovered; that's the design. LLM OS can be set up again. |
| Anything else | Ask LLM OS itself, or read `README.md`. Report problems to whoever gave them this folder. |

## Quick reference

- Setup tool: **"1 - START HERE"** in this folder → opens LLM OS Setup in the browser.
- Apple Silicon Mac: window only, `llmos-arm64.iso`, UTM.
- Intel Mac / PC: `llmos-x86_64.iso`; window (UTM / VirtualBox) or USB stick.
- Memory: 4 GB for LLM OS, 8 GB+ comfortable. VM disk 32 GB. USB stick 8 GB+.
- Never write disks by hand; use Setup's **Write** button.
- Install = inside LLM OS: "install LLM OS alongside Windows / macOS".
- Passphrase: optional, **no recovery**.
- Dictation: **Super+D**.
