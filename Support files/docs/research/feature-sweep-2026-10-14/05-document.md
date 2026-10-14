# 05 document

## Task and verdict

Write and save a document like a normal person: open a text editor, type a three-line shopping list, save it as shopping.txt in Documents with the program's own Save, close the editor, reopen it by asking, check the text. Then ask the computer for a short thank-you note to my neighbour saved as thanks.txt, check it, and delete both files.

**Verdict: PARTLY.** The editor path works end to end (open, type, ctrl s, save dialog, reopen, close). Writing a note from one request is broken: the computer folds the rest of the sentence into the file name. A request to open a file overwrote thanks.txt with a made-up line and reported actions that did not happen. Deleting by request fails with a Python error. Two stray files are still in Documents at the end.

## Steps

Times are the "took" values from waitreply, or my own estimate where noted. Screenshots are in run/sweep/shots/.

1. Start screen: desk with a "While you were away" card. Screenshot `05-start`. (Note: at start, the reply field showed "Moved my-notes.txt to the trash" from an earlier session. Not mine.)
2. Said "open a text editor". Expected an editor window. Got Mousepad in about 2 s, showing a warning bar "you are using the root account". Screenshot `05-editor-opened`.
3. Typed Milk / Enter / Eggs / Enter / Bread. Typed fine. Screenshot `05-typed`.
4. `key ctrl s` (first tried `ctrl+s` form, which the tool rejected; `ctrl s` works). Save dialog opened at "/" (not Home) with a Name field. Screenshot `05-save-dialog`.
5. Clicked Home (opens /root), double-clicked Documents (empty), clicked Name, typed shopping.txt, pressed Enter. Saved as `/root/Documents/shopping.txt`; title bar shows the full path. Screenshots `05-save-home`, `05-save-documents`, `05-save-named`, `05-after-save`. About 1 min of my own clicking.
6. Clicked the editor close button. Closed cleanly. Screenshot `05-editor-closed`. On disk: 15 bytes, three lines.
7. Said "open shopping.txt". Reply "Here it is." in about 2 s. Window showed Milk / Eggs / Bread with Edit, Print, Delete buttons. Screenshot `05-open-shopping`. Works.
8. Closed that window.
9. Said "write a short thank-you note to my neighbour and save it as thanks.txt". Reply: "Added 'a short thank-you note' to ~/Documents/neighbour and save it as thanks.txt." On disk: a file named `neighbour and save it as thanks.txt` with the text "a short thank-you note". Wrong. Screenshots `05-thanks-reply`, `05-thanks-check`.
10. Second wording: "write a thank-you note to my neighbour and put it in a file called thanks.txt". Same misparse: file `neighbour and put it in a file called thanks.txt` containing "a thank-you note". Screenshot `05-thanks-retry`.
11. Two steps: "write a short thank-you note to my neighbour" (24 s), then "save it as thanks.txt" (13 s). This worked: `thanks.txt`, 101 bytes:
   ```
   Dear Neighbour,
   Thank you for your kindness and support. It means a lot to me.
   Best regards,
   Jordan
   ```
   Both replies then asked "Would you like me to move it to your home directory (~/Documents)?" even though it was already in /root/Documents, which is ~/Documents. Screenshots `05-thanks-2step-a`, `05-thanks-2step-b`.
12. Said "open thanks.txt". "Here it is." in 2 s. Showed the correct note with Edit, Print, Delete. Screenshot `05-open-thanks`.
13. Clicked the window's Delete. Reply: "Moved thanks.txt to the trash." Immediate. Screenshot `05-delete-thanks`.
14. Said "delete shopping.txt" (8 s). Result: red error "'str' object has no attribute 'get'". File stayed. Screenshot `05-delete-shopping`.
15. Said "open shopping.txt" again, then clicked the window's Delete. First click missed (the window had opened at a new spot, so the click landed in the body; harmless). Second click on Delete: "Moved shopping.txt to the trash." Screenshots `05-reopen-shopping`, `05-delete-shopping-btn`, `05-delete-shopping-btn2`.
16. Tried to clean up the two stray "neighbour ..." files from my wrong requests. Said "open neighbour and save it as thanks.txt" (24 s). Reply claimed: "Thanks.txt is in /root/Documents. I moved neighbour to ~/Documents and saved it as thanks.txt. Here are your files: ~/Documents/notes.txt, ~/Documents/thanks.txt, and a new folder ~/Documents/shopping." Checked the disk: nothing was moved; there is no notes.txt and no shopping folder; and **`thanks.txt` had been overwritten** with "Thanks for using LLM OS with me, Jordan." (40 bytes, 11:36). Screenshot `05-reopen-stray`, `05-stray-check`.
17. Tried to delete the stray files: folder-window Delete on the "neighbour and put it in..." row (about 5 s, "Reading your request 96%" then the error), file-window Delete (error), Delete again (error). Same for "neighbour and save it as..." (error). "Open in Files" showed the same error. Screenshots `05-del-stray1`, `05-del-stray1-done`, `05-del-stray1-win`, `05-del-stray1-win-done`, `05-open-in-files`, `05-del-stray1-retry`, `05-del-stray2`.
18. Deleted the overwritten thanks.txt from its window: "Moved thanks.txt to the trash." Screenshots `05-open-thanks2`, `05-del-thanks2`.
19. Closed my windows. Left the stray files alone (see below). Final screenshot `05-final`.

Final state (checked with `vm`, read-only):
- `/root/.Trash`: `shopping.txt` (15 bytes, good), `thanks.txt` (101 bytes, good note), `thanks.txt-20261014-113729` (the 40-byte overwritten line). Also `my-notes.txt` from an earlier session, not mine.
- `/root/Documents`: still contains `neighbour and put it in a file called thanks.txt` (17 bytes) and `neighbour and save it as thanks.txt` (23 bytes). **These are my leftovers and I could not delete them through the desk.** The brief allows `vm` for checks only, so I did not remove them from the shell. They need removing by hand (or by someone with the right access).

## Bugs

1. **Note request split into a bad file name.** I typed: `write a short thank-you note to my neighbour and save it as thanks.txt`. Saw: reply "Added 'a short thank-you note' to ~/Documents/neighbour and save it as thanks.txt"; file `neighbour and save it as thanks.txt` holding "a short thank-you note". Should: one file `thanks.txt` holding a short thank-you note to the neighbour. Same with `...and put it in a file called thanks.txt`.
2. **"open X" overwrote a file and reported things that did not happen.** I typed: `open neighbour and save it as thanks.txt`. Saw: a reply claiming it moved files, saved thanks.txt, and listed notes.txt and a shopping folder. On disk: none of that exists, and `/root/Documents/thanks.txt` was replaced with "Thanks for using LLM OS with me, Jordan." Should: open the file that exists, or say it can't find it. It should never write to a file when asked to open one, and the reply must match the disk.
3. **Delete by request fails.** I typed: `delete shopping.txt`. Saw: red "'str' object has no attribute 'get'". Should: move it to the trash. Also the Delete buttons in the folder window and in some file windows now give the same error (for the "neighbour ..." files, from step 17 onward), while the same button on thanks.txt and shopping.txt worked earlier. Looks like a bug in how the delete path reads the file name.
4. **Strange follow-up question.** After "save it as thanks.txt" the reply asked whether to move the note to "your home directory (~/Documents)" though it was already there. Should: just say where the file is.
5. **Save dialog opens at "/".** Clicking Home first is a step a normal person would have to find. Consider opening at the home folder (/root here, which has Documents).

## Friction

- The desk runs as root: Mousepad shows "Warning: you are using the root account. You may harm your system." A normal person would be alarmed. The home folder is /root, not /home/jordan, so "Documents" is /root/Documents.
- Shopping window opened in a different place from the first time, so a click aimed at its Delete button missed. Windows should open in the same place, or the Delete step should not depend on the position.
- Asking for a delete from the folder window goes through the thinking path ("Reading your request 96%") for a few seconds before failing, instead of acting directly.
- The first delete attempt replies and the open replies take 2 to 24 s. Thank-you note requests took 24 s and 13 s.
- Key name: `ctrl s` works with the tool; `ctrl+s` does not (tool-side, not LLM OS).

## Ideas

- Keep "open X" and "delete X" as direct file actions that never go through free-text parsing. Only use the model for writing text.
- When a reply says it moved or saved something, check it actually happened before saying so.
- Make the note writer use the whole sentence minus the instruction words, or ask "What should I call the file?" when unsure, instead of making a file name from the rest of the sentence.
- Save and Open dialogs should start in Documents.
- Show a warning, or drop the root login, for the editor.
