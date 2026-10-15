# 15. Power, voice and display (real laptop)

## Task
Area "power, voice and display" on the real x86-64 laptop (Intel + NVIDIA, 1920x1200): restart and recovery, microphone, night light, brightness, a one-minute reminder with its notice and sound, and lock/unlock. Restart was allowed for this task only.

## Verdict
PARTLY. Restart, brightness, the reminder notice and lock/unlock work. The night light changes the screen only slightly, the sound of the reminder could not be confirmed, the microphone listens but was not tested with speech, and there is no lock icon anywhere.

## Steps

1. **Restart** (power icon, top right, Restart). Expected: laptop comes back by itself, normal desk.
   - Power panel showed Battery 100%, Sleep / Restart / Shut down. Clicked Restart (not Shut down). No confirmation asked.
   - Clock 02:33:26 at click. First `state` poll 20 s later failed. Answered by the 40 s poll. Uptime was 1 min at 02:34:50, so the reboot took about a minute. Total time to a working desk about 80 s.
   - Result: normal desk, unlocked, no error dialog. Screenshot `dev-15-after-restart`.
   - Difference: after the restart the whole UI is drawn larger (top bar text and request box are roughly 1.4x what they were before the restart). Screenshot `dev-15-start` vs `dev-15-after-restart`.
   - "While you were away" came back after the restart with the same three "Updated" rows it had before.

2. **Microphone** (button next to the request box). Expected: a listening sign, then stop on Esc.
   - Click: red mic button and the pill "Listening... speak, then pause." Screenshot `dev-15-mic-on`.
   - Esc: the pill went and the screen said "I didn't hear anything." Screenshot `dev-15-mic-stopped`. Esc also closed the "While you were away" panel, which I had not expected.
   - `arecord -l` on the laptop lists three capture devices on card 0 (HDA Analog, DMIC, DMIC16kHz). So the laptop has a real microphone. I did not speak, so recognition was not tested.
   - Time: under 2 s to start listening.

3. **Night light** ("turn on night light", then "turn off night light").
   - On: reply "Night light is on: the screen is warmer now, until 7 am" in 2 s. Panel showed "change night_light -> on". `wlsunset -t 3800 -T 6500 -S 07:00 -s 19:00` is running on the laptop.
   - Screen colour (average of sampled pixels, `dev-15-nightlight-before` vs `dev-15-nightlight-on`): before R 36 G 56 B 77; after R 36 G 53 B 71. The change is small: the desk still looks mostly blue. A capture may not include the gamma change, so this is inconclusive.
   - Off: reply "Night light is off" in 2 s. `wlsunset` is no longer running. Screenshot `dev-15-nightlight-off` (the reply panel covers part of the wallpaper, so colours are not comparable to the on-shot).

4. **Brightness** ("set the brightness to 30%", then "set the brightness to 100%").
   - Before: intel_backlight max 96000, brightness 96000.
   - 30%: reply "Brightness set to 30%." in 2 s. brightness 28800 (30%). Screenshot `dev-15-bright-30`.
   - 100%: reply "Brightness set to 100%." in 2 s. brightness 96000. Screenshot `dev-15-bright-100`.

5. **Reminder** ("remind me to stand up in 1 minute").
   - Set at 02:35:55. Reply: "Reminder set for 02:36: stand up." (2 s). So "1 minute" became the clock minute 02:36, about 5 s away, not a full minute. The firing time was not captured exactly. The alarm was on screen at my 02:37:37 check.
   - What appeared: a toast "Reminder: stand up" at top centre, an alarm window "⏰ Reminder: stand up" with OK, and a "While you were away" row. Screenshots `dev-15-reminder-fired` (taken 02:36:04, reply still showing "Reminder set") and `dev-15-reminder-check` (02:37:37, alarm window on screen).
   - Sound: ALSA `pcm0p/sub0/status` read "closed" at 02:36:04 and 02:37:43 (idle). I did not catch the moment of the alarm, my polling loop failed on a shell error, so I could not confirm any sound. The laptop logs (journal, grep for reminder/sound) had nothing to check.
   - Pressing OK made a new "Open now" panel appear: "While you were away, on the desk". It was not clear what it was for.

6. **Lock** (lock icon).
   - No lock icon exists in the top bar (icons: apps grid, model pill, "On its own", wifi, volume, battery, power). The power panel has only Sleep / Restart / Shut down. The apps grid has no lock. Settings tabs (Network, Sound, Displays, Keyboard and mouse, Bluetooth, Printers, Drives, Storage) and the Autonomy section have no lock or passphrase option. `find lock` and `find passphrase` both returned NOT FOUND.
   - Then typed "lock the screen" in the request box: reply "Done." Lock screen: "Locked. Press Unlock to come back. (Tip: with a passphrase, only you can. Say 'set a passphrase' any time.)" with an Unlock button. Screenshot `dev-15-lock-try`.
   - Unlock: one click returned to the desk without asking for anything. Screenshot `dev-15-unlocked`.
   - No passphrase was set (I did not set one).

## Bugs
- **Lock icon missing.** The brief expects a lock icon; the only way found was the request "lock the screen". Nothing on the desk says that.
- **Night light barely visible.** The reply says the screen is warmer, but the screenshot changes only a little (blue 77 to 71 on average). At 3800 K it should look clearly orange.
- **Sound not confirmed.** The reminder notice appeared on screen, but I could not confirm a sound.
- **Reminder time.** "Remind me ... in 1 minute" was set for 02:36, which was only a few seconds away. The reply does not make that clear.
- **Esc closed a panel.** Pressing Esc to stop listening also closed the "While you were away" panel.
- **Stale notice comes back.** "While you were away" showed the same three old "Updated" rows after the restart. It reappeared at 02:37 with the reminder row.
- **Extra panel after OK.** Clicking OK on the reminder opened "Open now: While you were away, on the desk", with no explanation.
- **UI scale changed after restart.** Text and controls are about 1.4x larger than before the restart, which looks like a display-scale setting not kept across a reboot. Compare `dev-15-start` and `dev-15-after-restart`.

## Friction and Ideas
- A lock icon, or a "Lock" entry in the power panel, would make step 6 findable.
- The reminder reply could say the actual time it will fire, and "in 1 minute" should mean one minute from now.
- A visible sign when the reminder sounds (or a note that it is silent) would help.
- Night light could show its current colour temperature in the reply.
- The microphone was not spoken to, so recognition is untested.

## Screenshots
`dev-15-start`, `dev-15-power-menu`, `dev-15-after-restart`, `dev-15-mic-on`, `dev-15-mic-stopped`, `dev-15-nightlight-before`, `dev-15-nightlight-on`, `dev-15-nightlight-off`, `dev-15-bright-30`, `dev-15-bright-100`, `dev-15-reminder-set`, `dev-15-reminder-fired`, `dev-15-reminder-check`, `dev-15-after-ok`, `dev-15-grid-menu`, `dev-15-onits-own`, `dev-15-settings-scrolled`, `dev-15-lock-try`, `dev-15-unlocked`, `dev-15-closed`.

## Cleanup
Closed the reminder, the "While you were away" panel and the "Open now" panels. Settings was closed; autonomy still reads full trust. Night light is off. Brightness is 100% (96000). The microphone is idle. The reply bar at the bottom closes on its own. The laptop was left on the normal desk, unlocked.
