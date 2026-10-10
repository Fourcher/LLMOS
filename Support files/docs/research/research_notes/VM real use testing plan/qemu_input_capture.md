# Driving a QEMU guest like a real user (macOS host, Wayland/sway guest): input injection and screen capture

Scope: arm64 guest with `-accel hvf` on Apple Silicon, and x86_64 guest under TCG. Host-side (QMP/HMP, VNC) and guest-side (wtype, ydotool, grim, AT-SPI, WebDriver) methods, settle detection, snapshots, and side channels (serial, qemu-guest-agent). Current as of October 2026. Items marked "(unverified)" in Inferences come from general knowledge and were not confirmed against a fetched source in this session.

## 1. QMP / HMP input and screen capture (input-send-event, send-key, screendump, query-mice, absolute pointing)

### Takeaway
QMP `input-send-event` (since 2.6) injects key, button, relative, absolute and multi-touch events. Absolute coordinates use a fixed 0 to 0x7fff range, so you scale pixels into that range yourself and need an absolute device (usb-tablet or virtio-tablet-pci). `screendump` (since 0.14) can write PNG directly since QEMU 7.1 via `"format":"png"`, and can target a specific `device`/`head`. That makes QMP alone a complete click/type/see loop with no network-facing server.

### Cited Findings
- `input-send-event` arguments: `device` ("display device to send event(s) to"), `head` ("head to send event(s) to, in case the display device supports multiple scanouts"), `events`. Since 2.6. Consoles are visible in the QOM tree under `/backend/console[$index]`. Doc example moves the pointer with `{ "type": "abs", "data": { "axis": "x", "value": 20000 } }` plus a matching y event. — [QEMU qapi/ui.json](https://gitlab.com/qemu-project/qemu/-/raw/master/qapi/ui.json)
- InputEvent types: `key`, `btn`, `rel`, `abs`, `mtt` (multi-touch). InputMoveEvent `value`: "For absolute coordinates the valid range is 0 to 0x7fff." InputAxis (since 2.0): `x`, `y`. — [QEMU qapi/ui.json](https://gitlab.com/qemu-project/qemu/-/raw/master/qapi/ui.json)
- InputButton values: left, middle, right, wheel-up, wheel-down, side, extra (side/extra since 2.9), wheel-left, wheel-right, touch (touch since 8.1). — [QEMU qapi/ui.json](https://gitlab.com/qemu-project/qemu/-/raw/master/qapi/ui.json)
- `send-key`: `hold-time` is the "time to delay key up events, milliseconds. Defaults to 100". An unknown or redundant key gives GenericError. QKeyCode is the key-name enum (since 1.3). Some codes are newer, e.g. `f13` since 8.0 and `lang1` since 6.1. `sysrq` is a synonym for `print`. — [QEMU qapi/ui.json](https://gitlab.com/qemu-project/qemu/-/raw/master/qapi/ui.json)
- `screendump`: `filename`, optional `device` (the primary display is used if missing), optional `head`, and `format` ("image format for screendump. (default: ppm) (Since 7.1)"). The `ImageFormat` enum (since 7.1) holds `png` and `ppm`. The command is only built `if CONFIG_PIXMAN`. — [QEMU qapi/ui.json](https://gitlab.com/qemu-project/qemu/-/raw/master/qapi/ui.json)
- PNG screendump came in with the patch "Added parameter to take screenshot with screendump as PNG". It uses libpng. QMP form: `{ "execute": "screendump", "arguments": { "filename": "/tmp/image", "format":"png" } }`. HMP form: `screendump /tmp/image -f png`. — [QEMU commit 9a0a119a](https://qemu.googlesource.com/qemu/+/9a0a119a382867dc9a5c2ae9348003bf79d84af2); [lore patch v5](https://lore.kernel.org/all/Yl%2FWaN3WTlWxRhb5@work-vm/T/)
- Known bug: QEMU 7.1.0 (x86_64) segfaulted after a PNG screendump through the HMP monitor, although the file was written correctly. The issue page shows no fix. — [QEMU issue #1210](https://gitlab.com/qemu-project/qemu/-/issues/1210)
- `query-mice` returns each active mouse device. `MouseInfo.absolute` is "true if this device supports absolute coordinates as input" and `current` is true if the device is "currently receiving mouse events". Since 0.14. — [QEMU qapi/ui.json](https://gitlab.com/qemu-project/qemu/-/raw/master/qapi/ui.json)
- On aarch64 `virt`, QEMU's reference graphical config uses virtio-gpu, because the "legacy VGA framebuffer is very troublesome on aarch64". For input it uses a USB keyboard and a USB tablet on xHCI, and it suggests `-display vnc=127.0.0.1:0` on headless hosts. — [QEMU docs/config/mach-virt-graphical.cfg](https://qemu.googlesource.com/qemu/+/fbd3c4cff641cae082edb765017cbb699efa6712/docs/config/mach-virt-graphical.cfg)
- The tablet reports absolute positions where the mouse reports relative movement. One user (pmbootstrap) saw the pointer land with a vertical offset when using the tablet, and kept the tablet opt-in for that reason. — [pmbootstrap commit f602df01](https://git.syndicate-lang.org/synit/pmbootstrap/commit/f602df01406fe8b1717aeaeb07bbb2d4118d6953)

### Inferences
- Pixel-to-abs mapping: `abs = round(px * 0x7fff / (width - 1))`, where `width` and `height` are the dimensions of the current screendump, not the window size on the macOS host. Re-read the dimensions after every mode change, because a virtio-gpu guest can resize its framebuffer. (Formula derived from the documented 0..0x7fff range.)
- Example click sequence (one `input-send-event` call, events applied in order):
  ```json
  {"execute":"input-send-event","arguments":{"events":[
    {"type":"abs","data":{"axis":"x","value":16383}},
    {"type":"abs","data":{"axis":"y","value":16383}}]}}
  {"execute":"input-send-event","arguments":{"events":[
    {"type":"btn","data":{"down":true,"button":"left"}}]}}
  {"execute":"input-send-event","arguments":{"events":[
    {"type":"btn","data":{"down":false,"button":"left"}}]}}
  ```
  Key event: `{"type":"key","data":{"down":true,"key":{"type":"qcode","data":"shift"}}}`. Split down and up into separate calls with a 20 to 50 ms gap, so the guest sees a distinct press. (unverified; the shape follows the documented InputEvent/KeyValue types)
- Recommended device set for an arm64 hvf guest: `-device virtio-gpu-pci -device qemu-xhci -device usb-kbd -device usb-tablet` (matches the reference config). `virtio-tablet-pci` plus `virtio-keyboard-pci` also work, but need `virtio_input` in the guest kernel (normally built in on distro kernels). Run `query-mice` once at startup and assert an entry with `absolute: true`. If none exists, absolute clicks silently turn into relative motion and land in the wrong place. (unverified)
- Run QMP over a UNIX socket (`-qmp unix:/path/qmp.sock,server=on,wait=off`) and send `{"execute":"qmp_capabilities"}` first. `-display none` or `-display vnc=...` still allows `screendump`, so the Cocoa window is not needed. Avoid driving through the Cocoa window, because macOS HiDPI scaling and window focus add a second, unrelated coordinate transform. (unverified)
- ramfb on arm64 is a simple boot/firmware framebuffer. Use virtio-gpu for the Wayland session, because sway needs a DRM/KMS device and virtio-gpu provides one. (unverified)
- Pin a QEMU version of 7.1 or newer for PNG. The 7.1.0 HMP PNG segfault is a reason to call screendump through QMP rather than HMP, and to test on the pinned version.

### Gaps
- No source fetched on scaling behaviour when the virtio-gpu guest resolution differs from the host window. With headless QMP screendump this should not matter, but it was not confirmed.
- No confirmation of whether issue #1210 was fixed, or in which version.
- Multi-touch (`mtt`) usage details were not researched.

## 2. Typing text reliably (latency, shifted chars, layouts, dropped keys under TCG)

### Takeaway
Host-side injection sends scancodes or qcodes, not characters. The host must map every character to keys (shift for uppercase and symbols) according to the guest's keyboard layout, and pace the keys. openQA, the largest production user of this approach, still loses characters under load. Its mitigations are rate limiting, typing in chunks with a check for screen change between chunks, and slow variants for critical strings.

### Cited Findings
- openQA's `type_string($string, max_interval => 1-250, wait_screen_change => N, wait_still_screen => S, secret => 1, timeout, similarity_level, lf => 1)`. A lower `max_interval` types more slowly. `wait_screen_change` types N characters at a time and waits for the screen to change between sets. — [openQA testapi](https://open.qa/api/testapi/)
- `send_key($key, hold_duration => s, wait_screen_change => …)`. `mouse_click` holds the button 0.15 s by default. — [openQA testapi](https://open.qa/api/testapi/)
- openQA's worker throttles VNC typing with `VNC_TYPING_LIMIT`, which sets `$seconds_per_keypress` in `vnc_base.pm`. For dropped keys on Hyper-V, a maintainer said "VNC won't let us do it a smarter way". — [openQA progress #19414 / related](https://progress.opensuse.org/issues/19414?tab=notes); [progress #55703](https://progress.opensuse.org/issues/55703)
- `send_key` did not respect `VNC_TYPING_LIMIT` in contrast to `type_string`. The tracker proposed honoring it or adding a `slow_send_key`. — [openQA progress #26014](https://progress.opensuse.org/issues/26014)
- Hypotheses recorded for missing characters: SUT delays (e.g. assets loaded over NFS), key events never reaching QEMU, or events reaching QEMU but not X. Proposed mitigations: a forced `wait_still_screen(1)` every 30 characters, and using `type_string_slow`. SUSE test code adds `type_slowly`/`type_very_slowly`. — [openQA progress #12250](https://progress.opensuse.org/issues/12250?tab=notes); [progress #17594](https://progress.opensuse.org/issues/17594); [progress #50399](https://progress.opensuse.org/issues/50399?tab=notes)
- For key combinations, send the keys in positional order, with enough time between them for the application to handle them. — [openQA progress #63826](https://progress.opensuse.org/issues/63826)
- QMP `send-key` holds each key for 100 ms by default (`hold-time`). — [QEMU qapi/ui.json](https://gitlab.com/qemu-project/qemu/-/raw/master/qapi/ui.json)

### Inferences
- Set the guest keymap to US (`input * xkb_layout us` in sway) and build the character map host-side: lowercase letters map directly to qcodes (`a`…`z`), digits to `0`…`9`, and uppercase and shifted symbols to shift-down, key, shift-up. Characters outside the layout (Unicode) cannot be typed host-side. Use guest-side `wtype`, or paste through the clipboard via the guest agent.
- TCG pacing: under TCG the guest runs many times slower than under hvf. Start at 30 to 50 ms between key events, plus a down/up hold, for TCG, and about 10 to 20 ms for hvf. After each 20 to 30 characters, wait for the screen to change. After typing, verify the text where possible: read the field via AT-SPI or WebDriver, or OCR the region, and retype on mismatch. (Inference modelled on openQA's mitigations.)
- Sending a whole string as one large `input-send-event` batch is fastest, but the most likely to drop or reorder keys in the guest's input path. One QMP call per key event, with a host-side sleep, is slower and more reliable.
- Secrets: openQA's `secret => 1` keeps typed strings out of logs. Do the same in our harness.

### Gaps
- No primary measurement of key-drop rates under QEMU TCG versus hvf was found. The openQA reports are anecdotal (2016 to 2021) and mostly from VNC-based workers.
- openQA's default `max_interval` value is not documented on the testapi page.
- Not confirmed: the exact QKeyCode spellings for punctuation (believed to be `spc`, `ret`, `tab`, `minus`, `equal`, `bracket_left`, `bracket_right`, `semicolon`, `apostrophe`, `grave_accent`, `backslash`, `comma`, `dot`, `slash`). Check the QKeyCode enum in qapi/ui.json before building the character map.

## 3. VNC (-vnc, vncdotool, RFB) as an alternative to QMP

### Takeaway
QEMU's built-in VNC server (`-display vnc=127.0.0.1:0`) is a standard RFB endpoint. vncdotool can drive it (type, key, move, click, capture, expect), and QEMU's server is in vncdotool's "regression tested on every pull request" tier. openQA historically drives QEMU through VNC. VNC sends keysyms, which QEMU translates through a keymap (an extra source of layout bugs), and its pacing caveats are documented. QMP is simpler for a local harness.

### Cited Findings
- vncdotool: install with `pip install vncdotool`. Examples: `vncdo -s vncserver type "hello world"`, `vncdo -s vncserver capture screen.png`. QEMU's VNC server is in the "Supported" tier, "regression tested on every pull request". The project describes itself as under active development. — [vncdotool README](https://github.com/sibson/vncdotool)
- QEMU's aarch64 virt reference config suggests `-display vnc=127.0.0.1:0` for headless hosts. — [QEMU mach-virt-graphical.cfg](https://qemu.googlesource.com/qemu/+/fbd3c4cff641cae082edb765017cbb699efa6712/docs/config/mach-virt-graphical.cfg)
- openQA throttles typing over VNC (`VNC_TYPING_LIMIT`). Maintainers say VNC offers no smarter flow control. — [openQA progress #19414](https://progress.opensuse.org/issues/19414?tab=notes)

### Inferences
- VNC advantages: a human can watch live with any VNC client, and you get framebuffer-update notifications (incremental updates) that can drive settle detection without polling screendump. vncdotool also has built-in `expect`/`rexpect` image matching. (unverified beyond the README)
- VNC disadvantages: keysym-to-scancode translation depends on QEMU's `-k` keymap and the client (classic shifted-symbol bugs). Pointer events are in pixel coordinates, which is simpler than 0..0x7fff, but they become absolute only if the guest has a tablet device. There is also one more network listener to secure (bind to 127.0.0.1 or a UNIX socket: `-vnc unix:/path/vnc.sock`). (unverified)
- Recommendation: QMP for injection and capture (deterministic, no keymap layer, local socket), with optional VNC on 127.0.0.1 purely for human observation. Do not mix VNC input and QMP input in one run, because both feed the same input layer and the order between them is undefined.

### Gaps
- The vncdotool docs page (readthedocs usage) returned 404, so the full command and API list (key, move, click, expect, `--delay`, Python `api.connect`) was not confirmed from the source.
- No source compared the latency of VNC framebuffer updates with QMP screendump.
- Not confirmed: whether macOS Screen Sharing accepts a QEMU VNC server that has no password (QEMU's default). It may refuse or prompt, which would need `-vnc ...,password=on` plus QMP `change-vnc-password`. A third-party viewer (e.g. TigerVNC) avoids the question.

## 4. Guest-side input and capture on Wayland (sway/wlroots): wtype, ydotool, grim, AT-SPI/dogtail, WebKitGTK WebDriver

### Takeaway
Fidelity ranking, closest to a real user first: (1) host-side QMP/VNC hardware events, which go through the guest's whole kernel input stack; (2) ydotool via uinput, also through the kernel input stack and libinput, but run from inside the guest; (3) wtype, a Wayland virtual keyboard injected at the compositor that bypasses the kernel; (4) AT-SPI or WebDriver, widget-level actions that bypass input entirely. Reliability runs roughly in reverse: WebDriver and AT-SPI give deterministic element targeting and readable state. Use host-side events for actions and guest-side introspection for assertions.

### Cited Findings
- ydotool uses the kernel's uinput framework rather than X events, and works on Wayland, X11, text consoles and framebuffer apps. The daemon `ydotoold` is mandatory since v1.0.0 and needs `/dev/uinput`, usually root. Commands: `click 0xC1` (right click), `mousemove` (relative by default; `--absolute -x 100 -y 100`), `type 'text'`, `key 29:1 29:0` (keycode:state, names from `linux/input-event-codes.h`). It does not detect custom layouts. The workaround is to set the layout on the virtual device in the compositor config (a sway `input` block, or Hyprland `device:ydotoold-virtual-device`). — [ydotool README](https://github.com/ReimuNotMoe/ydotool)
- wtype is "xdotool type for wayland". `-d <ms>` sets the delay between keystrokes. `-M`/`-m` press and release modifiers (`wtype -M ctrl c -m ctrl`). `-P`/`-p` press and release named keys (xkb keysym names). `-s <ms>` inserts a sleep. Unicode can be typed directly (`wtype ∇⋅∇ψ = ρ`). When wtype exits, all keys and modifiers are released because the compositor destroys the virtual keyboard. — [wtype README](https://github.com/atx/wtype)
- grim needs the wlroots screencopy protocol (Sway, Hyprland). xdg-output support is optional and improves fractional scaling. Options: `-o <output>`, `-g "<x>,<y> <w>x<h>"` (layout coordinates, `-` reads from stdin), `-s <factor>` scale, `-c` include cursors, `-T <toplevel id>` (newer releases only). Example: `grim -g "$(slurp)" shot.png`. — [grim(1), Arch](https://man.archlinux.org/man/grim.1.en); [grim(1), Ubuntu 1.4.0](https://manpages.ubuntu.com/manpages/jammy/man1/grim.1.html)
- dogtail 1.0 added Wayland support via `gnome-ponytail-daemon`, which uses GNOME's Screen Cast / Remote Desktop APIs and `org.gnome.Shell.Introspect`. On Wayland, AT-SPI knows only window-local coordinates, so Ponytail connects to the specific window to convert them to global coordinates. — [dogtail README (Debian)](https://sources.debian.org/src/dogtail/1.0.7-3/README.rst)
- WebKitGTK automation: `webkit_web_context_set_automation_allowed()` (since 2.18) is off by default, and only one WebKitWebContext can have it enabled. When WebKitWebDriver requests a session, the context emits `automation-started`. WebKitWebDriver is a separate server process that launches the browser per session (MiniBrowser by default, but any WebKitGTK browser). Igalia recommends enabling automation from startup behind a command-line flag. — [WebKitGTK API: set_automation_allowed](https://webkitgtk.org/reference/webkit2gtk/stable/method.WebContext.set_automation_allowed.html); [Igalia: WebDriver support in WebKitGTK 2.18](https://blogs.igalia.com/carlosgc/2017/09/)

### Inferences
- dogtail on sway: Ponytail depends on GNOME Shell D-Bus interfaces, so dogtail's Wayland input path will very likely not work on sway. AT-SPI tree reading (pyatspi / `gi.repository.Atspi`) should still work for querying widgets and their states, and for actions like `Action.do_action(0)` ("click") that need no coordinates. Window-local coordinates can be turned into screen coordinates by adding the window position from `swaymsg -t get_tree`. (Inference; not confirmed for sway.)
- The LLM OS desk and apps are WebKitGTK webviews. If the app calls `set_automation_allowed(TRUE)` behind a test-only flag, WebKitWebDriver can drive and inspect the DOM (`find element`, `get text`) over the standard W3C WebDriver protocol. This is the most reliable way to read UI state for assertions, but it does not exercise real input. Keep it off in shipped builds, since only one context can be automated and it opens a control channel. (Inference from the cited API semantics.)
- wtype relies on the compositor exposing the virtual-keyboard protocol (wlroots/sway do; GNOME Mutter historically does not). It uploads its own keymap, so it types arbitrary Unicode regardless of the layout. It is good for "type this text" steps, but less like a real user than host-side events. (unverified protocol details)
- grim versus host screendump: grim captures exactly what the compositor composed (including fractional scaling, and the cursor with `-c`). Host screendump captures the virtio-gpu scanout, which is what a monitor would show. For "what the user sees" the host screendump is closer to the truth, and it works even when the guest is hung. Use grim only for per-output or per-window crops.
- Running ydotoold as root inside the guest is a privileged test fixture that ships nothing to users. It belongs in the test image only.

### Gaps
- No source was fetched confirming wtype's protocol (zwp_virtual_keyboard_v1) or compositor support list. The README fetch did not state it.
- WebKitWebDriver's current (2026) completeness and whether a custom WebKitGTK app (not MiniBrowser) can be launched via `webkitgtk:browserOptions` → `binary`/`args` capabilities were not confirmed.
- No sway-specific AT-SPI reports were found.

## 5. Waiting for the screen to settle (frame-diff stability, timeouts, cursor/blink)

### Takeaway
The proven pattern, from openQA, has two parts: wait for a change after an action (with a timeout), then wait for the screen to stay still for a stilltime within a timeout, comparing frames with a similarity threshold instead of exact equality. Any blinking caret or animation needs a tolerance, or must be masked or disabled.

### Cited Findings
- openQA `wait_still_screen(stilltime=7s default, timeout=30s default, similarity_level, no_wait)` returns true if the screen stays unchanged for the stilltime. `wait_screen_change(CODEREF, timeout=10s, similarity_level=50)` runs the action and then waits for a change. `assert_screen(tags, timeout=30s)` / `check_screen(tags, timeout=0)` poll needles about once per second (`no_wait` polls faster). — [openQA testapi](https://open.qa/api/testapi/)
- openQA suggests `wait_still_screen(1)` every 30 typed characters to stop keys being lost. — [openQA progress #12250](https://progress.opensuse.org/issues/12250?tab=notes)

### Inferences
- Harness algorithm: `before = shot()`, do the action, poll `shot()` every 100 to 250 ms until `diff(before, now) > change_eps` or a change timeout (2 s for hvf, 5 to 10 s for TCG). Then poll until N consecutive frames over a stilltime (0.5 to 1 s for hvf, 1.5 to 3 s for TCG) differ by less than `still_eps`, or a settle timeout. Compute diffs on downscaled grayscale (e.g. 1/4 size) with a per-pixel threshold, and count changed pixels as a fraction of the total.
- Cursor and caret: hide or park the pointer in a corner, disable caret blink and animations in test mode, and keep a mask list for clocks and spinners.
- Under TCG every timeout should scale with a measured "slowness factor", e.g. time a fixed guest workload at boot, rather than use hard-coded values.
- PNG encoding in screendump costs CPU. For high-rate polling, PPM is cheaper to produce and parse. Use PNG only for artifacts saved to disk. (Inference.)

### Gaps
- openQA's default `similarity_level` for `wait_still_screen` is not stated on the testapi page.
- No benchmark of QMP screendump latency on hvf versus TCG was found.
- Not confirmed: the exact config knobs for hiding the cursor and stopping blink. Candidates are sway `seat * hide_cursor <ms>`, GTK `gtk-cursor-blink=false`, CSS `caret-color: transparent` in the webview, and `prefers-reduced-motion`.

## 6. Snapshots and fast reset (savevm/loadvm, snapshot-save/load, qcow2 overlays, -snapshot; hvf vs TCG; virtio-gpu / 9p constraints)

### Takeaway
For fast, reliable reset, prefer disk-only resets (a qcow2 overlay on a read-only base, recreated per test, or `-snapshot`) plus a cold boot, over live RAM snapshots. Live snapshots (savevm/loadvm) are blocked by any migration blocker, notably a mounted 9p/VirtFS share. On Apple Silicon hvf there is a 2026 regression where reverting a live snapshot crashes QEMU 11.0.1 (it works on 10.2.2; stopped-state snapshots revert fine).

### Cited Findings
- savevm fails when migration blockers are present, since a 2016 change; `migration_is_blocked()` is checked by both savevm and migrate. The motivating bug: after loadvm, a 9p mount in the guest gave "Protocol error". Example blocker message: "Migration is disabled when VirtFS export path '/' is mounted in the guest using mount_tag 'host'". — [QEMU commit 24f3902b "savevm: fail if migration blockers are present"](https://qemu.googlesource.com/qemu/+/24f3902b088cd4f2dbebfd90527b5d81d6a050e9%5E%21)
- The original Apple Silicon hvf commit says it includes the code to get basic VMs working, "including save/restore". Missing at the time: WFI handling and watchpoints/breakpoints. — [hvf: Add Apple Silicon support](https://git.cs.tu-dortmund.de/SYS-OSS/FRET-LibAFL/commit/a1477da3ddeb1b76adb71af7b5c46a18120dc952)
- QEMU issue #3565: on macOS Tahoe 26.5.1, Apple Silicon, qemu-system-aarch64 11.0.1, an Ubuntu 24.04 arm64 guest under libvirt. Reverting a snapshot taken while running crashes with the assertion `(!cpu->cpreg_vmstate_indexes)` in `target/arm/machine.c:1045` (`cpu_pre_load`). Reported as a regression from 10.2.2. Snapshots taken while stopped revert successfully. No fix is listed. — [QEMU issue #3565](https://gitlab.com/qemu-project/qemu/-/work_items/3565)
- 32-bit Arm guests using TrustZone had broken savevm/loadvm/migration, which does not apply to our aarch64 virt guest. — [QEMU issue #467](https://gitlab.com/qemu-project/qemu/-/issues/467)

### Inferences
- Pin the QEMU version used for the test VM, and check #3565 before relying on live revert with hvf on 11.0.x. Either pin 10.2.x for live snapshots, or take snapshots only while the VM is stopped (`stop`, then `snapshot-save`, then `cont`) if that path avoids the bug. Re-test after every QEMU upgrade with a smoke test: save, load, then click and assert.
- Disk-overlay reset (works on any accelerator, no vmstate): create a fresh qcow2 overlay on a read-only base per test (see Gaps for syntax), or use `-snapshot`, then throw the overlay away. Boot time is the cost: seconds on hvf, minutes on TCG x86_64.
- Live snapshots need no migration blockers (cited above). Use HMP `savevm`/`loadvm` or the QMP job-based equivalents (see Gaps).
- 9p: unmount the 9p share in the guest before savevm, or use virtio-serial or the guest agent for file transfer instead, so snapshots stay possible. The same applies to any other blocker-registering device. (Follows from commit 24f3902b.)
- Prefer the plain 2D virtio-gpu over GL/virgl variants for a snapshot-friendly test VM, since GL paths are more likely to carry unmigratable state (see Gaps).
- Speed: on hvf, loadvm cost is dominated by restoring guest RAM, so keep test-VM RAM modest (2 to 4 GB). Under TCG, loadvm skips a very slow boot and is therefore relatively more valuable, provided it works.

### Gaps
- No primary benchmark of savevm/loadvm time on hvf versus TCG was found.
- The exact QEMU version that introduced QMP `snapshot-save/load` was not confirmed from source in this session.
- No source confirming virtio-gpu migratability or virgl blockers was fetched.
- Not confirmed: the QMP `snapshot-save` / `snapshot-load` / `snapshot-delete` arguments (believed to be `job-id`, `tag`, `vmstate`, `devices`, added around QEMU 6.0) and the requirement that all writable disks be qcow2. The QMP reference fetch was truncated.
- Not confirmed: overlay syntax `qemu-img create -f qcow2 -F qcow2 -b base.qcow2 run.qcow2` (standard usage, not fetched).

## 7. Serial console and qemu-guest-agent for state checks alongside GUI driving

### Takeaway
Run a side channel next to the GUI. A serial console (`-serial`) gives boot logs and an emergency shell. qemu-guest-agent over virtio-serial gives structured `guest-exec` (with captured stdout/stderr) and `guest-file-read`. Use them to check ground truth (processes, files, logs) after GUI actions, never to perform the user-facing action.

### Cited Findings
- `guest-exec` (since 2.5): `path`, `arg`, `env`, `input-data` (base64 stdin), `capture-output`. The boolean form was added in 2.5; mode values `none|stdout|stderr|separated|merged` came in 8.0. Returns `{pid}`. — [QEMU guest agent reference](https://www.qemu.org/docs/master/interop/qemu-ga-ref.html)
- `guest-exec-status(pid)`: returns `exited`, `exitcode`, `signal`, base64 `out-data`/`err-data` (filled in only after exit), and `out-truncated`/`err-truncated`. It reaps the process once exited. — [QEMU guest agent reference](https://www.qemu.org/docs/master/interop/qemu-ga-ref.html)
- `guest-file-open(path, mode="r")` returns a handle. `guest-file-read(handle, count)` has a default count of 4 KB and a maximum of 48 MB, and returns `count`, `buf-b64`, `eof`. It is intended for "limited, ad-hoc debugging, such as log file access". Then call `guest-file-close`. All since 0.15.0. — [QEMU guest agent reference](https://www.qemu.org/docs/master/interop/qemu-ga-ref.html)
- `guest-sync-delimited(id)`: send a 0xFF byte before the request, on connect and after any timeout, and discard responses until the matching id returns. `guest-ping` checks liveness. — [QEMU guest agent reference](https://www.qemu.org/docs/master/interop/qemu-ga-ref.html)

### Inferences
- Wiring: a virtio-serial port named `org.qemu.guest_agent.0` backed by a host UNIX socket, plus `qemu-guest-agent.service` in the guest, and a serial console on a second UNIX socket (see Gaps for the unconfirmed syntax).
- Use QGA `guest-exec` to read GUI state that has no visible form, e.g. `swaymsg -t get_tree` for the focused window and geometry, `journalctl`, or app state files. Needed env: `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, and the session user (QGA runs as root, so `runuser -u <user> --` may be required).
- Guest agent commands can hang if the agent is not running. Always do `guest-sync-delimited` with a timeout before the first command, and treat timeouts as "guest unhealthy, take a screendump".
- Keep QGA in the test image only, or document it, because it gives the host full root control of the guest.

### Gaps
- Not confirmed: wiring syntax `-chardev socket,path=/tmp/qga.sock,server=on,wait=off,id=qga0 -device virtio-serial-pci -device virtserialport,chardev=qga0,name=org.qemu.guest_agent.0`; serial `-serial unix:/tmp/serial.sock,server=on,wait=off` with `console=ttyAMA0` (arm64 virt) or `console=ttyS0` (x86_64).
- QGA behaviour under hvf was not researched.
