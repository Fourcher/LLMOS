# 19. Laptop: less common tasks (shorter ability list)

## Task
Check the less common abilities still work on the real laptop after the shorter prompt (1.8.9.35): rename, find duplicates,
convert, trim, spreadsheet, zip, voices, models, timer while busy, and two ordinary questions. Test files were made in
/root/Videos/test19 with ffmpeg (three "Show s01 eNN raw.mp4" files and copy1.mp4, each 3 s).

## Verdict
**BROKEN** for the file tasks (rename, duplicates, spreadsheet) and the models question. WORKS for convert, trim, zip,
timer while busy, and the quick questions. Worst problems: folder names are resolved to a wrong path so the file
actions refuse, and "rename" just lists the folder.

## Steps
Times are from `waitreply` unless noted. Laptop clock is MST.

1. "rename the episodes in Videos/test19 so they are named like Show - S01E01": 20 s. Reply "4 items in ~/Videos/test19."
   The folder window opened instead. Nothing renamed (checked with ls). Shot dev-t19-01.
   Retry "rename the files in test19 to Show - S01E01, Show - S01E02 and so on": 2 s. Reply "/root/test19 is not a folder."
   Shot dev-t19-01b. Retry "rename the three Show s01 files in my Videos test19 folder to Show - S01E01 etc": 25 s. Listed
   the folder again. Nothing renamed. Shot dev-t19-01c. **Broken.**
2. "find duplicate files in Videos/test19": 2 s. Reply "/root/videos/test19 is not a folder." Shot dev-t19-02.
   Retry "find duplicate files in my test19 folder": 2 s. Reply "/root/test19 folder is not a folder." Shot dev-t19-02b.
   Retry "find duplicate files in this folder" (with the test19 window open): 2 s. Reply "/root/this folder is not a folder."
   Shot dev-t19-02c. **Broken.** No duplicates were looked for.
3. "convert copy1.mp4 in Videos/test19 to mp3": 34 s. Reply "Done: copy1.mp4 ... is now copy1.mp3." The file copy1.mp3 is
   real (format mp3, 3.0 s). The reply says "is now", but copy1.mp4 was kept. Shot dev-t19-03. **Works** (slightly
   misleading wording).
4. "trim the first 2 seconds of copy1.mp4 in Videos/test19": 29 s. Created "copy1 (trimmed).mp4", duration 1.0 s (correct),
   original kept. Shot dev-t19-04. **Works.**
5. "make a spreadsheet for a monthly budget with rent, food and transport": 7 s. Reply "Opened the spreadsheet (Gnumeric)."
   The window was an empty Book1.gnumeric: no rent, food or transport rows. Nothing was saved anywhere (find for budget,
   *.gnumeric, *.xlsx, *.csv found nothing). Shot dev-t19-05. **Broken.** The reply claims a budget that does not exist.
6. "zip the test19 folder in Videos": 43 s. Created /root/Videos/test19.zip with the 6 files (unzip -l checked). Shot
   dev-t19-06. **Works**, a bit slow.
7. "which voices can you speak with?": 159 s (over 2 min). The answer lists TTS voices (Kokoro, Bark, Chatterbox, ...)
   and "if installed" models, and a Sources window opened with "AI Voice Library ... TTS.ai". So it went to the web, not to
   the laptop's own list. Shot dev-t19-07. **Partly** (very slow, sources from the web, unclear what is installed here).
8. "what models can I use?": 106 s. Answered with the same voice list (Kokoro, Darwin TTS, Coqui XTTS). It did not say
   the chat model (Ministral 3 3B shown in the top bar). Shot dev-t19-08. **Broken** (wrong question answered).
9. Timer while busy: "set a 1 minute timer" then at once "write a 300 word story about a lighthouse".
   Laptop clock: timer set about 04:22:55 (reply "it rings in 1 minute (04:24)"). Time's up window and "While you were
   away" row appeared at 04:24:00, about 65 s after setting, while the story was still being written (busy true).
   Story finished about 04:24:58 (about 2 min). Word count not measured. Shots dev-t19-09a, dev-t19-09b. **Works.**
10. "how many days until christmas": 2 s. "71 days until Christmas (about 10 weeks): Friday 25 December 2026." Correct
    (Oct 15 to Dec 25 = 71). Shot dev-t19-10a. **Works.**
    "tell me a fun fact about octopuses in one sentence": 12 s. "Octopuses are the only cephalopods capable of natural
    camouflage ..." The claim is wrong (squid and cuttlefish camouflage too). Shot dev-t19-10b. **Works, but the fact is wrong.**

## Bugs
- Folder names: "Videos/test19", "test19", "my test19 folder", "this folder" are turned into /root/test19, /root/videos/test19
  or /root/this folder, then "X is not a folder." The real folder is ~/Videos/test19 (/root/Videos/test19). The desk
  reply for step 1 also says "/home/jordan/Videos/test19" while the files are under /root. Expected: find the folder that
  is open or under Videos.
- Rename and find duplicates do not act: rename shows the folder list ("4 items"), duplicates refuse the path.
- Spreadsheet: the reply says a budget was made, but the sheet is empty and not saved. Expected: rent, food, transport rows
  and a save location (for example ~/Documents).
- Models: "what models can I use?" answers with the voice list, and "which voices" goes to the web (TTS.ai) and takes 2.5 min.
- Octopus fact is wrong (camouflage is not unique to octopuses).
- Convert reply says copy1.mp4 "is now" copy1.mp3 while copy1.mp4 is still there.
- After the test files were deleted with the shell, the ~/Videos/test19 window still listed them (no refresh).
- A "Sources" window (TTS.ai link) stays open after the voice question. Only its title bar is visible behind the
  "While you were away" panel; I could not close it with the red dot.
- Memory notes are shown in the reply panel ("remember: Jordan's preferred voice models are ...", "Jordan's OS: Alpine
  Linux (no GUI, no X11)"). That is noisy, and the OS note looks wrong for a desktop.

## Friction and ideas
- The timer and the quick questions are fast and right. The file tasks are the weak part on this laptop.
- Slow answers: voices 159 s, models 106 s, zip 43 s, trim 29 s. Over 2 min is a problem.
- Retrying with another wording did not help for the file tasks, so the path should come from the open window or the
  Videos folder, not from the words typed.
- Cleanup: test19 files and zip deleted. Budget file: none was saved. Left open: "While you were away" (it was open at
  the start) and the Sources panel (see bugs).
