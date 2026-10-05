# Parity run: what stock Alpine + XFCE does, asked of LLM OS

Each row is something the XFCE desktop (docs/research/parity-xfce.md) lets a person do with its menus, settings
pages and programs, said the way a person would say it. `tools/usecase-run.py --file docs/research/parity-tasks.md
--out run/parity` runs them against the test VM; changes are followed by the row that puts them back. Results are
summarised in docs/research/parity-results.md.

| ID | Request | XFCE equivalent → what LLM OS should do | P |
|---|---|---|---|
| Q01 | "open the file manager" | Thunar from the menu → Files opens | P0 |
| Q02 | "open a terminal" | xfce4-terminal → a terminal window opens | P0 |
| Q03 | "open the text editor" | Mousepad → an editor window opens | P0 |
| Q04 | "open the browser" | Firefox → opens | P0 |
| Q05 | "new tab" | Ctrl+T in Firefox → a new tab | P0 |
| Q06 | "maximize the browser" | title-bar maximize → full size | P0 |
| Q07 | "minimize the browser" | title-bar minimize → hidden | P0 |
| Q08 | "switch to the browser" | taskbar click → back in front | P0 |
| Q09 | "show the desktop" | Show Desktop button → windows out of the way | P0 |
| Q10 | "close the browser" | title-bar close → closed | P0 |
| Q11 | "task manager" | xfce4-taskmanager → processes listed with End buttons | P0 |
| Q12 | "how much disk space do i have" | Thunar free space / disk usage → storage panel | P0 |
| Q13 | "about this computer" | About Xfce / system info → computer and OS details | P0 |
| Q14 | "check for updates" | (apk) → updates panel | P0 |
| Q15 | "displays" | Display settings → screens and resolutions | P0 |
| Q16 | "set the resolution to 1024x768" | Display settings resolution → changed | P0 |
| Q17 | "set the resolution to 1280x800" | (put back) | P0 |
| Q18 | "rotate the screen" | Display settings rotation → rotated | P0 |
| Q19 | "the screen is upside down" | (put back) → normal | P0 |
| Q20 | "make the mouse faster" | Mouse settings acceleration → faster | P0 |
| Q21 | "mouse normal speed" | (put back) | P0 |
| Q22 | "turn on natural scrolling" | Touchpad settings → on | P0 |
| Q23 | "natural scrolling off" | (put back) | P0 |
| Q24 | "keyboard layout" | Keyboard settings → layout panel | P0 |
| Q25 | "set my time zone to tokyo" | Time and date settings → zone changed | P0 |
| Q26 | "set my time zone to UTC" | (put back) | P0 |
| Q27 | "turn the screen off after 5 minutes" | Power manager display blanking → set | P0 |
| Q28 | "turn the screen off after 10 minutes" | (put back) | P0 |
| Q29 | "turn on night light" | (redshift) → warmer screen in the evening | P1 |
| Q30 | "turn off night light" | (put back) | P1 |
| Q31 | "do not disturb" | Notification settings DND → on | P0 |
| Q32 | "turn off do not disturb" | (put back) | P0 |
| Q33 | "dark mode" | Appearance style Adwaita-dark → dark | P0 |
| Q34 | "use a serif font" | Appearance fonts → serif | P0 |
| Q35 | "go back to the default theme" | (put back) | P0 |
| Q36 | "make the text bigger" | Appearance DPI / font size → bigger | P0 |
| Q37 | "normal text size" | (put back) | P0 |
| Q38 | "turn the volume up" | panel volume plugin → louder | P0 |
| Q39 | "mute" | panel volume plugin → muted | P0 |
| Q40 | "unmute" | (put back) | P0 |
| Q41 | "sound settings" | pavucontrol → sound panel with output choice | P0 |
| Q42 | "wifi" | network applet → networks in range | P0 |
| Q43 | "bluetooth" | blueman → Bluetooth panel | P0 |
| Q44 | "printers" | system-config-printer → printers panel | P0 |
| Q45 | "take a screenshot" | xfce4-screenshooter → saved and copied | P0 |
| Q46 | "clipboard history" | clipman → what was copied | P1 |
| Q47 | "show my files" | Thunar home → the home folder | P0 |
| Q48 | "make a folder called Parity Test" | Thunar new folder → made | P0 |
| Q49 | "find my files called parity" | Catfish search → found | P0 |
| Q50 | "show the trash" | Thunar trash → the trash | P0 |
| Q51 | "what's on my usb stick" | Thunar side pane → drives panel | P0 |
| Q52 | "eject the usb stick" | Thunar eject → nothing plugged in (said so) | P0 |
| Q53 | "lock the screen" | xflock4 → locked (or offered a passphrase) | P0 |
| Q54 | "open the calculator" | (galculator) → a calculator | P0 |
| Q55 | "open the calendar" | (orage) → a calendar | P1 |
| Q56 | "open the image viewer" | Ristretto → opens | P0 |
| Q57 | "keep the screen on" | presentation mode → screen stays on | P1 |
| Q58 | "turn the screen off after 10 minutes" | (put back) | P1 |
| Q59 | "what can I do here" | Help / menu browsing → what it can do | P0 |
| Q60 | "show all my programs" | Whisker menu → programs and apps listed | P0 |
