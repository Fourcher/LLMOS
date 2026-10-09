# Computer control: fast and smart (AT-SPI first, OCR fallback) — design, 2026-10-09

The owner's task: "Make computer control fast and smart: AT-SPI accessibility for buttons and fields, OCR only
as a fallback. Test: open the calculator, press 7 + 2 =, read 9."

## What exists today (read from source + driven by hand on the 1.7.1 arm64 VM)

Three input surfaces, in order of how reliable they are:

1. OS webkit apps (the calculator, timers, trackers the OS builds): already have a DOM bridge, not OCR.
   - apps.py _BRIDGE: postMessage({llmos:"press",text}) finds the element whose aria-label/value/innerText
     matches and clicks it; postMessage({llmos:"read"}) returns {text, controls[]}.
   - desk.app_press(text) / desk.app_read() drive it. Exact and fast — better than AT-SPI for the OS's own apps.
2. Native windows (Firefox, the foot terminal, GTK dialogs, system dialogs): only control.py exists —
   grim screenshot + tesseract OCR to find words/boxes, wlrctl to click, wtype to type. Slow and fuzzy.
   This is where AT-SPI belongs.
3. agent._screen_steps splits "press 7 then + then 2 then =" into steps and calls the click tool per key, which
   dispatches to (1) for an OS app or (2) for a native window.

## Why the owner's calculator test does not pass cleanly today (measured)

Driven by hand in the VM (CPU model):
- Opening the calculator works: llmos say "open the calculator" -> window app-calculator.
- llmos say "press 7" returns an empty spoken reply (the press may register, but nothing is said back).
- llmos say "open the calculator, then press 7 then + then 2 then = and tell me the result" routes to the
  on-device model (because "open ..." and "tell me the result" are not deterministic steps) and times out >120 s
  on the VM's CPU.
- _screen_steps reports "pressed 7, pressed +, ..." — it never reads the display and speaks the result.

So the gap is two-fold: the open + "tell me the result" fall to the slow model, and the press pipeline does not
read back the computed value.

## Plan

Milestone 1 — pass the owner's test deterministically (no model).
- A deterministic route for "[open the calculator] (then) press <k1> (then) <k2> ... (and tell me the result)":
  open the named app if asked, app_press each key in order, then app_read and speak the shown value (e.g. "9").
  Bare "press X" on an open app should also say a short confirmation or the current value, not "".
- Host-testable: the step/key parser. VM-testable: the calculator run is now fast (no model).

Milestone 2 — AT-SPI for native windows (the broader goal).
- Package: add at-spi2-core from Alpine's signed repos (AT-SPI D-Bus + Atspi-2.0 GI typelib; py3-gobject3 already
  installed). Confirm the exact typelib package at build time; no outside downloads.
- control.py: add atspi_controls() / atspi_find(target) / atspi_click(target) / atspi_set_text(field,text) using
  gi.repository.Atspi to enumerate accessible objects (role, name, position) of the focused app and act via AT-SPI
  actions. Guard with an available() check.
- Make read_screen(), find(), field_for() try AT-SPI first and fall back to OCR when AT-SPI yields nothing (the
  foot terminal and non-a11y apps stay on OCR).
- VM-testable: open the file manager / a GTK dialog and click a button by name via AT-SPI; foot still via OCR.

Order: Milestone 1 first (it is the acceptance test), then Milestone 2. Both ship in the 1.7.2 image build.
