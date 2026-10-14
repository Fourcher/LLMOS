# 26 retest on LLM OS 1.8.8: video card, root-account bars, window restore, thank-you note

**Verdict: PARTLY.** The video card and the root-account bar checks pass. Three real bugs: the Sound panel does not refresh when the 75% button is used, a maximized Home window does not restore to its place, and the thank-you note is reported as saved to ~/Documents but the file is not there.

Note on checks: every `vm` command I ran (`cat /root/Documents/thanks2.txt`, a volume query, a test `echo`) hung and returned no output, so the file check for step 5 was done on screen instead (Home window and "show my documents"). The times below are from the tool's `waitreply` output and the screenshots.

## Steps

| # | What I did | Expected | What I saw | Time | Screenshot |
|---|---|---|---|---|---|
| 0 | Closed "While you were away" with its X | Window closes | Closed | - | start1 |
| 1 | Said "play a funny cat video on YouTube" | Video window and "Now playing" card | Reply "Now playing ... Funny And Cute Cat's Life" in 8 s. Card appeared at once. Video window appeared about 5 s later, on top of the card. | 8 s reply, about 10 s to picture | t1-video, t1-video2 |
| 1a | Looked at the card title bar | Pause, Stop, Full screen, volume slider, no maximize | Card has Pause, Stop, Full screen, slider, minimize and close. No maximize. | - | t1-video |
| 1b | Clicked the video picture | Pauses within 2 s; card shows Resume | Picture froze (same frame 2 s apart); card showed Resume. Clicked again: picture moved, card showed Pause. | about 2 s each | t1b-paused, t1b-resume-btn, t1b-play2 |
| 1c | Clicked speaker icon in top bar | Sound panel opens showing a % | First click hit the video window title bar (it covered the icon), so nothing opened. After moving the video window, the panel showed 40%. Dragged card slider to about 20%: panel changed live to 20%, card matched. Clicked the panel's 75% button: toast "Volume set to 75%." but the panel still read 20% and the card slider did not move for at least 5 s. After closing and reopening the panel it read 75% and the card slider had moved to 75%. | - | t1c-sound, t1c-sound2, t1c-vol25, t1c-vol75, t1c-vol75b, t1c-reopen75 |
| 1d | Clicked "Full screen" on the card, then Esc | Video fills screen; Esc leaves it | Full screen filled the screen. Esc returned the video window to its place; card still shows Pause. | about 3 s | t1d-full, t1d-esc |
| 1e | Clicked the video window's own X | Card disappears within about 3 s | Video window closed. Card was gone in the screenshot taken 3 s later. | 3 s | t1e-closed |
| 2 | Apps grid, then Files tile | File manager opens, no root warning | Apps grid listed Files. Thunar opened with no root-account bar. Closed with its X. The Apps panel stayed open behind it (I closed it). | - | t2-apps, t2-files |
| 3 | Said "open the text editor" | Editor opens, no root warning | Mousepad opened with no root-account bar. Reply text was empty. Tool reported 62 s before it returned. Closed with its X. | up to about 62 s | t3-editor, t3-closed |
| 4 | Said "show my files" | Home window opens | Home window opened top-left at x 481-1259, y 67-560, reply "6 items in ~." | 62 s tool wait, reply empty; window was up when I looked | t4-home |
| 4a | Clicked maximize | Fills screen | Filled the screen. | - | t4-max |
| 4b | Clicked maximize again | Back to same place and size (x 481-1259, y 67-560) | Back to the same size, but moved to x 25-803 (456 px to the left). Same y and size. | - | t4-restored |
| 5 | Said "write a short thank-you note to my neighbour and save it as thanks2.txt" | Note saved as thanks2.txt, no blanks | Reply text: "Dear Neighbour, Thank you for your kindness and support over the years. Your help has made a big difference, and I truly appreciate it. Thanks2.txt is saved in ~/Documents." No square-bracket blanks in the reply. The file is not in ~/Documents: "show my documents" listed only zz-sweep3.txt (2 B, from another test). The Home window's Documents "Open" button did nothing (see bugs). | 62 s tool wait, reply empty; reply text on screen later | t5-after, t5-docs, t5-docs5 |
| 5b | Said "delete thanks2.txt" | Deletes the file | Reply: "The file was never created in ~/Documents. It was saved in ~/Documents as "thanks2.txt" in the previous step, but the file does not exist there." Nothing was deleted. zz-sweep3.txt was left alone. | 62 s tool wait | t5-delete |
| 6 | Closed Documents window and reply card | All closed | Closed. Desktop clean. | - | t6-clean, t6-clean2 |

## Bugs

1. **Sound panel and card do not update on the 75% button.** Typed/clicked: Sound panel open at 20%, then clicked its "75%" button. Saw: toast "Volume set to 75%.", but panel still "Volume 20%" and card slider still at 20% for 5+ s. Closing and reopening the panel showed 75% and the card slider at 75%. Should: panel and card follow the new volume at once. (The slider drag did update both live.)

2. **Home window does not restore to its place after maximize.** Clicked the maximize button, then the restore button. Saw: window back at x 25-803 instead of x 481-1259, same y and size. Should: back to exactly where it was.

3. **Home window: folder "Open" buttons and folder names do nothing.** Clicked "Open" on Documents, clicked the name "Documents", and double-clicked the name. Saw: no navigation, the name only got text-selected. Should: show the folder's contents. Saying "show my documents" did work and opened a ~/Documents window.

4. **Thank-you note reported as saved, but the file is not there.** Said "write a short thank-you note to my neighbour and save it as thanks2.txt". Saw: reply says "Thanks2.txt is saved in ~/Documents." "show my documents" lists only zz-sweep3.txt. Then "delete thanks2.txt" replied "The file was never created in ~/Documents. It was saved in ~/Documents as "thanks2.txt" in the previous step, but the file does not exist there." Should: the file is in ~/Documents, or the reply does not claim it was saved. The two replies also contradict each other.

5. **Video window covers the top bar and the card.** Default placement of the video window (top-left) covers the "Now playing" card. After I moved it, my click on the top-bar speaker icon landed on the video window's title bar. Should: the video window should not cover the top bar or the card, or the card should stay on top.

6. **Video window disappeared from the screen after I moved it.** Dragged its title bar from y 17 to y 290, then clicked the top-bar speaker icon. Saw: video window gone from the screen and from the window list; card still showed Pause. It came back when I clicked the card's Full screen. Should: stay visible where I put it.

7. **Reply text in the bottom bar loses line breaks.** Saw: "Dear Neighbour,Thank you for your kindness ... it.Thanks2.txt is saved in..." Should: keep the paragraph breaks.

8. **Apps panel stays open after opening an app from it.** Opened Files from the Apps grid. Saw: Apps panel still open behind Thunar. Should: close the grid or leave it clearly closed.

9. **Friction: "Full screen" label wraps to two lines on the card** while the card shows Resume (the button is taller than the others).

10. **Friction: replies arrive late or empty.** "open the text editor", "show my files", "write a short thank-you note...", "show my documents" and "delete thanks2.txt" each returned an empty reply after 62 s, with the screen read as null. The results showed up on screen a moment later. A person would wait and think nothing happened.

11. **Friction: `vm` checks hung.** Four separate `vm` commands (volume query, cat of thanks2.txt, ls, echo) hung past their timeouts and returned no output. This is the test tooling, not LLM OS, but it blocked the file check.

## Friction

- The video window opens on top of the card, so a person has to move it to see the card's buttons.
- Clicking the video picture to pause works well and is quick.
- The Sound panel's "More sound settings" button is not tested.
- Opening the text editor and Files works and is fast once the reply comes back.

## Ideas

- Make the card and the Sound panel share one live volume value, and refresh both on any change.
- Make the file action wait for the write to finish before saying "saved", and show the full path.
- Open the Home window's folders on a single click (or on double-click, as the rest of the desktop does).
- Keep the video window's default spot clear of the top bar and the card.
