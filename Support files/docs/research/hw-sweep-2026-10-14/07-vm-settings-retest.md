# VM settings retest 2026-10-14

Tester: Haiku 5.5 (via tools/vmuser.py). VM build: LLM OS 1.8.9.17 (per Settings > Version). Start and end state: English, accent default, screen-off 0 (never), autolock never. Only the "While you were away" window was open at start and end; it was there before I started and I left it.

## Verdict

- 1 Spanish: PASS (accent caveat, see below)
- 2 French: PASS
- 3 Accent green and reset: PASS
- 4 Screen-off 15 / 10 minutes: FAIL (Settings never shows the value)
- 5 Next Friday: PASS
- 6 Delete missing "Sweep" folder: PASS
- 7 Rainbow in two sentences: PASS (26 s)

Overall: WORKS except item 4. Worst problem: the screen-off request saves a value that Settings does not show, and Settings shows a different setting (Auto-lock) as "never".

## Steps

Times are from the waitreply output (time from sending to reply) and the clock.

1. **"change the language to Spanish"** (23:44:10). Reply "Done — language Español." in 3 s. Screenshot `run/sweep/shots/t1-spanish.png`: whole UI now in Spanish. PASS.
   - **"cambia el idioma a inglés"**: the typing tool cannot send "é" (it raised "no key mapping for character U+00E9"), so the request was not sent. Box was checked empty (`t1b-precheck.png`). Retried as "cambia el idioma a ingles" (23:44:26). Reply "Done — language English." in 3 s. Screenshot `t1b-english-back.png`: English, normal reply. PASS. The accented form itself was not tested because the tool cannot type it.
2. **"change the language to French"** (23:44:34). "Done — language Français." in 3 s (`t2-french.png`). **"mets la langue en anglais"** (23:44:45 start). "Done — language English." in 3 s. Screenshot `t2b-english-back.png`: English. PASS.
3. **"change the accent colour to green"** (23:44:48). "Done — accent green." in 3 s. Screenshot `t3-accent-green.png`: orb, send button and window borders are green. **"reset the accent colour"** (23:44:56). "Done — accent reset." in 3 s. Screenshot `t3-accent-reset.png`: orb, send button and borders are back to the default purple, same as the starting screenshot `start-state.png`. Settings > Looks/Accent reads "default". PASS.
4. **Open Settings and find the screen-off value.** Settings has no row called screen-off. It has an AUTO-LOCK group (never / 5 min / 15 min / 60 min), currently "never" (`t4-settings-scrolled6.png`). I treated Auto-lock as the closest match and checked it.
   - **"set the screen to turn off after 15 minutes"** (23:46:20). Reply "The screen turns off after 15 minutes without use" in 2 s. Chat tag shows "change screen_off -> 15" (`t4-15min.png`). Settings was closed and reopened (23:46:26): Auto-lock still shows "never" (`t4-15min-verify.png`). The stored file `/etc/llmos/settings.json` has `"screen_off": 15` and `"autolock": 0`. FAIL: the Settings screen does not show 15 minutes.
   - **"set the screen to turn off after 10 minutes"** (23:47:09). Reply in 3 s. Stored `screen_off` is 10, Auto-lock still "never" in Settings (`t4-10min.png`). Same FAIL.
   - Restored: **"set the screen to never turn off"** (8 s). Reply "The screen stays on". Stored `screen_off` is 0. Settings closed.
   - Baseline caveat: I did not read `screen_off` before my first change, so I cannot prove the original value. 0 was used because the VM's own test reset sets it to 0 (`/usr/lib/llmos/llmos/desk.py` around line 4864). If it was originally unset, the code default is 10 (desk.py line 2281), so the true original may differ.
5. **"what's the date next friday"** (23:47:24). Reply in 2 s: "This coming Friday is October 16; next week's is October 23." Names Friday with a date. PASS (it gives two Fridays, which is a reasonable reading of "next friday").
6. **"delete the Sweep folder"** (no such folder). Reply in 2 s: "There's nothing called Sweep to delete." Nothing deleted. Screenshot `t6-delete-sweep.png`. PASS.
7. **"explain how a rainbow forms in two sentences"** (sent right after item 6, finished 23:48:02). Reply in 26 s, exactly two sentences, normal prose (`t7-rainbow.png`). PASS, under 30 s.

## Bugs

1. **Screen-off not shown in Settings (item 4).** Typed: "set the screen to turn off after 15 minutes", then "...after 10 minutes". Saw: chat says it is done, stored value changes, Settings > Auto-lock still reads "never" after a fresh reopen. Should: Settings shows the screen-off value (15 or 10 minutes). Also the Settings Auto-lock control is a different setting (`autolock`), with no label that says "screen off". Either the chat request should write `autolock`, or Settings should show `screen_off` as "Turn off screen after".
2. **Settings pane did not repaint when a tab was clicked (found during step 4).** Clicked "Displays" in Settings (913,152). The tab highlighted but the list stayed on Autonomy, with faint ghost text behind it. Scrolling did not fix it. Closing and reopening Settings showed the normal list. Should: the page changes when the tab is clicked.
3. **Typing limit (not an LLM OS bug).** The VM typing tool cannot type "é", so the accented Spanish request could not be tested. Recorded so the next tester knows.
4. **Possible mismatch (not fully checked).** `/etc/llmos/settings.json` shows `"autonomy": "hands-off"`, while Settings had "full trust: does everything you say without asking" selected (`t4-settings-open.png`). I did not change anything here; worth a check.

## Friction

- Finding the screen-off value took many scrolls (Settings is long, about 25 screens). No search in Settings.
- Opening "Displays" by clicking the tab gave a stale page (bug 2). Asking "open display settings" opened a separate Displays window that only shows resolution, which is confusing.
- Language switch: "Done — language Español." and the whole UI changed within 3 s. Good.
- Accent reset went back to exactly the default colours. Good.
- The chat card keeps the old reply text while the new one arrives; a little confusing but harmless.

## Ideas

- Add a "Turn off screen after" row next to Auto-lock in Settings, reading `screen_off`, with options never / 5 / 10 / 15 / 60 min.
- Add a search box in Settings, or group screen and lock options under "Power and screen".
- Say "turn off screen" in Settings labels, so the spoken and visible words match.
- Settings should re-render when a chat request changes a setting.
