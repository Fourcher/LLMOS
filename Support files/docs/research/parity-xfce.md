# Feature parity checklist: stock Alpine 3.24 XFCE vs LLM OS

Comparison target: what `setup-desktop xfce` installs on Alpine 3.24 (XFCE 4.20), booted in a VM next to LLM OS.
Researched 2026-10-05 from alpine-conf `setup-desktop.in` (master) and aports `3.24-stable` APKBUILDs. Settings pages and controls come from XFCE 4.20 upstream. Items marked **(verify)** should be checked in the VM, because the build options or runtime dependencies leave them uncertain.

How to use: tick an item when LLM OS can do the same thing, either through the desk or by a plain-language request that works end to end. Section 5 lists what Lubuntu (LXQt) and Linux Mint XFCE users expect on top of the stock XFCE set.

---

## 0. Exactly what `setup-desktop xfce` installs (Alpine 3.24)

From `setup-desktop.in`, case `xfce)`:

```
prefer_gtk_dark      # writes /etc/gtk-3.0/settings.ini: gtk-application-prefer-dark-theme=1
setup-xorg-base xfce4 ${BROWSER:-firefox} elogind gvfs lightdm lightdm-gtk-greeter \
    polkit-elogind xfce4-screensaver xfce4-terminal font-dejavu
rc-update add lightdm
rc-update del acpid
```

- `setup-xorg-base` also enables the community repository and installs `xorg-server xf86-input-libinput xinit eudev mesa-dri-gallium`. It then runs `setup-devd udev`.
- If no user exists, it runs `setup-user -g "audio,video,netdev"`.
- The `xfce4` meta package (4.20) depends on: `exo font-dejavu garcon libxfce4ui libxfce4util libxfce4windowing thunar thunar-volman tumbler xfce4-appfinder xfce4-panel xfce4-power-manager xfce4-session xfce4-settings xfconf xfdesktop xfwm4`.
- Versions in 3.24-stable: xfce4-settings 4.20.4, xfce4-session 4.20.2, xfce4-panel 4.20.7, xfdesktop 4.20.1, thunar 4.20.8, xfwm4 4.20.0, xfce4-power-manager 4.20.0, xfce4-screensaver 4.20.2, xfce4-terminal 1.2.0, thunar-volman 4.20.0, tumbler 4.20.0, lightdm-gtk-greeter 2.0.9, firefox 151.0.3.
- Build options that matter:
  - xfce4-settings is built with libxklavier (keyboard layouts), sound-settings, upower, xorg-libinput and xrandr. colord-dev is a build dependency, so the Color Profiles dialog is built.
  - xfdesktop is built with desktop-menu, thunarx (the "Set as wallpaper" action), notifications, x11 and wayland.
  - thunar is built with exif, pcre and gudev.
  - xfwm4 is built with the compositor, xpresent and xsync.
  - tumbler is built against ffmpegthumbnailer, poppler, libgsf, libopenraw, libgepub and gstreamer, so it can make video, PDF, office, RAW and EPUB thumbnails **(verify)**.
  - xfce4-screensaver is built with elogind as the session manager.
  - xfce4-power-manager is built with wayland and polkit.
- There is also an `xfce-wayland` variant: `setup-wayland-base xfce4 firefox adwaita-icon-theme elogind greetd-gtkgreet gvfs labwc polkit-elogind xfce4-screensaver xfce4-terminal`, with greetd as the login screen. It uses **labwc**, the same compositor as LLM OS, so it is a useful second comparison.

### What stock Alpine XFCE does NOT install (a real XFCE user will notice)

Each of these is a separate `apk add`. Check each one in the VM with `apk info -e <pkg>`.

- [ ] No **notification daemon** (`xfce4-notifyd`). The Notifications settings page and its popups are missing **(verify)**.
- [ ] No **audio stack** (pipewire, wireplumber or pulseaudio), no `xfce4-pulseaudio-plugin` and no `pavucontrol`. There is no volume icon and no Sound settings.
- [ ] No **network GUI** (NetworkManager or nm-applet). Networking is set up with ifupdown and wpa_supplicant from `setup-interfaces`.
- [ ] No **Bluetooth** (bluez or blueman).
- [ ] No **printing** (cups or system-config-printer).
- [ ] No **text editor** (mousepad), **image viewer** (ristretto), **archive manager** (xarchiver or thunar-archive-plugin), **screenshot tool** (xfce4-screenshooter), **task manager** (xfce4-taskmanager), **media player** (parole), **PDF viewer** (only Firefox), **calculator**, **Whisker Menu**, **menu editor** (menulibre) or **lightdm-gtk-greeter-settings**.
- [ ] No GUI for **users**, **date/time**, **timezone**, **software updates** or **disks**.
- [ ] Only the core `gvfs` package, without gvfs-smb, gvfs-mtp, gvfs-sftp and similar backends. Network shares and phones cannot be browsed **(verify)**.
- [ ] Some default XFCE shortcuts point at tools that are not installed, for example Print → xfce4-screenshooter and Ctrl+Shift+Esc → xfce4-taskmanager. Those keys do nothing **(verify)**.

So the stock XFCE app set is: Firefox, Thunar (with volman and tumbler), xfce4-terminal, Application Finder, Settings Manager with its dialogs, Power Manager, Screensaver/Locker, Panel, Desktop, xfwm4, Session (log out dialog) and the LightDM GTK greeter.

---

## 1. XFCE Settings Manager: every page and its controls

### 1.1 Appearance (`xfce4-appearance-settings`)
**Style tab**
- [ ] Choose GTK theme from a list (Adwaita, Adwaita-dark, Default, plus any installed themes)
- [ ] Theme preview thumbnails
- [ ] Dark preference: Alpine sets `gtk-application-prefer-dark-theme=1` globally, so apps start dark
- [ ] Install a theme by dropping a theme archive into the dialog (drag and drop)
- [ ] "Set matching Xfwm4 theme if there is one" toggle (4.20)

**Icons tab**
- [ ] Choose icon theme (Adwaita, hicolor, and others)
- [ ] Install an icon theme by dragging an archive in

**Fonts tab**
- [ ] Default font family and size
- [ ] Default monospace font family and size
- [ ] Rendering: enable anti-aliasing
- [ ] Hinting: None, Slight, Medium, Full
- [ ] Sub-pixel order: None, RGB, BGR, Vertical RGB, Vertical BGR
- [ ] DPI: use a custom DPI setting, with a value

**Settings tab**
- [ ] Toolbar style: Icons, Text, Both, Both horizontal
- [ ] Show images on buttons
- [ ] Show images in menus
- [ ] Enable editable accelerators
- [ ] Enable event sounds
- [ ] Enable input feedback sounds
- [ ] Window scaling factor (1x, 2x) for HiDPI

### 1.2 Window Manager (`xfwm4-settings`)
**Style tab**
- [ ] Window decoration theme list (Default, Daloa, Kokodi, Moheli and others)
- [ ] Title font
- [ ] Title alignment: Left, Center, Right
- [ ] Button layout: drag Menu, Stick, Shade, Minimize, Maximize, Close and Title between active and hidden

**Keyboard tab**
- [ ] List of window actions with shortcuts
- [ ] Edit a shortcut
- [ ] Clear a shortcut
- [ ] Reset to defaults

**Focus tab**
- [ ] Focus model: Click to focus, or Focus follows mouse, with a delay slider
- [ ] New window focus: automatically give focus to newly created windows
- [ ] Raise on focus: automatically raise windows when they get focus, with a delay
- [ ] Raise on click: raise a window when clicking inside it

**Advanced tab**
- [ ] Window snapping: to screen borders
- [ ] Window snapping: to other windows
- [ ] Snap distance slider
- [ ] Wrap workspaces when the pointer reaches a screen edge
- [ ] Wrap workspaces when dragging a window off the edge
- [ ] Edge resistance slider
- [ ] Box move and resize: hide window content while moving
- [ ] Box move and resize: hide window content while resizing
- [ ] Double-click title bar action: Shade, Hide, Maximize, Fill, Nothing

### 1.3 Window Manager Tweaks (`xfwm4-tweaks-settings`)
**Cycling tab**
- [ ] Skip windows that have "skip pager" or "skip taskbar" set
- [ ] Include hidden (minimized) windows
- [ ] Cycle through windows on all workspaces
- [ ] Draw a frame around the selected window while cycling
- [ ] Raise windows while cycling
- [ ] Cycle through windows in a list (rather than an icon grid)

**Focus tab**
- [ ] Activate focus stealing prevention
- [ ] Honor the standard ICCCM focus hint
- [ ] When a window raises itself: bring it to the current workspace, switch to its workspace, or do nothing

**Accessibility tab**
- [ ] Key used to grab and move windows (Alt or Super)
- [ ] Raise windows when any mouse button is pressed
- [ ] Hide the frame of windows when maximized
- [ ] Hide the title of windows when maximized
- [ ] Automatically tile windows when moving them toward the screen edge
- [ ] Use edge resistance instead of window snapping
- [ ] Use the mouse wheel on the title bar to roll up (shade) the window
- [ ] Notify of urgency by making the window's decoration blink
- [ ] Keep urgent windows blinking repeatedly
- [ ] Zoom the desktop with Alt + mouse wheel (compositor zoom)
- [ ] Zoom the pointer along with the desktop

**Workspaces tab**
- [ ] Use the mouse wheel on the desktop to switch workspaces
- [ ] Remember and recall the previous workspace when switching with keyboard shortcuts
- [ ] Wrap workspaces depending on the actual desktop layout
- [ ] Wrap workspaces when the first or last workspace is reached

**Placement tab**
- [ ] Minimum window size that triggers smart placement (slider)
- [ ] Default placement: at the center of the screen, or under the mouse pointer

**Compositor tab**
- [ ] Enable display compositing
- [ ] Display fullscreen overlay windows directly (unredirect)
- [ ] Synchronize drawing to the vertical blank (vsync)
- [ ] Show window previews in place of icons when cycling
- [ ] Show shadows under popup windows
- [ ] Show shadows under dock windows
- [ ] Show shadows under regular windows
- [ ] Opacity of window decorations
- [ ] Opacity of inactive windows
- [ ] Opacity of windows during move
- [ ] Opacity of windows during resize
- [ ] Opacity of popup windows

### 1.4 Workspaces (`xfwm4-workspace-settings`)
- [ ] Number of workspaces (default 4)
- [ ] Rename each workspace (editable list)
- [ ] Margins tab: top, bottom, left and right screen margins that maximized windows will not cover

### 1.5 Desktop (`xfdesktop-settings`)
**Background tab**
- [ ] Pick the monitor and workspace being configured
- [ ] Apply to all workspaces toggle
- [ ] Choose an image folder and pick an image from the thumbnails
- [ ] Style: None, Centered, Tiled, Stretched, Scaled, Zoomed, Spanning screens
- [ ] Color: Solid color, Horizontal gradient, Vertical gradient, Transparent
- [ ] Color 1 and Color 2 pickers
- [ ] Change the background on a timer: every N seconds, minutes or hours, at start-up, hourly, daily, or chronologically
- [ ] Random order for the slideshow

**Menus tab**
- [ ] Desktop menu: show the application menu on right click
- [ ] Desktop menu: show application icons in the menu
- [ ] Window list menu: show it on middle click
- [ ] Window list menu: show workspace names
- [ ] Window list menu: show sticky windows only in the active workspace
- [ ] Window list menu: show options to add and remove workspaces
- [ ] Window list menu: show application icons

**Icons tab**
- [ ] Icon type: None, Minimized application icons, or File/launcher icons
- [ ] Icon size
- [ ] Custom icon font size
- [ ] Show icon tooltips, with a tooltip size
- [ ] Use a single click to activate items
- [ ] Show hidden files on the desktop
- [ ] Show thumbnails
- [ ] Default icons: Home
- [ ] Default icons: File System
- [ ] Default icons: Trash
- [ ] Default icons: Removable devices (network shares, disks and drives, other devices)
- [ ] Choose which monitor shows the icons (4.20)

### 1.6 Panel (`xfce4-panel --preferences`)
- [ ] Choose which panel to edit (Panel 1, Panel 2)
- [ ] Add a new panel (+)
- [ ] Remove a panel (−)
- [ ] Backup and restore the panel layout (4.20 profiles)

**Display tab**
- [ ] Mode: Horizontal, Vertical, Deskbar
- [ ] Output: which monitor (or Automatic)
- [ ] Span monitors
- [ ] Lock the panel (it can no longer be dragged)
- [ ] Don't reserve space on the screen borders
- [ ] Automatically hide the panel: Never, Intelligently, Always
- [ ] Keep the panel above windows
- [ ] Row size (pixels)
- [ ] Number of rows
- [ ] Length (%)
- [ ] Automatically increase the length
- [ ] Icon size: adjust automatically, or a fixed size

**Appearance tab**
- [ ] Background style: None (use the theme), Solid color, Background image
- [ ] Enable dark mode for the panel
- [ ] Color and image pickers
- [ ] Enter opacity (when the pointer is over the panel)
- [ ] Leave opacity

**Items tab**
- [ ] List the plugins on the panel
- [ ] Add a plugin (the plugin chooser)
- [ ] Remove a plugin
- [ ] Move a plugin up or down (or drag it on the panel in edit mode)
- [ ] Open a plugin's own settings
- [ ] About a plugin

### 1.7 Display (`xfce4-display-settings`)
**General tab**
- [ ] Monitor layout canvas: drag monitors to arrange them
- [ ] Select a display
- [ ] Enable or disable the display
- [ ] Resolution
- [ ] Refresh rate
- [ ] Rotation: None, Left, Inverted, Right
- [ ] Reflection: None, Horizontal, Vertical, Both
- [ ] Scale: 1x, 2x, or custom (fractional, using xrandr scaling)
- [ ] Set as primary display
- [ ] Mirror displays
- [ ] Apply, with "keep this configuration?" and an automatic revert after 10 s
- [ ] Identify displays (popup labels)

**Advanced tab**
- [ ] Profiles: save the current configuration as a profile
- [ ] Profiles: apply or delete a profile
- [ ] Configure new displays when they are connected (show a dialog, or mirror or extend automatically)
- [ ] Automatically enable profiles when a new display is connected
- [ ] Quick "minimal" popup (Super+P or XF86Display): Only display 1, Mirror, Extend, Only display 2

### 1.8 Keyboard (`xfce4-keyboard-settings`)
**Behavior tab**
- [ ] Restore the Num Lock state on startup
- [ ] Enable key repeat
- [ ] Repeat delay
- [ ] Repeat speed
- [ ] Show a blinking cursor
- [ ] Cursor blink delay
- [ ] Test area

**Application Shortcuts tab**
- [ ] List of command → shortcut pairs
- [ ] Add a shortcut (enter a command, then press the keys)
- [ ] Edit a shortcut
- [ ] Remove a shortcut
- [ ] Reset to defaults
- [ ] Defaults to check, as they ship (some targets are absent on Alpine, as noted in section 0):
  - Super / Alt+F1: application menu
  - Alt+F2: Application Finder (run box)
  - Alt+F3: Application Finder (full window)
  - Ctrl+Alt+L or Ctrl+Alt+Delete: lock screen
  - Ctrl+Alt+T: terminal
  - Super+E: file manager
  - Super+W: web browser
  - Super+M: mail
  - Super+P: display popup
  - Ctrl+Alt+Esc: xkill
  - Ctrl+Esc: desktop menu
  - Shift+Ctrl+Esc: task manager (not installed)
  - Print, Alt+Print and Shift+Print: screenshooter (not installed)
  - Media keys XF86WWW, XF86Mail and XF86Explorer: open the matching app

**Layout tab**
- [ ] Use system defaults toggle
- [ ] Keyboard model
- [ ] Shortcut to change layout (for example Alt+Shift)
- [ ] Compose key
- [ ] Layouts list: add a layout and variant
- [ ] Layouts list: edit a layout
- [ ] Layouts list: remove a layout
- [ ] Layouts list: move a layout up or down

### 1.9 Mouse and Touchpad (`xfce4-mouse-settings`)
**Devices tab**
- [ ] Choose the device (each pointer device)
- [ ] Buttons: right-handed or left-handed
- [ ] Reverse the scroll direction (natural scrolling)
- [ ] Pointer speed: acceleration
- [ ] Pointer speed: acceleration profile (libinput: adaptive or flat)
- [ ] Reset to defaults
- [ ] Touchpad section (only when a touchpad exists): disable the touchpad while typing, with a duration
- [ ] Touchpad section: tap the touchpad to click
- [ ] Touchpad section: scroll mode (None, Edge, Two-finger)
- [ ] Touchpad section: enable horizontal scrolling
- [ ] Touchpad section: click method (button areas or clickfinger)

**Behavior tab**
- [ ] Drag-and-drop threshold
- [ ] Double-click time
- [ ] Double-click distance

**Theme tab**
- [ ] Cursor theme list, with a preview
- [ ] Cursor size

### 1.10 Power Manager (`xfce4-power-manager-settings`)
**General tab**
- [ ] When the power button is pressed: Do nothing, Ask, Suspend, Hibernate, Shut down
- [ ] When the sleep button is pressed
- [ ] When the hibernate button is pressed
- [ ] When the battery button is pressed
- [ ] Handle the display brightness keys
- [ ] Brightness step count
- [ ] Exponential brightness steps
- [ ] Show notifications (needs a notification daemon, not installed)

**System tab** (separate On battery / Plugged in columns)
- [ ] System sleep mode: Suspend or Hibernate
- [ ] When inactive for N minutes, put the system to sleep
- [ ] When the laptop lid is closed: Switch off display, Suspend, Hibernate, Lock screen, Do nothing
- [ ] Critical battery level (%)
- [ ] On critical battery: Do nothing, Suspend, Hibernate, Shut down, Ask
- [ ] Lock the screen when the system is going to sleep

**Display tab** (separate On battery / Plugged in columns)
- [ ] Display power management (DPMS) on or off
- [ ] Blank after N minutes
- [ ] Put to sleep after N minutes
- [ ] Switch off after N minutes
- [ ] Brightness reduction: reduce brightness after N seconds of inactivity
- [ ] Brightness reduction: reduce to N%

**Security tab**
- [ ] Automatically lock the session: Never, When the screensaver is activated, ...
- [ ] Delay locking after the screensaver for N seconds
- [ ] Lock the screen when the system goes to sleep
- [ ] On this install the tab defers to xfce4-screensaver settings **(verify)**

**Devices tab**
- [ ] List batteries, AC adapter, UPS and wireless devices
- [ ] Show their charge, state, vendor, model and capacity (health)

**Power Manager panel plugin**
- [ ] Battery icon with percentage or time remaining
- [ ] Brightness slider
- [ ] Presentation mode toggle (inhibits sleep and blanking)
- [ ] Display power management toggle
- [ ] Open Power manager settings

### 1.11 Notifications (`xfce4-notifyd-config`): NOT INSTALLED on stock Alpine
Listed for parity because every Mint and most other XFCE users have this page.
- [ ] Behavior: Do Not Disturb toggle
- [ ] Behavior: notification log (record notifications, log size, clear log)
- [ ] Behavior: show on which monitor (focused or primary)
- [ ] Behavior: position (top left or right, bottom left or right, top or bottom center)
- [ ] Behavior: expire timeout (seconds)
- [ ] Behavior: fade-out
- [ ] Behavior: slide-out
- [ ] Behavior: show the summary only
- [ ] Appearance: theme (Default, Bright, Smoke, Retro, ...)
- [ ] Appearance: opacity
- [ ] Appearance: icon size
- [ ] Appearance: show a preview button
- [ ] Applications: per-app mute
- [ ] Applications: per-app urgency
- [ ] Notification panel plugin: bell icon, recent log, DND toggle, clear

### 1.12 Removable Drives and Media (`thunar-volman-settings`)
**Storage tab**
- [ ] Mount removable drives when hot-plugged
- [ ] Mount removable media when inserted
- [ ] Browse removable media when inserted
- [ ] Auto-run programs on new drives and media
- [ ] Auto-open files on new drives and media
- [ ] Blank CDs/DVDs: burn a data CD when a blank disc is inserted (command)
- [ ] Blank CDs/DVDs: burn an audio CD when a blank disc is inserted (command)
- [ ] Audio CDs: play audio CDs when inserted (command)

**Multimedia tab**
- [ ] Portable media players: play music files when connected (command)
- [ ] Digital cameras: import photos when connected (command)
- [ ] Scanners: run a command when a USB scanner is connected
- [ ] Printers: run a command when a USB printer is connected

**Input Devices tab**
- [ ] Keyboards: run a command when a USB keyboard is connected
- [ ] Mice: run a command when a USB mouse is connected
- [ ] Tablets: run a command when a tablet is connected

### 1.13 Default Applications (`xfce4-mime-settings`, 4.20 merges "Preferred Applications" and the MIME editor)
**Internet tab**
- [ ] Web browser (Firefox)
- [ ] Mail reader (none installed)

**Utilities tab**
- [ ] File manager (Thunar)
- [ ] Terminal emulator (xfce4-terminal)

**Others tab (MIME type editor)**
- [ ] Searchable list of all MIME types, with the current default app
- [ ] Filter by status (default, user-set, all)
- [ ] Change the default app for a type (choose from the list or a custom command)
- [ ] Reset a type to the system default

### 1.14 Accessibility (`xfce4-accessibility-settings`)
**Visual / General**
- [ ] Enable assistive technologies (AT-SPI); requires logging in again
- [ ] Find the cursor by pressing Ctrl (locate pointer)

**Keyboard tab**
- [ ] Sticky keys: enable
- [ ] Sticky keys: lock sticky keys
- [ ] Sticky keys: disable when two keys are pressed together
- [ ] Slow keys: enable, with an acceptance delay
- [ ] Bounce keys: enable, with a key repeat delay

**Mouse tab**
- [ ] Mouse emulation (keypad moves the pointer): enable
- [ ] Mouse emulation: acceleration delay
- [ ] Mouse emulation: repeat interval
- [ ] Mouse emulation: acceleration time
- [ ] Mouse emulation: maximum speed
- [ ] Mouse emulation: acceleration profile
- [ ] Note: no screen reader (Orca) or on-screen keyboard is installed

### 1.15 Session and Startup (`xfce4-session-settings`)
**General tab**
- [ ] Display the chooser on login (pick a saved session)
- [ ] Automatically save the session on logout
- [ ] Prompt on logout (show the log out dialog)
- [ ] Lock the screen before sleep **(verify)**

**Application Autostart tab**
- [ ] List of autostart entries with checkboxes
- [ ] Add an entry: name, description, command, and trigger (on login, on logout, on shutdown, on reboot, on suspend, on hibernate, on hybrid sleep, on switch user)
- [ ] Edit an entry
- [ ] Remove an entry
- [ ] Enable or disable an entry, including system items such as screensaver, power manager and volman

**Current Session tab**
- [ ] List of running session clients
- [ ] Restart style for each: Immediately, If running, Never
- [ ] Quit a program
- [ ] Save the session now

**Advanced tab**
- [ ] Compatibility: launch GNOME services on startup
- [ ] Compatibility: launch KDE services on startup
- [ ] Security: manage remote applications (TCP)
- [ ] Saved sessions: clear the saved sessions

### 1.16 Settings Editor (`xfce4-settings-editor`)
- [ ] Browse xfconf channels (xfwm4, xfce4-panel, xfce4-desktop, xsettings, keyboards, pointers, displays, xfce4-keyboard-shortcuts, xfce4-power-manager, xfce4-session, thunar, xfce4-screensaver, xfce4-appfinder, ...)
- [ ] Search for a property
- [ ] Add a new property with a type
- [ ] Edit a value
- [ ] Reset a property
- [ ] Delete a property
- [ ] Lock state shown (kiosk mode)
- [ ] Live monitor of channel changes

### 1.17 File Manager (Thunar Preferences, also opened from the Settings Manager)
**Display tab**
- [ ] View new folders using: Icon view, Detailed list, Compact list, or the last active view
- [ ] Show thumbnails: Never, Local files only, Always
- [ ] Only show thumbnails for files smaller than N
- [ ] Draw frames around thumbnails
- [ ] Sort folders before files
- [ ] Show hidden files at the end of the list
- [ ] Show file size in binary format (KiB versus kB)
- [ ] Remember view settings for each folder
- [ ] Icon view: text beside icons
- [ ] Date format: Today, Default, ISO, custom strftime
- [ ] Show full directory paths in tab titles
- [ ] Show the full path in the window title

**Side Pane tab**
- [ ] Shortcuts pane: icon size
- [ ] Shortcuts pane: show icon emblems
- [ ] Shortcuts pane: show the device usage bar
- [ ] Tree pane: icon size
- [ ] Tree pane: show icon emblems
- [ ] Tree pane: show hidden folders
- [ ] Image preview: embedded in the side pane or standalone

**Behavior tab**
- [ ] Navigation: single click to activate items, or double click
- [ ] Navigation: delay before an item is selected on hover
- [ ] Middle click: open the folder in a new window or a new tab
- [ ] Tabs: open new Thunar instances as tabs
- [ ] Tabs: restore tabs on startup
- [ ] File transfer: transfer files in parallel (always, never, or only between local devices)
- [ ] File transfer: use an intermediate file when copying
- [ ] File transfer: verify file checksums
- [ ] Context menu: show the action to permanently delete
- [ ] Context menu: show the action to create a link
- [ ] Ask before moving to trash or deleting

**Advanced tab**
- [ ] Folder permissions: apply recursively (Ask, Always, Never)
- [ ] Volume management: enable, with a button that opens the Removable Drives settings
- [ ] Search: enable recursive search (Local only, Always, Never)
- [ ] Search: include subfolders
- [ ] Show the "Recent" item and remember recent files
- [ ] Execute shell scripts: Never, Always, Ask

**Shortcuts editor** (Edit > Configure Keyboard Shortcuts, 4.18 and later)
- [ ] Rebind any Thunar action

### 1.18 Screensaver and Lock Screen (`xfce4-screensaver-preferences`; Light Locker is not used)
**Screensaver tab**
- [ ] Enable the screensaver
- [ ] Theme list: Blank screen, Random, and the bundled savers (Floaters, Pop art squares, Slideshow, ...)
- [ ] Change the theme after N minutes
- [ ] Activate the screensaver when the computer is idle
- [ ] Idle delay (minutes)
- [ ] Inhibit the screensaver for fullscreen applications
- [ ] Preview button

**Lock Screen tab**
- [ ] Enable the lock screen
- [ ] Lock the screen with the screensaver
- [ ] Lock delay after the screensaver (minutes)
- [ ] Lock the screen when the system is going to sleep
- [ ] On-screen keyboard (command field)
- [ ] Session status messages (allow a message on the lock screen)
- [ ] Logout: enable logging out from the lock screen after N minutes
- [ ] User switching: show "Switch user" on the lock screen

**Lock screen itself**
- [ ] Password prompt
- [ ] Clock
- [ ] Username shown
- [ ] Keyboard layout shown
- [ ] Switch user button
- [ ] Log out button

### 1.19 Color Profiles (`xfce4-color-settings`)
- [ ] Device list (displays, printers, scanners, cameras, via colord)
- [ ] Add an ICC profile to a device
- [ ] Remove a profile
- [ ] Make a profile the default
- [ ] Show profile details
- [ ] Works only if the colord daemon is present and running; it may show as empty **(verify)**

### 1.20 Printers: not present (no cups or system-config-printer)
Expected by Mint and Lubuntu users:
- [ ] Add a printer (auto-detect USB and network)
- [ ] Choose a driver
- [ ] Set the default printer
- [ ] Print a test page
- [ ] View and cancel jobs
- [ ] Share a printer

### 1.21 Network: not present (no NetworkManager or nm-applet)
Expected by Mint and Lubuntu users:
- [ ] Tray icon showing the connection state
- [ ] Choose a Wi-Fi network and enter a password
- [ ] Forget a network
- [ ] Wired: DHCP or static IPv4/IPv6, DNS
- [ ] VPN: OpenVPN or WireGuard import
- [ ] Hotspot
- [ ] Airplane mode / disable networking
- [ ] Hidden network
- [ ] Connection information dialog (IP, speed, MAC)
- [ ] Metered connection flag

### 1.22 Bluetooth: not present (no bluez or blueman)
Expected:
- [ ] Turn the adapter on or off
- [ ] Make the computer discoverable
- [ ] Scan and pair devices (PIN confirmation)
- [ ] Connect or disconnect audio, input and file-transfer devices
- [ ] Send a file
- [ ] Trust or remove a device

### 1.23 Sound: not present (no audio server, no pulseaudio plugin, no pavucontrol)
Expected with `pipewire wireplumber pipewire-pulse xfce4-pulseaudio-plugin pavucontrol`:
- [ ] Panel volume icon: scroll to change the volume
- [ ] Panel volume icon: click to mute
- [ ] Panel volume icon: output volume slider
- [ ] Panel volume icon: microphone slider and mute
- [ ] Choose the output and input device
- [ ] Media player (MPRIS) controls in the plugin
- [ ] Volume keys (XF86AudioRaiseVolume, LowerVolume, Mute, MicMute), with an on-screen notification
- [ ] Volume step and maximum volume (above 100%) settings
- [ ] pavucontrol Playback tab: per-app volume and per-app output device
- [ ] pavucontrol Recording tab: per-app input
- [ ] pavucontrol Output Devices tab: port selection, balance
- [ ] pavucontrol Input Devices tab
- [ ] pavucontrol Configuration tab: card profile (HDMI or analog, duplex)
- [ ] Event sounds toggle (Appearance > Settings)

### 1.24 Date and Time
- [ ] There is no date/time settings GUI. Time zone is set at install by `setup-timezone`, and NTP by `setup-ntp` (chrony).

**Clock panel plugin**
- [ ] Time zone used for display
- [ ] Layout: Analog, Binary, Digital, Fuzzy, LCD
- [ ] Tooltip format
- [ ] Digital layout: date only, time only, date then time, time then date
- [ ] Custom date and time strftime formats and fonts
- [ ] Show seconds
- [ ] 24-hour or 12-hour time
- [ ] Click shows a month calendar
- [ ] Alarm / sleep-monitor options, if any **(verify)**

### 1.25 Users: none
- [ ] There is no users and groups GUI. Users are created with `setup-user` / `adduser` in a terminal.
- [ ] Mint and Lubuntu users expect: add user, delete user, change password, change picture, administrator (sudo/wheel) toggle, autologin.

### 1.26 Other Settings Manager entries present
- [ ] **Application Finder** preferences: remember the last category, always center the window, keep the window open after launch, single-click execute, icon or list view, item icon size, category icon size, hide the category pane
- [ ] **Application Finder** custom actions: prefix or regex triggers, such as `#` for man pages, `!` to run in a terminal, `!w` for a Wikipedia search, and URL patterns that open the browser
- [ ] **Application Finder**: clear the history
- [ ] **xfce4-terminal** preferences (in the app, not the Settings Manager), covered in section 2

---

## 2. Default applications in stock Alpine XFCE, and what each lets a user do

### 2.1 Firefox 151 (the `BROWSER` variable, firefox by default)
- [ ] Browse the web
- [ ] Tabs, windows, private windows
- [ ] Bookmarks, history, downloads
- [ ] Saved passwords, sync account
- [ ] Extensions
- [ ] Built-in PDF viewer (the only PDF reader on the system)
- [ ] Play HTML5 audio and video (needs audio to be configured)
- [ ] Print (no printers configured), print to PDF
- [ ] Reader view, screenshots of pages (Firefox's built-in screenshot tool)
- [ ] Open local files (`file://`), view images and plain text
- [ ] Download files into ~/Downloads

### 2.2 Thunar 4.20 (file manager), with thunar-volman, tumbler and gvfs
- [ ] Browse folders: icon, detailed list and compact views
- [ ] Tabs and split view (F3)
- [ ] Copy, cut, paste, duplicate, make a link
- [ ] Rename (F2), bulk rename (Thunar Bulk Rename tool)
- [ ] New folder, new empty file, create documents from templates (~/Templates)
- [ ] Move to Trash, permanent delete (Shift+Del), restore from trash, empty trash
- [ ] Search by name, recursively (Ctrl+F)
- [ ] Location bar (Ctrl+L), path bar buttons
- [ ] Bookmarks in the side pane (Ctrl+D), editable
- [ ] Show hidden files (Ctrl+H)
- [ ] Select by pattern, select all, invert selection
- [ ] Undo and redo of file operations (Ctrl+Z / Ctrl+Shift+Z)
- [ ] Thumbnails through tumbler: images, video, PDF and others **(verify)**
- [ ] Image preview pane
- [ ] Properties dialog: name, type, size, dates, open with, permissions (owner/group/others, and apply recursively), emblems, highlight color, image EXIF tab
- [ ] "Open With" another application, and set the default
- [ ] Custom actions: "Open Terminal Here" is the default; users can add their own command actions
- [ ] "Set as wallpaper" on images (xfdesktop thunarx plugin)
- [ ] Mount, unmount, eject and safely remove USB drives in the side pane; the usage bar shows free space
- [ ] Auto-mount on hotplug via thunar-volman (user needs polkit/elogind; this is configured)
- [ ] Recent files, File System, Home, Desktop, Trash shortcuts
- [ ] Zoom icons (Ctrl+ / Ctrl−)
- [ ] Sort by name, size, type or date, ascending or descending
- [ ] Network browsing: no SMB, SFTP or MTP backends installed **(verify)**
- [ ] No compress or extract (no archive plugin or xarchiver)

### 2.3 xfce4-terminal 1.2.0
- [ ] Shell sessions in tabs and windows
- [ ] Split panes? Not supported in 1.2; tabs only **(verify)**
- [ ] Copy and paste (Ctrl+Shift+C / V), paste selection
- [ ] Find in scrollback (Ctrl+Shift+F)
- [ ] Zoom font (Ctrl+ / Ctrl−), fullscreen (F11)
- [ ] Drop-down (Quake) mode with `--drop-down`
- [ ] Set the tab title, and set the tab color (1.1 and later)
- [ ] Preferences, General tab: title, command (login shell or custom), scrolling (lines, unlimited), cursor shape and blink, clipboard behavior
- [ ] Preferences, Appearance tab: font, bold, background (solid, image, transparent) and opacity, window size and decorations, menubar and toolbar visibility, padding
- [ ] Preferences, Colors tab: presets, foreground, background, cursor, the 16-color palette
- [ ] Preferences, Compatibility tab: backspace and delete key bindings, reset compatibility
- [ ] Preferences, Advanced tab: double-click word characters, tab activity indicator, disable menu shortcut keys, disable help (F1), text blinking
- [ ] Preferences, Shortcuts tab: rebind keys
- [ ] Clickable URLs and email addresses
- [ ] Profiles (1.1 and later): save and choose terminal profiles

### 2.4 Application Finder (xfce4-appfinder)
- [ ] Run-box mode (Alt+F2): type a command or app name with autocomplete
- [ ] Full mode (Alt+F3): browse categories, search apps, launch apps
- [ ] Custom actions (man page, run in terminal, web search, open URL)
- [ ] Right-click an app: add it to Favourites, edit the launcher, hide it

### 2.5 xfce4-panel (the default layout is the upstream 4.20 one; Alpine does not change it)
First login asks to "Use default config" or "One empty panel" **(verify)**.
- [ ] Top panel: Applications Menu, Window Buttons, separator (expanding), Workspace Switcher, Notification Area (status tray), Power Manager plugin, Clock, Action Buttons
- [ ] Bottom dock panel (autohide): Show Desktop, launchers (Terminal, File Manager, Web Browser, Application Finder), Directory Menu
- [ ] Panel right-click menu: Panel > Panel Preferences, Add New Items, Logout, About; on a plugin: Move, Remove, Properties
- [ ] Plugins available with no extra packages:
  - [ ] Action Buttons: log out, lock, switch user, suspend, hibernate, hybrid sleep, restart, shut down; shown as buttons or a session menu; the title can be the user's name or full name; confirmation dialog toggle
  - [ ] Applications Menu: freedesktop menu with categories, generic names toggle, show icons and tooltips, custom button title and icon, custom menu file, "Edit menu" (needs menulibre, not installed)
  - [ ] Clock (see 1.24)
  - [ ] Directory Menu: browse a folder from the panel, open it in Thunar or a terminal, file pattern filter, show hidden files
  - [ ] Launcher: one or more `.desktop` items, drag files onto it to open them, arrow menu for multiple items, show the last used item
  - [ ] Notification Area (systray plus StatusNotifier): max icon size, square icons, single-row layout, hide individual items, show and hide arrow
  - [ ] Separator: line, handle, dots or transparent; expand toggle
  - [ ] Show Desktop: toggle minimize-all; middle click shows the desktop
  - [ ] Window Buttons (tasklist): show labels, flat buttons, show handle, sorting (none, timestamp, group title, window title), grouping (never, always), show windows from all workspaces, show only minimized, show only windows on this monitor, switch windows with the mouse wheel, middle click (nothing, close, minimize), window right-click menu (minimize, maximize, move, resize, always on top, workspace, close)
  - [ ] Window Menu: list of all windows; icon or arrow style; urgent indicator; workspace actions
  - [ ] Workspace Switcher (pager): rows, miniature window previews, switch with the scroll wheel, drag windows between workspaces in the pager, workspace settings button
  - [ ] Power Manager plugin (from xfce4-power-manager): battery, brightness, presentation mode
- [ ] Not available without extra packages: Whisker Menu (search-first menu with favourites), PulseAudio/volume, Notification plugin (bell), Screenshooter, Keyboard layouts (xkb), CPU graph, system load, network monitor, weather, clipman (clipboard history), places, mailwatch, sensors

### 2.6 xfdesktop
- [ ] Wallpaper per monitor and per workspace
- [ ] Desktop icons for files, launchers and volumes
- [ ] Right-click root menu
- [ ] Middle-click window list
- [ ] Scroll the wheel on the desktop to switch workspace (if enabled)
- [ ] Drag files to and from the desktop
- [ ] Next background item / slideshow

### 2.7 xfwm4 (window manager with compositor)
Decorations, snapping, tiling, compositor effects, workspaces, Alt+Tab. Details in section 3.

### 2.8 xfce4-session
- [ ] Log out dialog: Log Out, Restart, Shut Down, Suspend, Hibernate, Hybrid Sleep, Switch User; checkbox "Save session for future logins"
- [ ] Autostart applications
- [ ] Session save and restore
- [ ] `xflock4` lock helper (calls xfce4-screensaver)

### 2.9 xfce4-power-manager
Battery, sleep, DPMS, brightness, lid, critical battery. Covered in 1.10.

### 2.10 xfce4-screensaver
Blanking, screensaver themes, lock, unlock. Covered in 1.18.

### 2.11 LightDM + lightdm-gtk-greeter 2.0.9 (login screen)
- [ ] Choose a user from the list, or enter a username manually
- [ ] Password entry
- [ ] Session chooser (Xfce Session)
- [ ] Indicators: clock, host name, power menu (Suspend, Hibernate, Restart, Shut Down)
- [ ] Accessibility menu: large font, high contrast, on-screen keyboard (onboard is not installed)
- [ ] Keyboard layout indicator (if configured)
- [ ] Greeter background and theme come from `/etc/lightdm/lightdm-gtk-greeter.conf`; there is no GUI because lightdm-gtk-greeter-settings is not installed
- [ ] Autologin configuration: config file only
- [ ] Switch user (`dm-tool switch-to-greeter`) from the Action Buttons or the lock screen

### 2.11b (xfce-wayland variant) greetd + gtkgreet + labwc
- [ ] gtkgreet login (username, password, session = xfce4-wayland)
- [ ] labwc as the compositor with the XFCE panel and desktop on layer-shell
- [ ] Many xfwm4 settings do not apply here
- [ ] This variant is the closest stock analogue to LLM OS's stack

### 2.12 Supporting services
- [ ] polkit-elogind: authorization prompts for mount, power and similar actions
- [ ] elogind: seats, suspend and shutdown without root
- [ ] gvfs: trash, mounts, recent files
- [ ] eudev: hotplug
- [ ] font-dejavu: default font
- [ ] mesa-dri-gallium: GPU drivers
- [ ] xf86-input-libinput: input devices

---

## 3. Desktop behaviors

### 3.1 Right-click desktop menu (xfdesktop, empty area)
- [ ] Open in New Window (Thunar at ~/Desktop)
- [ ] Create Launcher…
- [ ] Create URL Link…
- [ ] Create Folder…
- [ ] Create Document → templates / Empty File
- [ ] Open Terminal Here
- [ ] Paste
- [ ] Arrange Desktop Icons (sort by name, size, type or date)
- [ ] Next Background
- [ ] Desktop Settings…
- [ ] Properties…
- [ ] Applications submenu (the full app menu)
- [ ] Right-click on a desktop icon: Open, Open With, Cut, Copy, Rename, Move to Trash, Delete, Properties
- [ ] Right-click on a volume icon: Mount, Unmount, Eject, Properties
- [ ] Middle click on the desktop: window list with workspaces, plus Add Workspace and Remove Workspace

### 3.2 Drag and drop
- [ ] Drag files between Thunar windows and tabs: move on the same filesystem, copy across filesystems
- [ ] Modifier keys while dragging: Ctrl copies, Shift moves, Ctrl+Shift links, and drop-and-ask shows a menu
- [ ] Drag files to and from the desktop
- [ ] Drag to the Trash icon to delete
- [ ] Drag a file onto a panel launcher to open it with that app
- [ ] Drag a file into the terminal to paste its quoted path
- [ ] Drag a file into the Firefox upload field or tab
- [ ] Drag an image onto the Desktop settings list to add it as a wallpaper
- [ ] Drag a theme archive into Appearance to install it
- [ ] Drag a window title in the pager to move the window to another workspace
- [ ] Drag a `.desktop` file onto the panel to create a launcher
- [ ] Drag text selections between applications
- [ ] Drag a tab out of Thunar or the terminal to make a new window

### 3.3 File management essentials
- [ ] Copy, cut and paste (Ctrl+C, Ctrl+X, Ctrl+V), with a progress dialog that can pause and cancel
- [ ] Conflict dialog: replace, skip, rename, apply to all
- [ ] Rename with F2; select the name without the extension
- [ ] Bulk rename: numbering, search and replace, insert date, uppercase or lowercase, remove characters
- [ ] Move to trash (Del), restore from trash, empty trash, delete permanently (Shift+Del) with confirmation
- [ ] Search by filename, recursive (Ctrl+F)
- [ ] File contents are not searched (no tracker/catfish)
- [ ] Thumbnails for images, video and PDF (tumbler) **(verify)**
- [ ] USB drive: auto-mount, appears in the side pane and on the desktop, open, eject or safely remove, usage bar
- [ ] Permissions and ownership edit (Properties > Permissions)
- [ ] Create a symlink
- [ ] Open as root: not provided by default
- [ ] Show hidden files (Ctrl+H)
- [ ] Hidden-file preference saved per view
- [ ] Open a terminal in the current folder
- [ ] Recent files
- [ ] Bookmarks
- [ ] Open With → other application
- [ ] Set the default app for a type
- [ ] Highlight colors on files (4.18 and later)
- [ ] Emblems on files

### 3.4 Keyboard shortcuts (xfwm4 defaults)
- [ ] Alt+Tab / Shift+Alt+Tab: cycle windows (with an icon or preview grid)
- [ ] Super+Tab: cycle windows of the same application **(verify)**
- [ ] Alt+F4: close the window
- [ ] Alt+F6: stick the window (show on all workspaces)
- [ ] Alt+F7: move the window with the keyboard
- [ ] Alt+F8: resize the window with the keyboard
- [ ] Alt+F9: minimize (hide)
- [ ] Alt+F10: maximize or restore
- [ ] Alt+F11: fullscreen
- [ ] Alt+F12: always on top
- [ ] Alt+Space: window operations menu
- [ ] Ctrl+Alt+D: show the desktop
- [ ] Ctrl+Alt+Left/Right/Up/Down: switch workspace
- [ ] Ctrl+F1…F12: go to workspace N
- [ ] Ctrl+Alt+Shift+Left/Right (or Alt+Ctrl+Home/End): move the window to the previous or next workspace
- [ ] Alt+Insert: add a workspace
- [ ] Alt+Delete: remove the last workspace
- [ ] Super+Left/Right/Up/Down: tile left, right, up or down (half screen) **(verify bindings)**
- [ ] Super+KP_Home/End/Page_Up/Page_Down: tile into a quarter (corner)
- [ ] Alt+Shift+PageDown: lower the window
- [ ] Alt+mouse drag: move the window
- [ ] Alt+right drag: resize the window
- [ ] Alt+scroll: compositor zoom (if enabled)
- [ ] Application shortcuts, listed in 1.8

### 3.5 Window management
- [ ] Alt-tab switching across all workspaces or the current one, including minimized windows
- [ ] Snap to screen edges and other windows; edge resistance
- [ ] Edge tiling: drag a window to the left or right edge for a half, to a corner for a quarter, to the top to maximize (if "tile when moving to edge" is on)
- [ ] Maximize by double-clicking the title bar
- [ ] Maximize horizontally or vertically with middle or right click on the maximize button
- [ ] Minimize; restore from the tasklist
- [ ] Shade (roll up) by mouse wheel or button
- [ ] Always on top / always below
- [ ] Sticky (all workspaces)
- [ ] Move to workspace from the window menu
- [ ] Fullscreen
- [ ] Window opacity (compositor)
- [ ] Shadows
- [ ] Multiple monitors: per-monitor panels, primary monitor, move a window to another monitor
- [ ] Session restore of windows on next login
- [ ] Kill an unresponsive window (xkill, Ctrl+Alt+Esc); "not responding" prompt to terminate on close

### 3.6 Multiple workspaces
- [ ] 4 by default
- [ ] Add, remove and rename workspaces
- [ ] Pager in the panel
- [ ] Keyboard switching
- [ ] Scroll-wheel switching on the desktop or the pager
- [ ] Wrap-around
- [ ] Per-workspace wallpaper
- [ ] Move windows between workspaces
- [ ] Per-workspace margins

### 3.7 Screenshots
- [ ] Stock: no screenshot tool installed; the Print key does nothing **(verify)**
- [ ] Expected with xfce4-screenshooter: full screen (Print), active window (Alt+Print), region (Shift+Print), delay, include the cursor, save, copy to clipboard, open with an app, upload
- [ ] Firefox's own page screenshot is the only built-in option

### 3.8 Lock screen
- [ ] Ctrl+Alt+L, Action Buttons > Lock Screen, or `xflock4`
- [ ] Automatic lock after the screensaver delay
- [ ] Lock on suspend
- [ ] Lock on lid close
- [ ] Unlock with the user's password
- [ ] Switch user from the lock screen
- [ ] Screensaver themes while locked

### 3.9 Session and power actions
- [ ] Log out (Action Buttons, desktop menu, `xfce4-session-logout`)
- [ ] Restart
- [ ] Shut down
- [ ] Suspend
- [ ] Hibernate (needs swap and a resume configuration)
- [ ] Hybrid sleep
- [ ] Switch user (via LightDM)
- [ ] Confirmation dialog with a 30 s countdown
- [ ] "Save session" checkbox
- [ ] Power button → configured action (1.10)
- [ ] Lid close → configured action
- [ ] Idle → sleep timers
- [ ] Critical battery → action

### 3.10 Notifications
- [ ] Stock: no daemon, so app notifications are not shown **(verify)**
- [ ] Expected with xfce4-notifyd: popup bubbles, actions on bubbles, persistence/log, Do Not Disturb, per-app mute, volume, brightness and battery OSD notifications

### 3.11 Miscellaneous expected behaviors
- [ ] Clipboard: regular, plus primary selection (middle-click paste)
- [ ] No clipboard history (clipman not installed)
- [ ] Input method (ibus/fcitx): not installed
- [ ] Keyboard layout switching via the layout shortcut (1.8)
- [ ] Brightness keys (power manager), on laptops only
- [ ] Media and volume keys do nothing without an audio stack
- [ ] HiDPI scaling (Appearance window scaling, Display scale)
- [ ] Night light / redshift: not available
- [ ] Autostart programs on login
- [ ] Open files and links in the default apps (exo-open / xdg-open)
- [ ] Polkit authentication prompt for privileged actions (polkit agent: xfce4-session/xfce-polkit? **verify** which agent is present; the absence of an agent breaks GUI mounts that need authentication)
- [ ] Trash location: ~/.local/share/Trash

---

## 4. What Lubuntu (LXQt) and Linux Mint XFCE users additionally expect

### 4.1 Lubuntu 24.04+/LXQt 2.x (for reference, Alpine `setup-desktop lxqt` installs: firefox lxqt-desktop lximage-qt obconf-qt pavucontrol-qt arandr sddm openbox elogind polkit-elogind gvfs udisks2 adwaita-qt oxygen)
- [ ] LXQt Configuration Center: Appearance (widget style, icons, fonts, LXQt theme, GTK style), Desktop (PCManFM-Qt wallpaper, icons), Desktop notifications, Keyboard and Mouse, Locale (formats), Monitor settings, Power management, Session settings (autostart, environment variables, user dirs), Shortcut keys, Date and time, Brightness, Openbox settings (ObConf), File associations, Users and groups? (via external tools)
- [ ] Apps: PCManFM-Qt, QTerminal (drop-down, split), FeatherPad (text editor), LXImage-Qt (viewer and screenshot), Screengrab, LXQt Archiver, qps (process viewer), Qlipper (clipboard history), KCalc, VLC, LibreOffice, Firefox, Discover / Muon (software center), Calamares installer, KDE Partition Manager, Skanlite, nm-tray (network), BlueDevil, Lubuntu Update Notifier, NobleNote, 2048
- [ ] Software updates via a GUI notifier
- [ ] Install and remove software via a GUI store (Discover with Snap/Flatpak)
- [ ] Network via nm-tray / NetworkManager (Wi-Fi, VPN)
- [ ] Sound via the pavucontrol-qt and LXQt volume plugin
- [ ] Printing via system-config-printer and CUPS
- [ ] Partitioning and formatting disks
- [ ] Clipboard history

### 4.2 Linux Mint 22.x XFCE Edition
- [ ] Whisker Menu: search-first menu, favourites, recently used, categories, run commands from search, actions on prefixes
- [ ] Network: nm-applet tray; Wi-Fi, VPN, hotspot, Network Connections editor
- [ ] Bluetooth: Blueman (pair, send files, audio profiles)
- [ ] Sound: PulseAudio/PipeWire panel plugin; Sound settings (pavucontrol)
- [ ] Notifications: xfce4-notifyd with DND and log
- [ ] Printers: system-config-printer, automatic driver detection
- [ ] Update Manager (mintupdate): update levels, kernel manager, automatic updates, Flatpak updates
- [ ] Software Manager (mintinstall): browse, search, install and remove apps, Flatpak support, reviews
- [ ] Software Sources: mirrors, PPAs, Flatpak remotes, repair keys
- [ ] Driver Manager: proprietary GPU, Wi-Fi and firmware drivers
- [ ] Timeshift: system snapshots and restore (rsync or btrfs), scheduled
- [ ] Backup Tool (mintbackup): home folder backup and restore
- [ ] Users and Groups: add or remove users, passwords, groups, pictures
- [ ] Login Window settings (slick-greeter): background, autologin, guest, appearance
- [ ] Date and Time (Mint tool): time zone, NTP, 12/24h
- [ ] Languages and Input Method settings: locale install, region formats, ibus/fcitx
- [ ] Firewall (gufw): enable or disable, rules
- [ ] System Reports: crash reports, system info, upgrade checks
- [ ] Disks (gnome-disks): format, partition, create a bootable USB (with mintstick: USB Image Writer and USB Stick Formatter)
- [ ] Disk Usage Analyzer (baobab)
- [ ] Welcome Screen (first steps checklist)
- [ ] Warpinator: send files over the LAN
- [ ] Web Apps manager: turn a site into an app
- [ ] Apps: Xed text editor, Xviewer image viewer, Xreader PDF, Pix (photo organizer), Drawing, Celluloid (video), Rhythmbox (music), Hypnotix (IPTV), LibreOffice, Thunderbird, Transmission (torrents), HexChat? (dropped in recent versions), Simple Scan (Document Scanner), GNOME Calculator, Calendar, Sticky Notes, Screenshot tool, Archive Manager (file-roller), Mousepad, Ristretto, Parole, Catfish (file search including contents), Task Manager, Onboard (on-screen keyboard), Orca (screen reader), Redshift / night light
- [ ] Thunar archive plugin (right-click Extract here / Compress), Thunar media tags, Thunar shares (Samba)
- [ ] Network share browsing (SMB, SFTP, MTP for phones)
- [ ] Panel plugins in Mint's default: Whisker, tasklist, systray, xkb keyboard layout, pulseaudio, notification bell, network, clock, power, user actions
- [ ] Keyboard shortcuts: Super opens Whisker, Print screenshot, Super+L lock, Ctrl+Alt+T terminal, Super+E files
- [ ] Night light (Redshift) and per-display color temperature
- [ ] Automatic system maintenance: snapshot before updates, kernel cleanup
- [ ] Mint Theme / Mint-Y colour variants; Flatpak themes

---

## 5. Capability table: XFCE clicks vs. a natural-language request

| # | Capability | How a user does it in stock XFCE (clicks) | Equivalent natural-language request |
|---|---|---|---|
| 1 | Open an app | Applications Menu (top-left) → category → app; or Alt+F2, type the name | "Open Firefox" |
| 2 | Search apps | Alt+F3 → type in the Application Finder | "What apps do I have for editing images?" |
| 3 | Switch windows | Alt+Tab, or click a Window Buttons entry | "Switch to the terminal" |
| 4 | Close a window | Click × or Alt+F4 | "Close the browser window" |
| 5 | Maximize / minimize | Title bar buttons, double-click the title bar, Alt+F10 / Alt+F9 | "Maximize this window" / "Hide everything" |
| 6 | Tile side by side | Drag a window to the left or right edge, or Super+Left/Right | "Put Firefox on the left and Files on the right" |
| 7 | Show the desktop | Ctrl+Alt+D or the Show Desktop button | "Show me the desktop" |
| 8 | Move to a workspace | Window menu → Move to Another Workspace, or drag in the pager | "Move this window to workspace 2" |
| 9 | Add or rename workspaces | Settings → Workspaces → number, names | "Give me 6 workspaces and call the second one Work" |
| 10 | Change the wallpaper | Right-click the desktop → Desktop Settings → Background → pick an image | "Use this photo as my wallpaper" |
| 11 | Wallpaper slideshow | Desktop Settings → Change the background every N min | "Rotate my wallpapers every 10 minutes" |
| 12 | Dark/light theme | Settings → Appearance → Style → Adwaita-dark | "Switch to a light theme" |
| 13 | Icon theme | Appearance → Icons | "Use a different icon set" |
| 14 | Bigger text | Appearance → Fonts → default font size / DPI | "Make the text bigger" |
| 15 | HiDPI scaling | Appearance → Settings → Window scaling 2x, or Display → Scale | "Everything is tiny, scale it up" |
| 16 | Display resolution | Settings → Display → Resolution → Apply → Keep | "Set the screen to 1920×1080" |
| 17 | Rotate the screen | Display → Rotation | "Rotate the monitor to portrait" |
| 18 | Second monitor | Display → arrange, Mirror/Extend, or Super+P | "Mirror my screen to the projector" |
| 19 | Keyboard layout | Settings → Keyboard → Layout → uncheck system defaults → Add | "Add a French keyboard and let me switch with Alt+Shift" |
| 20 | Key repeat | Keyboard → Behavior → repeat delay and speed | "Keys repeat too fast" |
| 21 | Custom shortcut | Keyboard → Application Shortcuts → Add → command → press keys | "Make Super+B open the browser" |
| 22 | Mouse speed | Settings → Mouse and Touchpad → Acceleration | "Make the mouse faster" |
| 23 | Left-handed mouse | Mouse → Buttons → Left-handed | "Swap the mouse buttons" |
| 24 | Natural scrolling | Mouse → Reverse scroll direction | "Reverse scroll direction" |
| 25 | Tap to click | Mouse → Touchpad → Tap touchpad to click | "Turn on tap to click" |
| 26 | Cursor size | Mouse → Theme → Cursor size | "Make the pointer bigger" |
| 27 | Screen blank time | Power Manager → Display → Blank after | "Don't turn the screen off for an hour" |
| 28 | Auto-suspend | Power Manager → System → When inactive for | "Never sleep while plugged in" |
| 29 | Lid behavior | Power Manager → System → When laptop lid is closed | "Don't suspend when I close the lid" |
| 30 | Brightness | Brightness keys or the Power plugin slider | "Dim the screen to 40%" |
| 31 | Battery status | Power plugin icon / Power Manager → Devices | "How much battery do I have?" |
| 32 | Presentation mode | Power plugin → Presentation mode | "Keep the screen on during my presentation" |
| 33 | Lock the screen | Ctrl+Alt+L or Action Buttons → Lock | "Lock the screen" |
| 34 | Lock timing | Screensaver prefs → Lock Screen → Lock delay | "Lock 5 minutes after the screen blanks" |
| 35 | Screensaver | Screensaver prefs → theme, idle delay | "Use a blank screensaver after 10 minutes" |
| 36 | Log out | Action Buttons → Log Out → confirm | "Log me out" |
| 37 | Restart / shut down | Action Buttons → Restart / Shut Down → confirm | "Restart the computer" / "Shut down" |
| 38 | Suspend | Action Buttons → Suspend | "Go to sleep" |
| 39 | Switch user | Action Buttons → Switch User | "Let someone else log in" |
| 40 | Autostart app | Settings → Session and Startup → Application Autostart → Add | "Start the terminal every time I log in" |
| 41 | Default browser | Settings → Default Applications → Internet → Web Browser | "Make Firefox my default browser" |
| 42 | Default app per file type | Default Applications → Others, or Thunar → Properties → Open With → Set default | "Always open PDFs in Firefox" |
| 43 | Open a file | Thunar → double-click | "Open my résumé" |
| 44 | Find a file | Thunar → Ctrl+F → type the name | "Find the spreadsheet I downloaded last week" |
| 45 | Copy / move files | Thunar: select → Ctrl+C → go to the folder → Ctrl+V, or drag | "Copy all photos from Downloads to Pictures" |
| 46 | Rename a file | Select → F2 → type | "Rename report.txt to report-final.txt" |
| 47 | Bulk rename | Select files → right-click → Rename (Bulk Rename) → numbering | "Rename these to holiday-001, holiday-002…" |
| 48 | New folder | Right-click → Create Folder | "Make a folder called Taxes in Documents" |
| 49 | Delete to trash | Select → Del | "Delete the old drafts" |
| 50 | Restore from trash | Thunar → Trash → right-click → Restore | "Bring back the file I just deleted" |
| 51 | Empty the trash | Trash → Empty Trash → confirm | "Empty the trash" |
| 52 | Hidden files | Ctrl+H | "Show hidden files in my home folder" |
| 53 | File properties / permissions | Right-click → Properties → Permissions | "Make this script executable" |
| 54 | Bookmark a folder | Ctrl+D in Thunar | "Add Projects to my sidebar" |
| 55 | Open a terminal here | Right-click → Open Terminal Here | "Open a terminal in this folder" |
| 56 | USB drive | Plug in → auto-mounts → appears in the Thunar side pane / desktop | "What's on my USB stick?" |
| 57 | Eject USB | Thunar side pane → ⏏ Eject (or right-click → Eject/Safely Remove) | "Eject the USB stick" |
| 58 | Free disk space | Thunar side pane usage bar / Properties of / | "How much disk space is left?" |
| 59 | Thumbnails | Thunar → View → Icons, with thumbnails on | "Show my photos as thumbnails" |
| 60 | Set an image as wallpaper | Right-click the image in Thunar → Set as wallpaper | "Make this picture the wallpaper" |
| 61 | Panel position / autohide | Right-click the panel → Panel Preferences → Display → Autohide / drag the handle | "Auto-hide the taskbar" / "Move the panel to the bottom" |
| 62 | Add a launcher to the panel | Panel → Add New Items → Launcher → add the app | "Pin Terminal to the panel" |
| 63 | Clock format | Right-click clock → Properties → format | "Show 24-hour time with seconds" |
| 64 | Calendar | Click the clock | "What day is the 14th next month?" |
| 65 | Time zone | No GUI (`setup-timezone` as root) | "Set my time zone to Europe/London" |
| 66 | Window snapping / focus model | Settings → Window Manager → Advanced / Focus | "Make windows follow the mouse focus" |
| 67 | Compositor effects | Window Manager Tweaks → Compositor → shadows, opacity | "Turn off window shadows" |
| 68 | Title bar buttons | Window Manager → Style → button layout | "Put the close button on the left" |
| 69 | Window theme | Window Manager → Style → theme | "Use a thinner window border" |
| 70 | Alt-Tab behaviour | Tweaks → Cycling | "Make Alt-Tab include minimized windows" |
| 71 | Accessibility keys | Settings → Accessibility → Sticky keys / Slow keys | "Turn on sticky keys" |
| 72 | Locate pointer | Accessibility → Find cursor (press Ctrl) | "Where's my mouse?" |
| 73 | Zoom the screen | Alt+scroll (compositor zoom) | "Zoom in on the top-left corner" |
| 74 | Removable media actions | Settings → Removable Drives and Media | "Don't auto-open USB drives" |
| 75 | Hidden tweak | Settings → Settings Editor → channel → property | "Change any setting I can't find in the menus" |
| 76 | Terminal appearance | Terminal → Edit → Preferences → Colors / Appearance | "Make the terminal background black with green text" |
| 77 | Run a command | Terminal or Alt+F2 | "Run `df -h` and tell me what it means" |
| 78 | Kill a frozen app | Ctrl+Alt+Esc (xkill) then click; or terminal `kill` | "Firefox is frozen, close it" |
| 79 | Screenshot | Not installed (Print does nothing) | "Take a screenshot of this window" |
| 80 | Volume | Not installed (no audio stack) | "Turn the volume down" / "Mute" |
| 81 | Wi-Fi | Not installed (terminal: `setup-interfaces`, wpa_supplicant) | "Connect to the CoffeeShop Wi-Fi, password is …" |
| 82 | Bluetooth | Not installed | "Pair my headphones" |
| 83 | Print | Not installed | "Print this PDF" |
| 84 | Notifications | Not installed | "Don't disturb me for an hour" |
| 85 | Install software | No GUI; terminal `doas apk add …` | "Install a text editor" |
| 86 | Update the system | No GUI; terminal `apk upgrade` | "Update everything" |
| 87 | Add a user | No GUI; terminal `adduser` | "Create an account for my son" |
| 88 | Change password | No GUI; terminal `passwd` | "Change my password" |
| 89 | Edit a text file | No editor installed (only a terminal editor such as vi) | "Open notes.txt so I can edit it" |
| 90 | View an image | No viewer; Firefox opens it | "Show me this photo" |
| 91 | Extract a zip | No archive tool; terminal `unzip` | "Unzip this download" |
| 92 | System info | No GUI; terminal `uname -a`, `free`, `lscpu` | "What hardware does this computer have?" |
| 93 | Process list | No task manager installed; terminal `top` | "What's using all the CPU?" |
| 94 | Session save | Log out dialog → Save session | "Reopen my windows next time I log in" |
| 95 | Login screen | LightDM greeter: pick the user, type the password | (n/a: LLM OS boots to the desk) "Lock on startup" / "Log in automatically" |

---

## 6. Counting

Sections 0–4 hold about 700 checkbox items, and section 5 has 95 capability rows. Items marked **(verify)** should be confirmed in the side-by-side Alpine 3.24 XFCE VM. Useful commands there: `apk info -e xfce4-notifyd pipewire xfce4-screenshooter mousepad ristretto`, `xfconf-query -c xfce4-keyboard-shortcuts -l -v`, `xfconf-query -c xfwm4 -l -v`, and a screenshot of each Settings Manager page.

### Sources
- alpine-conf `setup-desktop.in` and `setup-xorg-base.in` (gitlab.alpinelinux.org/alpine/alpine-conf, master)
- aports `3.24-stable`: community/xfce4, xfce4-settings, xfce4-session, xfce4-panel, xfdesktop, thunar, xfwm4, xfce4-power-manager, xfce4-screensaver, xfce4-terminal, thunar-volman, tumbler, lightdm-gtk-greeter, firefox, gvfs APKBUILDs
- XFCE 4.20 upstream docs (docs.xfce.org) for the dialogs and controls; Linux Mint 22 and Lubuntu release notes for the extra expectations (from general knowledge, not fetched)
