# LLM OS changelog

Versions are in `VERSION`; every image and ISO carries its version in
`/etc/llmos-release` (`llmos version` prints it, Settings shows it) and
`dist/RELEASE.json` lists what a release contains with checksums.

## 1.8.2
- The firewall can be turned off and on by asking, for example "turn off the firewall". On the balanced setting it asks first. "Undo" puts it back, and the status answer tells the truth.
- "Turn off the guard", "stop asking me before acting on emails" and "trust everything" are understood.
- The question before acting on web, email or file instructions now says why it asked and how to stop it.
- Reminders: "remind me at 3 to ...", "remind me to ... at 3 / tonight / this evening / next monday" all work. A trailing "please" is ignored. "Remind me what's on tonight" is a question, not a reminder.
- Trailing "please" or "thanks" no longer breaks quick commands.
- "Open the file manager / word / excel", "open /path with spaces", "apt install a b" (several packages) and "uninstall X" work.
- "Share over the network", "map of Paris" (OpenStreetMap), "do I have new email", "youtube music" and "use my claude account" work.
- More ways to turn the internet off: "turn off the internet", "work offline".
- "Sign out" and "log out" lock the screen and say so.
- "Connected but no internet" gets plain help. "Browser left, notes right" tiles two windows.
- "This app is frozen", "voice memo" and "add french keyboard" work.
- "What is my IP" asks before going online when the internet setting is "ask".
- The website check honours internet off.
- "Undo delete" restores only deletions. "Get my file back" and "open the bin" show the trash.
- Declined dialogs close when you stop a request.
- Internet questions use plain wording.
- "What can you do" mentions the new things.
- Faster first replies. Rarely used tools are only offered when you ask about them.

## 1.8.1
- The desk runs under your own account when you have one. If that can't start, it falls back safely.
- Replies come back in your language at once.
- "Private window", "reopen what I closed", bare "force quit" (asks first), "font bigger", "scale 150%", "show all apps", "less blue light at night" and "too dark, go back" all work.
- "Alarm for 7am", "24 hour clock", "restore from trash", "keep awake", "world clock tokyo", city names with accents, "discord" and a scientific calculator.
- Apps open as soon as their window appears. Clicks, typing and compound steps are faster.
- The system starts a little faster: its code is prepared once at install.
- When I'm unsure you asked for something, I ask you first instead of refusing.
- Do-not-disturb silences the away card's alert and holds it until it is off.
- "What did I miss" opens the away card.
- The folder-lock password tip is shown once.
- "Forget my routines" and "clear the activity log" work. The activity log is trimmed past 2 MB.
- The online-assistant privacy disclosure now says exactly what goes with a request.
- Updates and the search-model download follow the setting that asks before going online.
- The clock-sync disclosure is its own sentence.
- Accent colour contrast is 4.69:1, and the keyboard focus is visible.
- Wording fixes in plain language.
- The Gemma AI models give an answer instead of only thinking.
- Settings are checked. A typo in mail security can no longer send mail unencrypted.

## 1.8.0
- Clean jokes come back at once, without waiting for the model. Jokes about today's news still go to the model.
- Text boxes and the switch knob are easy to read in both the dark and light themes.
- Settings has a switch for "ask before acting on things I read online or in emails", in all 6 languages.
- Turning off that check, based on text the OS has just read, now asks first. The owner on hands-off mode is not asked.
- "Stop the music" is answered at once.

## 1.7.9
- The first reply after start-up is faster: the model is warmed up with exactly what the first request sends.
- Test resets close other programs and bring the desk back to the front.

## 1.7.8
- Faster web search: both engines run at once, gives up after 10 seconds, and shows plain error text.
- Instant answers for greetings with a friendly word, and for "15 percent of 240".
- Typos like "opn firefox" are understood.
- "Always open PDFs in Firefox" sets the default app.
- The files window shows icons or a list, and remembers which you chose.
- "Turn word doc into PDF" and "show my to do list" go straight to the right place.
- Plain error messages instead of raw codes.
- "Click File" answers faster when nothing matches.
- Test-shell measurement works on the first-run wizard.

## 1.7.7
- Real-input test hooks: desk `rect`, `testreset-min`, and testshell fixed sampling.
- Photo search by "my pics from X".
- "Where did it save" is answered.
- Spreadsheets.
- Saves never overwrite an existing file.
- An honest "skipped" message.
- All 6 languages complete.

## 1.7.6
- Replies say "you", never "the owner".
- "Why is my disk full" opens the storage view at once.
- "Open my bookmarks" opens them.
- "Find the file I was working on" and "show my recent files" list the newest files first.
- "How do I keep this without the USB stick" is answered at once.
- A program that isn't installed is named plainly, with how to get it.
- "Make the browser dark" and "change my homepage" are answered at once.

## 1.7.5
- "Turn wifi on/off" works at once.
- Reading the screen is faster (its text recognition runs in parallel).
- A click when nothing is open says so at once.
- "Biggest files" skips hidden files and works for a named folder ("the biggest file in Downloads").

## 1.7.4
- "What's on my screen" lists the open windows at once.
- "What's plugged into my computer" lists USB devices, cameras, drives and sound.
- "Show my biggest files" and "what's taking up space" are answered without the model.
- "Change the volume up" works.
- Deleting something that isn't there says so instead of asking first.
- A click on something not on the screen says so.
- The speed sweep now records the follow-up answer.

## 1.7.3
- The first-run wizard starts on "On its own" (hands-off).
- Tool errors and desk messages are in plain words.
- Wi-Fi connects without a fixed 4-second wait.
- "Delete the folder X" works without the model.
- Facts like a capital are looked up, not guessed.
- "Skip" with nothing playing, "unlock" when not locked, and "hello" are answered at once.
- Common typos in commands are fixed before matching.
- "What did I say" is answered from the conversation.
- Desk diagnostics are saved to /run/llmos/desk.log.

## 1.7.1 — in progress
The owner decides how much it asks, and is never second-guessed.

- **Full trust is truly full.** Choosing it (at set-up, or saying "full
  trust") shows once, in plain words, everything it will then do without
  asking — email, deleting, emptying the trash, installing and removing
  programs, settings, commands — and from then on nothing is asked: no
  confirmations, no "Sure?" on delete buttons, no questions before ending a
  program or installing updates. "Ask me before risky things" goes back.
- **Instructions inside web pages, emails and files** are still shown first
  in every mode (they don't come from you); "follow instructions in web pages
  too" turns that off as well.
- **No refusals.** Files outside the home folder can be deleted and folders
  made anywhere; system packages can be removed — you're told what that
  affects instead of being stopped.
- **Stop means stop.** Stop (or saying "stop") ends the request at once, even
  while the model is still reading it, and drops anything waiting behind it.
- **Everyday requests answered directly** (no model, about 1 second):
  directions, jobs, shopping, paying bills, dictionary, calendars ("add dinner
  friday 7pm to my calendar"), repeating reminders ("every monday remind me…"),
  combined requests ("open my email and play music"), backing up to and
  restoring from a USB drive, formatting a drive, screen and voice recording,
  games, the open-windows list, side by side, battery saver, "what did you
  do", magnifier, on-screen keyboard, ssh, git clone, dark mode in other
  languages, and plain answers about root, the firewall, viruses, crashes and
  booting.
- **Files:** show hidden files; rename a set of photos ("Holiday 1, 2, 3");
  find duplicates (and delete the extra copies to the trash); join PDFs; read
  the text in a screenshot and copy it; **share a folder** with your other
  computers and phones on the same network (read-only, until you stop);
  **lock a folder with its own password** (an AES-256 7z file that also opens
  on other computers).
- **Video:** cut the first or last seconds, or keep a part (a new file; the
  original stays); photo slideshow.
- **Quick answers and actions:** days until a date or holiday; a work-hours
  timer; what's using a port and stopping it; a local web server and HTML
  preview; temperature, battery and drive health; parcel tracking; typing and
  language practice; the computer's name; **focus mode** ("focus mode for an
  hour" blocks YouTube and social sites and quiets notifications, then undoes
  itself); programs that open at login; a VPN from its WireGuard or OpenVPN
  file; slower double-click and key repeat for shaky hands; keep running with
  the lid closed; the chime on or off; Super+T keeps a window on top.
- **Start fresh:** "reset this computer" says what it erases and keeps, offers
  a backup, asks once more, then erases everything personal and restarts at
  setup (the AI model stays). Also: the system log at a glance, the default
  shell in words, sharing an app you made as one file, Super+Shift+Left/Right
  moves a window to the other screen, and truthful answers about disk
  encryption, guest use, passwords, cloud backup, snapshots and kids mode.
- **Find things by what they're about** ("find the photo of the dog", "my
  letter about the car insurance", "search my files for a dessert recipe"):
  EmbeddingGemma 2 (Google, Apache-2.0) runs on this computer, indexes your
  documents, notes and photos (photos in the background), and says plainly
  when nothing matches. The model (310 MB + 555 MB for pictures) is fetched on
  first use and pinned by SHA-256; the image carries a llama.cpp built from a
  pinned commit for it.
- **New model:** Underdog 27B (Conway Research, Apache-2.0) for 32 GB machines.
- **Everyday basics, exact and at once:** sums and percentages, unit and
  temperature conversions, splitting a bill, the time elsewhere, time until an
  hour, what day a date falls on, spelling, definitions (Wiktionary),
  synonyms, weather for here or anywhere (Open-Meteo, no key), whether the
  internet works, which Wi-Fi, what's playing, folder sizes, notes ("write
  down: …"), alarms, timers, reminders by their words, text files by name,
  "email <address> saying …", "read my latest email", "did Craig reply".
- **Extreme requests:** any look you describe ("make the windows triangles",
  "a 1950s newspaper") is written as a style for the desk (the request box
  always stays usable; Super+Shift+Escape resets); chains of steps go to the
  model whole and keep going; pictures edited in any order of steps and saved
  as PDF; email attachments; batch rename/convert/edit; tasks on every unlock;
  block sites or allow only some; a task you schedule yourself carries your
  permission.
- **Fixed:** the model no longer opens the passphrase window or changes the
  trust setting for unrelated security questions; a passing request is no
  longer saved as a lasting "fact" about you;
  "every monday" was set up as every day; reminders now say which
  day; "update my apps" installs the updates instead of only listing them.

- **Everyday pass (112 requests, graded and read by hand).** The OS answers
  more plain requests itself, in about a second: weekdays in day counts ("next
  friday"); tips, taxes and discounts; "thanks"; sending an email to an
  address, replying to the last email, emailing a resume; how loud it is; the
  newest video or song; what was written in notes; 24-hour clock; unknown
  service status and opening hours from one search; a daily reminder
  ("remind me to … every day at 8am"); printing a file by name; the newest
  PDF; the taskbar layout ("look like windows 7"); Bluetooth on and off with
  the real result.
- **No refusals, no questions back, no lectures.** A single plain tool's own
  result is the reply (no second model turn). Writing requests are answered in
  words; a file or app is made only when asked for. Several things in one
  request are all done. Biggest files are listed as sizes and names.
- **Mail:** attachments choose the likely document (never test or cache
  files); a refused address is said plainly; mail errors name the server.
- **Cancelling tasks** matches the words given ("shutdown task" finds "shut the
  computer down").

- **Everyday passes 4–7.** Timers: "set a timer for 15 minutes for the pasta"
  makes a timer. Do not disturb "for an hour" turns itself off again. Bluetooth
  on and off answer at once with the real result (a failed switch says why, in
  plain words). "Is the wifi down" is a connectivity check. Who-won answers
  come from one search with its source; "last night" is added only for games and
  matches. A frozen screen gets straight advice; "my computer is slow" names the
  busy programs and says when memory is nearly full. "Yes" with nothing waiting
  says so. Biggest files, rename (the likely file), USB copy (what to do next),
  install ("installed: X -- open it by name"), and Wi-Fi and help replies say what
  they show. A note or list reply names the list it went to.
- **Build fixes.** The search-by-meaning runtime is built inside the target
  with /dev, /proc and /sys bound and a resolver set, so the image build no
  longer fails with "could not open /dev/null". The image build waits stop on
  git errors instead of waiting out their full timeout.

## 1.7.0 — 2026-10-05
Useful, not just pretty: real apps, programs that behave, a conversation that
never needs clearing, a living background, and what a stock Linux desktop
does, asked for in plain words. Checked against a list of 283 everyday tasks
(the 93 must-work ones run on the real OS, failures fixed and run again), an
item-by-item map of what stock Alpine + XFCE offers (809 items; a 60-task
side-by-side run of the everyday ones), and reviews from four kinds of user.

- **One conversation that never needs clearing.** A follow-up continues the
  topic in progress; something unrelated starts clean; earlier topics come back
  as short notes when asked about, so the model never drowns in old messages
  (the same for the online models). "New topic", side chats in their own
  windows, Conversations to resume or forget a topic.
- **Apps that work.** "Make me a calculator" (or a timer, notes, to-do,
  converter, calendar, sketch pad, password generator, dice, a tracker that
  sets itself up from what you ask for (water, steps, budget, sleep…), tip
  splitter, countdown, flashcards, tic-tac-toe, snake) opens a working app at
  once; "…with a forest theme" keeps that look; anything else is written by
  the model. Apps can't reach the network and keep their data.
- **Programs.** Firefox, Files (Thunar), a text editor, image viewer, word
  processor, spreadsheet, archive manager, sound mixer and a terminal are
  installed and open by what people call them. "Install Spotify / VS Code /
  GIMP" installs from Alpine or Flathub; "uninstall …" removes it. Window
  control in words: switch to, maximize, minimize, close, force quit a frozen
  one, put the browser on the left, show the desktop, browser back / reload /
  new tab. A program started for you never freezes the desk any more.
- **Looks as whole themes.** Dark mode is a neutral dark look (no bright
  wallpaper left behind); "ocean", "retro terminal", "make everything purple"
  are coherent palettes with readable text; fonts (sans, serif, mono, pixel)
  apply everywhere; programs follow dark mode, the font and the terminal
  colours. "Go back to the default theme" resets it.
- **A living background**, dark by default: slow, surreal colour fields that
  breathe while idle, swirl while the model thinks, ripple where you click;
  light on the processor (it slows itself on weak graphics).
- **System panels**, instant even while the model is busy: task manager, USB
  drives (open, eject), displays (resolution, extend/mirror, rotate), sound,
  Wi-Fi, Bluetooth, printers (add, test page, default), keyboard and mouse,
  storage clean-up, updates, about this computer. Plain words work too: "make
  the mouse faster", "reverse scrolling", "eject the USB stick", "set the
  resolution to 1920x1080", "the screen is upside down".
- **Everyday system things:** screenshots (Print Screen, saved and copied),
  clipboard history (Super+V), camera and microphone check, time zone and
  network time, screen off when idle / keep the screen on, sleep after a while,
  lid closes to sleep, low-battery warning, night light, do not disturb,
  programs' notifications, lock with Super+L, change the passphrase, the
  screen scaled for high-resolution laptops (programs too), edit / print /
  unzip files, your own photo as wallpaper, a trash you can restore from.
- **Is it installed?** The status bar says when LLM OS is running from the USB
  stick, with Install in the power menu; "is this running off the USB?"
  answers plainly.
- **Safer by default.** The assistant now asks before anything irreversible
  (it used to act on its own unless set otherwise); email that leaves,
  emptying the trash and removing programs always ask; and once it has read a
  web page, a file or an email in a request, any change it makes is shown
  first (such text can carry instructions meant to trick it). Delete buttons
  ask "Sure?" first. Notes meant for the model never reach the screen.
- **For everyday people:** "check my email" opens your webmail (asked once);
  "write an email to…" writes it for you to paste; "print this" opens the
  print window of the program in front; photos show as pictures; answers that
  need reading stay up; the Windows key brings LLM OS back over any program.
- **Known limits:** programs run as the computer's single owner account
  (root), so a few apps warn about it; films and music with copy protection
  (Netflix, Disney+, Spotify) can sign in but not play; Spotify, Zoom and
  Steam from Flathub are made for Intel/AMD PCs only.
- Fixes: Settings, Lists and the top/bottom bar buttons respond at once; "dark
  mode" no longer leaves an orange wallpaper; "music" plays music; "start a
  video call" opens a call (it used to play a song called "Video Call").

## 1.6.1 — 2026-10-05
The first run, after booting a real PC: clearer, bigger, fitted to the
computer, and connecting Claude or ChatGPT without typing a key.

- **Language:** English is already picked; Next (or Enter) goes on.
- **One page of six settings, as plain choices.** The sliders looked
  continuous but meant two or three things; each setting is now a card with
  its two or three choices as buttons (On its own / If it's risky / Every
  time, On / Ask first / Off, …) and what the chosen one means under it.
  Three cards across on a laptop screen, all six visible at once; text
  15–17 px; on small screens the list scrolls with a visible bar.
- **A system check.** The page says what it found ("This computer: 16 GB
  memory · 8 processor cores · Intel graphics") and uses it: the on-device
  model's choices are this computer's real models that fit its memory, each
  as "needs about 7 GB of this computer's 16 GB of memory" plus ready /
  downloads after set-up (5.2 GB); Balanced is recommended with 8+ cores and
  16 GB, gentle animation without graphics acceleration. A computer too small
  for any model is told the installed one will be slow, instead of nothing.
- **Sign in instead of a key.** "Sign in to Claude" / "Sign in to ChatGPT"
  opens the service's own key page in a private window (Google / Apple /
  Microsoft sign-in pop-ups work); press Copy next to the new key and the
  window closes by itself, the key is checked and kept. For ChatGPT the
  newest general GPT model the account offers is chosen. Pasting a key stays
  as a fallback; *Later* leaves it for the desk, which offers the same
  sign-in buttons. Saying "sign in to ChatGPT" works any time.
- **The screen is scaled to the display**, the way PCs pick their default
  (125 % on a 15-inch 1080p laptop, 150 % on a 14-inch one or a 27-inch 4K
  monitor, 200 % above): text was tiny on such screens. Text size now uses
  the page's own zoom, so layouts stay intact at any size.
- The last page recaps the choices in the same words as the settings page.
- Replies the OS gives itself no longer end with notes meant for the model
  ("…Say one sentence at most."), and the activity line names the online-model
  steps in words instead of raw arguments.
- **Locking no longer freezes the screen.** Locking ends the session's
  programs but spares the desk's own page process; Linux cuts process names
  at 15 characters ("WebKitWebProces"), so that exception never matched and
  the page was killed: the screen stayed on the desk (not the lock screen) and
  could not be unlocked without restarting. Names are now compared whole and
  cut, and if the page's process ever ends for another reason the desk loads
  it again with its windows. `desk-smoke.sh` checks the page survives a lock.
- Build: the OS files in the images were owned by the building Mac's user
  (uid 501); they are now root's (the payload is archived as root and
  unpacked without owners).

## 1.6.0 — 2026-10-05
Hand someone the LLM OS folder and it just works: they open Start Here on
their Mac, Windows PC or Linux computer, make a USB stick, and that stick
starts an ordinary PC with Secure Boot left on.

### Starts with Secure Boot on (x86-64)
Nearly every Windows PC ships with Secure Boot on, and it refused the old
stick ("Access Denied"); turning Secure Boot off meant firmware menus and, on
encrypted Windows laptops, a BitLocker recovery prompt. Now the x86-64 image
and ISO boot the chain such PCs already trust, from Debian 13:

- **shim 16.1, signed by Microsoft** with both the UEFI CA 2011 and the UEFI
  CA 2023 (old and new PCs accept it) → **GRUB 2.12 signed by Debian** (the
  removable-media build on the stick, the disk build when installed) →
  **Linux 6.12.111 signed by Debian**, with every module signed, so the
  kernel runs locked down as Secure Boot requires.
- No firmware settings, no key to enroll, no BitLocker prompt. BIOS-only PCs
  still start Alpine's GRUB as before. Each `.deb` is pinned by SHA-256 in
  `secureboot.env` and checked by the build (`tools/fetch-secureboot.sh`
  fetches them).
- Installing keeps it: on UEFI the installer puts the same signed chain in
  `EFI/llmos` (with a firmware boot entry) and, on a whole disk or a free
  removable path, `EFI/BOOT`; a Windows fallback is never overwritten.
- The ISO is assembled with the same xorriso layout `grub-mkrescue` used (CD
  and USB, BIOS and UEFI), with the signed EFI image and `/.disk/info`.
- Tests: `stick-boot-test.sh secureboot` (Setup writes the real image; a PC
  with Secure Boot enforced and Microsoft's keys starts it) and
  `secureboot-test.sh` (that PC installs LLM OS on a blank disk in words and
  restarts from it, Secure Boot still on).

### Setup rebuilt so anyone can make a working stick

- **The folder:** the top shows only *Start Here (Mac)*, *Start Here
  (Windows)*, *Start Here (Linux)* and one folder, *Support files*, holding
  everything else. `tools/package.sh` makes the zip to give someone (about
  6 GB: Start Here, Setup and the two ISOs).
- **Writing the stick works on macOS:** Setup now opens the stick through
  Apple's `authopen` (macOS's own password prompt) and streams the image
  itself. The old way (`osascript … with administrator privileges` + `dd`)
  ran outside Terminal's privacy permissions, so macOS refused it with
  "Operation not permitted" even with Full Disk Access. Windows and Linux
  write through an elevated copy of Setup (the "Yes" prompt / polkit). Every
  system writes the image's first 4 MiB last and reads the whole stick back
  to compare.
- **No choices to get wrong:** the stick always gets the x86-64 image, the one
  every computer that can start from USB (Windows PCs, Intel Macs) needs; the
  page no longer offers a list of files or assumes the stick is for the
  computer running Setup. The processor is read from the hardware, so a Mac
  with Apple silicon is recognised even when Python runs under Rosetta, and a
  Windows PC on ARM as such.
- **Safer drive list:** never the disk Setup runs from, a Time Machine
  backup, an internal/system/boot disk, or (Linux) one holding the running
  system. The old list offered an external drive holding both the LLM OS
  folder and a Time Machine backup.
- **The image is checked before anything is erased:** Setup verifies the ISO
  against `SHA256SUMS` in the background; a damaged copy is refused with the
  stick untouched.
- **A new page:** two choices (make a USB stick, try it in a window), one
  short step at a time, live stick detection, progress with time left,
  boot-menu keys for the common makers when it's done. Light and dark,
  phone-width safe.
- **No Python install needed:** the Start Here files use a Python 3.8+ the
  computer has, or fetch a private copy once (python.org's embeddable Python
  on Windows, the python-build-standalone build on Mac/Linux), pinned and
  checked against the publishers' SHA-256. On Windows, starting from inside a
  zip that wasn't extracted says to extract it.
- **Removed:** the save-the-ISO step, the per-machine instruction lists, the
  Full Disk Access pre-check, and "2 - Set up with AI.md" (Setup now guides by
  itself).
- **Tests:** `test-setup-writer` (the write core, the authopen hand-off, the
  drive filter on this Mac, whole jobs through Setup's API onto a raw block
  device), `stick-boot-test.sh` (Setup writes the real image, then a virtual
  PC starts from it as a USB stick under UEFI and BIOS), `test-start` (the
  launchers, the private-Python fetch and its checksum), `test-package.sh`
  (the zip as a recipient uses it), and a rewritten `test-setup-csrf`
  (security, plus recognising every kind of computer).

## 1.5.0 — 2026-10-04
A whole-OS review against the original brief (seven parallel reviewers, every
finding checked against the code) found and fixed these. New host tests cover
each: `test-risk`, `test-installer`, `test-store`, `test-downloads`,
`refusal-probe`, and additions to the voice, cloud, connector, uispec and
setup suites.

Safety and privacy (the core promises):
- **The desk was unreadable and the lock screen leaked.** A stylesheet comment
  left unclosed in 1.3.0 killed the colour, layout and `hidden` rules, so every
  screen drew on top of the others and the lock screen no longer covered the
  desk. Fixed, with a check that the base rules survive.
- **Nothing typed or spoken reaches the assistant while locked.** Off the desk
  (lock screen, first-run, boot) the page may only do what that screen is for;
  the microphone and Super+D work on the desk alone; the compositor keeps no
  shortcuts while locked (so no terminal over the lock screen), at boot too; a
  text console and the desk now lock together; and one wrong passphrase at a
  time no longer counts several failures toward the automatic power-off.
- **The assistant cannot loosen its own leash.** Writing any of the OS's own
  rules — its settings, the conduct text, the firewall, its code — is now a
  security action that always asks, even hands-off, however the command is
  written (`/bin/rm`, `sh -c …`, newlines, wrappers). Risk and
  internet-use detection were rewritten to see through those disguises.
- **The never-refuse promise is now measured.** `tools/refusal-probe.py` runs
  real owner requests through the shipped prompt and tools; the release gate is
  zero refusals on the default guidance.
- **Installing next to another OS can no longer format the wrong partition.**
  The new partition is identified by where it starts, never by a number that
  can have gaps; anything uncertain is refused and nothing is written.
- **Firewall and Tor fail closed.** With the internet off, connections open
  before the switch are cut too; with Tor on, only Tor may reach the network,
  so a program that does not use it fails instead of leaking (mail, http
  connectors and the browser are covered, and media look-ups resolve names
  through Tor). The launcher's host services are allowed only when this boot was
  actually given them.
- **The microphone bridge is trusted only from the launcher.** It takes a
  per-launch secret, so no other program on the host — or on the network — can
  open the Mac's microphone or feed the OS audio.
- **Secrets stay secret.** Online-model keys and tokens are redacted from the
  audit log and the screen (by name and by shape), credentials typed in a
  request are not kept in the conversation sent to an online model, and the
  online model's own blocks never carry the OS's private bookkeeping.
- **Programs you run keep their data inside the vault**, not in the OS's cache
  on the bare disk; while the vault is locked, nothing personal is written
  outside it; and concurrent changes from the desk, console and scheduler no
  longer overwrite each other.
- **Downloads are verified every time**, including a file already on disk; a
  changed file is fetched again.

Works as described:
- **Fits a 4 GB machine.** On a small model context the tool list is compact
  and trimmed to leave room, so an ordinary request no longer overflows the
  model's memory; the everyday tools always fit, the owner's connectors next.
- **The online model works with current Claude models** (Opus 5.5, Sonnet 5.5,
  Fable 5.1): no sampling settings are sent, thinking blocks are replayed
  unchanged, room is left for the model to think, and a service refusal is
  answered on the computer instead. The model list is current.
- **Dictation can use better models:** the voice catalogue pointed at a repo
  that no longer answers; it is corrected and every model's checksum pinned.
- **The live ISO boots from an IDE/SATA CD** (QEMU's default machine,
  VirtualBox), not only virtio.
- **Inbox triage is honest:** it sorts the newest unread in batches and reports
  how many remain, instead of claiming "inbox zero" after looking at 40.
- **Email works with Gmail:** mailbox names are quoted, so archiving no longer
  fails on folders like `[Gmail]/All Mail`.
- **Connectors don't hang the OS:** a stalled one is given up on at its
  deadline; http connectors keep their session and protocol headers.
- **"No corners" rounds the corners** (the brief's example), themes keep text
  readable, and a few command phrases ("use firefox", "speak up") no longer
  switch the whole interface language.
- Setup recognises an Apple Silicon Mac even when its Python runs under Rosetta;
  it never lists a disk that holds the running system; its page carries no
  secret (the launch key travels in the address fragment) and only its own
  script may run; device names can't inject into it.
- Clearer guidance: Secure Boot must be off (the boot loader is unsigned),
  suspend BitLocker first, a T2 Mac needs "No Security"; the docs on
  unattended tasks, the host list, the package manifest
  (`/etc/llmos/packages.txt`), and local-by-default-with-optional-online now
  match the code.

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
