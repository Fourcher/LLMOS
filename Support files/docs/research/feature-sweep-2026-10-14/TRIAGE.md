# Feature sweep 2026-10-14: what the 14 testers found, ranked

Each tester (Haiku 5.5, medium) used the 1.8.5 desk on the arm64 VM through the screen (QMP mouse and keyboard, OCR, screenshots). Notes are in 01–14. Verdicts:
- WORKS (with friction): 1 (browser)
- PARTLY: 13
- BROKEN: 0

The browser problem the owner reported did **not** reproduce on the VM. Pages load in 2–7 s. It may be specific to that machine (x86, its graphics, or its network or internet setting).

## Fix order (severity × how often a person hits it)
1. **Deleting fails with "'str' object has no attribute 'get'"** (files, folders, email, desk banner). Testers 04, 05, 06, 11.
2. **Names and paths are taken apart wrongly, and one case overwrote a file** (testers 04, 05):
   - "in <folder>" becomes part of the file name.
   - "... and save it as X" makes a file named "neighbour and save it as X".
   - A move used unquoted paths, so it went to /root/Test with a false "Moved" reply.
   - "open <odd name>" overwrote thanks.txt.
3. **Email** (tester 11):
   - The Read button starts mutt, which asks to create /root/Mail.
   - Delete fails.
   - "summarize my unread emails" fails after running find / for 30–48 s.
   - Opening a message by sender fails.
4. **Failures hunt with shell commands for up to 48 s before saying they couldn't** (testers 11, 12). They should stop after one or two tries.
5. **Open windows don't refresh after actions**:
   - Files: rename, delete, restore.
   - Models: download, use.
   - Inbox.
   - Sound: level and mute.
   - Apps list.
   - Testers 04, 08, 09, 11, 12.
6. **Window behaviour** (tester 07):
   - A new system window closes the one already open, so Settings and Files never stay together.
   - A window can be dragged off the bottom, out of reach.
   - Restoring after maximize returns a window to an off-screen spot.
7. **Stop drops waiting requests without a word.** Quick answers given while a long task runs never show on screen (tester 10).
8. **Video** (tester 03):
   - Pause hides the picture, and resume doesn't bring it back.
   - "close the video" says the player isn't open while it plays.
   - "make the video full screen" fails after 3.5 min with a JSON error.
   - "stop the music" doesn't stop it.
   - Typing reaches a full-screen player.
9. **Answers that are wrong, empty or thin** (testers 02, 08, 12, 14):
   - The weather has no source and may be wrong.
   - "search the web for X" only opens Firefox, with no answer.
   - "which model are you using" answers Whisper.
   - "how do I connect to wifi" fails after 30 s.
   - The Wi-Fi reply contradicts the panel.
   - The disk-space reply has no numbers.
   - "make a to-do list for moving house" gives an empty list.
   - "A and B" is added as one item.
10. **Apps** (tester 09):
    - The "Files" tile opens a broken Thunar ("Failed to open 'File'").
    - VLC/mpv won't open (X11 assertion on Wayland).
    - An installed app is missing from the apps list.
    - A closed editor leaves its chip and process behind.
    - The calculator's bottom row is cut off.
    - The text editor shows a root warning.
11. **Wallpaper**: "set my wallpaper to mountains" shows no mountains, and putting it back fails (tester 13).
12. **Settings** (tester 06):
    - Replies show raw language codes.
    - "change the language back to English" and "back to dark" changed other settings.
    - "reset the accent colour" falsely says done.
    - A+ text size pushes Settings off screen.
    - Spanish is only partly translated.
13. **Small things**:
    - The lock icon needed two clicks.
    - Night light gives no visible sign before 7 pm.
    - Timer and reminder names are mixed up.
    - History merges topics.
    - Stale reply text.

## Status after fixes and retests (1.8.7, 2026-10-14)
Retests 21–25 were run by Haiku testers through the screen on the VM, on the fixed build.
- **Fixed and retested (PASS):**
  - Deleting files and folders by request or button; a bare name finds the file in a subfolder.
  - Files made "in <folder>"; moves into folders the owner made; the "note … and save it as X" naming.
  - Email: the Read button opens the message; Delete, summarize unread, open by sender.
  - Windows: Settings and Files stay open together; no window lost off screen; restore stays on screen; open windows refresh after changes.
  - Queue: quick answers show while busy; Stop says what it cancelled.
  - Video: pause keeps the picture; resume, full screen, exit full screen, close the video.
  - The Files tile; mpv opens.
  - Settings: language and colour back; proper language names.
  - Answers: which model, Wi-Fi wording and panel, disk-space numbers (now matching the window), search the web for a question (with a source).
  - The desk filling the screen after an update. This was found by a retest screenshot and fixed.
- **Fixed after its retest, host-tested only:**
  - "Put the wallpaper back" restores the previous picture.
  - The inbox window updates and isn't stacked; the summary lists every message.
- **Still open:**
  - Weather has no source.
  - Search answers are slow (85 s on the VM CPU).
  - "make a to-do list for X" can come back empty; "A and B" is added as one item.
  - Apps run as root, so the root warning appears in Mousepad and Thunar. Fixing it is the planned unprivileged-user work.
  - The calculator's bottom row is cut off.
  - A closed editor leaves its chip.
  - Stale reply text after some actions.
  - The mute state isn't shown.
  - The lock icon needs two clicks.
  - Timer and reminder names.
  - History merges topics.
  - Night light has no preview.
  - Restore after maximize moves the window.
  - A stopped story has no "Stopped" line on its card.
  - "show my documents" replaces the Home window.
- **Not reproduced:** "the browser doesn't work" works on the arm64 VM. It needs a look on the owner's machine.
