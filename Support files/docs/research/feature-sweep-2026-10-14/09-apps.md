# 09 apps

## Task
Find, install, open and remove programs. Show my apps, open two from the list by clicking (calculator and text editor), close them. Install VLC, wait, open it, close it, uninstall it. Open the calculator, work out 12 x 7 + 3 by clicking, ask what it shows.

## Verdict
PARTLY. Listing, opening by click, the calculator and uninstall work. Install reports success and the package is really installed, but "open VLC" fails: it tries to start mpv and crashes with an X11 assertion. VLC never appears in the apps list.

## Steps

| # | What I did | Expected | What happened | Time | Screenshot |
|---|---|---|---|---|---|
| 1 | Checked VM state (desk, not busy) | Clean desk | Desk with "While you were away" (1.8.5 installed) | - | 09-start.png |
| 2 | Said "show my apps" | Apps window with list | Apps window: Programs (AbiWord, Archive manager, Files, Firefox, Gnumeric, Image viewer, Terminal, Text editor), Make one (Scientific calculator, Calculator, Calendar, Clock, Converter, Countdown, Dice, Flashcards) | 2 s | 09-show-apps.png |
| 3 | Clicked "Text editor" | Editor opens | Mousepad opened with a red banner "Warning: you are using the root account. You may harm your system." | <3 s | 09-open-texteditor.png |
| 4 | Dragged the editor window left to uncover the list | Window moves | Moved | - | 09-moved-editor.png |
| 5 | Clicked "Calculator" in the list | Calculator opens | Calculator opened with the reply "Here's your Calculator. It's kept in your apps". It sits under "Make one", so it was generated on the spot, not started from an installed program. | ~5 s | 09-open-calc.png |
| 6 | Closed Calculator (x) and Mousepad (x) | Both close | Both windows closed, but a "Mousepad" chip stayed at the bottom left. The process was still running in the VM. Clicking the chip's x stopped it. | - | 09-closed-two.png, 09-chip-closed.png |
| 7 | Said "install VLC" | Install runs, then a clear result | Reply "Installed: vlc -- open it by name." The package really installed (apk db changed at 11:56:44, vlc-libs trigger ran, /usr/bin/vlc present). It finished before my first check at about 10 s, so I saw no progress at all. | <10 s | 09-install-t1.png |
| 8 | Said "open VLC" | VLC window opens | Reply: "Could not start mpv Media Player: it closed at once (Assertion failed: !vo->x11 (../video/out/x11_common.c: vo_x11_init: 679))." No window. | 2 s | 09-open-vlc.png |
| 9 | Said "open the video player" (second natural wording) | Same, or a window | Same mpv error, same text | 3 s | 09-open-vlc-alt.png |
| 10 | Said "show my apps" again | VLC listed | VLC is not listed. Calculator now appears as an app with Open and Remove buttons. | 2 s | 09-apps-after-install.png |
| 11 | Said "uninstall VLC" | VLC removed | Reply "Removed vlc". Confirmed in the VM: `command -v vlc` is empty and `apk info -e vlc` shows nothing. | 2 s | 09-uninstall-vlc.png |
| 12 | Clicked "Open" on Calculator in the Apps window | Calculator opens | Opened, reply "Opened the app 'Calculator'." | ~3 s | 09-calc-open.png |
| 13 | Clicked 1, 2, x, 7, + 3 (six clicks, 0.7 s apart) | Display shows 12 x 7 + 3 | Display "84 +" then "3" | - | 09-calc-before-equals.png |
| 14 | Clicked = (at the very bottom edge of the window) | 87 | Display "84 + 3 =" and "87". Correct. | 1 s | 09-calc-result.png |
| 15 | Said "what does the calculator show?" | "87" | Reply "The calculator shows 87." | 2 s | 09-calc-question.png |
| 16 | Closed Calculator and Apps windows | Windows close | Closed. Desk shows only "While you were away". | - | 09-final.png |

Notes on the leftovers: the Calculator app I generated (step 5) is still in the apps list, because I did not remove it. The VM was left with no vlc, no mousepad and no calc processes running.

Waits over 30 s: none. The slowest step was the calculator generation at about 5 s. The install was under 10 s, so the "would a person see it" question has no clear answer from this run.

## Bugs

1. **Open VLC fails.** Typed: "open VLC". Saw: "Could not start mpv Media Player: it closed at once (Assertion failed: !vo->x11 (../video/out/x11_common.c: vo_x11_init: 679))." Should have: a VLC window opens. The reply also names mpv, not VLC, and shows a raw assertion. A person would not know what to do. The same failure came from "open the video player".
2. **VLC is not in the apps list after install.** Typed: "show my apps" after "install VLC". Saw: no VLC entry. Should have: VLC under Programs, with Open and Remove, so the user can find it.
3. **Apps list was stale.** Typed: "show my apps" right after the calculator was made in the same session. Saw at the start: "No apps yet." Then the Calculator tile appeared only after a later "show my apps". Should have: the new app listed right away, not "No apps yet".
4. **Editor left running after its window closed.** Clicked the window's x on Mousepad. Saw: window gone, but a "Mousepad" chip stayed at the bottom left, and the process kept running in the VM. Should have: the chip removed with the window.
5. **Stale reply text.** After "open calc" the reply box kept repeating "Here's your Calculator. It's kept in your apps..." through later actions, and the reply after the Open button click was the same kind of line. Should have: the reply matches the latest action.
6. **Calculator window cuts off the bottom row.** The 0, ., and = keys are partly under the window bottom and need the window scrollbar to reach. Should have: the whole keypad visible at the default size.
7. **Root warning on the text editor.** Mousepad opens with "Warning: you are using the root account. You may harm your system." A normal person would be confused by this for a plain text editor. Should have: no root warning, or a clear reason.

## Friction

- The "Make one" group lists Calculator, so it is not clear which items are installed and which are made on the spot. Step 5 took a moment before the window appeared, with no progress shown.
- The install gives no progress. It finished before my first check, so there was nothing for a person to watch. Nothing shows that an install is in progress.
- Install says "open it by name" but the name it installs under (vlc) does not match what the open command actually starts (mpv).
- The apps window and the reply can disagree (see bug 3 and 5).

## Ideas

- When an install succeeds, add the app to the Programs list at once, and show a short "Installed. Open it" button.
- For open failures, say which app was opened and why, in plain words, and offer a fallback (another player) instead of a raw assertion.
- Clean up the taskbar chip when a window closes.
- Make the calculator window large enough to show all keys.
