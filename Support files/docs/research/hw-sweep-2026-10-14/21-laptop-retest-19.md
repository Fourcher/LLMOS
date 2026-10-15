# 21. Laptop: retest of last round's file and model tasks (1.8.9.36)

## Task
Re-test what failed in round 19 on the real laptop: rename episodes, find duplicates, spreadsheet, models, voices,
convert, folder window refresh, Sources window, power panel, memory. Test files were made in /root/Videos/test21
with ffmpeg (three "Show s01 eNN raw.mp4" files and copy1.mp4, each 3 s). Release checked: VERSION=1.8.9.36.

## Verdict
**PARTLY.** WORKS now: folder open, rename, duplicates (both wordings), models, voices, convert, the web answer, the
power panel (Lock present). Fixed since round 19: folder names, rename, duplicates, models, voices. BROKEN: the
spreadsheet (still an empty sheet, nothing saved). Worst problems: the spreadsheet claim is false, the folder window
does not show files added outside LLM OS, and the Duplicates window text wraps one word per line.

## Steps
Times are from `waitreply` unless noted.

1. "show my Videos/test21 folder": 16 s. Folder window "~/Videos/test21" opened with the 4 files. Shot dev-21-01a.
   "rename the episodes in Videos/test21 so they are named like Show - S01E01": 2 s. Reply "Renamed 3 file(s) in
   /root/Videos/test21: Show - S01E01.mp4 … Show - S01E03.mp4." ls shows the three new names, copy1.mp4 untouched, and
   the open window shows the new names. Shot dev-21-01b. **Works.**
2. "find duplicate files in my test21 folder": 2 s. Duplicates window: "1 file(s) have copies; the extra copies take
   94.4 KB." Group "Show - S01E01.mp4, 4 copies, oldest kept" (copy1.mp4 is one of the 4). Shot dev-21-02a. **Works**
   (result right, layout broken, see Bugs).
   "find duplicate files in this folder" (test21 window open): 2 s, same result. Shot dev-21-02b. **Works.**
3. "make a spreadsheet for a monthly budget with rent, food and transport": 7 s. Reply "Opened the spreadsheet (Gnumeric)
   in a window." The window is an empty Book1.gnumeric (A1 empty, no Rent/Food/Transport, no Total). No file saved:
   find finds no budget file; /root/Documents was created empty by the attempt and removed by me. Shot dev-21-03.
   **Broken**, same as round 19.
4. "what models can I use?": 2 s. Models window opened, "Ministral 3 3B (in use)" at the top, with an "On this computer"
   list and an online section. Shot dev-21-04. **Works** (was 106 s and wrong last round).
5. "which voices can you speak with?": 2 s. "I speak with one voice: the computer's built-in eSpeak voice, in
   English ... For listening I use the Whisper Base speech model." No web search, no Sources window. Shot dev-21-05.
   **Works** (was 159 s and went to the web last round).
6. "convert copy1.mp4 in Videos/test21 to mp3": 25 s. Reply "Done: copy1.mp4 in ~/Videos/test21 is now copy1.mp3."
   copy1.mp3 is real (mp3, 3.0 s) and copy1.mp4 is still there. Shot dev-21-06. **Works**, but the reply still says
   "is now" and does not say the original is kept.
7. Folder window refresh: with the test21 window open, I added copy1.mp3 from the shell (cp), waited 10 s, and the
   window still listed only the four original files (copy1.mp4 and the three renamed files). I then removed copy1.mp3
   with rm and waited 10 s; the window was still correct. Shots dev-21-07a, dev-21-07b. **Broken**: the window does not
   pick up new files, so the rm check proves nothing. Expected: the window lists copy1.mp3 within a few seconds.
8. "who wrote the book Dune": 2 s. "Dune is a 1965 epic science fiction novel by American author Frank Herbert ...
   (source: en.wikipedia.org)". No Sources window opened, so nothing to close. Shot dev-21-08. **Works.**
9. Power button at the top right: the Power panel shows Battery 100%, and buttons Lock, Sleep, Restart, Shut down.
   Lock is there. Closed with Esc (Lock, Sleep, Restart and Shut down not clicked). Shots dev-21-09, dev-21-09b. **Works.**
10. Memory (`store.facts()` after all requests): the list is "set up LLM OS on 2026-10-13", "Jordan" (2026-10-14), and
    "owner's name is Jordan" (added 2026-10-15). Nothing from my requests (no folders, dates or voices). The last fact
    is dated today but I did not say my name, so it came from some other source; it needs a look.
Cleanup: test21 folder removed (rm -rf); windows closed (Models, Duplicates, the test21 folder, Gnumeric from the dock).
"While you were away" was open at the start and is still open. No budget file exists, so there was nothing to delete.

## Bugs
- Spreadsheet: "Opened the spreadsheet" with an empty Book1 and no file. Expected: rent, food, transport rows and a Total,
  saved to Documents, with the reply naming the file.
- Folder window: does not refresh when files change outside LLM OS (copy1.mp3 added by another process never appeared).
  Expected: the open folder shows new and removed files.
- Duplicates window: the text is one word per line in a narrow column; the "Delete ..." buttons run off the right edge
  so the third button is cut off. Also "1 file(s) have copies" reads oddly; "1 group of duplicates (4 copies)" would be clearer.
- Convert reply: "copy1.mp4 ... is now copy1.mp3" while copy1.mp4 is kept. Expected: "Made copy1.mp3; copy1.mp4 is kept."
- Rename and duplicate replies show /root/Videos/... while the window says ~/Videos/...; the user sees two paths for one folder.
- Memory: "owner's name is Jordan" saved on 2026-10-15 with no request from this test (see step 10).

## Friction and ideas
- Models and voices are now fast and right (2 s each). Rename and duplicates are fast too.
- Duplicates should show the file names in a readable list with the Delete buttons inside the window.
- Folder window needs a refresh (on open, after each action, or on a timer) so it matches the disk.
