# 24 retest-settings-answers

## Task and verdict

Retest of earlier fixes: language and colour reversals in Settings, wallpaper set and restore, and the everyday answers (model, wifi, disk space, web search, version).

**Verdict: PARTLY.** Language, colour, model, wifi, and version work. The wallpaper restore does not bring back the picture that was showing at the start. The disk-space reply gives numbers that disagree with the Storage window on the same screen. The Tokyo search gives a sourced figure but takes 85 s.

| # | Check | Verdict |
|---|-------|---------|
| 1 | Language Spanish, then back to English | PASS |
| 2 | Colour purple, then back to dark | PASS |
| 3 | Wallpaper mountains, then restore | FAIL (restore) |
| 4a | "which model are you using?" | PASS |
| 4b | "how do I connect to wifi?" | PASS |
| 4c | "how much disk space do I have" | FAIL (reply and window disagree) |
| 4d | "search the web for the population of Tokyo" | PASS, slow (85 s) |
| 4e | "what version is this" | PASS |

## Baseline (before any change)

- Settings: Autonomy "full trust", Internet "yes", Tor off, Where it thinks "Only on this computer", Guidance "Follows my instructions", Language English, Settings language default, Text color #e8e9ef, Background #0b0d14, Accent #7a52ff, Version 1.8.6c, Font Sans, Corners rounded, Text size 100%, Animations Full, Background "Living (animated)" (checked after the wallpaper test; not checked before it).
- VM gsettings: picture-uri adwaita-l.jxl, color-scheme default, text-scaling-factor 1.0, enable-animations true.
- Desk at start: sepia mountain picture (run/sweep/shots/24-pre-wallpaper.png, also 24-start.png). Top bar: "Ministral 3 3B", "On its own".

## Steps

Times are from the request to the reply (`vmuser.py waitreply`).

1. **"pull up a settings menu"**: reply "Here it is." Settings opened, 2 s. Shot 24-settings-open.png.
2. **"change the language to Spanish"**: reply "Done — language Español." 2 s. Shot 24-es-1.png. UI switched to Spanish (clock, "Hacer", "Historial", "Cerrar"). The chat card's label reads "· change the look" (wrong label for a language change).
3. **"change the language back to English"**: reply "Done — language English." 2 s. Shots 24-en-back.png, 24-after1-scroll1 to 4, 24-after1-top.png. Compared with the baseline: Autonomy full trust, Internet yes, Tor off, Where it thinks "Only on this computer", Guidance "Follows my instructions", Language English, Settings language default, colours, Version, Looks, Font Sans all unchanged. VM gsettings unchanged (color-scheme default, text scaling 1.0, animations true).
4. **"set the colour to purple"**: reply "Done — purple theme." 2 s. Shot 24-purple.png. Desk and windows took a purple tint.
5. **"change the colour back to dark"**: reply "Done — dark mode." 2 s. Shots 24-dark-back-top.png, 24-dark-back-look.png, 24-dark-back-accent2.png. Background #0b0d14, Accent #7a52ff, Text #e8e9ef, Autonomy, Internet, Tor, Where it thinks, Guidance all unchanged from baseline. Only the look changed back.
6. Closed Settings (X at 1233,89).
7. **"set my wallpaper to a picture of mountains"**: reply "Wallpaper set: Himalayas, Ama Dablam, Nepal.jpg (Vyacheslav Argenberg, CC BY 4.0)." 2 s. Shot 24-wallpaper-mountains.png: snow-capped Himalayan peaks fill the desk. PASS.
8. **"put the wallpaper back to how it was"**: reply "Wallpaper removed." 2 s. Shot 24-wallpaper-restored.png: desk now shows the animated purple "Living" glow, not the sepia mountains that were there at the start. FAIL. Settings > Background still reads "Living (animated)". The chat says "removed", not "restored".
9. Re-opened Settings and scanned the Background section: Living (animated) selected, Still and Plain available. Closed Settings again. Shots 24-bgs4 to 8, 24-living-a and 24-living-b (the glow moves over time).
10. **"what version is this"**: reply "This is LLM OS 1.8.6c (build 2026-10-14, aarch64). Updates come from Jordans-Mac-Mini.local; the last one (1.8.6c) was installed." 2 s. Matches the Settings Version row. PASS.
11. **"which model are you using?"**: reply "I'm using Ministral 3 3B on this computer (2.1 GB). Change it on the Models page." 2 s. Matches the top-bar model name. PASS.
12. **"how do I connect to wifi?"**: reply "This computer has no Wi-Fi. It's online through its network cable." 2 s. The Network window opened on the right at the same time (shot 24-wifi.png). Panel says "Now: Connected (cable). This computer has no Wi-Fi; plug in a network cable." Reply and panel agree. PASS.
13. Closed Network window.
14. **"how much disk space do I have"**: reply "You have 3.4 GB free of 4.0 GB. The details are in the window." 2 s. The Storage window opened (shot 24-disk.png, 24-tokyo.png). The Storage window shows "9.0 GB free of 15.5 GB", with Disk bar, Documents 2 B, Pictures 192 KB, On-device models 2.1 GB, Trash 379 B, Caches 153.6 MB. The reply and the window disagree about total and free space. FAIL on consistency. The numbers are present, though.
15. **"search the web for the population of Tokyo"**: reply "Tokyo's population in 2026 is approximately **14,264,798 residents**." Took **85 s**. A Sources window opened with the link "Tokyo Population 2026 — 14,264,798 People | Gro...". Figure and source both present. PASS, but over the 30 s mark (under 2 min). Shot 24-tokyo.png.
16. Closed Sources window (X at 465,153) and Storage window (X at 1233,89). Shot 24-final.png: only "While you were away" open, as at the start.

## Bugs

1. **Wallpaper restore does not restore the picture.** Words typed: "put the wallpaper back to how it was". Saw: reply "Wallpaper removed", and the desk changed from the sepia mountain picture to the animated purple "Living" glow. Should have: put back the sepia mountain picture that was showing before the change. Caveat: I did not check Settings > Background before the mountain change, so I cannot rule out that the sepia picture was itself the Living background at a certain frame. If it was not, this is a fail. The VM is left on Living (animated), with the original file unidentified. The owner should confirm the starting background. The wallpaper set by the first request is also not recorded in the VM's gsettings (picture-uri still reads adwaita-l.jxl after the change), so the app keeps its own record of the wallpaper.
2. **Disk-space reply does not match the Storage window.** Words typed: "how much disk space do I have". Saw: reply "3.4 GB free of 4.0 GB", Storage window "9.0 GB free of 15.5 GB" on the same screen. Should have: the same figures in the reply and the window.
3. **Language reply labelled "change the look".** Words typed: "change the language to Spanish". The chat card's label under "LLM OS" reads "· change the look" instead of "change the language". Cosmetic.

## Friction

- Tokyo search took 85 s before the figure arrived. Under 2 min, over the 30 s mark.
- The "Wallpaper removed" reply does not say what the desk now shows, so the person cannot tell whether the restore worked.
- The Sources window opens on top of "While you were away" and covers its text.
- Settings > Background sits between Font and Corners far down the list. Hard to find without scrolling.

## Ideas

- Make "put it back" restore the exact previous wallpaper (file or Living/Still/Plain mode) and say which one in the reply.
- Make the disk reply read its numbers from the same source as the Storage window.
- Use "change the language" as the card label for language changes.

## Cleanup

- Language: English (as found).
- Colour: dark (as found), Background #0b0d14, Accent #7a52ff.
- Wallpaper: NOT restored to the sepia picture. Now Living (animated) (see Bug 1).
- Windows: Settings, Network, Storage and Sources closed. "While you were away" left open (it was open at the start).
- Screenshots: run/sweep/shots/24-*.png.
