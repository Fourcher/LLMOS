# 06 Settings, appearance and languages

## Task and verdict
Area: Settings, appearance and languages (light/dark, text size, Spanish and back, accent colour, wallpaper, auto-lock, desk layouts). Every window opened was closed and every setting was returned to its starting value.

**Verdict: PARTLY.** Light/dark, text size, accent, wallpaper request, layouts and the Settings list work. Language switching is the weak point: a Spanish-to-English request was misread and produced a raw tool-call string, several strings stay English in Spanish, and the 15-minute auto-lock request said "done" but did not change the setting.

Starting state (recorded before any change): Autonomy "full trust"; Internet "yes"; Where it thinks "Only on this computer"; Guidance "Follows my instructions"; Language English; Settings language default; Looks: none selected; Font Sans; Background Living (animated); Corners rounded; Text size 100%; Desk layout Clean; Animations Full; Speak replies off; Focus mode off; Encrypted storage on; Auto-lock never; Volume 40%; keyboard layout English (US). The info block showed Text colour #e8e9ef, Background #0b0d14, Accent #7a52ff.

Note on the brief: the request said to put auto-lock "back to 10". There is no 10 option (never / 5 min / 15 min / 60 min) and it was "never" at the start, so I restored "never".

## Steps
1. **Open Settings** ("open settings"): opened in 2-3 s. Scrolled every section: Autonomy, Internet, Where it thinks, Guidance, Conduct, the info block, Language, Looks, Font, Background, Corners, Text size, Desk layout, Animations, toggles, Encrypted storage, Auto-lock. All sections render and fit the window. Screenshots: settings-open.png, settings-s2..s9.png, settings-top2.png.
   - Top tabs (Network, Sound, Displays, Keyboard and mouse, Bluetooth, Printers, Drives, Storage): Sound, Displays and Keyboard and mouse opened. Network opened too (see Bugs). Printers, Drives, Storage, Bluetooth were not opened.
2. **"switch to light mode"**: reply "Done — light mode." in about 2 s; desk turned light. Screenshot light-mode.png.
   **"dark mode"**: reply "Done — dark mode." in about 2 s. Screenshot dark-mode.png.
3. **"make the text bigger" x2**: 120%, then 140%. "While you were away" grows and its bottom runs to the edge of the screen; the reply card covers part of it; nothing clipped at the top bar. Screenshot text-big2.png.
   **"make the text smaller" x2**: 120%, then 100%. Back to start. Screenshot text-small2.png.
4. **"change the language to Spanish"**: reply "Done — language Español." in about 2 s. Desk, Settings and Files switched to Spanish (see Bugs for what stayed English). Screenshots lang-es-1.png, lang-es-settings.png, lang-es-files.png.
   **"abre mis archivos"**: took 114 s to reply ("6 items in ~."). Files window opened as "Inicio".
   **"cambia el idioma a inglés"** (typed without the accent; see Bugs): took about 3.5 minutes. The reply was a raw tool-call string and the language stayed Spanish. Fixed by choosing English in the Settings language list (click). Reply "Done — language English." Screenshot lang-en-restored.png.
5. **"change the accent colour to green"**: reply "Done — accent green." in about 2 s; accent and the living background went green. Screenshot accent-green.png.
   **"reset the accent colour"**: reply "Done — accent green." and the accent stayed green (see Bugs).
   **"change the accent colour back to purple"**: reply "Done — accent purple." in about 13 s; accent back to purple. Screenshot accent-purple2.png.
6. **"change the wallpaper to mountains"**: reply "Wallpaper set: Himalayas, Ama Dablam, Nepal.jpg (Vyacheslav Argenberg, CC BY 4.0)." The desk still showed the purple living background, no mountain picture (see Bugs). Screenshots wallpaper-mountains.png, wallpaper-m2.png, wallpaper-m3.png.
   **"put the wallpaper back"**: reply "Wallpaper put back to how it was" in about 2 s.
7. **"set the screen to turn off after 15 minutes"**: reply "The screen turns off after 15 minutes without use." Settings opened after that still showed "never" (autolock-15b.png). I clicked "15 min" in Settings to confirm the control works (autolock-click15.png: "Auto-lock after 15 minutes of inactivity"), then clicked "never" (autolock-restored.png: "Auto-lock is off").
8. **"switch to the windows layout"**: reply "Done — the layout is now Windows-style." in about 3 s. Taskbar at the bottom; the whole theme went blue (see Friction). Screenshot layout-windows2.png.
   **"switch to the mac layout"**: reply "Done — the layout is now Mac-style." in about 2 s. Traffic-light buttons on windows; dock at the bottom with Settings, Files, Lists. Screenshot layout-mac2.png.
   **"switch to the clean layout"**: reply "Done — color reset, background reset, accent reset, layout clean." Screenshot layout-clean2.png. Settings then showed Text colour, Background and Accent as "default" (was hex values). Auto-lock, Clean layout, Living background, Full animations, Language English, rounded corners, Sans font and 100% text were all as at the start (clean-s2..clean-end.png).
9. **Closed every window**: Settings, Sound, Displays, Network, Keyboard and mouse, and Files. Left only "While you were away", which was already open at the start.

## Bugs
1. **"cambia el idioma a ingles" was misread and changed the wrong setting.** Typed as "cambia el idioma a ingles" (no accent, because the test tool cannot type é). The desk log showed "change setting ... change guidance -> english" twice, and the reply was the raw text `[TOOL_CALLS]run_command[ARGS]{"command": "export LANG=en_US.UTF-8"}`. Guidance was still "Follows my instructions" afterwards, so the net effect looked nil, but the request was never met. Should: switch to English, reply in plain words, and not touch Guidance. Screenshot lang-back-en2.png.
2. **Language change took about 3.5 minutes** (the "cambia..." request, busy for the whole time) before it returned the raw string. Should be seconds.
3. **Spanish is only partly translated.** Still English after switching to Spanish: the "While you were away" window and its "Updated" / "Remote testing on" items; the reply bar text "Here it is."; reply card labels ("change the look", "Done — language Español."); the Files toolbar ("Open in Files", "A–Z", "Newest", "Biggest", "Show hidden files"); the Files reply "6 items in ~."; the Settings Keyboard and Mouse / Displays / Sound sub-windows (not checked in Spanish). Settings labels that were translated are fine, but a few are cut off: "equilibrado: pregunta antes de acciones destructivas o irrev".
4. **Settings window does not refresh after a language change.** After choosing English in the list, the Settings window still showed "Idioma Español" and Spanish labels until it was closed and reopened.
5. **Sub-windows open behind Settings.** Network, Keyboard and mouse opened behind the Settings window, with its text showing through. Esc then closed Settings instead of the Network window. Screenshots settings-network.png, settings-network2.png, network-esc.png, settings-keyboard.png, kb-close.png.
6. **Network reply is wrong in context.** Opening Keyboard and mouse replied "Check the cable or batteries and try another USB port." Nothing was wrong.
7. **15-minute auto-lock said done but did nothing.** "set the screen to turn off after 15 minutes" replied "The screen turns off after 15 minutes without use", but Settings still said "never". Only clicking "15 min" in Settings worked. Screenshot autolock-15b.png.
8. **"reset the accent colour" did not reset.** Reply "Done — accent green." while the accent stayed green. "change the accent colour back to purple" did work. Screenshots accent-now.png, accent-purple2.png.
9. **Wallpaper not visible.** "change the wallpaper to mountains" replied with the Himalayas picture name and CC BY credit, but the desk still showed the purple living background (wallpaper-m3.png). Either the living background hides the wallpaper or the image did not load. The reply also dumps an attribution line that a person does not need.
10. **"switch to the clean layout" reset colour, background and accent too.** Reply "Done — color reset, background reset, accent reset, layout clean." The user asked only for the layout. Afterwards the info block showed Text colour, Background and Accent as "default" (they were #e8e9ef, #0b0d14, #7a52ff at the start). Looks the same on screen, but the saved values changed. Owner should confirm this is acceptable.
11. **Windows layout re-colours the whole desk blue.** Switching to Windows style turned the background and accent blue, which is not a layout change.
12. **Displays shows resolutions that do not fit the screen.** The panel "Resolution: Virtual-1" lists 5120x2160, 4096x2160, 3840x2160, 2560x1080, 2048x1152 and 1920x1440 for a 1280x800 display, with no current one highlighted. I did not click them.
13. **Esc closes the focused Settings window** without warning (see 5).

## Friction
- Starting the test with the lock screen takes one passphrase entry; fine.
- Spanish request "abre mis archivos" took 114 s; the "cambia el idioma" request about 3.5 min. Both far above the 30 s mark.
- The reply card for every change repeats the request and adds "· change the look" / "· set appearance" lines, which is noisy for simple changes.
- Settings has many sections in one long list with no headings at the top; the tabs (Network etc.) are the only navigation and they open separate windows.
- "Settings language" and "Language" both appear in the info block with different meanings and "default" vs "English"; hard to read.
- Autonomy and Guidance sections are long, with some wording that is hard to follow ("Conduct (under the hood)", "Standard caution").
- The reply bar overlaps the bottom of the Settings window (the "Here it is." strip sits over the Settings content).
- Typing accented letters is not possible through the test tool, so the Spanish "inglés" request could not be sent as written. A person typing on a keyboard would be fine.

## Ideas
- Say the result in the current language (reply "Hecho" when the desk is in Spanish) and translate the Files toolbar and reply strings.
- Refresh an open Settings window on language change, or close and reopen it.
- Open Settings sub-windows on top of Settings, not behind.
- Make "reset the accent colour" reset only the accent; make "switch to the clean layout" change only the layout.
- Auto-lock: add a "10 min" option if the owner wants one, or make the voice command write the setting.
- Hide the wallpaper attribution from the reply, or put it in About.
- Show the current accent, text colour and background values as named choices with a reset, not hex.
- Replace the Displays resolution buttons with only the sizes the screen supports, and mark the current one.

## Verdict line for the sweep
PARTLY: light/dark, text size, accent, layouts and the Settings list work; language is the worst (misread request with a raw tool-call reply, 3.5 min wait, half-translated Spanish, Settings not refreshing), and the 15-minute auto-lock and accent-reset voice requests reported success without doing it. Wallpaper reply does not match the screen.
