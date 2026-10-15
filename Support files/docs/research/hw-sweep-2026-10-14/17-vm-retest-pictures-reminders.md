# 17. VM retest: pictures, reminders and lists

Run on the test VM (tools/vmuser.py), not the laptop. Desk was 1280x800. Update 1.8.9.32 had just been installed.

## Task
Re-test the things earlier testers found broken: picture edits, wallpaper, reminders, timers, packing list, and footnote marks in web answers.

## Verdict
PARTLY. Rotate, black and white, wallpaper set and put-back, and weekly reminders work. The PDF reply, file-name layout, cancel reply, timer panel, packing list and footnote marks are still broken. One new serious bug: the Close buttons in the "Open now" panel moved my screenshots to the trash.

## Steps

| # | Typed | Expected | What happened | Time | Shot |
|---|---|---|---|---|---|
| 1 | take a screenshot | screenshot saved | Saved ~/Pictures/screenshot-20261015-033220.png | 3 s | 17-start / 17-01 |
| 1 | rotate it | rotated copy shown, no new screenshot | Saved ...-edited.png "with: rotate; the original is unchanged". Rotated copy shown in its window. No new screenshot. | 2 s | 17-01-rotate |
| 2 | make it black and white | acts on the picture on screen, shows result | Acted on the rotated copy on screen. Saved ...-edited-edited.png, shown in grey. No new screenshot. | 3 s | 17-02-bw |
| 3 | save it as a PDF | PDF made, reply not "no changes" | PDF made (...-edited-edited.pdf, 508 KB). Reply still says "with: no changes; the original is unchanged." | 3 s | 17-03-pdf |
| 4 | show my pictures | file names readable under thumbnails | Window "~/Pictures" opens, but the file names under the thumbnails run into each other and cannot be read. | 2 s | 17-04-pictures |
| 5 | draw me a cat | a cat picture | "I couldn't finish that. Try saying it another way..." | 69 s | 17-05-cat |
| 5 | open the screenshot-20261015-033220.png picture | picture opens | Opened in its own window. "Here it is." | 14 s | 17-05b-open |
| 5 | use this picture as my wallpaper | wallpaper set, reply names file | "Wallpaper set to screenshot-20261015-033220.png." Window shown. | 2 s | 17-06-wallpaper |
| 6 | put my old wallpaper back | previous wallpaper back at once | "Wallpaper put back to how it was". Desk looked like the original mountain picture. I did not measure the change exactly. | 2 s | 17-07-oldwall |
| 7 | remind me every Monday to take out the bins | repeats weekly | "Reminder every Mon at 09:00: take out the bins." | 2 s | 17-08 |
| 7 | what are my reminders | shows it repeats | "Scheduled: take out the bins (every Mon at 09:00)." Scheduled window lists "every Mon at 09:00". | 3 s | 17-08-reminders |
| 8 | set an alarm for 7am | alarm set | "Reminder set for 07:00: Alarm." | 2 s | 17-09-alarm |
| 8 | Cancel button on the Alarm row | cancelled, no code numbers | Row greyed, then reply: "Task 70e93e ("Alarm") has been cancelled." Internal task code shown. | 8 s | 17-10 / 17-10b |
| 9 | set a 1 minute timer for the tea | rings in 1 minute | "Timer set — 1 minute (the tea), it rings at in 1 minute at (03:36)." Awkward wording ("rings at in"). | 3 s | 17-11-timer |
| 9 | (wait for it) | "Time's up" window, then not listed as scheduled | Time's up window opened about 03:37. But the Scheduled window still listed "1 minute (the tea) / in 1 minute (03:36)" while the timer window was open. | ~2 min | 17-12, 17-13-fired2 |
| 9 | OK | timer no longer scheduled, no extra panel | Timer dropped from the Scheduled list after OK. An extra "Open now" panel appeared, listing the open windows, each with a Close button. Reply: "Closed." Unexplained panel. | 2 s | 17-14-ok |
| 10 | make a packing list with socks, charger and toothbrush | list opens in its own window | No window. The list came back in the answer bubble, with "2 pairs of socks" and an added "Toothpaste (if needed)" that was not asked for. | 8 s | 17-15-packing |
| 11 | what is the capital of France | plain answer, no footnote marks | "Paris[b] is the capital ... [4] and a metropolitan population..." Both [b] and [4] shown. Also ends with "(source: en.wikipedia.org)". | 2 s | 17-16-france |

## Bugs
1. **PDF reply says "no changes".** Typed "save it as a PDF". The PDF is saved, but the reply says "with: no changes; the original is unchanged."
2. **Picture file names overlap.** "show my pictures": the names under the thumbnails run into each other (17-04-pictures). Expected: each name readable.
3. **Cancel reply shows a task code.** Cancel on the Alarm row replied "Task 70e93e ("Alarm") has been cancelled." Expected: no number codes. The same happened for the bins reminder cancel: "Task 2cdd1a has been cancelled."
4. **Fired timer stays listed while ringing.** The tea timer still showed as "in 1 minute (03:36)" in the Scheduled window after it went off. It was gone only after OK.
5. **Unexplained "Open now" panel after OK.** Clicking OK on the Time's up window opened an "Open now" window listing open windows with Close buttons. Nobody asked for it.
6. **Close buttons in "Open now" delete pictures (serious).** Clicking Close on the screenshot rows in "Open now" was read as a request ("close window file:/root/Pictures/screenshot-20261015-033220-edited.png"). The app replied "Deleted the screenshot and moved it to the trash." It then did this for the other picture rows too. Three of my test screenshots (the .png originals and both edits) went to the VM trash. The PDF was kept. I restored the three PNG files from the trash to ~/Pictures with mv, and checked that the folder matches the list above. Nothing was permanently deleted. Expected: Close closes the window and deletes nothing.
7. **Packing list is not a window.** "make a packing list with socks, charger and toothbrush" answered in the chat bubble. Expected: a list window. It also added items I did not ask for.
8. **Footnote marks in web answer.** "what is the capital of France" shows "[b]" and "[4]" and a "(source: en.wikipedia.org)" line. Expected: plain text answer.
9. **"draw me a cat" fails.** "I couldn't finish that." after 69 s. (Opening a picture worked.)
10. **Timer reply wording.** "it rings at in 1 minute at (03:36)".

## Friction and ideas
- Cancel buttons in the Scheduled window work well; the greyed "..." while cancelling is clear.
- "Open now" lists every window with a Close button. Its Close buttons act on the files, so it is easy to lose pictures. Consider a plain window close there.
- Left after the test: the pictures I made (screenshot-20261015-033220.png, -edited.png, -edited-edited.png and .pdf) are still in ~/Pictures on the VM. The wallpaper is back to the original. Reminders: bins and alarm cancelled; tea timer gone. The packing list was never saved, so there is nothing to delete. The "While you were away" window is closed.
