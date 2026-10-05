# LLM OS vs stock Alpine XFCE: parity results

Maps every item of [parity-xfce.md](parity-xfce.md) to how LLM OS covers it. Checked against the source in `src/` (working tree on branch llmos-1.5.0 after the 1.6.1 release, 2026-10-05). No VM was run: items marked *verify* depend on labwc/acpid defaults that the source does not set explicitly.

Statuses: **YES** = LLM OS does it (words or button, and the code). **PROGRAM** = an installed program does it (`PKGS` in src/install.sh, opened with "open <kind>" via programs.py). **PARTIAL** = some of it (what is missing is said). **NO** = missing. File references are under `src/rootfs/usr/lib/llmos/llmos/` unless a path is given.

## Closed since this mapping (1.7.0, same day)

The ranked gaps below were mapped from the source before the fixes. These were then closed in 1.7.0 (gap numbers from the
ranked table; each is in the code and, where marked, was run in the test VM by `tools/usecase-run.py --file
docs/research/parity-tasks.md`, results in `run/parity*/`):

| Gap | What now works | Run in VM |
|---:|---|---|
| 1 | Own photo as wallpaper: "set ~/Pictures/x.jpg as my wallpaper", *Set as wallpaper* on any picture; "change my wallpaper" offers choices | |
| 2 | Mouse/keyboard in plain words ("make the mouse faster", "reverse scrolling", "I'm left-handed", key repeat) | Q20–Q23 |
| 3 | "edit the file …" and an *Edit* button open text in the text editor | |
| 4 | Programs follow dark/light mode, the font, the text size; terminal colours follow the theme | Q33–Q37 |
| 5 | High-resolution screens are scaled in the compositor, so programs scale too | |
| 6 | "eject the USB stick", "what's on my USB stick" | Q51, Q52 |
| 7, 13, 57 | Screen off after N minutes, "keep the screen on", sleep after N minutes; maximized programs leave the bar visible | Q27, Q28, Q57, Q58 |
| 8 | Time zone by words, time set from the network, "the time is wrong" | Q25, Q26 |
| 9 | Programs' notifications (mako, in the desk's colours); do not disturb | Q31, Q32 |
| 10, 15, 21 | Lid closes → lock (with a passphrase) and sleep; low-battery warning and sleep at 3 % | |
| 11 | "print the file …", *Print* buttons, "print this" opens the print window of the program in front | |
| 12, 23, 25 | Resolution and rotation by words, true mirroring, projector-only | Q16–Q19 |
| 14 | Area screenshots ("snip", Shift+Print, Super+Shift+S), copied to the clipboard | Q45 |
| 16, 18, 19, 29 | Window control by words ("close the browser window", "put the browser on the left", "show the desktop"); dock chips focus programs | Q05–Q10 |
| 17 | "unzip …" extracts into a folder next to it | |
| 20, 47, 61 | Keys: Super+L / Ctrl+Alt+L lock, Ctrl+Alt+T terminal, Super+E files, Ctrl+Shift+Esc task manager, media keys, Super brings LLM OS back | |
| 22 | Change the passphrase ("change my password") | |
| 26, 27 | Do not disturb, night light | Q29–Q32 |
| 28 | Printer panel *Test page* / *Make default* work | |
| 32, 53 | Forget / disconnect a Wi-Fi network, airplane mode | |
| 38 | Four workspaces (Ctrl+Alt+arrows, Super+1–4, "go to workspace 2") | |
| 44 | Pause/play any player including videos in the browser (MPRIS) | |
| 52 | "uninstall …" (Alpine or Flathub) | |
| 71 | Clipboard history (Super+V), "what did I copy" | Q46 |
| 77 | Natural scrolling applies to a mouse too when asked | |

Still open, by design or for later: separate user accounts (everything runs as the one owner, root), a screen
reader, VPN/static IP, desktop icons, per-app notification rules, display profiles, cloud-drive sync.

## Counts (as mapped before the fixes above)

| Status | Sections 0-4 (inventory items) | Section 5 (capability rows) | All |
|---|---:|---:|---:|
| YES | 95 | 30 | 125 |
| PROGRAM | 98 | 4 | 102 |
| PARTIAL | 174 | 35 | 209 |
| NO | 347 | 26 | 373 |
| **Total** | **714** | **95** | **809** |

Many NO items are xfwm4/xfdesktop/panel knobs that ordinary people rarely touch; the ranking below puts the everyday ones first. 161 distinct gaps cover all 582 PARTIAL and NO items.

## Gaps, ranked

Ranked by how likely an ordinary person is to ask for it (score 0-100, a judgement). Each gap lists the items it covers (section.item numbers refer to the full mapping below) and one concrete fix.

| # | Score | Gap | Items (PARTIAL / NO) | Fix |
|---:|---:|---|---|---|
| 1 | 90 | **Use my own photo as the wallpaper** | 1.5.3 Choose an image folder and pick an image (P); 2.2.18 Set as wallpaper (N); 3.2.8 Image onto the Desktop settings (N); 5.10 Use this photo as my wallpaper (P); 5.60 Make this picture the wallpaper (P) | tools.set_wallpaper: accept a local image path (copy it to config.data('wallpaper.img'), backdrop=photo); add a 'Set as wallpaper' button to the image window in tools.open_file; intent._WALLPAPER: match 'this picture / the file X as (my) wallpaper'. |
| 2 | 88 | **Mouse/keyboard settings in plain words** | 5.20 Keys repeat too fast (P); 5.22 Make the mouse faster (P); 5.23 Swap the mouse buttons (P); 5.24 Reverse scroll direction (P); 5.25 Turn on tap to click (P) | intent.py: new _INPUT regex for natural variants ('make the mouse faster', 'swap the mouse buttons', 'reverse the scrolling', 'turn on tap to click', 'keys repeat too fast') that returns the exact phrases desk._system_shortcut already handles; or add input keys to tools.change_setting so the model has a tool (today it has none). |
| 3 | 85 | **Open a text file to edit it** | 5.89 Open notes.txt so I can edit it (P) | tools.open_file: when _display_available(), launch programs.find('editor') (Mousepad) with the path for text files instead of the read-only window; keep the window for 'show me' and for the console. |
| 4 | 84 | **Dark mode for programs too** | 1.1.3 Dark preference for apps (P); 4.2.31 Mint-Y colour variants, themes (P) | tools.set_appearance: on theme/mode change write ~/.config/gtk-3.0/settings.ini and gtk-4.0/settings.ini (gtk-application-prefer-dark-theme, gtk-theme-name Adwaita-dark) - programs get XDG_CONFIG_HOME=~/.config from config.personal_env; Firefox follows the GTK preference. |
| 5 | 82 | **Scale programs, not only the desk** | 1.1.13 Custom DPI (P); 1.1.20 Window scaling factor (HiDPI) (P); 1.7.8 Scale (1x, 2x, fractional) (P); 3.11.7 HiDPI scaling (P); 5.15 Everything is tiny, scale it up (P) | syspanels: set_scale(output, f) via `wlr-randr --output X --scale 1.25`; call it from desk._apply_zoom with _display_scale and from set_appearance scale when the owner says 'everything'; today only the desk page zooms (Desk._apply_zoom). |
| 6 | 80 | **USB stick requests in words ('eject the USB stick', 'what's on my USB stick?')** | 5.56 What's on my USB stick? (P); 5.57 Eject the USB stick (P) | intent.py: regex 'eject/safely remove (the/my) (usb/stick/drive/flash drive)' -> desk 'eject drive <first syspanels.removable()>' (Desk._system_shortcut already ejects); widen the _SYS drives regex to 'what's on (the/my) usb (stick/drive)'; or drive tools for the model, which has none. |
| 7 | 78 | **Screen off / blank after idle; presentation mode** | 1.10.15 Display power management on/off (N); 1.10.16 Blank after N minutes (N); 1.10.17 Put display to sleep after N minutes (N); 1.10.18 Switch display off after N minutes (N); 1.10.19 Reduce brightness after N seconds (N); 1.10.20 Reduce brightness to N% (N); 1.10.29 Panel: presentation mode (P); 1.10.30 Panel: display power management toggle (N); 5.27 Don't turn the screen off for an hour (P); 5.32 Keep the screen on during my presentation (P) | Add swayidle to PKGS; Desk starts `swayidle timeout N 'wlr-randr --output X --off' resume '... --on'`; change_setting screen_off=<minutes/never>; 'keep the screen on' = stop swayidle. Today nothing ever blanks the screen. |
| 8 | 75 | **Set the time zone / time sync after setup** | 0.7 No GUI for users, date/time, time zone, updates, disks (P); 1.24.1 Date/time GUI, time zone, NTP (P); 1.24.2 Clock: time zone used for display (P); 4.1.1 Configuration Center (P); 4.2.15 Date and Time (time zone, NTP, 12/24h) (P); 5.65 Set my time zone to Europe/London (P) | tools.change_setting: add 'timezone' to the enum (the branch already calls system.set_timezone); intent regex 'set my time zone to X'; Settings: turn the time-zone row into a button with the wizard's tz search; enable chronyd or busybox ntpd when internet is allowed (install.sh deletes chronyd, so the clock never syncs). |
| 9 | 75 | **Show programs' notifications** | 0.1 No notification daemon (P); 1.11.2 Notification log (P); 1.11.13 Per-app mute (N); 1.11.14 Per-app urgency (N); 1.11.15 Bell plugin: recent log, DND toggle, clear (N); 3.10.1 Stock: no daemon, app notifications not shown (P); 3.10.2 Expected with notifyd: bubbles, actions, log, DND, per-app mute, OSD (P) | desk.py: own org.freedesktop.Notifications on the desk's session bus (Gio.bus_own_name + register_object), turning Notify calls into toasts (and the away card); no daemon exists, so Firefox/Thunar notifications are dropped. |
| 10 | 72 | **Closing the lid sleeps (and locks)** | 1.10.11 When the lid is closed (N); 3.8.4 Lock on lid close (N); 3.9.11 Lid close -> configured action (N); 5.29 Don't suspend when I close the lid (N) | Ship /etc/acpi/LID/00000080 (busybox acpid is enabled in install.sh) running a control-socket command that locks (vault) then syspanels.sleep; setting lid=sleep/nothing. |
| 11 | 70 | **'Print this PDF/document'** | 5.83 Print this PDF (P) | tools.py: print_file(path, printer) using `lp -d`; intent 'print <file>'; a Print button on file windows; today only programs' own Print dialogs print. |
| 12 | 70 | **Display changes in words** | 5.16 Set the screen to 1920x1080 (P); 5.18 Mirror my screen to the projector (P) | intent.py: 'set the screen/resolution to WxH' -> desk 'set resolution <first output> WxH'; add a set_display tool (resolution, rotation, scale) since the model has no display tool. |
| 13 | 70 | **Sleep after N minutes idle** | 1.10.10 Sleep when inactive for N minutes (N); 3.9.12 Idle -> sleep timers (N); 5.28 Never sleep while plugged in (P) | swayidle timeout -> syspanels.sleep (on battery by default); change_setting sleep_after=<minutes/never>. |
| 14 | 66 | **Screenshot of a window or area, to clipboard** | 3.7.2 Full screen, window, region, delay, cursor, save, clipboard, open with, upload (P); 5.79 Take a screenshot of this window (P) | Add slurp and wl-clipboard to PKGS; tools.screenshot gains area ('grim -g "$(slurp)"'), window (geometry from lswt) and copy (wl-copy); intent._SHOT: 'of this window/an area', 'copy it'. |
| 15 | 62 | **Lock when going to sleep** | 1.10.14 Lock when going to sleep (N); 1.10.23 Lock the screen when the system goes to sleep (N); 1.15.4 Lock the screen before sleep (N); 1.18.11 Lock when going to sleep (N); 3.8.3 Lock on suspend (N) | desk.py sleep branch of _system_shortcut: call self.lock() (when a vault exists) before syspanels.sleep; syspanels.sleep currently leaves the vault open on waking. |
| 16 | 62 | **Window requests with 'this window' / 'window'** | 5.4 Close a window: 'Close the browser window' (P); 5.5 Maximize / minimize: 'Maximize this window' / 'Hide everything' (P) | desk.py _WIN: allow a trailing 'window/app' ('close the browser window') and 'this window/it' -> wm.last_program(); 'hide everything' -> minimize all (see show_desktop). |
| 17 | 60 | **'Unzip this' extracts it** | 5.91 Unzip this download (P) | tools.py: extract_archive(path) using `7z x -o<folder>` / `tar -xf` into a folder beside it, then show_files; intent 'unzip/extract X'; today open_file only launches Xarchiver. |
| 18 | 58 | **Click a running program in the dock to switch to it** | 2.5.13 Window Buttons (tasklist) (P); 2.5.14 Window Menu (list of all windows) (P); 3.5.6 Minimize; restore from the tasklist (P) | desk.js dock(): chip onclick posts {t:'app.focus', pid}; Desk.handle 'app.focus' (currently `pass`) maps the pid's program to wm.PROCS/app id and calls wm.act('focus'). |
| 19 | 56 | **'Put Firefox on the left and Files on the right'** | 3.4.18 Super+arrows tile (P); 3.4.19 Super+keypad corners: quarter tiling (N); 5.6 Tile: 'Put Firefox on the left and Files on the right' (N) | wm.py: tile(target, side) = act('focus') then `wtype -M logo -k Left -m logo` (rc.xml already binds W-Left/W-Right to SnapToEdge); _WIN regex 'put X on the left/right'; corner keys if labwc's SnapToEdge supports them. |
| 20 | 55 | **A key to lock (Super+L / Ctrl+Alt+L)** | 1.8.16 Default: Ctrl+Alt+L / Ctrl+Alt+Del lock (P); 3.8.1 Ctrl+Alt+L, Action Buttons > Lock, xflock4 (P) | rc.xml: <keybind key="W-l"> and C-A-l -> Execute a new `llmos lock` CLI that sends 'lock' to the desk control socket (desk.control). |
| 21 | 55 | **Act on critical battery** | 1.10.12 Critical battery level (N); 1.10.13 On critical battery (N); 3.9.13 Critical battery -> action (N) | Desk._poll_away: when _battery() <= 10% and discharging, toast + chime; at 3% lock and syspanels.sleep (or poweroff). |
| 22 | 55 | **Change my passphrase** | 1.25.2 Add/delete user, password, picture, admin, autologin (P); 5.88 Change my password (P) | vault.change_passphrase exists but nothing calls it: add a nonce form like vault-form in desk.py and intent 'change my (passphrase/password)'. |
| 23 | 55 | **True mirroring** | 1.7.10 Mirror displays (P) | syspanels.arrange('mirror'): give the second output the main output's mode (or --scale to fit) at 0,0; for different aspect ratios use wl-mirror (add package). |
| 24 | 52 | **Print Screen key** | 0.9 Default shortcuts point at missing tools (Print, Ctrl+Shift+Esc) (P); 1.8.25 Default: Print / Alt+Print / Shift+Print screenshot (N) | rc.xml: <keybind key="Print"> Execute `llmos screenshot` (new CLI subcommand calling grim into ~/Pictures and toasting via the control socket). |
| 25 | 52 | **Rotate / flip the screen** | 1.7.6 Rotation (N); 1.7.7 Reflection (N); 5.17 Rotate the monitor to portrait (N) | syspanels.set_transform(output, t) via `wlr-randr --output X --transform 90/180/270/flipped`; buttons in syspanels.displays; intent 'rotate the screen (to portrait)'. |
| 26 | 50 | **Do not disturb** | 1.11.1 Do Not Disturb (N); 4.2.5 Notifications with DND and log (N); 5.84 Don't disturb me for an hour (N) | change_setting do_not_disturb on/off (+minutes) that Desk.emit drops toasts/chime for and show_away defers; intent 'don't disturb me for an hour'. |
| 27 | 50 | **Night light** | 3.11.8 Night light / redshift (N); 4.2.29 Night light (N) | Add wlsunset (or gammastep) to PKGS; change_setting night_light on/off/auto (sunset by time zone); intent 'night light on'. |
| 28 | 50 | **Printer panel 'Test page' and 'Make default' buttons** | 1.20.3 Set the default printer (P); 1.20.4 Print a test page (P) | desk._system_shortcut: handle 'make (\S+) the default printer' (lpadmin -d) and 'print a test page on (\S+)' (lp -d X /usr/share/cups/data/testprint); today both phrases fall through to the model. |
| 29 | 48 | **Show the desktop / hide everything** | 2.5.12 Show Desktop (N); 3.4.12 Ctrl+Alt+D show desktop (N); 5.7 Show the desktop (N) | wm.minimize_all(): wlrctl toplevel minimize for every wm.windows(); _WIN 'show (me) the desktop/hide everything/minimize all'; rc.xml C-A-d (W-d is dictation). |
| 30 | 45 | **Bigger pointer / cursor theme** | 1.9.15 Cursor theme (N); 1.9.16 Cursor size (N); 5.26 Make the pointer bigger (N) | Desk.apply_input: write XCURSOR_SIZE (and XCURSOR_THEME=Adwaita) to the labwc environment file it already writes; intent 'make the pointer bigger'; labwc needs a restart of programs to pick it up. |
| 31 | 45 | **More buttons in file windows** | 3.1.13 Right-click a desktop icon: open, open with, cut, copy, rename, trash, delete, properties (P) | tools.show_files: add Rename, Move to..., Copy to USB and 'Open with Files' actions per item (the tools exist: rename_file, move_files). |
| 32 | 42 | **Forget a Wi-Fi network** | 1.21.3 Forget a network (N) | Desk.network_panel: 'Forget' action on known networks -> `iwctl known-networks <ssid> forget`; intent 'forget the wifi X'. |
| 33 | 40 | **Auto-lock: without a passphrase, and in other words** | 1.10.22 Delay locking after the screensaver (P); 1.18.9 Lock with the screensaver (P); 5.34 Lock 5 minutes after the screen blanks (P) | tools.change_setting autolock: allow it without a vault (Desk.lock already has a no-passphrase screen lock path); add 'lock' to agent._ONLY_IF_ASKED['change_setting'] (today 'lock 5 minutes after the screen blanks' is refused as not asked) and widen intent._AUTOLOCK. |
| 34 | 40 | **Keep-or-revert after a resolution change** | 1.7.11 Apply with keep/revert after 10 s (N) | syspanels.set_mode: remember the previous mode; desk shows a 'Keep this?' dialog with a 15 s timer that reverts via wlr-randr. |
| 35 | 40 | **Other people's accounts / switch user** | 1.18.15 Show 'Switch user' (N); 1.18.20 Switch user button (N); 1.25.1 Users and groups GUI (N); 2.11.1 Choose a user or type a username (N); 2.11.9 Switch user (N); 3.8.6 Switch user from the lock screen (N); 3.9.7 Switch user (N); 4.2.13 Users and Groups (N); 5.39 Let someone else log in (N); 5.87 Create an account for my son (N) | By design one owner. If wanted: adduser + a per-user vault and a user picker on the lock screen (large change across vault.py, desk.lock/unlock). |
| 36 | 40 | **Pin programs to the dock** | 2.5.2 Bottom dock: show desktop, launchers, directory menu (P); 2.5.9 Launcher (P); 3.2.5 Onto a panel launcher (N); 3.2.11 .desktop file onto the panel (N); 5.62 Pin Terminal to the panel (N) | settings appearance.pinned=[program ids]; desk.js dock() renders them as launch chips; intent 'pin X to the dock'. |
| 37 | 40 | **Two keyboard layouts with a switch key** | 1.8.29 Shortcut to change layout (N); 1.8.31 Add a layout and variant (P); 1.8.33 Remove a layout (N); 1.8.34 Move a layout up/down (N); 3.11.4 Layout switching via shortcut (N); 5.19 Add a French keyboard and let me switch with Alt+Shift (P) | Desk.apply_input already allows 'us,fr' in XKB_DEFAULT_LAYOUT: add XKB_DEFAULT_OPTIONS=grp:alt_shift_toggle, an 'Add another layout' choice in syspanels.input_panel, and a status chip showing the active layout. |
| 38 | 40 | **Workspaces** | 1.2.16 Wrap workspaces at the pointer edge (N); 1.2.17 Wrap workspaces when dragging a window (N); 1.3.3 Cycle through all workspaces (N); 1.3.21 Mouse wheel on desktop switches workspace (N); 1.3.22 Remember previous workspace (N); 1.3.23 Wrap by desktop layout (N); 1.3.24 Wrap at first/last workspace (N); 1.4.1 Number of workspaces (N); 1.4.2 Rename workspaces (N); 2.5.15 Workspace Switcher (N); 2.6.5 Scroll the wheel to switch workspace (N); 3.2.10 Window in the pager to another workspace (N); 3.4.4 Alt+F6 stick (N); 3.4.13 Ctrl+Alt+arrows switch workspace (N); 3.4.14 Ctrl+F1..F12 go to workspace (N); 3.4.15 Move window to previous/next workspace (N); 3.4.16 Alt+Insert add workspace (N); 3.4.17 Alt+Delete remove workspace (N); 3.5.9 Sticky (all workspaces) (N); 3.5.10 Move to workspace from the window menu (N); 3.6.1 4 by default (N); 3.6.2 Add, remove, rename (N); 3.6.3 Pager in the panel (N); 3.6.4 Keyboard switching (N); 3.6.5 Scroll-wheel switching (N); 3.6.6 Wrap-around (N); 3.6.7 Per-workspace wallpaper (N); 3.6.8 Move windows between workspaces (N); 3.6.9 Per-workspace margins (N); 5.8 Move this window to workspace 2 (N); 5.9 Give me 6 workspaces and call the second one Work (N) | rc.xml: <desktops number="4"/> plus GoToDesktop/SendToDesktop keybinds (C-A-Left/Right, S-C-A-Left/Right); wm.py: send those keys with wtype for 'move this window to workspace 2'; a desk.js indicator. |
| 39 | 38 | **'What apps do I have for X?'** | 5.2 Search apps: 'What apps do I have for editing images?' (P) | tools.manage_apps list: return programs.installed() names, generic names and categories to the model (today it returns only the owner's made apps), or add a find_program tool. |
| 40 | 36 | **Find files by kind and date** | 5.44 Find the spreadsheet I downloaded last week (P) | tools.find_paths: understand 'last week/yesterday/today' (mtime) and kind words (spreadsheet/pdf/photo via tools.KINDS) instead of name-only matching. |
| 41 | 36 | **One trash for the desk and Files** | 3.11.12 Trash location ~/.local/share/Trash (P) | tools._trash/delete_file/restore_file: use the freedesktop trash (~/.local/share/Trash/files + info/*.trashinfo) that Thunar/gvfs use, instead of ~/.Trash. |
| 42 | 35 | **Bluetooth pairing that needs a PIN/confirmation** | 1.22.3 Scan and pair (PIN confirmation) (P) | syspanels.bt_action connect: run a bluetoothctl agent (KeyboardDisplay) and surface the passkey through Desk.ask; today devices that need confirmation fail. |
| 43 | 35 | **Clock format (24-hour, seconds)** | 1.24.3 Clock layout: analog, binary, digital, fuzzy, LCD (N); 1.24.4 Tooltip format (N); 1.24.5 Date then time / time only ... (N); 1.24.6 Custom strftime formats and fonts (N); 1.24.7 Show seconds (N); 1.24.8 24-hour or 12-hour (P); 5.63 Show 24-hour time with seconds (N) | settings appearance.clock {hour12, seconds, date}; desk.js clock() reads it; intent 'show 24-hour time with seconds'. |
| 44 | 35 | **Control any player (Firefox video)** | 1.23.6 Media player (MPRIS) controls (P) | Add playerctl; tools.media_control falls back to `playerctl play-pause/next`; rc.xml XF86AudioPlay/Next/Prev. |
| 45 | 35 | **See / cancel print jobs** | 1.20.5 View and cancel jobs (N) | syspanels.printers: list `lpstat -o` with a Cancel action (`cancel <job>`), handled in desk._system_shortcut. |
| 46 | 35 | **Start programs at login** | 1.15.5 Autostart list (N); 1.15.6 Add an autostart entry (with triggers) (N); 1.15.7 Edit an entry (N); 1.15.8 Remove an entry (N); 1.15.9 Enable/disable entries incl. system items (P); 2.8.2 Autostart applications (N); 3.11.9 Autostart programs on login (N); 5.40 Start the terminal every time I log in (N) | settings.autostart=[commands]; Desk.enter_desk launches them via launch_app; intent 'start X every time I log in' and a list in Settings. |
| 47 | 35 | **Usual app shortcuts (Ctrl+Alt+T, Super+E, Ctrl+Shift+Esc...)** | 1.8.13 Default: Super / Alt+F1 application menu (P); 1.8.14 Default: Alt+F2 run box (P); 1.8.15 Default: Alt+F3 Application Finder (P); 1.8.17 Default: Ctrl+Alt+T terminal (P); 1.8.18 Default: Super+E file manager (N); 1.8.19 Default: Super+W web browser (N); 1.8.20 Default: Super+M mail (N); 1.8.22 Default: Ctrl+Alt+Esc xkill (P); 1.8.23 Default: Ctrl+Esc desktop menu (N); 1.8.24 Default: Shift+Ctrl+Esc task manager (P); 1.8.26 Default: XF86WWW / XF86Mail / XF86Explorer (N); 3.4.24 Application shortcuts from 1.8 (P); 4.2.28 Shortcuts: Super menu, Print, Super+L, Ctrl+Alt+T, Super+E (P) | rc.xml: C-A-t foot, W-e thunar, W-b firefox, C-S-Escape and W-Space -> control-socket commands ('task manager', 'show my apps'). |
| 48 | 35 | **VPN** | 1.21.5 VPN import (N); 4.1.5 Network (Wi-Fi, VPN) (P); 4.2.2 Network: nm-applet, VPN, hotspot, connections editor (P) | Add wireguard-tools (and openvpn) to PKGS; tool vpn_import(file) + on/off via wg-quick; a VPN row in the network panel. |
| 49 | 35 | **Zoom into part of the screen** | 1.3.19 Zoom desktop with Alt+wheel (N); 1.3.20 Zoom the pointer with the desktop (N); 3.4.23 Alt+scroll zoom (N); 5.73 Zoom in on the top-left corner (N) | rc.xml keybinds W-plus/W-minus -> labwc ZoomIn/ZoomOut (labwc >= 0.8 magnifier; verify version); intent 'zoom in on the screen' sends them with wtype. |
| 50 | 32 | **Open a terminal in this folder** | 2.2.17 Custom actions: Open Terminal Here (P); 3.1.6 Open Terminal Here (P); 3.3.15 Open a terminal in the current folder (P); 5.55 Open a terminal in this folder (P) | intent 'open a terminal in X' -> Desk.run_in_terminal with cd X; set exo's TerminalEmulator=foot (~/.config/xfce4/helpers.rc) so Thunar's 'Open Terminal Here' works (verify). |
| 51 | 32 | **Tell me when updates exist** | 4.1.3 Software updates via a GUI notifier (P); 4.2.7 Update Manager (levels, kernels, automatic, Flatpak) (P) | llmos-scheduler daily: syspanels.updates_check() when internet is allowed -> away card 'N updates' with an Install button. |
| 52 | 32 | **Uninstall a program** | 4.1.4 Install and remove software via a GUI store (P); 4.2.8 Software Manager (browse, install, remove, reviews) (P) | tools.py: remove_software(packages) using `apk del` (DESTRUCTIVE risk); intent 'uninstall X'; today only run_command can. |
| 53 | 30 | **Airplane mode** | 1.21.7 Airplane mode / disable networking (P) | `rfkill block all` / unblock (busybox rfkill or util-linux) behind change_setting airplane on/off; today 'internet off' only firewalls. |
| 54 | 30 | **Back up to a USB stick (on a schedule)** | 4.2.12 Backup Tool (P) | tools.py: backup(folder, 'usb') that copies the named folder (~/Documents) with `rsync -a` (installed) so repeats copy only changes; works with schedule_task ('every Friday'). |
| 55 | 30 | **Click the clock for a calendar** | 1.24.9 Click shows a month calendar (P) | desk.js: clock click -> 'open the calendar' (the Calendar app) or a small month popup; today it opens the world Clock app. |
| 56 | 30 | **Import photos from a camera/phone** | 1.12.10 Cameras: import photos (P) | tools.move_files: allow from='usb' (mounted stick/card) to Pictures; MTP phones need gvfs-mtp (see netshares). |
| 57 | 30 | **Maximized programs cover the bar and clock** | 1.4.3 Margins maximized windows will not cover (N); 1.6.9 Don't reserve space (N); 1.6.11 Keep the panel above windows (N) | rc.xml: reserve the bar with labwc's <margin top="N"/> (verify labwc version) so maximized programs stop below the desk's bar. |
| 58 | 30 | **My own keyboard shortcuts** | 1.2.6 Edit a shortcut (N); 1.2.7 Clear a shortcut (N); 1.2.8 Reset shortcuts to defaults (N); 1.8.9 Add a shortcut (N); 1.8.10 Edit a shortcut (N); 1.8.11 Remove a shortcut (N); 1.8.12 Reset to defaults (N); 5.21 Make Super+B open the browser (N) | settings input.keys=[{key, say}]; Desk.apply_input injects <keybind> elements executing a control-socket 'say'; intent 'make Super+B open the browser'. |
| 59 | 30 | **Network shares and phones (SMB/SFTP/MTP)** | 0.8 Only core gvfs (no SMB/MTP/SFTP) (N); 2.2.24 Network browsing (SMB/SFTP/MTP) (N); 4.2.26 Network share browsing (SMB, SFTP, MTP) (N) | Add gvfs-smb gvfs-mtp gvfs-sftp to PKGS (Thunar then browses them); intent 'connect to server smb://...' -> launch thunar with the URI. |
| 60 | 30 | **On-screen volume/brightness indicator** | 1.10.8 Show notifications (P); 1.23.7 Volume keys with on-screen notification (P) | `llmos volume/brightness` (keys) send a toast to the desk control socket after devices.volume/brightness. |
| 61 | 30 | **Play/pause/next keys** | 3.11.6 Media and volume keys (P) | rc.xml: XF86AudioPlay/Pause/Next/Prev -> `llmos media toggle/next` (media.ipc for mpv, playerctl for others). |
| 62 | 30 | **React when a second screen is plugged in** | 1.7.15 Configure new displays when connected (P) | Desk: the Gdk monitors 'items-changed' hook (already used for zoom) also opens syspanels.displays() with Extend/Mirror. |
| 63 | 30 | **Refresh rate** | 1.7.5 Refresh rate (N) | syspanels.displays: offer rates per resolution; set_mode passes 'WxH@R' to `wlr-randr --mode`. |
| 64 | 30 | **Turn a specific screen on/off** | 1.7.3 Enable or disable a display (P) | syspanels.displays: per-output On/Off actions (`wlr-randr --output X --on/--off`). |
| 65 | 30 | **Volume slider** | 1.23.3 Output volume slider (P) | Desk.sound_panel: a range block (uispec) posting 'set the volume to N%' instead of four preset buttons. |
| 66 | 28 | **Alt-Tab extras** | 1.3.1 Skip windows with skip-pager/taskbar while cycling (N); 1.3.2 Include minimized windows in cycling (P); 1.3.5 Raise windows while cycling (N); 1.3.30 Window previews when cycling (N); 3.4.1 Alt+Tab / Shift+Alt+Tab (P); 3.4.2 Super+Tab: same application (P); 3.5.1 Alt-Tab across workspaces, incl. minimized (P); 5.70 Make Alt-Tab include minimized windows (P) | rc.xml: S-A-Tab PreviousWindow; windowRule skipWindowSwitcher="yes" for org.llmos.desk so the desk is not in the list; preview="yes" for thumbnails. |
| 67 | 25 | **Arrange screens (left/right/above), primary** | 1.7.1 Monitor layout canvas (drag to arrange) (N); 1.7.9 Set as primary display (N); 1.7.12 Identify displays (N); 3.5.14 Multiple monitors: per-monitor panels, primary, move a window (P) | syspanels.displays: Left of / Right of / Above buttons using `wlr-randr --pos`; the desk (and its bar) stays on the first output. |
| 68 | 25 | **Battery time left and health** | 1.10.25 List batteries, AC adapter, UPS, wireless devices (P); 1.10.26 Charge, state, vendor, model, capacity (health) (P); 1.10.27 Panel: battery icon with % or time remaining (P) | desk._battery: read energy_now/power_now (time left) and energy_full/energy_full_design (health); show in Desk.power_panel and the chip tooltip. |
| 69 | 25 | **Brightness control on screen** | 1.10.28 Panel: brightness slider (P); 2.5.16 Power Manager plugin (P) | Desk.power_panel: brightness buttons/slider posting 'brightness N%' (intent._BRIGHT handles it) when /sys/class/backlight exists. |
| 70 | 25 | **Choose default browser/editor/terminal** | 1.13.1 Web browser (P); 1.13.3 File manager (P); 1.13.4 Terminal emulator (P); 5.41 Make Firefox my default browser (P) | settings defaults.{browser,editor,terminal}; programs.find honours them before KINDS order; intent 'make X my default browser'. |
| 71 | 25 | **Clipboard history** | 2.5.17 Not available without extras (Whisker, volume, bell, screenshooter, xkb, CPU, load, network, weather, clipman, places, mailwatch, sensors) (P); 3.11.2 No clipboard history (N); 4.1.9 Clipboard history (N) | Add cliphist + wl-clipboard; Desk starts `wl-paste --watch cliphist store`; a 'clipboard' panel listing recent items with Copy buttons. |
| 72 | 25 | **Connection details** | 1.21.9 Connection information (IP, speed, MAC) (P) | Desk.network_panel: rows for IP, MAC, signal and link speed from `iwctl station <dev> show` and `ip -o link`. |
| 73 | 25 | **Default app per file type** | 1.13.5 Searchable list of MIME types (N); 1.13.6 Filter by status (N); 1.13.7 Change the default app for a type (P); 1.13.8 Reset a type to the system default (N); 3.11.10 Open files and links in default apps (xdg-open) (P); 5.42 Always open PDFs in Firefox (P) | tools.open_file: consult ~/.config/mimeapps.list (what Thunar's 'Open With > set default' writes) before its fixed extension map; 'always open PDFs in X' writes it. |
| 74 | 25 | **Fonts for programs** | 1.1.8 Default font family and size (P); 1.1.9 Default monospace font (N) | set_appearance font: also write gtk-font-name to the GTK settings.ini and font= to ~/.config/foot/foot.ini. |
| 75 | 25 | **Format a USB stick** | 4.1.8 Partitioning and formatting disks (N); 4.2.19 Disks: format, partition, bootable USB (N) | syspanels.drives: 'Format' action -> Desk.ask confirm -> mkfs.exfat / mkfs.vfat (exfatprogs, dosfstools installed) on removable disks only. |
| 76 | 25 | **Lock screen clock, power buttons, layout** | 1.18.13 Session status messages (N); 1.18.14 Log out from the lock screen after N minutes (N); 1.18.17 Clock (N); 1.18.18 Username shown (N); 1.18.19 Keyboard layout shown (N); 1.18.21 Log out button (N); 2.11.4 Indicators: clock, host name, power menu (N); 2.11.5 Accessibility menu (large font, contrast, OSK) (N); 2.11.6 Keyboard layout indicator (N); 4.2.14 Login Window settings (background, autologin, guest) (P) | index.html screen-lock + desk.js screen(): add the clock, Restart/Shut down buttons and the current keyboard layout. |
| 77 | 25 | **Natural scrolling for a mouse** | 1.9.3 Reverse scroll direction (P) | Desk.apply_input writes <naturalScroll> only for category touchpad: add it to the default device too, with its own toggle. |
| 78 | 25 | **Open drives automatically / quiet plug-in** | 1.12.1 Mount removable drives when hot-plugged (P); 1.12.3 Browse removable media when inserted (P); 1.17.32 Volume management (button to Removable Drives settings) (P); 2.2.20 Auto-mount on hotplug (volman) (P); 5.74 Don't auto-open USB drives (P) | Desk._poll_drives: setting drives=open/ask/quiet; 'open' mounts (syspanels.mount) and shows files; install thunar-volman only if Thunar should do it. |
| 79 | 25 | **Other everyday programs** | 4.1.2 Apps (PCManFM-Qt, QTerminal, FeatherPad, LXImage, Screengrab, Archiver, qps, Qlipper, KCalc, VLC, LibreOffice, Discover, Calamares, Partition Manager, Skanlite, nm-tray, BlueDevil, notifier, notes, 2048) (P); 4.2.24 Apps (Xed, Xviewer, Xreader, Pix, Drawing, Celluloid, Rhythmbox, Hypnotix, LibreOffice, Thunderbird, Transmission, Simple Scan, Calculator, Calendar, Sticky Notes, Screenshot, Archive Manager, Mousepad, Ristretto, Parole, Catfish, Task Manager, Onboard, Orca, Redshift) (P) | install_app already installs on request; add Alpine package names to programs.KINDS ('music' -> rhythmbox/lollypop, 'office' -> libreoffice, 'torrent' -> transmission-gtk) so 'install a music player' picks a real package. |
| 80 | 25 | **Power button action** | 1.10.1 Power button action (P); 1.10.2 Sleep button action (N); 1.10.3 Hibernate button action (N); 1.10.4 Battery button action (N); 3.9.10 Power button -> configured action (P) | Ship /etc/acpi/PWRF/00000080 that opens Desk.power_panel through the control socket instead of busybox acpid's immediate poweroff (verify default). |
| 81 | 25 | **Programs' theme** | 1.1.1 Choose GTK theme from a list (N); 1.1.2 Theme preview thumbnails (N) | Write gtk-theme-name (Adwaita / Adwaita-dark, adwaita-icon-theme is installed) with set_appearance; no theme chooser today. |
| 82 | 25 | **Reopen my programs next time** | 1.15.1 Session chooser on login (N); 1.15.2 Save session on logout (N); 1.15.11 Restart style per client (N); 1.15.13 Save the session now (N); 1.15.17 Clear saved sessions (N); 2.8.3 Session save and restore (N); 3.5.15 Session restore of windows (N); 3.9.9 'Save session' checkbox (N); 5.94 Reopen my windows next time I log in (N) | On shutdown save the argv of Desk.apps to settings; Desk.enter_desk relaunches them when 'restore programs' is on. |
| 83 | 25 | **Right-click on the desk** | 1.5.9 Right-click desktop menu (N); 1.5.10 Application icons in that menu (N); 2.6.3 Right-click root menu (N); 3.1.1 Open in New Window (N); 3.1.2 Create Launcher (N); 3.1.3 Create URL Link (N); 3.1.4 Create Folder (P); 3.1.5 Create Document / Empty File (P); 3.1.7 Paste (N); 3.1.11 Properties (N) | desk.py run(): the WebView 'context-menu' signal is suppressed; give the page its own small menu (New folder, Paste file, Change background, Settings) that posts act phrases. |
| 84 | 25 | **Scan a document** | 1.12.11 Scanners: run a command (N) | Install sane-backends + simple-scan on request (install_app); add 'scan' to programs.KINDS. |
| 85 | 25 | **Screen reader / read everything aloud** | 1.14.14 No screen reader or on-screen keyboard (P) | On request: install orca and drop GTK_A11Y=none / NO_AT_BRIDGE=1 in usr/libexec/llmos-desk; the desk already reads its own replies aloud (speak_replies). |
| 86 | 25 | **Search inside files** | 3.3.7 File contents not searched (P) | tools.find_files: optional 'containing X' via `grep -ril` (and pdftotext if installed) under the home folder. |
| 87 | 25 | **Super+P display switcher** | 1.7.17 Quick popup (Super+P / XF86Display) (P); 1.8.21 Default: Super+P display popup (N) | rc.xml W-p -> control-socket 'displays' (syspanels.displays already has Extend/Mirror/Only). |
| 88 | 25 | **Terminal look and settings** | 1.26.4 xfce4-terminal preferences (P); 2.3.8 Preferences: General (P); 2.3.9 Preferences: Appearance (P); 2.3.10 Preferences: Colors (P); 2.3.11 Preferences: Compatibility (P); 2.3.12 Preferences: Advanced (P); 2.3.13 Preferences: Shortcuts (P); 2.3.15 Profiles (N); 5.76 Make the terminal background black with green text (P) | set_appearance: write ~/.config/foot/foot.ini [colors]/[main] font from the theme; intent 'make the terminal background black with green text'. |
| 89 | 20 | **Auto-hide or move the bar** | 1.6.10 Auto-hide: never / intelligently / always (N); 5.61 Auto-hide the taskbar / move the panel to the bottom (P) | desk.css/desk.js: an autohide class on #top and #dock and a bar position setting in set_appearance (the windows/mac layouts are the only placement choice today). |
| 90 | 20 | **Bar orientation/position** | 1.6.5 Mode: horizontal / vertical / deskbar (P) | Same as panel_autohide: a bar position setting; today only the clean/windows/mac layout presets move it. |
| 91 | 20 | **Confirm before shutting down from the button** | 3.9.8 Confirmation dialog with 30 s countdown (P) | Desk.shortcut 'shut down'/'restart' from a button: Desk.ask confirmation first (typed requests through system_power already follow autonomy). |
| 92 | 20 | **Printers that need a driver** | 1.20.2 Choose a driver (P); 4.2.6 Printers with automatic driver detection (P) | Printers panel: 'Add with driver' using `lpinfo -m` models; install gutenprint/hplip on request; add_printer only uses -m everywhere (driverless). |
| 93 | 20 | **Right-click Extract/Compress in Files** | 2.2.25 Compress or extract (P); 4.2.25 Thunar archive plugin, media tags, shares (N) | Add thunar-archive-plugin to PKGS (Xarchiver is already installed). |
| 94 | 20 | **Screensaver** | 1.18.1 Enable the screensaver (N); 1.18.2 Theme list (N); 1.18.3 Change theme after N minutes (N); 1.18.4 Activate when idle (N); 1.18.5 Idle delay (N); 1.18.6 Inhibit for fullscreen applications (P); 1.18.7 Preview (N); 3.8.7 Screensaver themes while locked (P); 5.35 Use a blank screensaver after 10 minutes (N) | swayidle timeout -> the desk shows its living background full-screen (desk-bg.js) until input; option in Settings. |
| 95 | 20 | **Sticky/slow/bounce keys** | 1.14.3 Sticky keys: enable (N); 1.14.4 Sticky keys: lock (N); 1.14.5 Sticky keys: disable on two keys (N); 1.14.6 Slow keys (N); 1.14.7 Bounce keys (N); 5.71 Turn on sticky keys (N) | labwc has no AccessX: needs a compositor patch or keyd; out of reach without new components. |
| 96 | 20 | **Which folders/files fill the disk** | 4.2.20 Disk Usage Analyzer (P) | syspanels.storage: drill into the largest folders/files (`du -x` sorted) with Open / Move to trash actions. |
| 97 | 20 | **Wi-Fi hotspot** | 1.21.6 Hotspot (N) | `iwctl device wlan0 set-property Mode ap` + `iwctl ap wlan0 start SSID PASS`; a Hotspot button in Desk.network_panel. |
| 98 | 20 | **Window borders/title bars match the theme** | 1.1.5 Set matching window-manager theme toggle (N); 1.2.1 Window decoration theme list (N); 1.2.2 Title font (N); 1.2.3 Title alignment (N); 5.69 Use a thinner window border (N) | set_appearance: regenerate usr/share/themes/llmos/labwc/themerc (copy to XDG_CONFIG_HOME/themes) from the theme colours and border width, then `labwc --reconfigure`. |
| 99 | 20 | **xfwm-style window keys** | 3.4.7 Alt+F9 minimize (P); 3.4.8 Alt+F10 maximize (P); 3.4.9 Alt+F11 fullscreen (P); 3.4.10 Alt+F12 always on top (P); 3.4.11 Alt+Space window menu (P); 3.5.8 Always on top / below (P) | rc.xml: A-F9 Iconify, A-F10 ToggleMaximize, A-F11 ToggleFullscreen, A-space ShowMenu client-menu, a key for ToggleAlwaysOnTop. |
| 100 | 15 | **Assistive technologies (AT-SPI)** | 1.14.1 Enable assistive technologies (AT-SPI) (N) | usr/libexec/llmos-desk exports GTK_A11Y=none NO_AT_BRIDGE=1: make them conditional on an accessibility setting. |
| 101 | 15 | **Bluetooth discoverable / send a file** | 1.22.2 Make the computer discoverable (N); 1.22.5 Send a file (N); 4.2.3 Bluetooth: Blueman (pair, send files, profiles) (P) | bluetoothctl discoverable on; file send needs bluez-obexd (add package) and an obexctl wrapper. |
| 102 | 15 | **Desktop icons** | 1.5.16 Desktop icon type (N); 1.5.17 Icon size (N); 1.5.18 Custom icon font size (N); 1.5.19 Icon tooltips (N); 1.5.20 Single click to activate (N); 1.5.21 Show hidden files on the desktop (N); 1.5.22 Show thumbnails (N); 1.5.23 Default icon: Home (P); 1.5.24 Default icon: File System (N); 1.5.25 Default icon: Trash (P); 1.5.26 Default icons: removable devices (P); 1.5.27 Which monitor shows the icons (N); 2.6.2 Desktop icons for files, launchers, volumes (N); 3.1.8 Arrange Desktop Icons (N) | A desk.js 'Desktop' strip showing ~/Desktop files, Home and Trash; low priority. |
| 103 | 15 | **Drag files onto/off the desk** | 2.6.6 Drag files to and from the desktop (N); 3.2.3 To and from the desktop (N) | desk.js: accept drops (WebKit drop event with file URIs) -> open_file; drag out is not possible from WebKit to programs easily. |
| 104 | 15 | **Find my pointer** | 1.14.2 Locate pointer with Ctrl (N); 5.72 Where's my mouse? (N) | A labwc keybind (verify an action exists) or a desk overlay ring at the pointer for 1 s on double Ctrl. |
| 105 | 15 | **Focus follows mouse** | 1.2.9 Focus model: click / follows mouse (N); 5.66 Make windows follow the mouse focus (N) | Desk.apply_input: rewrite <followMouse> from a setting. |
| 106 | 15 | **Hibernate** | 1.10.9 System sleep mode: suspend or hibernate (P); 3.9.5 Hibernate (P); 3.9.6 Hybrid sleep (N) | Needs swap + resume= on the kernel line; 'hibernate' currently suspends to RAM (syspanels.sleep). |
| 107 | 15 | **Hidden Wi-Fi network** | 1.21.8 Hidden network (N) | tools.wifi_connect / Desk._wifi_connect: use `iwctl station <dev> connect-hidden <ssid>` when the SSID is not in the scan. |
| 108 | 15 | **Input methods (Chinese/Japanese typing)** | 3.11.3 Input method (ibus/fcitx) (N); 4.2.16 Languages and input methods (locale, formats, ibus/fcitx) (P) | fcitx5 + labwc environment (GTK_IM_MODULE etc.); needed for CJK typing in programs. |
| 109 | 15 | **Key repeat delay** | 1.8.3 Repeat delay (P) | syspanels.input_panel: delay buttons; input.repeat_delay is already written by Desk.apply_input but nothing sets it. |
| 110 | 15 | **List all keyboard shortcuts** | 1.2.5 List of window actions with shortcuts (P); 1.8.8 List of command-shortcut pairs (P) | Help panel (Desk.panel_spec 'help'): render the keybinds from rc.xml instead of the one-line d_shortcuts text. |
| 111 | 15 | **More pointer options** | 1.9.1 Choose the device (P); 1.9.5 Acceleration profile (N); 1.9.6 Reset to defaults (P); 1.9.7 Touchpad: disable while typing (P); 1.9.9 Touchpad: scroll mode (N); 1.9.10 Touchpad: horizontal scrolling (N); 1.9.11 Touchpad: click method (N); 1.9.12 Drag-and-drop threshold (N); 1.9.13 Double-click time (N); 1.9.14 Double-click distance (N) | Desk.apply_input: accelProfile, scrollMethod, clickMethod, disableWhileTyping, and <mouse><doubleClickTime> from settings. |
| 112 | 15 | **Num Lock on at start** | 1.8.1 Restore Num Lock on startup (N) | Desk.apply_input: add <numlock>on</numlock> to <keyboard> (labwc option). |
| 113 | 15 | **On-screen keyboard** | 1.18.12 On-screen keyboard command (N) | Add wvkbd; toggle in Settings and on the lock screen. |
| 114 | 15 | **Rotating wallpapers** | 1.5.7 Change the background on a timer (N); 1.5.8 Random order (N); 2.6.7 Next background / slideshow (N); 3.1.9 Next Background (N); 5.11 Rotate my wallpapers every 10 minutes (N) | scheduler: a 'wallpaper rotate' job picking the next image from ~/Pictures/Wallpapers (after wall_local). |
| 115 | 15 | **See every setting** | 1.16.1 Browse channels (P); 1.16.2 Search for a property (N); 1.16.3 Add a property (N); 1.16.4 Edit a value (P); 1.16.5 Reset a property (P); 1.16.6 Delete a property (N); 1.16.7 Lock state (kiosk) (N); 1.16.8 Live monitor of changes (N); 5.75 Change any setting I can't find in the menus (P) | A Settings 'All settings' view listing /etc/llmos/settings.json keys with their values (changes still through change_setting/set_appearance). |
| 116 | 15 | **Static IP / DNS** | 1.21.4 Wired: DHCP or static IPv4/IPv6, DNS (P) | Write an iwd network file [IPv4] or /etc/network/interfaces static stanza from a form in the network panel. |
| 117 | 15 | **Status icons of programs (tray)** | 2.5.10 Notification Area (systray) (N); 4.2.27 Mint panel plugins (Whisker, tasklist, systray, xkb, volume, bell, network, clock, power, user actions) (P) | StatusNotifierItem host in desk.py over the session bus; large job, few programs need it here. |
| 118 | 15 | **System snapshots** | 4.2.11 Timeshift snapshots (N); 4.2.30 Automatic maintenance (snapshot before updates, kernel cleanup) (N) | Not planned (no btrfs); backups via backup gap. |
| 119 | 15 | **Title-bar buttons order** | 1.2.4 Button layout (N); 5.68 Put the close button on the left (N) | Desk.apply_input: rewrite <titlebar><layout> from a setting ('close on the left'). |
| 120 | 15 | **Video/PDF thumbnails in Files** | 2.2.13 Thumbnails (images, video, PDF) (P); 3.3.8 Thumbnails for images, video, PDF (P) | Add ffmpegthumbnailer and tumbler's poppler plugin to PKGS (verify Alpine package split). |
| 121 | 10 | **Bar configuration (size, opacity, monitor)** | 1.6.1 Choose which panel to edit (N); 1.6.2 Add a panel (N); 1.6.3 Remove a panel (N); 1.6.4 Backup/restore panel layout (N); 1.6.6 Output monitor (N); 1.6.7 Span monitors (N); 1.6.12 Row size (P); 1.6.13 Number of rows (N); 1.6.14 Length (%) (N); 1.6.15 Automatically increase length (N); 1.6.16 Icon size (P); 1.6.19 Colour and image pickers (P); 1.6.20 Enter opacity (N); 1.6.21 Leave opacity (N) | Settings for bar height/opacity in desk.css variables via set_appearance. |
| 122 | 10 | **CDs/DVDs** | 1.12.2 Mount removable media when inserted (P); 1.12.6 Burn a data CD on blank disc (N); 1.12.7 Burn an audio CD on blank disc (N); 1.12.8 Play audio CDs when inserted (N) | syspanels.removable skips iso9660 media: show sr0; burning needs xorriso; playing audio CDs mpv cdda://. |
| 123 | 10 | **Compose key, keyboard model** | 1.8.28 Keyboard model (N); 1.8.30 Compose key (N) | Desk.apply_input: XKB_DEFAULT_OPTIONS=compose:ralt (and XKB_DEFAULT_MODEL) in the environment file. |
| 124 | 10 | **Display profiles** | 1.7.13 Profiles: save (N); 1.7.14 Profiles: apply or delete (N); 1.7.16 Auto-enable profiles on connect (N) | Save wlr-randr state per set of connected outputs in settings, or add kanshi. |
| 125 | 10 | **Driver/firmware manager** | 4.2.10 Driver Manager (N) | Show missing firmware from dmesg and offer linux-firmware-* via install_app. |
| 126 | 10 | **Event sounds on/off** | 1.1.18 Enable event sounds (P); 1.1.19 Input feedback sounds (N); 1.23.14 Event sounds toggle (N) | A setting that devices.chime checks; GTK event sounds need libcanberra. |
| 127 | 10 | **Icon theme** | 1.1.6 Choose icon theme (N); 5.13 Use a different icon set (N) | gtk-icon-theme-name in the GTK settings.ini (needs more icon packages). |
| 128 | 10 | **Log out / switch user / hybrid sleep** | 1.15.3 Prompt on logout (N); 2.5.5 Action Buttons (P); 2.8.1 Log out dialog (log out, restart, shut down, suspend, hibernate, hybrid, switch user, save session) (P); 3.9.1 Log out (N); 5.36 Log me out (N) | No sessions to log out of (one owner, root). 'Log out' could map to lock; switching user needs users. |
| 129 | 10 | **Move/resize/lower with the keyboard** | 3.4.5 Alt+F7 move with keyboard (N); 3.4.6 Alt+F8 resize with keyboard (N); 3.4.20 Alt+Shift+PageDown lower window (N) | rc.xml keybinds for labwc MoveToEdge/ResizeTo/Lower (verify action names). |
| 130 | 10 | **Process details** | 1.15.10 List of running session clients (P) | syspanels.processes: show all processes / sort by CPU, not only the 14 largest by memory. |
| 131 | 10 | **Scroll on the volume icon** | 1.23.1 Scroll on the volume icon (N) | desk.js: wheel on the sound chip posts 'turn the volume up/down'. |
| 132 | 10 | **Send files over the local network** | 4.2.22 Warpinator (LAN file sending) (N) | Not planned (would need a service + discovery). |
| 133 | 10 | **Snapping/resistance strength** | 1.2.13 Snap to screen borders (P); 1.2.14 Snap to other windows (P); 1.2.15 Snap distance (N); 1.2.18 Edge resistance slider (N); 1.3.15 Edge resistance instead of snapping (N); 3.5.2 Snap to edges and windows; edge resistance (P) | Desk.apply_input: <snapping><range> and <resistance> from a setting. |
| 134 | 10 | **Terminal tabs** | 2.3.1 Shell sessions in tabs and windows (P); 2.3.2 Split panes (N); 2.3.7 Tab title and colour (N) | foot has no tabs: add a tabbed terminal only if asked (or use foot windows). |
| 135 | 10 | **Wallpaper fit/colour gradient** | 1.5.4 Style: centered, tiled, stretched, scaled, zoomed, spanning (N); 1.5.5 Color: solid / gradients / transparent (P); 1.5.6 Color 1 and Color 2 pickers (P) | theme_payload: a backdrop fit setting (cover/contain/tile) and gradient backgrounds in desk-bg.js. |
| 136 | 10 | **Window shadows on/off** | 1.3.31 Shadows under popups (P); 1.3.32 Shadows under docks (P); 1.3.33 Shadows under regular windows (P); 3.5.13 Shadows (P); 5.67 Turn off window shadows (N) | Desk.apply_input: rewrite <dropShadows> from a setting. |
| 137 | 8 | **Add/remove bar items** | 1.6.22 List the plugins (N); 1.6.23 Add a plugin (N); 1.6.24 Remove a plugin (N); 1.6.25 Move a plugin (N); 1.6.26 A plugin's own settings (N); 1.6.27 About a plugin (N); 2.5.1 Top panel: menu, window buttons, workspace switcher, tray, power, clock, actions (P); 2.5.3 Panel right-click menu (N); 2.5.4 Plugins available with no extra packages (P); 2.5.11 Separator (N) | A list of optional chips in settings read by desk.js status(). |
| 138 | 8 | **Favourites/hide in the program list** | 1.26.1 Application Finder preferences (N); 2.4.4 Right-click: favourites, edit, hide (N) | settings programs.hidden/favourites used by Desk.show_apps. |
| 139 | 8 | **Notification look and placement** | 1.11.3 Which monitor (N); 1.11.4 Position (N); 1.11.5 Expire timeout (N); 1.11.6 Fade-out (P); 1.11.7 Slide-out (P); 1.11.8 Show summary only (N); 1.11.10 Opacity (N); 1.11.11 Icon size (N); 1.11.12 Preview button (N) | desk.css toast position/time settings if ever asked. |
| 140 | 5 | **Brightness step size** | 1.10.6 Brightness step count (N); 1.10.7 Exponential brightness steps (N) | devices.brightness step from a setting (keys use +-10). |
| 141 | 5 | **Fixed window-manager behaviour** | 1.2.10 Give focus to new windows (P); 1.2.11 Raise on focus (P); 1.2.12 Raise on click (P); 1.2.21 Double-click title bar action (P); 1.3.10 Key used to grab and move windows (P); 1.3.11 Raise when any mouse button is pressed (P); 1.3.26 Default placement (center / under mouse) (P) | Expose the rc.xml values (raiseOnFocus, placement policy, double-click) as settings in Desk.apply_input if ever asked. |
| 142 | 5 | **Metered connection** | 1.21.10 Metered connection flag (N) | A flag that pauses update checks/model downloads. |
| 143 | 5 | **Middle-click window list** | 1.5.11 Window list on middle click (N); 1.5.12 Window list: workspace names (N); 1.5.13 Window list: sticky windows only in active workspace (N); 1.5.14 Window list: add/remove workspace items (N); 1.5.15 Window list: application icons (N); 2.6.4 Middle-click window list (N); 3.1.15 Middle-click window list with workspaces (N) | Not needed: Alt-Tab and 'switch to X' cover it. |
| 144 | 5 | **Mouse keys** | 1.14.8 Mouse emulation: enable (N); 1.14.9 Mouse emulation: acceleration delay (N); 1.14.10 Mouse emulation: repeat interval (N); 1.14.11 Mouse emulation: acceleration time (N); 1.14.12 Mouse emulation: maximum speed (N); 1.14.13 Mouse emulation: acceleration profile (N) | Same constraint as sticky_keys (no AccessX in labwc). |
| 145 | 5 | **Per-monitor/workspace wallpaper** | 1.5.1 Pick monitor and workspace to configure (N); 1.5.2 Apply to all workspaces (N); 2.6.1 Wallpaper per monitor and per workspace (N) | Only after workspaces/multi-output desk exist. |
| 146 | 5 | **Per-port firewall rules** | 4.2.17 Firewall (gufw) (P) | system.firewall_rules is policy-only (internet yes/ask/no, Tor); rules per port not planned. |
| 147 | 5 | **Run a command when a device is plugged in** | 1.12.9 Portable media players: play music (N); 1.12.12 Printers: run a command when connected (P); 1.12.13 Keyboards: run a command (N); 1.12.14 Mice: run a command (N); 1.12.15 Tablets: run a command (N) | udev rules or a hook in Desk._poll_drives; rarely wanted. |
| 148 | 5 | **Share a printer** | 1.20.6 Share a printer (N) | cupsctl --share-printers on request. |
| 149 | 5 | **System reports** | 4.2.18 System Reports (P) | About panel + audit already; crash reports not planned. |
| 150 | 5 | **Turn a site into an app** | 4.2.23 Web Apps manager (N) | Pinned Firefox --kiosk launchers via dock_pins. |
| 151 | 5 | **Volume step / over 100%** | 1.23.8 Volume step and maximum above 100% (N) | devices.volume step setting; pipewire allows >100% via wpctl. |
| 152 | 5 | **Window opacity** | 1.3.34 Opacity of decorations (N); 1.3.35 Opacity of inactive windows (N); 1.3.36 Opacity while moving (N); 1.3.37 Opacity while resizing (N); 1.3.38 Opacity of popups (N); 3.5.12 Window opacity (N) | labwc windowRules with opacity (verify support); low value. |
| 153 | 3 | **Autorun from drives** | 1.12.4 Auto-run programs on new media (N); 1.12.5 Auto-open files on new media (N) | Deliberately absent (security). |
| 154 | 3 | **Colour profiles** | 1.19.1 Device list (colord) (N); 1.19.2 Add an ICC profile (N); 1.19.3 Remove a profile (N); 1.19.4 Make a profile default (N); 1.19.5 Profile details (N); 1.19.6 Works only with colord running (N) | colord is absent; not planned. |
| 155 | 3 | **Drop-down terminal** | 2.3.6 Drop-down (Quake) mode (N) | Not planned. |
| 156 | 3 | **Font hinting/antialiasing** | 1.1.10 Rendering: anti-aliasing (N); 1.1.11 Hinting (N); 1.1.12 Sub-pixel order (N) | fontconfig local.conf from a setting; rarely asked. |
| 157 | 3 | **Install themes by dragging an archive** | 1.1.4 Install a theme by drag and drop (N); 1.1.7 Install an icon theme by dragging an archive (N); 3.2.9 Theme archive into Appearance (N) | Not planned. |
| 158 | 3 | **Rare xfwm4 tweaks** | 1.2.19 Hide content while moving (N); 1.2.20 Hide content while resizing (N); 1.3.7 Focus stealing prevention (N); 1.3.8 Honor ICCCM focus hint (N); 1.3.9 When a window raises itself (N); 1.3.12 Hide frame when maximized (N); 1.3.13 Hide title when maximized (N); 1.3.16 Mouse wheel on title bar shades (N); 1.3.17 Urgency: blink decoration (N); 1.3.18 Urgency: keep blinking (N); 1.3.25 Minimum size for smart placement (N); 3.5.7 Shade (roll up) (P) | Not worth doing; labwc lacks most of them. |
| 159 | 3 | **Software sources** | 4.2.9 Software Sources (N) | /etc/apk/repositories editing; not for ordinary users. |
| 160 | 3 | **Toolkit details (toolbar style, cursor blink...)** | 1.1.14 Toolbar style (N); 1.1.15 Show images on buttons (N); 1.1.16 Show images in menus (N); 1.1.17 Editable accelerators (N); 1.8.5 Blinking cursor (N); 1.8.6 Cursor blink delay (N) | GTK settings.ini keys if ever asked. |
| 161 | 2 | **GNOME/KDE services, remote apps** | 1.15.14 Launch GNOME services (N); 1.15.15 Launch KDE services (N); 1.15.16 Manage remote applications (TCP) (N); 2.11.3 Session chooser (N) | Not applicable. |

## Full mapping

### 0 What stock Alpine XFCE does NOT install

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 0.1 | No notification daemon | PARTIAL | LLM OS shows its own events as toasts and the 'While you were away' card (desk.py Desk.show_away, Desk.emit toast), but programs' desktop notifications go nowhere (no org.freedesktop.Notifications server). | notify |
| 0.2 | No audio stack / volume icon / Sound settings | YES | pipewire, wireplumber, pipewire-pulse, pavucontrol in PKGS (src/install.sh); started by desk.py Desk._start_sound; sound chip -> Desk.sound_panel; 'volume 40%' -> intent._device -> tools.set_volume -> devices.volume. |  |
| 0.3 | No network GUI | YES | iwd in PKGS; network chip (desk.js status) -> Desk.network_panel / Desk.wifi_join; 'connect to the CoffeeShop wifi, password is ...' -> tools.wifi_connect. |  |
| 0.4 | No Bluetooth | YES | bluez in PKGS, bluetooth service enabled (install.sh); 'bluetooth' / 'pair my headphones' -> Desk._system_shortcut (_SYS) -> syspanels.bluetooth. |  |
| 0.5 | No printing | YES | cups, cups-filters, avahi in PKGS, cupsd enabled; 'printers' / 'add a printer' -> syspanels.printers / syspanels.add_printer (details in 1.20). |  |
| 0.6 | No editor, viewer, archiver, screenshooter, task manager, player, PDF viewer, calculator, Whisker, menu editor, greeter settings | YES | Mousepad, Ristretto, Xarchiver, mpv installed (PROGRAM, opened by 'open the text editor' etc. via programs.find); screenshot: 'take a screenshot' -> tools.screenshot; task manager: syspanels.processes; calculator app (apps/calculator.html) and tools.calculate; program list: apps chip -> Desk.show_apps; PDF opens in Firefox (tools.open_file), as on XFCE. No menu or greeter to edit. |  |
| 0.7 | No GUI for users, date/time, time zone, updates, disks | PARTIAL | Updates: 'updates' -> syspanels.updates_panel. Drives: syspanels.drives. Time zone only in the first-run wizard (Desk.wizard_step 'timezone'). No users, no date/time or NTP, no disk formatting. | timezone |
| 0.8 | Only core gvfs (no SMB/MTP/SFTP) | NO | Same as stock: gvfs only (PKGS). Network shares and phones cannot be browsed. | netshares |
| 0.9 | Default shortcuts point at missing tools (Print, Ctrl+Shift+Esc) | PARTIAL | The tools exist (screenshot, task manager) but rc.xml binds neither Print nor Ctrl+Shift+Esc; reachable by words only. | print_key |

### 1.1 Appearance

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.1.1 | Choose GTK theme from a list | NO | set_appearance themes only the desk (themes.PALETTES); programs keep the stock GTK look; no GTK settings.ini is written. | gtk_theme |
| 1.1.2 | Theme preview thumbnails | NO | Settings shows named theme buttons (Desk.panel_spec 'settings', Presets), no previews. | gtk_theme |
| 1.1.3 | Dark preference for apps | PARTIAL | 'dark mode' -> intent._theme -> tools.set_appearance theme=dark darkens the desk; Firefox, Thunar, Mousepad stay light (nothing sets gtk-application-prefer-dark-theme). | gtk_dark |
| 1.1.4 | Install a theme by drag and drop | NO | No theme installation. | theme_install |
| 1.1.5 | Set matching window-manager theme toggle | NO | Window frames use the static labwc theme usr/share/themes/llmos/labwc/themerc; it does not follow the desk theme. | wm_theme |
| 1.1.6 | Choose icon theme | NO | adwaita-icon-theme only; no chooser. | icon_theme |
| 1.1.7 | Install an icon theme by dragging an archive | NO | Not available. | theme_install |
| 1.1.8 | Default font family and size | PARTIAL | 'change the font to serif' -> intent._theme (_FONT) -> set_appearance font (sans/serif/mono/pixel, themes.FONTS) and size via 'make the text bigger' (scale); desk only, programs unchanged. | fonts |
| 1.1.9 | Default monospace font | NO | Desk uses JetBrains Mono fixed; programs/terminal not configurable. | fonts |
| 1.1.10 | Rendering: anti-aliasing | NO | Fontconfig defaults, no setting. | font_render |
| 1.1.11 | Hinting | NO | No setting. | font_render |
| 1.1.12 | Sub-pixel order | NO | No setting. | font_render |
| 1.1.13 | Custom DPI | PARTIAL | The desk picks a scale from the screen's pixels per inch (desk.py _display_scale) times the owner's text size ('make everything bigger' -> appearance.scale); programs are not scaled. | scale_programs |
| 1.1.14 | Toolbar style | NO | No setting. | gtk_misc |
| 1.1.15 | Show images on buttons | NO | No setting. | gtk_misc |
| 1.1.16 | Show images in menus | NO | No setting. | gtk_misc |
| 1.1.17 | Editable accelerators | NO | No setting. | gtk_misc |
| 1.1.18 | Enable event sounds | PARTIAL | The desk chimes for timers and finished background work (devices.chime); no on/off and no sounds for programs. | event_sounds |
| 1.1.19 | Input feedback sounds | NO | None. | event_sounds |
| 1.1.20 | Window scaling factor (HiDPI) | PARTIAL | Desk only (desk.py Desk._apply_zoom); wlr-randr --scale is never used, so programs stay at 1x. | scale_programs |

### 1.2 Window Manager (xfwm4 settings -> labwc)

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.2.1 | Window decoration theme list | NO | Fixed labwc theme 'llmos' (rc.xml <theme><name>). | wm_theme |
| 1.2.2 | Title font | NO | Fixed Inter 10 (rc.xml <font place=ActiveWindow>). | wm_theme |
| 1.2.3 | Title alignment | NO | Fixed. | wm_theme |
| 1.2.4 | Button layout | NO | Fixed 'icon:iconify,max,close' (rc.xml <titlebar><layout>). | button_layout |
| 1.2.5 | List of window actions with shortcuts | PARTIAL | Help panel shows one line (i18n d_shortcuts: Esc, F1, Ctrl+L); the rc.xml keybinds are not listed anywhere. | shortcuts_view |
| 1.2.6 | Edit a shortcut | NO | rc.xml keybinds are fixed; Desk.apply_input copies them unchanged. | custom_keys |
| 1.2.7 | Clear a shortcut | NO | Not possible. | custom_keys |
| 1.2.8 | Reset shortcuts to defaults | NO | Not possible. | custom_keys |
| 1.2.9 | Focus model: click / follows mouse | NO | Fixed click-to-focus (rc.xml <followMouse>no). | focus_follow |
| 1.2.10 | Give focus to new windows | PARTIAL | labwc default: new windows get focus; not adjustable. | wm_fixed |
| 1.2.11 | Raise on focus | PARTIAL | Fixed on (rc.xml <raiseOnFocus>yes). | wm_fixed |
| 1.2.12 | Raise on click | PARTIAL | labwc default; not adjustable. | wm_fixed |
| 1.2.13 | Snap to screen borders | PARTIAL | labwc built-in edge resistance/snapping defaults (not set in rc.xml; verify); not adjustable. | snapping |
| 1.2.14 | Snap to other windows | PARTIAL | labwc default window-edge resistance (verify); not adjustable. | snapping |
| 1.2.15 | Snap distance | NO | No setting. | snapping |
| 1.2.16 | Wrap workspaces at the pointer edge | NO | There is one workspace (no <desktops> in rc.xml). | workspaces |
| 1.2.17 | Wrap workspaces when dragging a window | NO | One workspace. | workspaces |
| 1.2.18 | Edge resistance slider | NO | No setting. | snapping |
| 1.2.19 | Hide content while moving | NO | No setting. | wm_misc |
| 1.2.20 | Hide content while resizing | NO | No setting. | wm_misc |
| 1.2.21 | Double-click title bar action | PARTIAL | Maximize (labwc default; desk windows too: desk.js openWindow dblclick -> maximize); not changeable. | wm_fixed |

### 1.3 Window Manager Tweaks

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.3.1 | Skip windows with skip-pager/taskbar while cycling | NO | No setting; note the desk itself is in the Alt-Tab list (rc.xml windowRule skipWindowSwitcher="no"). | alttab |
| 1.3.2 | Include minimized windows in cycling | PARTIAL | labwc's switcher lists minimized windows by default (verify); not adjustable. | alttab |
| 1.3.3 | Cycle through all workspaces | NO | One workspace. | workspaces |
| 1.3.4 | Draw a frame around the selected window | YES | rc.xml <windowSwitcher outlines="yes">. |  |
| 1.3.5 | Raise windows while cycling | NO | Not configured. | alttab |
| 1.3.6 | Cycle in a list | YES | rc.xml <windowSwitcher><osd show="yes"/> shows a list. |  |
| 1.3.7 | Focus stealing prevention | NO | Not available. | wm_misc |
| 1.3.8 | Honor ICCCM focus hint | NO | Not applicable on Wayland. | wm_misc |
| 1.3.9 | When a window raises itself | NO | No setting. | wm_misc |
| 1.3.10 | Key used to grab and move windows | PARTIAL | labwc default mouse bindings (rc.xml <mouse><default/>): Alt+drag (verify); not adjustable. | wm_fixed |
| 1.3.11 | Raise when any mouse button is pressed | PARTIAL | labwc default; not adjustable. | wm_fixed |
| 1.3.12 | Hide frame when maximized | NO | Not available. | wm_misc |
| 1.3.13 | Hide title when maximized | NO | Not available. | wm_misc |
| 1.3.14 | Tile when moving to the screen edge | YES | labwc default snapping: drag to the left/right edge = half, top = maximize (verify version); Super+Left/Right in rc.xml (SnapToEdge). |  |
| 1.3.15 | Edge resistance instead of snapping | NO | No setting. | snapping |
| 1.3.16 | Mouse wheel on title bar shades | NO | Not configured. | wm_misc |
| 1.3.17 | Urgency: blink decoration | NO | Not available. | wm_misc |
| 1.3.18 | Urgency: keep blinking | NO | Not available. | wm_misc |
| 1.3.19 | Zoom desktop with Alt+wheel | NO | No magnifier binding. | magnifier |
| 1.3.20 | Zoom the pointer with the desktop | NO | No magnifier. | magnifier |
| 1.3.21 | Mouse wheel on desktop switches workspace | NO | One workspace. | workspaces |
| 1.3.22 | Remember previous workspace | NO | One workspace. | workspaces |
| 1.3.23 | Wrap by desktop layout | NO | One workspace. | workspaces |
| 1.3.24 | Wrap at first/last workspace | NO | One workspace. | workspaces |
| 1.3.25 | Minimum size for smart placement | NO | No setting. | wm_misc |
| 1.3.26 | Default placement (center / under mouse) | PARTIAL | Fixed center (rc.xml <placement><policy>center); desk windows cascade (desk.js openWindow). | wm_fixed |
| 1.3.27 | Enable display compositing | YES | Always: labwc is a Wayland compositor. |  |
| 1.3.28 | Unredirect fullscreen windows | YES | wlroots does direct scan-out automatically (verify). |  |
| 1.3.29 | Vsync | YES | Wayland presents on vblank. |  |
| 1.3.30 | Window previews when cycling | NO | rc.xml windowSwitcher preview="no". | alttab |
| 1.3.31 | Shadows under popups | PARTIAL | Fixed on (rc.xml <dropShadows>yes). | shadows |
| 1.3.32 | Shadows under docks | PARTIAL | Fixed on. | shadows |
| 1.3.33 | Shadows under regular windows | PARTIAL | Fixed on; 'turn off window shadows' has no route. | shadows |
| 1.3.34 | Opacity of decorations | NO | No setting. | opacity |
| 1.3.35 | Opacity of inactive windows | NO | No setting. | opacity |
| 1.3.36 | Opacity while moving | NO | No setting. | opacity |
| 1.3.37 | Opacity while resizing | NO | No setting. | opacity |
| 1.3.38 | Opacity of popups | NO | No setting. | opacity |

### 1.4 Workspaces

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.4.1 | Number of workspaces | NO | labwc default of one; rc.xml sets no <desktops>. | workspaces |
| 1.4.2 | Rename workspaces | NO | One workspace. | workspaces |
| 1.4.3 | Margins maximized windows will not cover | NO | None set (programs maximize over the desk's bar, see 1.6). | panel_above |

### 1.5 Desktop

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.5.1 | Pick monitor and workspace to configure | NO | One wallpaper for the desk. | wall_multi |
| 1.5.2 | Apply to all workspaces | NO | One workspace. | wall_multi |
| 1.5.3 | Choose an image folder and pick an image | PARTIAL | 'set a wallpaper of the Alps' -> intent._photo (_WALLPAPER) -> tools.set_wallpaper downloads a Wikimedia Commons photo; the owner's own pictures cannot be used. | wall_local |
| 1.5.4 | Style: centered, tiled, stretched, scaled, zoomed, spanning | NO | No fit option. | wall_style |
| 1.5.5 | Color: solid / gradients / transparent | PARTIAL | 'plain background' (backdrop=plain) and 'make the background dark blue' -> set_appearance background; no gradients. Living/still backgrounds are LLM OS's own (desk-bg.js). | wall_style |
| 1.5.6 | Color 1 and Color 2 pickers | PARTIAL | One colour by words or #hex ('make the background #223344'); no picker, no second colour. | wall_style |
| 1.5.7 | Change the background on a timer | NO | No slideshow. | wall_slideshow |
| 1.5.8 | Random order | NO | No slideshow. | wall_slideshow |
| 1.5.9 | Right-click desktop menu | NO | desk.py run(): the WebView 'context-menu' signal returns True (suppressed). | desk_menu |
| 1.5.10 | Application icons in that menu | NO | No desk menu. | desk_menu |
| 1.5.11 | Window list on middle click | NO | Not available. | window_list |
| 1.5.12 | Window list: workspace names | NO | Not available. | window_list |
| 1.5.13 | Window list: sticky windows only in active workspace | NO | Not available. | window_list |
| 1.5.14 | Window list: add/remove workspace items | NO | Not available. | window_list |
| 1.5.15 | Window list: application icons | NO | Not available. | window_list |
| 1.5.16 | Desktop icon type | NO | No desktop icons. | desk_icons |
| 1.5.17 | Icon size | NO | No desktop icons. | desk_icons |
| 1.5.18 | Custom icon font size | NO | No desktop icons. | desk_icons |
| 1.5.19 | Icon tooltips | NO | No desktop icons. | desk_icons |
| 1.5.20 | Single click to activate | NO | No desktop icons. | desk_icons |
| 1.5.21 | Show hidden files on the desktop | NO | No desktop icons. | desk_icons |
| 1.5.22 | Show thumbnails | NO | No desktop icons. | desk_icons |
| 1.5.23 | Default icon: Home | PARTIAL | 'show my files' -> intent._FILES -> tools.show_files; Files chip in the mac layout dock / start menu (desk.js dock, START_ITEMS). | desk_icons |
| 1.5.24 | Default icon: File System | NO | show_files of '/' works by words ('what's in /'), no icon. | desk_icons |
| 1.5.25 | Default icon: Trash | PARTIAL | 'show the trash' -> intent._notes (_TRASH) -> show_files ~/.Trash. | desk_icons |
| 1.5.26 | Default icons: removable devices | PARTIAL | A plugged-in stick raises a toast and the Drives panel (desk.py Desk._poll_drives -> syspanels.drives); no icon stays. | desk_icons |
| 1.5.27 | Which monitor shows the icons | NO | No desktop icons. | desk_icons |

### 1.6 Panel

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.6.1 | Choose which panel to edit | NO | One bar, not configurable. | panel_cfg |
| 1.6.2 | Add a panel | NO | Not possible. | panel_cfg |
| 1.6.3 | Remove a panel | NO | Not possible. | panel_cfg |
| 1.6.4 | Backup/restore panel layout | NO | Not possible. | panel_cfg |
| 1.6.5 | Mode: horizontal / vertical / deskbar | PARTIAL | Three layout presets: 'give me a windows style desk' (bottom taskbar + start button), 'mac style', 'clean' (intent._layout -> set_appearance layout). | panel_pos |
| 1.6.6 | Output monitor | NO | The desk lives on one output. | panel_cfg |
| 1.6.7 | Span monitors | NO | Not possible. | panel_cfg |
| 1.6.8 | Lock the panel | YES | The bar is part of the desk page (desk.js status) and cannot be dragged. |  |
| 1.6.9 | Don't reserve space | NO | No reserved space at all. | panel_above |
| 1.6.10 | Auto-hide: never / intelligently / always | NO | Not available. | panel_autohide |
| 1.6.11 | Keep the panel above windows | NO | Program windows sit on top of the desk, so a maximized Firefox covers the bar and clock. | panel_above |
| 1.6.12 | Row size | PARTIAL | Grows with the text size ('make everything bigger'). | panel_cfg |
| 1.6.13 | Number of rows | NO | Not possible. | panel_cfg |
| 1.6.14 | Length (%) | NO | Full width, fixed. | panel_cfg |
| 1.6.15 | Automatically increase length | NO | Not applicable. | panel_cfg |
| 1.6.16 | Icon size | PARTIAL | Follows the text size. | panel_cfg |
| 1.6.17 | Background style | YES | Follows the desk theme: 'ocean theme', 'make the background navy' (set_appearance). |  |
| 1.6.18 | Dark mode for the panel | YES | 'dark mode' (intent._theme -> set_appearance). |  |
| 1.6.19 | Colour and image pickers | PARTIAL | Colours by words; no image. | panel_cfg |
| 1.6.20 | Enter opacity | NO | No setting. | panel_cfg |
| 1.6.21 | Leave opacity | NO | No setting. | panel_cfg |
| 1.6.22 | List the plugins | NO | Bar items are fixed (desk.js status). | panel_items |
| 1.6.23 | Add a plugin | NO | Not possible. | panel_items |
| 1.6.24 | Remove a plugin | NO | Not possible. | panel_items |
| 1.6.25 | Move a plugin | NO | Not possible. | panel_items |
| 1.6.26 | A plugin's own settings | NO | Each chip opens its panel; no per-chip settings. | panel_items |
| 1.6.27 | About a plugin | NO | Not applicable. | panel_items |

### 1.7 Display

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.7.1 | Monitor layout canvas (drag to arrange) | NO | Only Extend puts outputs left-to-right (syspanels.arrange). | display_arrange |
| 1.7.2 | Select a display | YES | 'displays' / 'second screen' -> Desk._system_shortcut (_SYS) -> syspanels.displays lists outputs (wlr-randr --json). |  |
| 1.7.3 | Enable or disable a display | PARTIAL | 'Only this screen' button -> 'use only the main display' -> syspanels.arrange('only') turns the others off; 'Extend' turns them on; no per-output switch. | display_onoff |
| 1.7.4 | Resolution | YES | Displays panel: resolution buttons (top 6 modes of the first two outputs) -> 'set resolution OUT WxH' -> syspanels.set_mode (wlr-randr --mode). Typed requests: see 5.16. |  |
| 1.7.5 | Refresh rate | NO | set_mode passes WxH only. | refresh |
| 1.7.6 | Rotation | NO | wlr-randr --transform never used. | rotate |
| 1.7.7 | Reflection | NO | Not available. | rotate |
| 1.7.8 | Scale (1x, 2x, fractional) | PARTIAL | Desk page only (desk.py _display_scale, Desk._apply_zoom); programs not scaled. | scale_programs |
| 1.7.9 | Set as primary display | NO | The desk stays on the first output. | display_arrange |
| 1.7.10 | Mirror displays | PARTIAL | 'Mirror' button / 'mirror the displays' -> syspanels.arrange('mirror') puts the second output at 0,0 with its own mode: a real mirror only when both resolutions match. | mirror |
| 1.7.11 | Apply with keep/revert after 10 s | NO | set_mode applies at once with no revert. | display_revert |
| 1.7.12 | Identify displays | NO | Not available. | display_arrange |
| 1.7.13 | Profiles: save | NO | Not available. | display_profiles |
| 1.7.14 | Profiles: apply or delete | NO | Not available. | display_profiles |
| 1.7.15 | Configure new displays when connected | PARTIAL | labwc/wlroots enables a new output automatically (verify); the panel says 'Plug in a second screen and it appears here'; nothing pops up. | display_hotplug |
| 1.7.16 | Auto-enable profiles on connect | NO | No profiles. | display_profiles |
| 1.7.17 | Quick popup (Super+P / XF86Display) | PARTIAL | Saying 'projector' or 'use both screens' opens the Displays panel with Extend / Mirror / Only this screen; no key. | display_key |

### 1.8 Keyboard

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.8.1 | Restore Num Lock on startup | NO | Not set in rc.xml. | numlock |
| 1.8.2 | Enable key repeat | YES | Always on; rate written by Desk.apply_input (<repeatRate>). |  |
| 1.8.3 | Repeat delay | PARTIAL | Desk.apply_input writes input.repeat_delay (default 600) but nothing lets the owner change it. | key_repeat |
| 1.8.4 | Repeat speed | YES | 'keyboard and mouse' panel -> Slower / Normal / Faster -> 'key repeat faster' -> Desk._system_shortcut -> input.repeat_rate -> Desk.apply_input (labwc --reconfigure). |  |
| 1.8.5 | Blinking cursor | NO | No setting. | gtk_misc |
| 1.8.6 | Cursor blink delay | NO | No setting. | gtk_misc |
| 1.8.7 | Test area | YES | Type in the request bar. |  |
| 1.8.8 | List of command-shortcut pairs | PARTIAL | Not shown (see 1.2). | shortcuts_view |
| 1.8.9 | Add a shortcut | NO | rc.xml is fixed. | custom_keys |
| 1.8.10 | Edit a shortcut | NO | Not possible. | custom_keys |
| 1.8.11 | Remove a shortcut | NO | Not possible. | custom_keys |
| 1.8.12 | Reset to defaults | NO | Not possible. | custom_keys |
| 1.8.13 | Default: Super / Alt+F1 application menu | PARTIAL | Ctrl+L puts the cursor in the bar (desk.js keydown); the apps chip and the Windows-layout start button open the list; no Super key. | hotkeys_std |
| 1.8.14 | Default: Alt+F2 run box | PARTIAL | Ctrl+L then '!command' runs it in a terminal window (Desk.shortcut -> Desk.run_in_terminal); 'open X' starts programs. | hotkeys_std |
| 1.8.15 | Default: Alt+F3 Application Finder | PARTIAL | 'show my apps' / apps chip -> Desk.show_apps (programs.installed + made apps); no key. | hotkeys_std |
| 1.8.16 | Default: Ctrl+Alt+L / Ctrl+Alt+Del lock | PARTIAL | Say 'lock' (_LOCK_WORDS -> Desk.lock) or the lock chip; no key bound. | lock_key |
| 1.8.17 | Default: Ctrl+Alt+T terminal | PARTIAL | Super+Return opens foot (rc.xml); 'open a terminal' (intent._TERMINAL). | hotkeys_std |
| 1.8.18 | Default: Super+E file manager | NO | Not bound; 'open files' by words. | hotkeys_std |
| 1.8.19 | Default: Super+W web browser | NO | Not bound; 'open the browser' by words. | hotkeys_std |
| 1.8.20 | Default: Super+M mail | NO | Not bound; 'check my email' by words (mail tools). | hotkeys_std |
| 1.8.21 | Default: Super+P display popup | NO | Not bound. | display_key |
| 1.8.22 | Default: Ctrl+Alt+Esc xkill | PARTIAL | 'Firefox is frozen' / 'force quit the terminal' -> Desk._window_shortcut -> wm.force_quit (asks first); no key. | hotkeys_std |
| 1.8.23 | Default: Ctrl+Esc desktop menu | NO | No desk menu. | hotkeys_std |
| 1.8.24 | Default: Shift+Ctrl+Esc task manager | PARTIAL | 'task manager' -> syspanels.processes; no key. | hotkeys_std |
| 1.8.25 | Default: Print / Alt+Print / Shift+Print screenshot | NO | No Print keybind (rc.xml). | print_key |
| 1.8.26 | Default: XF86WWW / XF86Mail / XF86Explorer | NO | Not bound. | hotkeys_std |
| 1.8.27 | Use system defaults toggle | YES | US layout until the owner picks one (settings input.layout default 'us'). |  |
| 1.8.28 | Keyboard model | NO | Not configurable. | kb_extra |
| 1.8.29 | Shortcut to change layout | NO | One layout at a time. | kb_multi |
| 1.8.30 | Compose key | NO | Not configurable. | kb_extra |
| 1.8.31 | Add a layout and variant | PARTIAL | 'use a French keyboard' -> Desk._system_shortcut -> syspanels.layout_code -> input.layout -> Desk.apply_input (XKB_DEFAULT_LAYOUT); it replaces the layout; input.variant is read but cannot be set. | kb_multi |
| 1.8.32 | Edit a layout | YES | Pick another in the Keyboard and mouse panel (syspanels.input_panel choices) or say 'use a German keyboard'. |  |
| 1.8.33 | Remove a layout | NO | Only one layout exists. | kb_multi |
| 1.8.34 | Move a layout up/down | NO | Only one layout exists. | kb_multi |

### 1.9 Mouse and Touchpad

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.9.1 | Choose the device | PARTIAL | Settings apply to all pointers (labwc device categories default + touchpad in Desk.apply_input). | input_more |
| 1.9.2 | Right- or left-handed | YES | Keyboard and mouse panel toggle -> 'left handed mouse on' -> Desk._system_shortcut -> Desk.apply_input <leftHanded>. |  |
| 1.9.3 | Reverse scroll direction | PARTIAL | 'natural scrolling on' toggle, but Desk.apply_input writes <naturalScroll> for touchpads only. | natural_mouse |
| 1.9.4 | Pointer speed | YES | Slower / Normal / Faster -> 'mouse faster' -> input.pointer_speed -> <pointerSpeed>. |  |
| 1.9.5 | Acceleration profile | NO | Not configurable. | input_more |
| 1.9.6 | Reset to defaults | PARTIAL | 'mouse normal speed' resets the speed only. | input_more |
| 1.9.7 | Touchpad: disable while typing | PARTIAL | libinput/labwc default (verify); not adjustable. | input_more |
| 1.9.8 | Touchpad: tap to click | YES | Toggle -> 'tap to click on' -> Desk.apply_input <tap>. |  |
| 1.9.9 | Touchpad: scroll mode | NO | Not configurable. | input_more |
| 1.9.10 | Touchpad: horizontal scrolling | NO | Not configurable. | input_more |
| 1.9.11 | Touchpad: click method | NO | Not configurable. | input_more |
| 1.9.12 | Drag-and-drop threshold | NO | Not configurable. | input_more |
| 1.9.13 | Double-click time | NO | Not configurable. | input_more |
| 1.9.14 | Double-click distance | NO | Not configurable. | input_more |
| 1.9.15 | Cursor theme | NO | Not configurable. | cursor |
| 1.9.16 | Cursor size | NO | Not configurable. | cursor |

### 1.10 Power Manager

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.10.1 | Power button action | PARTIAL | busybox acpid is enabled (install.sh) and its default powers off at once (verify); not configurable. | power_button |
| 1.10.2 | Sleep button action | NO | Not handled. | power_button |
| 1.10.3 | Hibernate button action | NO | Not handled. | power_button |
| 1.10.4 | Battery button action | NO | Not handled. | power_button |
| 1.10.5 | Handle brightness keys | YES | rc.xml XF86MonBrightnessUp/Down -> `llmos brightness +10/-10` (usr/bin/llmos) -> devices.brightness. |  |
| 1.10.6 | Brightness step count | NO | Fixed 10%. | brightness_cfg |
| 1.10.7 | Exponential brightness steps | NO | Linear. | brightness_cfg |
| 1.10.8 | Show notifications | PARTIAL | Desk toasts for its own actions; nothing when keys change volume/brightness. | osd |
| 1.10.9 | System sleep mode: suspend or hibernate | PARTIAL | Suspend only: 'sleep' -> syspanels.sleep writes 'mem'; 'hibernate' also suspends. | hibernate |
| 1.10.10 | Sleep when inactive for N minutes | NO | No idle handling at all. | idle_sleep |
| 1.10.11 | When the lid is closed | NO | No lid handler (verify busybox acpid defaults). | lid |
| 1.10.12 | Critical battery level | NO | Not watched. | critical_battery |
| 1.10.13 | On critical battery | NO | Nothing happens. | critical_battery |
| 1.10.14 | Lock when going to sleep | NO | syspanels.sleep leaves the vault open and the desk unlocked on waking. | lock_on_sleep |
| 1.10.15 | Display power management on/off | NO | No DPMS/idle. | idle_blank |
| 1.10.16 | Blank after N minutes | NO | The screen never blanks. | idle_blank |
| 1.10.17 | Put display to sleep after N minutes | NO | Never. | idle_blank |
| 1.10.18 | Switch display off after N minutes | NO | Never. | idle_blank |
| 1.10.19 | Reduce brightness after N seconds | NO | Never. | idle_blank |
| 1.10.20 | Reduce brightness to N% | NO | Never. | idle_blank |
| 1.10.21 | Automatically lock the session | YES | 'lock after 15 minutes' -> intent._autolock -> change_setting autolock -> Desk._poll_autolock; Settings choices 5/15/60/never (only with a passphrase vault). |  |
| 1.10.22 | Delay locking after the screensaver | PARTIAL | One idle-minutes value (autolock); no screensaver stage. | autolock_novault |
| 1.10.23 | Lock the screen when the system goes to sleep | NO | See above. | lock_on_sleep |
| 1.10.24 | Security tab defers to screensaver settings | YES | One setting (autolock) owns locking. |  |
| 1.10.25 | List batteries, AC adapter, UPS, wireless devices | PARTIAL | Battery % in the status chip and Power panel (desk.py _battery); no AC/UPS/peripheral batteries. | battery_info |
| 1.10.26 | Charge, state, vendor, model, capacity (health) | PARTIAL | Percent and charging only. | battery_info |
| 1.10.27 | Panel: battery icon with % or time remaining | PARTIAL | Battery chip with % and a charging mark (desk.js status); no time remaining. | battery_info |
| 1.10.28 | Panel: brightness slider | PARTIAL | 'brightness 40%' / 'dimmer' (intent._BRIGHT -> tools.set_brightness) and the keys; no on-screen control. | brightness_ui |
| 1.10.29 | Panel: presentation mode | PARTIAL | Nothing blanks the screen anyway; auto-lock can be switched off ('turn off auto-lock'); no single toggle. | idle_blank |
| 1.10.30 | Panel: display power management toggle | NO | No DPMS. | idle_blank |
| 1.10.31 | Panel: open power settings | YES | Power chip -> Desk.power_panel. |  |

### 1.11 Notifications (not installed on stock)

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.11.1 | Do Not Disturb | NO | Focus mode blocks distracting websites (change_setting focus_mode -> system.focus), it does not silence notifications. | dnd |
| 1.11.2 | Notification log | PARTIAL | Background and scheduled results collect in the 'While you were away' card (Desk.show_away, store.unseen); no log of programs' notifications. | notify |
| 1.11.3 | Which monitor | NO | Toasts appear on the desk. | notify_cfg |
| 1.11.4 | Position | NO | Fixed. | notify_cfg |
| 1.11.5 | Expire timeout | NO | Fixed (desk.js toast). | notify_cfg |
| 1.11.6 | Fade-out | PARTIAL | Toasts animate; 'fewer animations' / 'turn animations off' (set_appearance motion) affects them. | notify_cfg |
| 1.11.7 | Slide-out | PARTIAL | Same as fade-out. | notify_cfg |
| 1.11.8 | Show summary only | NO | Not available. | notify_cfg |
| 1.11.9 | Theme | YES | Toasts follow the desk theme (set_appearance). |  |
| 1.11.10 | Opacity | NO | Not available. | notify_cfg |
| 1.11.11 | Icon size | NO | Not available. | notify_cfg |
| 1.11.12 | Preview button | NO | Not available. | notify_cfg |
| 1.11.13 | Per-app mute | NO | No program notifications at all. | notify |
| 1.11.14 | Per-app urgency | NO | Not available. | notify |
| 1.11.15 | Bell plugin: recent log, DND toggle, clear | NO | No bell. | notify |

### 1.12 Removable Drives and Media

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.12.1 | Mount removable drives when hot-plugged | PARTIAL | Plug-in -> toast + Drives panel (desk.py Desk._poll_drives); mounted when the owner presses Open (syspanels.mount) or copies to it (tools.move_files). | automount |
| 1.12.2 | Mount removable media when inserted | PARTIAL | Same for cards; CDs/DVDs are skipped (syspanels.removable drops iso9660). | optical |
| 1.12.3 | Browse removable media when inserted | PARTIAL | Open in the Drives panel -> show_files; not automatic. | automount |
| 1.12.4 | Auto-run programs on new media | NO | Deliberately not done. | autorun |
| 1.12.5 | Auto-open files on new media | NO | Not done. | autorun |
| 1.12.6 | Burn a data CD on blank disc | NO | No burning tools. | optical |
| 1.12.7 | Burn an audio CD on blank disc | NO | No burning tools. | optical |
| 1.12.8 | Play audio CDs when inserted | NO | Not handled. | optical |
| 1.12.9 | Portable media players: play music | NO | Not handled. | device_actions |
| 1.12.10 | Cameras: import photos | PARTIAL | A camera or card that mounts as a drive shows in Drives; the model can copy with move_files/run_command; no import action; MTP not supported. | camera_import |
| 1.12.11 | Scanners: run a command | NO | No scanning (no sane). | scanner |
| 1.12.12 | Printers: run a command when connected | PARTIAL | USB printers appear in 'Look for printers' (syspanels.printers via lpinfo); nothing runs on plug-in. | device_actions |
| 1.12.13 | Keyboards: run a command | NO | Not handled. | device_actions |
| 1.12.14 | Mice: run a command | NO | Not handled. | device_actions |
| 1.12.15 | Tablets: run a command | NO | Not handled. | device_actions |

### 1.13 Default Applications

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.13.1 | Web browser | PARTIAL | Only Firefox is installed; programs.find('browser') prefers Epiphany > Firefox > Chromium; no choice to make. | default_apps |
| 1.13.2 | Mail reader | YES | Built in: 'set up my email ...' -> intent._mail_setup -> tools.mail_setup; 'check my email' -> mail_inbox / mail_read / mail_send / mail_reply / mail_triage (mail.py). |  |
| 1.13.3 | File manager | PARTIAL | The desk's own file windows (tools.show_files) for requests; Thunar for 'open files'; no setting. | default_apps |
| 1.13.4 | Terminal emulator | PARTIAL | foot, fixed (rc.xml W-Return, Desk.run_in_terminal). | default_apps |
| 1.13.5 | Searchable list of MIME types | NO | Not available. | mime |
| 1.13.6 | Filter by status | NO | Not available. | mime |
| 1.13.7 | Change the default app for a type | PARTIAL | Thunar's Open With > 'use as default' writes it for programs, but LLM OS's own opening (tools.open_file) uses a fixed extension map (.pdf Firefox, .docx AbiWord, .xlsx Gnumeric, .zip Xarchiver). | mime |
| 1.13.8 | Reset a type to the system default | NO | Not available. | mime |

### 1.14 Accessibility

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.14.1 | Enable assistive technologies (AT-SPI) | NO | usr/libexec/llmos-desk exports GTK_A11Y=none and NO_AT_BRIDGE=1. | a11y_atspi |
| 1.14.2 | Locate pointer with Ctrl | NO | Not available. | locate_pointer |
| 1.14.3 | Sticky keys: enable | NO | Not available in labwc. | sticky_keys |
| 1.14.4 | Sticky keys: lock | NO | Not available. | sticky_keys |
| 1.14.5 | Sticky keys: disable on two keys | NO | Not available. | sticky_keys |
| 1.14.6 | Slow keys | NO | Not available. | sticky_keys |
| 1.14.7 | Bounce keys | NO | Not available. | sticky_keys |
| 1.14.8 | Mouse emulation: enable | NO | Not available. | mousekeys |
| 1.14.9 | Mouse emulation: acceleration delay | NO | Not available. | mousekeys |
| 1.14.10 | Mouse emulation: repeat interval | NO | Not available. | mousekeys |
| 1.14.11 | Mouse emulation: acceleration time | NO | Not available. | mousekeys |
| 1.14.12 | Mouse emulation: maximum speed | NO | Not available. | mousekeys |
| 1.14.13 | Mouse emulation: acceleration profile | NO | Not available. | mousekeys |
| 1.14.14 | No screen reader or on-screen keyboard | PARTIAL | LLM OS reads its replies aloud ('read your replies aloud' -> change_setting speak_replies -> voice.speak, espeak-ng), takes speech (F1 / mic, Super+D dictation via voice.dictate), and has high-contrast, bigger text and reduced-motion looks; no screen reader for programs, no on-screen keyboard. | screen_reader |

### 1.15 Session and Startup

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.15.1 | Session chooser on login | NO | No sessions. | session_save |
| 1.15.2 | Save session on logout | NO | Not available. | session_save |
| 1.15.3 | Prompt on logout | NO | No log out. | power_actions |
| 1.15.4 | Lock the screen before sleep | NO | See 1.10. | lock_on_sleep |
| 1.15.5 | Autostart list | NO | No autostart of the owner's programs. | autostart |
| 1.15.6 | Add an autostart entry (with triggers) | NO | Not available (schedule_task runs tasks at times, not at login). | autostart |
| 1.15.7 | Edit an entry | NO | Not available. | autostart |
| 1.15.8 | Remove an entry | NO | Not available. | autostart |
| 1.15.9 | Enable/disable entries incl. system items | PARTIAL | System services are fixed by install.sh; the owner can only switch Tor, internet policy and focus mode. | autostart |
| 1.15.10 | List of running session clients | PARTIAL | 'what's running' -> syspanels.processes (14 largest by memory). | task_mgr_more |
| 1.15.11 | Restart style per client | NO | Not available. | session_save |
| 1.15.12 | Quit a program | YES | Task manager End (syspanels.end_process, confirmed) or 'close the browser' (Desk._window_shortcut -> wm.act close); dock chip X (Desk.close_app). |  |
| 1.15.13 | Save the session now | NO | Not available. | session_save |
| 1.15.14 | Launch GNOME services | NO | Not applicable. | compat |
| 1.15.15 | Launch KDE services | NO | Not applicable. | compat |
| 1.15.16 | Manage remote applications (TCP) | NO | Not applicable. | compat |
| 1.15.17 | Clear saved sessions | NO | No sessions. | session_save |

### 1.16 Settings Editor

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.16.1 | Browse channels | PARTIAL | The Settings panel shows the main values (Desk.panel_spec 'settings' kv rows); no raw browser. | settings_editor |
| 1.16.2 | Search for a property | NO | Not available. | settings_editor |
| 1.16.3 | Add a property | NO | Not available. | settings_editor |
| 1.16.4 | Edit a value | PARTIAL | Named settings via tools.change_setting / set_appearance; raw files via run_command/write_file, which always ask for the OS's own files (tools.touches_policy -> SECURITY). | settings_editor |
| 1.16.5 | Reset a property | PARTIAL | 'undo' (tools.undo restores the settings snapshot), 'default theme', 'reset the conduct'. | settings_editor |
| 1.16.6 | Delete a property | NO | Not available. | settings_editor |
| 1.16.7 | Lock state (kiosk) | NO | Not available. | settings_editor |
| 1.16.8 | Live monitor of changes | NO | Not available (the audit panel lists the assistant's actions: 'audit'). | settings_editor |

### 1.17 Thunar Preferences

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.17.1 | View new folders using (icon/detailed/compact/last) | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.2 | Show thumbnails: never/local/always | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.3 | Only thumbnails for files smaller than N | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.4 | Frames around thumbnails | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.5 | Sort folders before files | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.6 | Hidden files at the end | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.7 | File size in binary format | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.8 | Remember view settings per folder | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.9 | Icon view: text beside icons | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.10 | Date format | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.11 | Full paths in tab titles | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.12 | Full path in window title | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.13 | Shortcuts pane icon size | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.14 | Shortcuts pane emblems | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.15 | Shortcuts pane device usage bar | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.16 | Tree pane icon size | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.17 | Tree pane emblems | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.18 | Tree pane hidden folders | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.19 | Image preview embedded or standalone | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.20 | Single or double click | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.21 | Hover delay before select | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.22 | Middle click: new window or tab | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.23 | Open new instances as tabs | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.24 | Restore tabs on startup | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.25 | Parallel transfers | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.26 | Intermediate file when copying | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.27 | Verify checksums | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.28 | Context menu: permanent delete | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.29 | Context menu: create link | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.30 | Ask before trash/delete | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.31 | Folder permissions recursively | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.32 | Volume management (button to Removable Drives settings) | PARTIAL | thunar-volman is not installed, so the option has nothing to open; the desk's Drives panel does plug-in handling. | automount |
| 1.17.33 | Recursive search | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.34 | Search subfolders | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.35 | Show 'Recent' and remember recent files | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.36 | Execute shell scripts: never/always/ask | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |
| 1.17.37 | Rebind Thunar actions | PROGRAM | Thunar is installed (PKGS); 'open files' / 'open thunar' -> programs.find -> tools.open_app; Edit > Preferences. |  |

### 1.18 Screensaver and Lock Screen

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.18.1 | Enable the screensaver | NO | No screensaver (the living background never takes over by idle). | screensaver |
| 1.18.2 | Theme list | NO | Not available. | screensaver |
| 1.18.3 | Change theme after N minutes | NO | Not available. | screensaver |
| 1.18.4 | Activate when idle | NO | Not available. | screensaver |
| 1.18.5 | Idle delay | NO | Not available. | screensaver |
| 1.18.6 | Inhibit for fullscreen applications | PARTIAL | Auto-lock waits while any program is open or media plays (Desk._poll_autolock); there is no screensaver to inhibit. | screensaver |
| 1.18.7 | Preview | NO | Not available. | screensaver |
| 1.18.8 | Enable the lock screen | YES | 'lock' -> Desk.lock (with a passphrase vault: 'set a passphrase' -> intent._autolock (_PASS) -> tools.set_passphrase); without a vault the screen still locks with an Unlock button. |  |
| 1.18.9 | Lock with the screensaver | PARTIAL | Auto-lock after idle minutes, only with a vault (change_setting autolock says 'nothing to lock' otherwise). | autolock_novault |
| 1.18.10 | Lock delay | YES | 'lock after 5 minutes' -> change_setting autolock. |  |
| 1.18.11 | Lock when going to sleep | NO | See 1.10. | lock_on_sleep |
| 1.18.12 | On-screen keyboard command | NO | Not available. | osk |
| 1.18.13 | Session status messages | NO | Not available. | lock_extras |
| 1.18.14 | Log out from the lock screen after N minutes | NO | Not available (5 wrong passphrases power off: Desk.unlock). | lock_extras |
| 1.18.15 | Show 'Switch user' | NO | One owner. | users |
| 1.18.16 | Password prompt | YES | Lock screen passphrase field (index.html #screen-lock) -> Desk.unlock -> vault.unlock. |  |
| 1.18.17 | Clock | NO | The lock screen has no clock. | lock_extras |
| 1.18.18 | Username shown | NO | Not shown. | lock_extras |
| 1.18.19 | Keyboard layout shown | NO | Not shown. | lock_extras |
| 1.18.20 | Switch user button | NO | One owner. | users |
| 1.18.21 | Log out button | NO | No power or log-out buttons on the lock screen. | lock_extras |

### 1.19 Color Profiles

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.19.1 | Device list (colord) | NO | colord is not installed. | color_profiles |
| 1.19.2 | Add an ICC profile | NO | colord is not installed. | color_profiles |
| 1.19.3 | Remove a profile | NO | colord is not installed. | color_profiles |
| 1.19.4 | Make a profile default | NO | colord is not installed. | color_profiles |
| 1.19.5 | Profile details | NO | colord is not installed. | color_profiles |
| 1.19.6 | Works only with colord running | NO | colord is not installed. | color_profiles |

### 1.20 Printers

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.20.1 | Add a printer (USB and network auto-detect) | YES | 'printers' / 'add a printer' -> Desk._system_shortcut (_SYS) -> syspanels.printers (lpinfo ipp/ipps/dnssd/usb) -> Add -> 'add printer URI' -> syspanels.add_printer (lpadmin -m everywhere, made default). |  |
| 1.20.2 | Choose a driver | PARTIAL | Driverless only (-m everywhere); printers that need a PPD cannot be added from the panel. | printer_driver |
| 1.20.3 | Set the default printer | PARTIAL | New printers become default; the panel's 'Make default' button says 'make X the default printer', which no shortcut handles, so it goes to the model (run_command lpadmin, asked). | printer_buttons |
| 1.20.4 | Print a test page | PARTIAL | The 'Test page' button's phrase is likewise left to the model. | printer_buttons |
| 1.20.5 | View and cancel jobs | NO | No job list. | print_jobs |
| 1.20.6 | Share a printer | NO | Not available. | print_share |

### 1.21 Network

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.21.1 | Tray icon showing connection state | YES | Network chip: Wi-Fi / wired / offline icon (desk.js status, Desk.push_status 'net'). |  |
| 1.21.2 | Choose a Wi-Fi network and enter a password | YES | Network chip -> Desk.network_panel (iwctl scan) -> Connect -> password form -> Desk.wifi_join / _wifi_connect; or say 'connect to CoffeeShop, the password is ...' -> tools.wifi_connect. |  |
| 1.21.3 | Forget a network | NO | No forget action. | wifi_forget |
| 1.21.4 | Wired: DHCP or static IPv4/IPv6, DNS | PARTIAL | Wired DHCP is automatic (install.sh writes eth0 inet dhcp); no static address or DNS settings. | static_ip |
| 1.21.5 | VPN import | NO | No VPN tools installed. | vpn |
| 1.21.6 | Hotspot | NO | Not available. | hotspot |
| 1.21.7 | Airplane mode / disable networking | PARTIAL | 'turn the internet off' -> intent._policy -> change_setting internet=no -> system.apply_firewall blocks outgoing traffic; radios stay on. | airplane |
| 1.21.8 | Hidden network | NO | wifi_connect uses `iwctl station connect` (no connect-hidden). | wifi_hidden |
| 1.21.9 | Connection information (IP, speed, MAC) | PARTIAL | 'show my network in one panel' -> tools.system_panel shows interface and IPv4; no speed or MAC. | net_info |
| 1.21.10 | Metered connection flag | NO | Not available. | metered |

### 1.22 Bluetooth

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.22.1 | Turn the adapter on or off | YES | Bluetooth panel toggle -> 'bluetooth on/off' -> syspanels.bt_action. |  |
| 1.22.2 | Make the computer discoverable | NO | Not available. | bt_extra |
| 1.22.3 | Scan and pair (PIN confirmation) | PARTIAL | Search -> Pair -> 'bluetooth connect MAC' -> syspanels.bt_action (trust, pair, connect); no PIN/passkey agent, so devices that ask for confirmation fail. | bt_pin |
| 1.22.4 | Connect or disconnect devices | YES | Connect / Disconnect buttons -> syspanels.bt_action; audio goes through PipeWire (wireplumber). |  |
| 1.22.5 | Send a file | NO | No OBEX. | bt_extra |
| 1.22.6 | Trust or remove a device | YES | Trusted automatically on connect; Forget -> 'bluetooth forget MAC' -> bluetoothctl remove. |  |

### 1.23 Sound

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.23.1 | Scroll on the volume icon | NO | Not available. | volume_scroll |
| 1.23.2 | Click to mute | YES | Sound chip -> Desk.sound_panel -> mute button; or say 'mute' (intent._device). |  |
| 1.23.3 | Output volume slider | PARTIAL | Preset buttons 25/50/75/100% and words ('volume 40%', 'louder'); no slider. | volume_slider |
| 1.23.4 | Microphone slider and mute | PROGRAM | Sound panel 'More sound settings' -> 'open pavucontrol' -> Input Devices tab. |  |
| 1.23.5 | Choose output and input device | PROGRAM | pavucontrol (installed). |  |
| 1.23.6 | Media player (MPRIS) controls | PARTIAL | The 'Now playing' window controls what LLM OS plays (play_media / media_control -> Desk.media_action, mpv IPC); Firefox media is not controllable. | mpris |
| 1.23.7 | Volume keys with on-screen notification | PARTIAL | rc.xml XF86AudioRaiseVolume/LowerVolume/Mute -> `llmos volume +5/-5/toggle` -> devices.volume; no on-screen indicator; MicMute not bound. | osd |
| 1.23.8 | Volume step and maximum above 100% | NO | Fixed 5% keys / 10% words, max 100% (devices.volume). | volume_cfg |
| 1.23.9 | pavucontrol Playback tab | PROGRAM | pavucontrol. |  |
| 1.23.10 | pavucontrol Recording tab | PROGRAM | pavucontrol. |  |
| 1.23.11 | pavucontrol Output Devices tab | PROGRAM | pavucontrol. |  |
| 1.23.12 | pavucontrol Input Devices tab | PROGRAM | pavucontrol. |  |
| 1.23.13 | pavucontrol Configuration tab | PROGRAM | pavucontrol. |  |
| 1.23.14 | Event sounds toggle | NO | Not available. | event_sounds |

### 1.24 Date and Time

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.24.1 | Date/time GUI, time zone, NTP | PARTIAL | Time zone chosen in the first-run wizard (Desk.wizard_step 'timezone' -> system.set_timezone) and shown in Settings; afterwards no button or phrase (change_setting has a 'timezone' branch but it is not in the tool's enum); NTP is off (install.sh removes chronyd). | timezone |
| 1.24.2 | Clock: time zone used for display | PARTIAL | The bar clock uses the system time zone; the Clock app adds world cities (apps/clock.html). | timezone |
| 1.24.3 | Clock layout: analog, binary, digital, fuzzy, LCD | NO | Digital only (desk.js clock). | clock_fmt |
| 1.24.4 | Tooltip format | NO | Fixed tooltip 'Clock & calendar'. | clock_fmt |
| 1.24.5 | Date then time / time only ... | NO | Fixed: time then short date. | clock_fmt |
| 1.24.6 | Custom strftime formats and fonts | NO | Not available. | clock_fmt |
| 1.24.7 | Show seconds | NO | Not available. | clock_fmt |
| 1.24.8 | 24-hour or 12-hour | PARTIAL | Follows the interface language's locale (toLocaleTimeString(lang)); no setting. | clock_fmt |
| 1.24.9 | Click shows a month calendar | PARTIAL | Clicking the clock opens the Clock app (world clock); the Calendar app opens with 'open the calendar'. | clock_calendar |
| 1.24.10 | Alarm options | YES | 'every weekday at 7 remind me to wake up' / 'set a timer for 10 minutes' -> intent._schedule / _timer -> tools.schedule_task (chime and card when due). |  |

### 1.25 Users

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.25.1 | Users and groups GUI | NO | One owner by design (root home). | users |
| 1.25.2 | Add/delete user, password, picture, admin, autologin | PARTIAL | Autologin is how it works without a passphrase; a passphrase can be set ('set a passphrase' -> tools.set_passphrase) but not changed (vault.change_passphrase is never called); no other users. | passphrase_change |

### 1.26 Other Settings Manager entries

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 1.26.1 | Application Finder preferences | NO | No preferences for the program list. | app_menu_cfg |
| 1.26.2 | Application Finder custom actions (#, !, !w, URLs) | YES | The request bar: '!df -h' runs in a terminal (Desk.shortcut), 'look up X' searches the web (intent._WEB_SEARCH -> tools.browse), a URL opens Firefox (intent._open_url). |  |
| 1.26.3 | Clear the history | YES | 'forget this conversation' / 'new topic' (Desk.shortcut -> conversation new_topic); Conversations panel Forget. |  |
| 1.26.4 | xfce4-terminal preferences | PARTIAL | foot has no preferences window; see 2.3. | terminal_prefs |

### 2.1 Firefox

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.1.1 | Browse the web | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). |  |
| 2.1.2 | Tabs, windows, private windows | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). |  |
| 2.1.3 | Bookmarks, history, downloads | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). |  |
| 2.1.4 | Saved passwords, sync account | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). |  |
| 2.1.5 | Extensions | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). |  |
| 2.1.6 | Built-in PDF viewer | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). PDFs open in it: tools.open_file maps .pdf to firefox. |  |
| 2.1.7 | Play HTML5 audio and video | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). PipeWire runs (Desk._start_sound). |  |
| 2.1.8 | Print, print to PDF | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). CUPS printers from the Printers panel. |  |
| 2.1.9 | Reader view, page screenshots | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). |  |
| 2.1.10 | Open local files | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). |  |
| 2.1.11 | Download into ~/Downloads | PROGRAM | Firefox in PKGS; 'open the browser' / 'go to youtube' -> intent._everyday -> tools.browse -> programs.find('browser'). HOME=/root via config.personal_env. |  |

### 2.2 Thunar (with volman, tumbler, gvfs)

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.2.1 | Browse folders: icon, list, compact views | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. The desk's own list: 'show my documents' -> tools.show_files. |  |
| 2.2.2 | Tabs and split view | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.3 | Copy, cut, paste, duplicate, link | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. By words: 'copy all photos from Downloads to Pictures' -> tools.move_files. |  |
| 2.2.4 | Rename, bulk rename | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. (Bulk Rename tool). By words: 'rename X to Y' -> tools.rename_file. |  |
| 2.2.5 | New folder, empty file, templates | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. By words: 'make a folder called Taxes in Documents' -> tools.make_folder. |  |
| 2.2.6 | Trash, permanent delete, restore, empty | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. The desk has its own trash (~/.Trash: delete_file/restore_file/empty_trash), separate from Thunar's (see 3.11). |  |
| 2.2.7 | Search by name (Ctrl+F) | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. By words: 'find my tax pdf' -> tools.find_files. |  |
| 2.2.8 | Location bar, path bar | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.9 | Bookmarks in the side pane | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.10 | Show hidden files | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. (the desk's file windows always hide dotfiles). |  |
| 2.2.11 | Select by pattern, select all, invert | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.12 | Undo and redo of file operations | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. The desk: 'undo' -> tools.undo (moves, trash, new folder). |  |
| 2.2.13 | Thumbnails (images, video, PDF) | PARTIAL | tumbler is installed; ffmpegthumbnailer is not in PKGS, so no video thumbnails (PDF: verify). | thumbs |
| 2.2.14 | Image preview pane | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.15 | Properties dialog (permissions, open with, EXIF...) | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.16 | Open With and set default | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. (LLM OS's own opening ignores it: 1.13). |  |
| 2.2.17 | Custom actions: Open Terminal Here | PARTIAL | Thunar's action calls exo's TerminalEmulator, which may not know foot (verify); no desk phrase for 'a terminal in this folder'. | term_here |
| 2.2.18 | Set as wallpaper | NO | No xfdesktop plugin; the desk cannot use a local picture (1.5). | wall_local |
| 2.2.19 | Mount, unmount, eject in side pane, usage bar | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. Also the desk's Drives panel (syspanels.drives: Open / Eject). |  |
| 2.2.20 | Auto-mount on hotplug (volman) | PARTIAL | thunar-volman not installed; the desk announces the drive (Desk._poll_drives) and mounts on Open. | automount |
| 2.2.21 | Recent, File System, Home, Desktop, Trash shortcuts | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.22 | Zoom icons | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.23 | Sort by name/size/type/date | PROGRAM | Thunar (with gvfs, udisks2, tumbler) via 'open files'. |  |
| 2.2.24 | Network browsing (SMB/SFTP/MTP) | NO | No gvfs backends. | netshares |
| 2.2.25 | Compress or extract | PARTIAL | Xarchiver and 7zip are installed; 'open the file x.zip' launches Xarchiver (tools.open_file); no right-click Extract here (no thunar-archive-plugin). | archive_menu |

### 2.3 Terminal (foot instead of xfce4-terminal)

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.3.1 | Shell sessions in tabs and windows | PARTIAL | Windows: Super+Return, 'open a terminal' (intent._TERMINAL), '!command'; foot has no tabs. | term_tabs |
| 2.3.2 | Split panes | NO | Not in foot (nor in xfce4-terminal 1.2). | term_tabs |
| 2.3.3 | Copy and paste | PROGRAM | foot Ctrl+Shift+C / Ctrl+Shift+V, primary selection. |  |
| 2.3.4 | Find in scrollback | PROGRAM | foot Ctrl+Shift+R. |  |
| 2.3.5 | Zoom font, fullscreen | PROGRAM | foot Ctrl+= / Ctrl+-; fullscreen Super+F (rc.xml). |  |
| 2.3.6 | Drop-down (Quake) mode | NO | Not available. | term_dropdown |
| 2.3.7 | Tab title and colour | NO | No tabs. | term_tabs |
| 2.3.8 | Preferences: General | PARTIAL | foot.ini only (no window); the model could write ~/.config/foot/foot.ini with write_file. | terminal_prefs |
| 2.3.9 | Preferences: Appearance | PARTIAL | foot.ini only. | terminal_prefs |
| 2.3.10 | Preferences: Colors | PARTIAL | foot.ini only; the desk theme does not reach the terminal. | terminal_prefs |
| 2.3.11 | Preferences: Compatibility | PARTIAL | foot.ini only. | terminal_prefs |
| 2.3.12 | Preferences: Advanced | PARTIAL | foot.ini only. | terminal_prefs |
| 2.3.13 | Preferences: Shortcuts | PARTIAL | foot.ini [key-bindings] only. | terminal_prefs |
| 2.3.14 | Clickable URLs and email addresses | PROGRAM | foot URL mode (Ctrl+Shift+O). |  |
| 2.3.15 | Profiles | NO | Not available. | terminal_prefs |

### 2.4 Application Finder

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.4.1 | Run box with autocomplete | YES | Ctrl+L to the bar; 'open mousepad' (intent._apps -> programs.find -> tools.open_app); '!cmd' in a terminal; Up/Down recall earlier requests (desk.js). |  |
| 2.4.2 | Full mode: categories, search, launch | YES | Apps chip / 'show my apps' -> Desk.show_apps lists every installed program (programs.installed) as a button. |  |
| 2.4.3 | Custom actions (man, terminal, web search, URL) | YES | See 1.26: 'look up X', '!cmd', URLs. |  |
| 2.4.4 | Right-click: favourites, edit, hide | NO | No favourites or hiding. | app_menu_cfg |

### 2.5 xfce4-panel default layout and plugins

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.5.1 | Top panel: menu, window buttons, workspace switcher, tray, power, clock, actions | PARTIAL | The bar (desk.js status): apps chip, model, network, sound, battery, power chips and the clock; no window buttons (clean layout), workspace switcher or tray. | panel_items |
| 2.5.2 | Bottom dock: show desktop, launchers, directory menu | PARTIAL | The dock (desk.js dock) shows minimized desk windows and running programs (close only); no launchers. | dock_pins |
| 2.5.3 | Panel right-click menu | NO | Not available. | panel_items |
| 2.5.4 | Plugins available with no extra packages | PARTIAL | See the plugins below. | panel_items |
| 2.5.5 | Action Buttons | PARTIAL | Power chip -> Desk.power_panel: Lock (with vault), Sleep, Restart, Shut down; no log out, switch user, hibernate. | power_actions |
| 2.5.6 | Applications Menu | YES | Apps chip / Windows-layout start button (desk.js startMenu) / 'show my apps'. |  |
| 2.5.7 | Clock | YES | desk.js clock() in the bar. |  |
| 2.5.8 | Directory Menu | YES | 'show my documents' / 'open my downloads folder' -> intent._OPEN_FOLDER -> tools.show_files. |  |
| 2.5.9 | Launcher | PARTIAL | No pinned launchers; the mac layout dock has fixed Settings / Files / Lists buttons. | dock_pins |
| 2.5.10 | Notification Area (systray) | NO | No StatusNotifier host. | systray |
| 2.5.11 | Separator | NO | Not applicable. | panel_items |
| 2.5.12 | Show Desktop | NO | Not available. | show_desktop |
| 2.5.13 | Window Buttons (tasklist) | PARTIAL | Windows layout lists the desk's own windows in the dock; running programs show as dock chips that can only be closed (Desk.handle 'app.focus' does nothing). | dock_focus |
| 2.5.14 | Window Menu (list of all windows) | PARTIAL | Alt-Tab list (rc.xml windowSwitcher) and 'switch to the browser' (Desk._window_shortcut -> wm.act focus). | dock_focus |
| 2.5.15 | Workspace Switcher | NO | One workspace. | workspaces |
| 2.5.16 | Power Manager plugin | PARTIAL | Battery chip and Power panel; brightness by words and keys only. | brightness_ui |
| 2.5.17 | Not available without extras (Whisker, volume, bell, screenshooter, xkb, CPU, load, network, weather, clipman, places, mailwatch, sensors) | PARTIAL | Present: volume chip, screenshot, keyboard layout panel, task manager and system panel (CPU/load), network chip, weather and mail by asking; missing: clipboard history, layout indicator, bell, sensors. | clipboard_hist |

### 2.6 xfdesktop

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.6.1 | Wallpaper per monitor and per workspace | NO | One wallpaper. | wall_multi |
| 2.6.2 | Desktop icons for files, launchers, volumes | NO | No desktop icons. | desk_icons |
| 2.6.3 | Right-click root menu | NO | Suppressed (desk.py run: context-menu). | desk_menu |
| 2.6.4 | Middle-click window list | NO | Not available. | window_list |
| 2.6.5 | Scroll the wheel to switch workspace | NO | One workspace. | workspaces |
| 2.6.6 | Drag files to and from the desktop | NO | The desk page takes no drops. | desk_dnd |
| 2.6.7 | Next background / slideshow | NO | Not available. | wall_slideshow |

### 2.8 xfce4-session

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.8.1 | Log out dialog (log out, restart, shut down, suspend, hibernate, hybrid, switch user, save session) | PARTIAL | Power panel: Lock, Sleep, Restart, Shut down (Desk.power_panel); 'restart' / 'shut down' / 'go to sleep' by words; no log out, hybrid sleep, switch user or session saving. | power_actions |
| 2.8.2 | Autostart applications | NO | Not available. | autostart |
| 2.8.3 | Session save and restore | NO | Not available. | session_save |
| 2.8.4 | xflock4 lock helper | YES | 'lock' -> Desk.lock; lock chip (status bar) when a vault exists. |  |

### 2.11 LightDM + GTK greeter

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.11.1 | Choose a user or type a username | NO | One owner. | users |
| 2.11.2 | Password entry | YES | Passphrase on the lock screen at start when a vault exists (Desk.boot_screen -> lock screen -> Desk.unlock). |  |
| 2.11.3 | Session chooser | NO | One session. | compat |
| 2.11.4 | Indicators: clock, host name, power menu | NO | Lock screen has none. | lock_extras |
| 2.11.5 | Accessibility menu (large font, contrast, OSK) | NO | Not on the lock screen. | lock_extras |
| 2.11.6 | Keyboard layout indicator | NO | Not shown. | lock_extras |
| 2.11.7 | Greeter background and theme | YES | The lock screen uses the desk theme (Desk.theme_payload applies to every screen). |  |
| 2.11.8 | Autologin | YES | Without a passphrase the desk opens directly (Desk.boot_screen); with one, the passphrase is asked. |  |
| 2.11.9 | Switch user | NO | One owner. | users |

### 2.11b xfce-wayland variant (greetd + gtkgreet + labwc)

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.11b.1 | gtkgreet login | YES | Equivalent: the lock screen passphrase (vault). |  |
| 2.11b.2 | labwc as compositor with panel and desktop | YES | LLM OS runs labwc with the desk on top (usr/libexec/llmos-desk: seatd-launch labwc -s 'llmos desk-app'). |  |
| 2.11b.3 | Many xfwm4 settings do not apply | YES | Informational: the same is true for LLM OS (labwc), reflected in 1.2/1.3. |  |
| 2.11b.4 | Closest stock analogue to LLM OS | YES | Informational. |  |

### 2.12 Supporting services

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 2.12.1 | polkit-elogind prompts | YES | Not needed: the desk session runs as the owner (root), so mounting and power need no prompt. |  |
| 2.12.2 | elogind: suspend and shutdown without root | YES | syspanels.sleep writes /sys/power/state; Desk.shutdown runs poweroff/reboot. |  |
| 2.12.3 | gvfs: trash, mounts, recent | YES | gvfs in PKGS (for Thunar). |  |
| 2.12.4 | eudev: hotplug | YES | eudev/udev-init-scripts in PKGS; udev services added (install.sh). |  |
| 2.12.5 | font-dejavu | YES | Inter, Noto (incl. CJK, Arabic, Hebrew, Devanagari, Thai, emoji), JetBrains Mono, Terminus. |  |
| 2.12.6 | mesa-dri-gallium | YES | mesa-dri-gallium, mesa-egl, mesa-gles, mesa-gbm; software rendering in VMs (llmos-desk). |  |
| 2.12.7 | libinput | YES | labwc uses libinput; settings via Desk.apply_input. |  |

### 3.1 Right-click desktop menu

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.1.1 | Open in New Window | NO | No desk menu. | desk_menu |
| 3.1.2 | Create Launcher | NO | No desk menu. | desk_menu |
| 3.1.3 | Create URL Link | NO | No desk menu. | desk_menu |
| 3.1.4 | Create Folder | PARTIAL | 'make a folder called X' (intent._MAKE_FOLDER -> tools.make_folder); no menu. | desk_menu |
| 3.1.5 | Create Document / Empty File | PARTIAL | By asking ('make an empty file notes.txt in Documents' -> tools.write_file); no templates or menu. | desk_menu |
| 3.1.6 | Open Terminal Here | PARTIAL | 'open a terminal' opens in the home folder. | term_here |
| 3.1.7 | Paste | NO | No desk menu. | desk_menu |
| 3.1.8 | Arrange Desktop Icons | NO | No desktop icons. | desk_icons |
| 3.1.9 | Next Background | NO | No slideshow. | wall_slideshow |
| 3.1.10 | Desktop Settings | YES | 'settings' -> Desk.open_panel('settings') (looks, background, size). |  |
| 3.1.11 | Properties | NO | No desk menu. | desk_menu |
| 3.1.12 | Applications submenu | YES | Apps chip / 'show my apps'. |  |
| 3.1.13 | Right-click a desktop icon: open, open with, cut, copy, rename, trash, delete, properties | PARTIAL | File windows have Open and Delete buttons (tools.show_files); rename/move by words; no cut/copy/open-with. | file_window_actions |
| 3.1.14 | Right-click a volume icon: mount, unmount, eject | YES | Drives panel Open / Eject (syspanels.drives, syspanels.mount, syspanels.eject). |  |
| 3.1.15 | Middle-click window list with workspaces | NO | Not available. | window_list |

### 3.2 Drag and drop

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.2.1 | Between Thunar windows and tabs | PROGRAM | Thunar. |  |
| 3.2.2 | Modifier keys while dragging (copy/move/link/ask) | PROGRAM | Thunar. |  |
| 3.2.3 | To and from the desktop | NO | The desk takes no drops. | desk_dnd |
| 3.2.4 | Onto the Trash | PROGRAM | Thunar side pane Trash. |  |
| 3.2.5 | Onto a panel launcher | NO | No launchers. | dock_pins |
| 3.2.6 | Into the terminal (quoted path) | PROGRAM | foot accepts dropped files (verify). |  |
| 3.2.7 | Into a Firefox upload field | PROGRAM | Wayland drag and drop between programs (labwc). |  |
| 3.2.8 | Image onto the Desktop settings | NO | No local wallpapers. | wall_local |
| 3.2.9 | Theme archive into Appearance | NO | No theme install. | theme_install |
| 3.2.10 | Window in the pager to another workspace | NO | No pager. | workspaces |
| 3.2.11 | .desktop file onto the panel | NO | No launchers. | dock_pins |
| 3.2.12 | Text between applications | PROGRAM | Wayland drag and drop (labwc). |  |
| 3.2.13 | Tab out to a new window | PROGRAM | Firefox and Thunar tabs. |  |

### 3.3 File management essentials

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.3.1 | Copy, cut, paste with progress (pause, cancel) | PROGRAM | Thunar. By words: tools.move_files (no progress). |  |
| 3.3.2 | Conflict dialog | PROGRAM | Thunar (tools.move_files skips files that already exist). |  |
| 3.3.3 | Rename (F2), name without extension selected | YES | 'rename report.txt to report-final.txt' -> intent._RENAME -> tools.rename_file (keeps the extension unless a new one is given); F2 in Thunar. |  |
| 3.3.4 | Bulk rename | PROGRAM | Thunar Bulk Rename. |  |
| 3.3.5 | Trash, restore, empty, delete permanently | YES | 'delete the file X' -> tools.delete_file (~/.Trash, undoable); 'restore X from the trash' -> restore_file; 'empty the trash' -> empty_trash; Trash window 'Delete for good'. |  |
| 3.3.6 | Search by filename, recursive | YES | 'find my resume' -> intent._FIND_FILE -> tools.find_files (whole home folder). |  |
| 3.3.7 | File contents not searched | PARTIAL | Same as stock XFCE: names only; the model could run grep via run_command. | content_search |
| 3.3.8 | Thumbnails for images, video, PDF | PARTIAL | See 2.2. | thumbs |
| 3.3.9 | USB drive: auto-mount, side pane, desktop, eject, usage bar | YES | Plug-in toast and Drives panel (Desk._poll_drives, syspanels.drives: Open/Eject; eject syncs, unmounts and powers off); Thunar side pane with usage bar. |  |
| 3.3.10 | Permissions and ownership | PROGRAM | Thunar Properties > Permissions; by words via run_command ('make this script executable'). |  |
| 3.3.11 | Create a symlink | PROGRAM | Thunar Make Link. |  |
| 3.3.12 | Open as root | YES | Not needed: the owner's session already runs as root. |  |
| 3.3.13 | Show hidden files (Ctrl+H) | PROGRAM | Thunar. |  |
| 3.3.14 | Hidden-file preference per view | PROGRAM | Thunar. |  |
| 3.3.15 | Open a terminal in the current folder | PARTIAL | See 2.2. | term_here |
| 3.3.16 | Recent files | PROGRAM | Thunar Recent (gvfs); the desk: 'open what I just downloaded' -> tools.open_latest. |  |
| 3.3.17 | Bookmarks | PROGRAM | Thunar. |  |
| 3.3.18 | Open With another application | PROGRAM | Thunar. |  |
| 3.3.19 | Set the default app for a type | PROGRAM | Thunar (not used by the desk's own opening: 1.13). |  |
| 3.3.20 | Highlight colours | PROGRAM | Thunar 4.20. |  |
| 3.3.21 | Emblems | PROGRAM | Thunar. |  |

### 3.4 Keyboard shortcuts (xfwm4 defaults)

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.4.1 | Alt+Tab / Shift+Alt+Tab | PARTIAL | Alt+Tab -> NextWindow (rc.xml); Shift+Alt+Tab is not bound. | alttab |
| 3.4.2 | Super+Tab: same application | PARTIAL | Bound to NextWindow (all windows). | alttab |
| 3.4.3 | Alt+F4 close | YES | rc.xml A-F4 (also Super+Q); Esc / Ctrl+W close desk windows (desk.js). |  |
| 3.4.4 | Alt+F6 stick | NO | One workspace. | workspaces |
| 3.4.5 | Alt+F7 move with keyboard | NO | Not bound. | kb_move |
| 3.4.6 | Alt+F8 resize with keyboard | NO | Not bound. | kb_move |
| 3.4.7 | Alt+F9 minimize | PARTIAL | Super+Down / Super+Escape (rc.xml Iconify); 'minimize the browser' by words. | hotkeys_wm |
| 3.4.8 | Alt+F10 maximize | PARTIAL | Super+Up (ToggleMaximize); 'maximize firefox'. | hotkeys_wm |
| 3.4.9 | Alt+F11 fullscreen | PARTIAL | Super+F (ToggleFullscreen). | hotkeys_wm |
| 3.4.10 | Alt+F12 always on top | PARTIAL | Title-bar right-click menu (labwc default client menu; verify); no key. | hotkeys_wm |
| 3.4.11 | Alt+Space window menu | PARTIAL | Right-click the title bar (labwc default); no key. | hotkeys_wm |
| 3.4.12 | Ctrl+Alt+D show desktop | NO | Not available. | show_desktop |
| 3.4.13 | Ctrl+Alt+arrows switch workspace | NO | One workspace. | workspaces |
| 3.4.14 | Ctrl+F1..F12 go to workspace | NO | One workspace. | workspaces |
| 3.4.15 | Move window to previous/next workspace | NO | One workspace. | workspaces |
| 3.4.16 | Alt+Insert add workspace | NO | One workspace. | workspaces |
| 3.4.17 | Alt+Delete remove workspace | NO | One workspace. | workspaces |
| 3.4.18 | Super+arrows tile | PARTIAL | Super+Left/Right tile halves (SnapToEdge); Super+Up maximizes and Super+Down minimizes instead of tiling. | tile_words |
| 3.4.19 | Super+keypad corners: quarter tiling | NO | Not bound. | tile_words |
| 3.4.20 | Alt+Shift+PageDown lower window | NO | Not bound. | kb_move |
| 3.4.21 | Alt+drag move | YES | labwc default mouse bindings (rc.xml <mouse><default/>; verify). |  |
| 3.4.22 | Alt+right-drag resize | YES | labwc default mouse bindings (verify). |  |
| 3.4.23 | Alt+scroll zoom | NO | No magnifier. | magnifier |
| 3.4.24 | Application shortcuts from 1.8 | PARTIAL | See 1.8. | hotkeys_std |

### 3.5 Window management

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.5.1 | Alt-Tab across workspaces, incl. minimized | PARTIAL | One workspace; Alt-Tab OSD list (rc.xml). | alttab |
| 3.5.2 | Snap to edges and windows; edge resistance | PARTIAL | labwc defaults, not adjustable (verify). | snapping |
| 3.5.3 | Edge tiling by dragging (half, quarter, top = maximize) | YES | labwc default snapping: halves and top-maximize (verify; quarters depend on the labwc version). |  |
| 3.5.4 | Maximize by double-clicking the title bar | YES | labwc default; desk windows too (desk.js openWindow dblclick). |  |
| 3.5.5 | Maximize horizontally/vertically with middle/right click | YES | labwc default Maximize-button bindings (verify). |  |
| 3.5.6 | Minimize; restore from the tasklist | PARTIAL | Minimize: button, Super+Down, 'minimize the browser'; restore: Alt-Tab or 'switch to the browser'; dock chips do not restore programs (desk windows restore from the dock). | dock_focus |
| 3.5.7 | Shade (roll up) | PARTIAL | Not bound in rc.xml; labwc has ToggleShade (verify the default client menu). | wm_misc |
| 3.5.8 | Always on top / below | PARTIAL | Title-bar menu 'Always on Top' (labwc default; verify); no always-below. | hotkeys_wm |
| 3.5.9 | Sticky (all workspaces) | NO | One workspace. | workspaces |
| 3.5.10 | Move to workspace from the window menu | NO | One workspace. | workspaces |
| 3.5.11 | Fullscreen | YES | Super+F (rc.xml); programs' own F11. |  |
| 3.5.12 | Window opacity | NO | Not available. | opacity |
| 3.5.13 | Shadows | PARTIAL | Always on (rc.xml dropShadows). | shadows |
| 3.5.14 | Multiple monitors: per-monitor panels, primary, move a window | PARTIAL | Windows can be dragged to the other screen; the desk and its bar stay on one output; no primary choice. | display_arrange |
| 3.5.15 | Session restore of windows | NO | Not available. | session_save |
| 3.5.16 | Kill an unresponsive window | YES | 'Firefox is frozen' / 'force quit the terminal' -> Desk._window_shortcut -> wm.force_quit (asks); task manager End. |  |

### 3.6 Multiple workspaces

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.6.1 | 4 by default | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.2 | Add, remove, rename | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.3 | Pager in the panel | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.4 | Keyboard switching | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.5 | Scroll-wheel switching | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.6 | Wrap-around | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.7 | Per-workspace wallpaper | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.8 | Move windows between workspaces | NO | One workspace (rc.xml has no <desktops>). | workspaces |
| 3.6.9 | Per-workspace margins | NO | One workspace (rc.xml has no <desktops>). | workspaces |

### 3.7 Screenshots

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.7.1 | Stock: no screenshot tool, Print does nothing | YES | 'take a screenshot' -> intent._SHOT -> tools.screenshot (grim) saves to ~/Pictures and shows it. Print is still unbound (1.8). |  |
| 3.7.2 | Full screen, window, region, delay, cursor, save, clipboard, open with, upload | PARTIAL | Full screen and save only; no window/region (no slurp), delay, clipboard (no wl-clipboard) or upload. | screenshot_more |
| 3.7.3 | Firefox's page screenshot | PROGRAM | Firefox. |  |

### 3.8 Lock screen

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.8.1 | Ctrl+Alt+L, Action Buttons > Lock, xflock4 | PARTIAL | 'lock' and the lock chip / Power panel Lock (vault); no key. | lock_key |
| 3.8.2 | Automatic lock after delay | YES | 'lock after 15 minutes' -> change_setting autolock -> Desk._poll_autolock (with a vault). |  |
| 3.8.3 | Lock on suspend | NO | syspanels.sleep does not lock. | lock_on_sleep |
| 3.8.4 | Lock on lid close | NO | No lid handling. | lid |
| 3.8.5 | Unlock with the user's password | YES | Passphrase -> Desk.unlock -> vault.unlock. |  |
| 3.8.6 | Switch user from the lock screen | NO | One owner. | users |
| 3.8.7 | Screensaver themes while locked | PARTIAL | The lock screen shows the animated orb and halo (desk.js tick); no screensaver choice. | screensaver |

### 3.9 Session and power actions

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.9.1 | Log out | NO | No log out (one owner, the desk is the session). | power_actions |
| 3.9.2 | Restart | YES | 'restart' (Desk.shortcut -> Desk.shutdown('reboot')), Power panel Restart, 'restart the computer' -> intent._policy -> tools.system_power. |  |
| 3.9.3 | Shut down | YES | 'shut down' / Power panel / tools.system_power; the vault is locked first (Desk.shutdown). |  |
| 3.9.4 | Suspend | YES | 'sleep' / 'go to sleep' / Power panel Sleep -> Desk._system_shortcut -> syspanels.sleep. |  |
| 3.9.5 | Hibernate | PARTIAL | 'hibernate' suspends to RAM instead. | hibernate |
| 3.9.6 | Hybrid sleep | NO | Not available. | hibernate |
| 3.9.7 | Switch user | NO | One owner. | users |
| 3.9.8 | Confirmation dialog with 30 s countdown | PARTIAL | tools.system_power is DESTRUCTIVE (asked per autonomy); the Power-panel buttons and typed 'shut down' act at once. | power_confirm |
| 3.9.9 | 'Save session' checkbox | NO | No sessions. | session_save |
| 3.9.10 | Power button -> configured action | PARTIAL | acpid default only (1.10). | power_button |
| 3.9.11 | Lid close -> configured action | NO | Not handled. | lid |
| 3.9.12 | Idle -> sleep timers | NO | Not handled. | idle_sleep |
| 3.9.13 | Critical battery -> action | NO | Not handled. | critical_battery |

### 3.10 Notifications

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.10.1 | Stock: no daemon, app notifications not shown | PARTIAL | Same for programs; LLM OS's own events show as toasts and the away card. | notify |
| 3.10.2 | Expected with notifyd: bubbles, actions, log, DND, per-app mute, OSD | PARTIAL | Toasts and away card for LLM OS only; no actions, DND or OSD. | notify |

### 3.11 Miscellaneous expected behaviours

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 3.11.1 | Clipboard plus primary selection | YES | Wayland clipboard and primary selection through labwc in programs. |  |
| 3.11.2 | No clipboard history | NO | Same as stock. | clipboard_hist |
| 3.11.3 | Input method (ibus/fcitx) | NO | Not installed. | ime |
| 3.11.4 | Layout switching via shortcut | NO | One layout at a time. | kb_multi |
| 3.11.5 | Brightness keys | YES | rc.xml -> `llmos brightness` -> devices.brightness. |  |
| 3.11.6 | Media and volume keys | PARTIAL | Volume and mute keys work (rc.xml -> `llmos volume`); play/pause/next keys are not bound. | media_keys |
| 3.11.7 | HiDPI scaling | PARTIAL | The desk scales itself (desk.py _display_scale); programs do not. | scale_programs |
| 3.11.8 | Night light / redshift | NO | Not installed. | night_light |
| 3.11.9 | Autostart programs on login | NO | Not available. | autostart |
| 3.11.10 | Open files and links in default apps (xdg-open) | PARTIAL | The desk opens files with its own map (tools.open_file) and links in Firefox; xdg-utils is not in PKGS, so programs rely on gio. | mime |
| 3.11.11 | Polkit authentication prompt | YES | Not needed (root session). |  |
| 3.11.12 | Trash location ~/.local/share/Trash | PARTIAL | The desk's trash is ~/.Trash (tools._trash) while Thunar uses ~/.local/share/Trash: two separate trashes. | trash_unify |

### 4.1 Lubuntu (LXQt) expectations

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 4.1.1 | Configuration Center | PARTIAL | Settings panel (Desk.panel_spec 'settings': Network, Sound, Displays, Keyboard and mouse, Bluetooth, Printers, Drives, Storage, Updates, Power, What's running, Apps, Conversations, About, plus looks and language); no date & time, users or shortcuts pages. | timezone |
| 4.1.2 | Apps (PCManFM-Qt, QTerminal, FeatherPad, LXImage, Screengrab, Archiver, qps, Qlipper, KCalc, VLC, LibreOffice, Discover, Calamares, Partition Manager, Skanlite, nm-tray, BlueDevil, notifier, notes, 2048) | PARTIAL | Equivalents: Thunar, foot, Mousepad, Ristretto, screenshot tool, Xarchiver, task manager, calculator app, mpv, AbiWord/Gnumeric, install by asking, installer (install_to_disk), network and Bluetooth panels, updates panel, notes/lists, games apps; missing clipboard history, scanner, partition manager, full LibreOffice. | apps_missing |
| 4.1.3 | Software updates via a GUI notifier | PARTIAL | 'updates' -> syspanels.updates_panel on request; no automatic check or notice. | update_notify |
| 4.1.4 | Install and remove software via a GUI store | PARTIAL | 'install X' -> tools.install_app (apk add); no remove tool and no browsable store. | app_remove |
| 4.1.5 | Network (Wi-Fi, VPN) | PARTIAL | Wi-Fi yes (network panel); no VPN. | vpn |
| 4.1.6 | Sound (volume plugin, pavucontrol) | YES | Sound chip, sound panel, pavucontrol. |  |
| 4.1.7 | Printing (CUPS, system-config-printer) | YES | Printers panel (syspanels.printers), driverless. |  |
| 4.1.8 | Partitioning and formatting disks | NO | Only the LLM OS installer partitions (installer.py); no formatting of sticks. | format_disk |
| 4.1.9 | Clipboard history | NO | Not available. | clipboard_hist |

### 4.2 Linux Mint XFCE expectations

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 4.2.1 | Whisker Menu (search, favourites, recent) | YES | Type in the bar ('open mousepad', programs.find) or the apps chip (Desk.show_apps); no favourites/recent list. |  |
| 4.2.2 | Network: nm-applet, VPN, hotspot, connections editor | PARTIAL | Wi-Fi only. | vpn |
| 4.2.3 | Bluetooth: Blueman (pair, send files, profiles) | PARTIAL | Pair/connect/forget (syspanels.bluetooth); no file sending; profiles via pavucontrol. | bt_extra |
| 4.2.4 | Sound: plugin + pavucontrol | YES | Sound chip/panel + pavucontrol. |  |
| 4.2.5 | Notifications with DND and log | NO | See 1.11. | dnd |
| 4.2.6 | Printers with automatic driver detection | PARTIAL | Driverless only. | printer_driver |
| 4.2.7 | Update Manager (levels, kernels, automatic, Flatpak) | PARTIAL | Updates panel (apk upgrade, syspanels.updates_apply; says when a restart is needed); no automatic updates. | update_notify |
| 4.2.8 | Software Manager (browse, install, remove, reviews) | PARTIAL | Install by asking (tools.install_app); no remove/browse. | app_remove |
| 4.2.9 | Software Sources | NO | Not available. | repos |
| 4.2.10 | Driver Manager | NO | Not available. | drivers |
| 4.2.11 | Timeshift snapshots | NO | Not available. | snapshots |
| 4.2.12 | Backup Tool | PARTIAL | 'back up my documents to the USB stick' -> intent._MOVE -> tools.move_files (copy); no restore or incremental backup, and 'documents' there means document-type files directly in the home folder, not ~/Documents (move_files keeps only files whose dirname is the source folder). | backup |
| 4.2.13 | Users and Groups | NO | One owner. | users |
| 4.2.14 | Login Window settings (background, autologin, guest) | PARTIAL | Lock screen follows the theme; autologin = no passphrase; no guest or own background. | lock_extras |
| 4.2.15 | Date and Time (time zone, NTP, 12/24h) | PARTIAL | See 1.24. | timezone |
| 4.2.16 | Languages and input methods (locale, formats, ibus/fcitx) | PARTIAL | 'put everything in French' -> intent._policy (_LANGUAGE) -> set_appearance language (interface, i18n.py); no region formats or input methods. | ime |
| 4.2.17 | Firewall (gufw) | PARTIAL | Internet allow/ask/off (change_setting internet -> system.apply_firewall, nftables) and Tor; no per-port rules. | firewall_rules |
| 4.2.18 | System Reports | PARTIAL | 'about this computer' (syspanels.about) and 'audit'; no crash reports. | sysreports |
| 4.2.19 | Disks: format, partition, bootable USB | NO | Not available. | format_disk |
| 4.2.20 | Disk Usage Analyzer | PARTIAL | 'storage' -> syspanels.storage (folder totals, trash, caches, models); no drill-down. | disk_usage |
| 4.2.21 | Welcome Screen | YES | First-run wizard (Desk.wizard_step) and 'what can you do' -> help panel. |  |
| 4.2.22 | Warpinator (LAN file sending) | NO | Not available. | lan_share |
| 4.2.23 | Web Apps manager | NO | Not available. | webapps |
| 4.2.24 | Apps (Xed, Xviewer, Xreader, Pix, Drawing, Celluloid, Rhythmbox, Hypnotix, LibreOffice, Thunderbird, Transmission, Simple Scan, Calculator, Calendar, Sticky Notes, Screenshot, Archive Manager, Mousepad, Ristretto, Parole, Catfish, Task Manager, Onboard, Orca, Redshift) | PARTIAL | Have: Mousepad, Ristretto, Firefox PDF, Sketch app, mpv, AbiWord/Gnumeric, mail tools, calculator/calendar/notes apps, screenshot, Xarchiver, task manager; missing: music library, IPTV, torrents, scanning, content search, on-screen keyboard, screen reader, night light. | apps_missing |
| 4.2.25 | Thunar archive plugin, media tags, shares | NO | Not installed. | archive_menu |
| 4.2.26 | Network share browsing (SMB, SFTP, MTP) | NO | Not available. | netshares |
| 4.2.27 | Mint panel plugins (Whisker, tasklist, systray, xkb, volume, bell, network, clock, power, user actions) | PARTIAL | Bar chips cover menu, network, volume, clock, power; no tray, layout indicator or bell; tasklist partial. | systray |
| 4.2.28 | Shortcuts: Super menu, Print, Super+L, Ctrl+Alt+T, Super+E | PARTIAL | None of these keys are bound (Super+Return opens a terminal). | hotkeys_std |
| 4.2.29 | Night light | NO | Not available. | night_light |
| 4.2.30 | Automatic maintenance (snapshot before updates, kernel cleanup) | NO | Not available. | snapshots |
| 4.2.31 | Mint-Y colour variants, themes | PARTIAL | Colour themes for the desk ('ocean theme', 'make everything teal': themes.PALETTES / themes.from_color); programs not themed. | gtk_dark |

### 5 Capability table: the 95 natural-language requests

| # | Item | Status | How (words / button) and code | Gap |
|---|---|---|---|---|
| 5.1 | Open an app: 'Open Firefox' | YES | intent._everyday (_OPEN_BROWSER) -> tools.browse; any program: intent._apps (_OPEN_APP) -> programs.find -> tools.open_app. |  |
| 5.2 | Search apps: 'What apps do I have for editing images?' | PARTIAL | The model has no list of installed programs (manage_apps 'list' returns only made apps); 'show my apps' shows them all. | app_search |
| 5.3 | Switch windows: 'Switch to the terminal' | YES | Desk._window_shortcut (_WIN focus) -> wm.act('focus'). |  |
| 5.4 | Close a window: 'Close the browser window' | PARTIAL | 'close the browser' works (wm.act close); with the word 'window' the _WIN regex does not match and the model has no window tool. | win_words |
| 5.5 | Maximize / minimize: 'Maximize this window' / 'Hide everything' | PARTIAL | 'maximize' and 'maximize firefox' work; 'this window' and 'everything' are rejected by wm.app_id. | win_words |
| 5.6 | Tile: 'Put Firefox on the left and Files on the right' | NO | Only Super+Left/Right by hand. | tile_words |
| 5.7 | Show the desktop | NO | 'show me the desktop' opens the ~/Desktop folder listing (intent._OPEN_FOLDER -> show_files) instead of revealing the desk. | show_desktop |
| 5.8 | Move this window to workspace 2 | NO | One workspace. | workspaces |
| 5.9 | Give me 6 workspaces and call the second one Work | NO | One workspace. | workspaces |
| 5.10 | Use this photo as my wallpaper | PARTIAL | Only a Wikimedia photo by subject (tools.set_wallpaper). | wall_local |
| 5.11 | Rotate my wallpapers every 10 minutes | NO | No slideshow. | wall_slideshow |
| 5.12 | Switch to a light theme | YES | intent._theme (_DARK/_MODE) -> set_appearance theme=light (desk; programs unchanged, see gtk_dark). |  |
| 5.13 | Use a different icon set | NO | Not available. | icon_theme |
| 5.14 | Make the text bigger | YES | intent._scale -> set_appearance scale (+20%, desk). |  |
| 5.15 | Everything is tiny, scale it up | PARTIAL | The model raises the desk's scale; programs stay small. | scale_programs |
| 5.16 | Set the screen to 1920x1080 | PARTIAL | Displays panel buttons work; the typed sentence has no route and the model has no display tool. | display_words |
| 5.17 | Rotate the monitor to portrait | NO | Not available. | rotate |
| 5.18 | Mirror my screen to the projector | PARTIAL | Only the bare word 'projector' opens the Displays panel (then Mirror, syspanels.arrange, exact only when resolutions match); the sentence goes to the model, which has no display tool. | display_words |
| 5.19 | Add a French keyboard and let me switch with Alt+Shift | PARTIAL | 'use a French keyboard' replaces the layout; no second layout or switch key. | kb_multi |
| 5.20 | Keys repeat too fast | PARTIAL | Only the panel's 'key repeat slower' phrase works; the sentence goes to the model, which has no input tool. | input_words |
| 5.21 | Make Super+B open the browser | NO | Not available. | custom_keys |
| 5.22 | Make the mouse faster | PARTIAL | 'mouse faster' (panel button) works; 'make the mouse faster' goes to the model, which has no input tool. | input_words |
| 5.23 | Swap the mouse buttons | PARTIAL | Panel toggle only ('left handed mouse on'). | input_words |
| 5.24 | Reverse scroll direction | PARTIAL | Panel toggle only, and for touchpads only. | input_words |
| 5.25 | Turn on tap to click | PARTIAL | Exact 'tap to click on' only. | input_words |
| 5.26 | Make the pointer bigger | NO | Not available. | cursor |
| 5.27 | Don't turn the screen off for an hour | PARTIAL | Nothing turns it off anyway; no setting exists. | idle_blank |
| 5.28 | Never sleep while plugged in | PARTIAL | Nothing sleeps by itself; no setting exists. | idle_sleep |
| 5.29 | Don't suspend when I close the lid | NO | No lid handling at all. | lid |
| 5.30 | Dim the screen to 40% | YES | 'brightness 40%' is instant (intent._device _BRIGHT); this wording goes to the model, which calls tools.set_brightness -> devices.brightness. |  |
| 5.31 | How much battery do I have? | YES | _BATTERY_Q -> Desk.shortcut instant reply from desk._battery. |  |
| 5.32 | Keep the screen on during my presentation | PARTIAL | No blanking exists; auto-lock can be turned off ('turn off auto-lock'). | idle_blank |
| 5.33 | Lock the screen | YES | _LOCK_WORDS -> Desk.lock. |  |
| 5.34 | Lock 5 minutes after the screen blanks | PARTIAL | 'lock after 5 minutes' works (intent._autolock -> change_setting autolock, vault needed); this sentence misses the regex and the model's change_setting call is refused by agent._ONLY_IF_ASKED (no 'lock' word in its list). | autolock_novault |
| 5.35 | Use a blank screensaver after 10 minutes | NO | No screensaver. | screensaver |
| 5.36 | Log me out | NO | No log out. | power_actions |
| 5.37 | Restart the computer / Shut down | YES | intent._policy (_POWER) -> tools.system_power; 'restart'/'shut down' -> Desk.shutdown. |  |
| 5.38 | Go to sleep | YES | Desk._system_shortcut -> syspanels.sleep. |  |
| 5.39 | Let someone else log in | NO | One owner. | users |
| 5.40 | Start the terminal every time I log in | NO | No autostart. | autostart |
| 5.41 | Make Firefox my default browser | PARTIAL | It already is the only browser; no setting. | default_apps |
| 5.42 | Always open PDFs in Firefox | PARTIAL | Already so (tools.open_file map); no per-type setting. | mime |
| 5.43 | Open my resume | YES | The model: tools.find_files then tools.open_file (.docx -> AbiWord, .pdf -> Firefox). |  |
| 5.44 | Find the spreadsheet I downloaded last week | PARTIAL | intent._FIND_FILE -> tools.find_files matches names only; no kind or date filter. | file_search_date |
| 5.45 | Copy all photos from Downloads to Pictures | YES | intent._everyday (_MOVE) -> tools.move_files. |  |
| 5.46 | Rename report.txt to report-final.txt | YES | intent._RENAME -> tools.rename_file. |  |
| 5.47 | Rename these to holiday-001, holiday-002... | PROGRAM | Thunar Bulk Rename. |  |
| 5.48 | Make a folder called Taxes in Documents | YES | intent._MAKE_FOLDER -> tools.make_folder. |  |
| 5.49 | Delete the old drafts | YES | The model: find_files + delete_file (to the trash, undoable). |  |
| 5.50 | Bring back the file I just deleted | YES | 'undo' -> tools.undo, or 'restore X from the trash' -> tools.restore_file. |  |
| 5.51 | Empty the trash | YES | intent._notes (_TRASH) -> tools.empty_trash. |  |
| 5.52 | Show hidden files in my home folder | PROGRAM | Thunar Ctrl+H (the desk's file windows hide them). |  |
| 5.53 | Make this script executable | YES | The model: run_command 'chmod +x' (CHANGE risk, follows autonomy). |  |
| 5.54 | Add Projects to my sidebar | PROGRAM | Thunar Ctrl+D. |  |
| 5.55 | Open a terminal in this folder | PARTIAL | Terminals open in the home folder. | term_here |
| 5.56 | What's on my USB stick? | PARTIAL | 'what's on my usb' and 'usb stick' open the Drives panel (_SYS drives -> syspanels.drives -> Open), but 'what's on my USB stick?' does not match the regex and the model has no drive tool. | eject_words |
| 5.57 | Eject the USB stick | PARTIAL | Eject button in the Drives panel; the typed sentence matches no shortcut and the model has no eject tool. | eject_words |
| 5.58 | How much disk space is left? | YES | 'storage' -> syspanels.storage; the sentence -> the model -> tools.system_panel (disk). |  |
| 5.59 | Show my photos as thumbnails | PROGRAM | Thunar icon view (tumbler). |  |
| 5.60 | Make this picture the wallpaper | PARTIAL | See 1.5. | wall_local |
| 5.61 | Auto-hide the taskbar / move the panel to the bottom | PARTIAL | 'windows style desk' puts the taskbar at the bottom; no auto-hide. | panel_autohide |
| 5.62 | Pin Terminal to the panel | NO | No pinning. | dock_pins |
| 5.63 | Show 24-hour time with seconds | NO | No clock settings. | clock_fmt |
| 5.64 | What day is the 14th next month? | YES | Answered by the model; Calendar app ('open the calendar', apps/calendar.html). |  |
| 5.65 | Set my time zone to Europe/London | PARTIAL | Wizard only; no phrase and no enum value for the model. | timezone |
| 5.66 | Make windows follow the mouse focus | NO | Fixed in rc.xml. | focus_follow |
| 5.67 | Turn off window shadows | NO | Fixed in rc.xml. | shadows |
| 5.68 | Put the close button on the left | NO | Fixed in rc.xml. | button_layout |
| 5.69 | Use a thinner window border | NO | Static labwc theme. | wm_theme |
| 5.70 | Make Alt-Tab include minimized windows | PARTIAL | labwc already lists them (verify); no setting. | alttab |
| 5.71 | Turn on sticky keys | NO | Not available. | sticky_keys |
| 5.72 | Where's my mouse? | NO | Not available. | locate_pointer |
| 5.73 | Zoom in on the top-left corner | NO | No magnifier. | magnifier |
| 5.74 | Don't auto-open USB drives | PARTIAL | It never auto-opens; the plug-in toast and Drives panel cannot be silenced. | automount |
| 5.75 | Change any setting I can't find in the menus | PARTIAL | Named settings via change_setting/set_appearance; anything else via run_command/write_file with confirmation for the OS's own files. | settings_editor |
| 5.76 | Make the terminal background black with green text | PARTIAL | The model could write foot.ini; no direct route (the 'retro theme' changes the desk, not foot). | terminal_prefs |
| 5.77 | Run df -h and tell me what it means | YES | tools.run_command (read-only commands run without asking), or '!df -h' in a terminal. |  |
| 5.78 | Firefox is frozen, close it | YES | Desk._window_shortcut (frozen) -> wm.force_quit after a confirmation. |  |
| 5.79 | Take a screenshot of this window | PARTIAL | Whole screen only (tools.screenshot). | screenshot_more |
| 5.80 | Turn the volume down / Mute | YES | intent._device (_VOL) -> tools.set_volume. |  |
| 5.81 | Connect to the CoffeeShop Wi-Fi, password is ... | YES | tools.wifi_connect (iwctl), or the network panel form. |  |
| 5.82 | Pair my headphones | YES | _SYS bluetooth -> syspanels.bluetooth -> Search -> Pair (devices that need a PIN fail: bt_pin). |  |
| 5.83 | Print this PDF | PARTIAL | No print tool; open it in Firefox and use Ctrl+P. | print_file |
| 5.84 | Don't disturb me for an hour | NO | No do-not-disturb ('focus mode for 60 minutes' blocks sites instead). | dnd |
| 5.85 | Install a text editor | YES | tools.install_app (apk add); Mousepad is already installed. |  |
| 5.86 | Update everything | YES | _SYS updates -> syspanels.updates_panel -> 'install the updates' -> syspanels.updates_apply (asks). |  |
| 5.87 | Create an account for my son | NO | One owner. | users |
| 5.88 | Change my password | PARTIAL | A passphrase can be set, not changed. | passphrase_change |
| 5.89 | Open notes.txt so I can edit it | PARTIAL | tools.open_file shows text read-only; editing needs 'open the text editor' then File > Open. | edit_text |
| 5.90 | Show me this photo | YES | tools.open_file shows images in a window; Ristretto via 'open photos'. |  |
| 5.91 | Unzip this download | PARTIAL | tools.open_file launches Xarchiver; nothing extracts it by request. | unzip |
| 5.92 | What hardware does this computer have? | YES | 'about this computer' / 'specs' -> _SYS about -> syspanels.about; this wording goes to the model (read-only run_command lscpu/free, no asking). |  |
| 5.93 | What's using all the CPU? | YES | 'what's using the cpu' -> _SYS processes -> syspanels.processes; with 'all' it goes to the model (read-only ps/top via run_command). |  |
| 5.94 | Reopen my windows next time I log in | NO | No session restore. | session_save |
| 5.95 | Login screen: lock on startup / log in automatically | YES | With a passphrase vault the computer starts at the lock screen; without one it opens directly (Desk.boot_screen). |  |

## Notes on what was verified

- Deterministic routes (no model): `intent.match` and `desk.Desk.shortcut` / `_system_shortcut` / `_window_shortcut` (regexes `_SYS`, `_WIN`). Several panel buttons send exact phrases ("mouse faster", "key repeat slower", "set resolution OUT WxH", "eject drive /dev/X"); the same wishes in other words go to the model, which has no tool for input settings, displays or ejecting (gaps input_words, display_words, eject_words).
- The printers panel's "Test page" and "Make default" buttons send phrases that no shortcut handles (syspanels.printers vs desk._system_shortcut).
- `tools.change_setting` has a working `timezone` branch that its own enum leaves out; `vault.change_passphrase` exists with no caller; `Desk.handle('app.focus')` is `pass`.
- The desk session runs as root with a private D-Bus session bus (usr/libexec/llmos-desk: dbus-run-session); system dbus, cupsd, avahi-daemon, bluetooth, iwd and acpid are enabled in install.sh; chronyd is removed, so nothing syncs the clock.
- labwc: `<keyboard>` in rc.xml defines keybinds without `<default/>`, so only the listed keys exist; `<mouse><default/>` keeps labwc's default mouse bindings (title-bar menu, Alt+drag) which is why several items say *verify*. No `<desktops>`: one workspace.

