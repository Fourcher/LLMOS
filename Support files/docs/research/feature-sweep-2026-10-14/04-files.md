# 04 files: manage files like a normal person

## Task
Ask "show my files"; open files by clicking; create folder "Sweep Test" in Documents; put a new text file in it; rename it; move it to Downloads; delete the folder and the file; check the Trash and restore something. Try asking and clicking. Check with `vm ls` only after each on-screen step.

## Verdict
PARTLY. Browsing, opening folders by clicking, creating a folder, renaming, Delete on a file (to Trash), Trash view and Restore all worked. Putting a file into a folder failed (it ended up in the wrong folder while the reply said it succeeded), and deleting a folder failed in every way I tried. The computer also reported false results twice.

## Steps
Times are from the `say` / `waitreply` output unless noted. Screenshots are in `run/sweep/shots/`.

1. Start state: desk idle, one pre-existing window "While you were away" (not mine, left open). Shot `04-before.png`.
2. Said "show my files". Reply "6 items in ~." in 2 s; a Home window opened listing Apps, Documents, Downloads, Music, Pictures, Videos. Expected: a list. Got it. Shot `04-show-files.png`.
3. Done after step 4: clicked the Open button on the Sweep Test row in the Documents window. Expected: the folder opens. It did not open straight away. It sent a chat request "show my files in /root/Documents/Sweep Test" that I did not type, and the folder window only opened after the reply came back (about 5 s). Shots `04-open-folder.png`, `04-open-folder-reply.png`.
4. Said "create a folder called Sweep Test in Documents". Reply "Made the folder ~/Documents/Sweep Test." in 2 s. `vm ls -la /root/Documents` showed `Sweep Test`. Shot `04-make-folder.png`.
5. Said "make a new text file called notes.txt in Sweep Test". Reply "Made ~/Documents/notes.txt in Sweep Test.txt." in 2 s. `vm` showed the file at `/root/Documents/notes.txt in Sweep Test.txt` (0 bytes), not in the folder. The folder stayed empty. Shot `04-new-text.png`.
6. Clicked the up arrow to Documents, which showed the stray file with Open and Delete buttons. Shot `04-up-to-documents.png`.
7. Said "move the file notes.txt in Sweep Test.txt into the Sweep Test folder". Chat showed "About to: delete file ..." and then the error "'str' object has no attribute 'get'". Nothing was deleted. Took 8 s. Shot `04-move-into-folder.png`.
8. Dragged the stray file onto the Sweep Test row. It only selected text; no move, no error. Shot `04-drag-into-folder.png`.
9. Said "rename notes.txt in Sweep Test.txt to my-notes.txt". Reply "Renamed ..." in 2 s. `vm` confirmed `my-notes.txt`. The window still showed the old name until refreshed. Shot `04-rename.png`.
10. Said "move my-notes.txt into Sweep Test". Took 19 s. Reply: "The folder Sweep Test does not exist in /root/Documents/. The owner should confirm ..." This was false: the folder existed and was empty. Shot `04-move-retry.png`. (My first `vm` check of the folder was also wrong, because `vm` joins arguments without quoting, so the path split into two. Re-checked with quoted path: the folder existed.)
11. Said "put my-notes.txt inside the Sweep Test folder". Reply "Moved my-notes.txt into Sweep Test." in 13 s. The chat log showed `mkdir -p ~/Documents/Sweep Test` and `mv ~/Documents/my-notes.txt ~/Documents/Sweep Test/`. On disk the file was at `/root/Test/my-notes.txt`, and a new `/root/Test/Sweep` folder had appeared. Sweep Test stayed empty. Shot `04-put-inside.png`.
12. Said "move my-notes.txt to Downloads". Reply "Moved 1 file(s) to ~/Downloads." in 2 s. `vm` showed `/root/Downloads/my-notes.txt`. This step worked, from the wrong starting place, but the file was found without me saying where it was. Shot `04-to-downloads.png`.
13. Home window: clicked Open on Downloads, clicked the red Delete button on my-notes.txt. Toast "Moved my-notes.txt to the trash." The file left Downloads on disk, but the window still listed it. Shots `04-downloads-open.png`, `04-delete-file.png`.
14. Said "delete the Sweep Test folder in Documents": chat error "'str' object has no attribute 'get'". Folder still there. Shot `04-delete-folder.png`.
15. Said "move the Sweep Test folder to the trash": same error. Shot `04-trash-folder.png`.
16. Clicked Documents, then right-clicked the Sweep Test row to look for a menu. Nothing appeared. Folder rows only have an Open button; no Delete. Shot `04-rightclick-folder.png`.
17. Said "remove the Sweep Test folder": same error. Shot `04-remove-folder.png`.
18. Said "show my trash". Reply "Here's the trash (1 item). Press Restore to put one back." in 2 s. Trash window listed my-notes.txt with Restore and Delete for good. Shot `04-show-trash.png`.
19. Clicked Restore. Toast "Put my-notes.txt back at /root/Downloads/my-notes.txt." `vm` confirmed the file. The Trash window still listed it (stale). Shot `04-restore.png`.
20. Cleanup: closed the Trash window; said "show my Downloads"; clicked Delete on the restored file (back in Trash); closed the Downloads window. Shots `04-close-trash.png`, `04-delete-restored.png`, `04-final.png`.

## Bugs
1. **File created in the wrong place.** Typed: "make a new text file called notes.txt in Sweep Test". Saw: file named `notes.txt in Sweep Test.txt` in Documents, not inside the folder. Reply: "Made ~/Documents/notes.txt in Sweep Test.txt." Should: create `notes.txt` inside `Sweep Test`. The phrase "in Sweep Test" was taken as part of the name.
2. **Move into folder misfires as a delete, then fails.** Typed: "move the file notes.txt in Sweep Test.txt into the Sweep Test folder". Saw: "About to: delete file ..." and "'str' object has no attribute 'get'". Should: move the file.
3. **Move into folder: wrong folder, false success.** Typed: "put my-notes.txt inside the Sweep Test folder". Saw: the file ended in /root/Test/my-notes.txt and a new /root/Test/Sweep folder. Reply: "Moved my-notes.txt into Sweep Test." Should: move it into /root/Documents/Sweep Test. The generated command used an unquoted path: `mkdir -p ~/Documents/Sweep Test` and `mv ... ~/Documents/Sweep Test/`, which split at the space.
4. **False "does not exist" reply.** Typed: "move my-notes.txt into Sweep Test". Saw: "The folder Sweep Test does not exist in /root/Documents/." The folder existed and was empty. Should: move the file or give the real error.
5. **Delete folder fails in every way tried.** Typed: "delete the Sweep Test folder in Documents", "move the Sweep Test folder to the trash", "remove the Sweep Test folder". Saw: the same error "'str' object has no attribute 'get'" each time. Clicking: folder rows have only Open (no Delete), and right-click shows no menu. Should: folder moves to the Trash. Result: Sweep Test still exists in /root/Documents.
6. **Stray folder left behind.** /root/Test and /root/Test/Sweep were created by bug 3. Nothing in the window offers to delete them. Left in place (see below).
7. **Clicking Open on a folder sends a chat request.** Clicked Open on Sweep Test. Saw: a chat item "show my files in /root/Documents/Sweep Test" that I did not type; the folder opened only after the reply, several seconds later. Should: open the folder at once with no chat message. Also paths differ: the window says ~/Documents, chat says /root/Documents.
8. **Windows do not refresh after an action.** After rename, the window still showed "notes.txt in Sweep Test.txt". After delete to Trash, Downloads still listed my-notes.txt. After restore, the Trash window still listed it. Should: refresh the list.
9. **Note, not a bug.** "move my-notes.txt to Downloads" worked from the wrong place: the file was in /root/Test at that point, and the computer found it and moved it anyway. Reply and disk agree.

## Left on the computer (not removed, per the brief: vm is for checks only)
- `/root/Documents/Sweep Test`: empty folder. Cannot be deleted in the window (bug 5). Needs a manual delete.
- `/root/Test/` and `/root/Test/Sweep/`: empty folders created by bug 3.
- `/root/Downloads/`: empty. my-notes.txt is in the Trash (put there at step 20).
- The pre-existing "While you were away" window is still open. Not mine.

## Friction
- The Open button on a folder goes through the chat, so it is slow (several seconds) and fills the chat log with a request the user did not type.
- Reply wording is confusing: "Made ~/Documents/notes.txt in Sweep Test.txt."
- Folders cannot be deleted by click. The only Delete button is on files.
- Going Up uses "↑ Documents" and "↑ Home" buttons; they are clear.
- Timings: most chat requests took 2 to 13 s. The move that failed took 8 s, and the move that picked the wrong folder took 13 s. The "Sweep Test does not exist" reply took 19 s.

## Ideas
- Quote folder and file names in the generated commands (fixes bugs 1 to 3).
- Add Delete (move to Trash) to folder rows and a right-click menu with Rename, Move, Delete.
- Refresh a window after any action on its folder.
- Make clicking a folder open it directly, not through the chat.
- Use a file-name picker in chat ("which file?") when a name is ambiguous, instead of building one.
