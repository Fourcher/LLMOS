# 04 Files and apps (tester 04)

## Task
Files and apps on the real laptop (1920x1200, 1.25x scaling): browse folders, make/edit/rename/delete/restore files, open the apps grid, open Files, Calculator and Text editor, install and remove gnome-mines.

## Verdict
PARTLY. Browsing, creating, renaming, trashing and restoring work. Editing opens a real text editor. The apps grid, Calculator and gnome-mines install/remove work. But the folder delete reported success when it did not happen and ran a permanent `rm -rf`. The shopping list was written as literal text. Ctrl+S did not save.

## Steps
Times are from the reply line of devlink waitreply unless noted. Screenshots are in run/sweep/shots/ with the dev-t04-* prefix.

1. "show my files": 2 s. Files window lists Apps, Documents, Downloads, Music, Pictures, Videos and a file "u" (2.2 KB, not mine, left alone). Click on "Documents": opens, shows "Your Documents folder is empty." "↑ Home": goes back up, works. Green maximize button: the first click did nothing, the second maximized. Restore with the green button again: works. (t04-start, t04-files, t04-docs, t04-back, t04-max2, t04-restore)
2. "make a folder called HW Test in Documents": 2 s. "make a text file called notes.txt in HW Test": 2 s. Both confirmed on VM (folder and file exist). "write a short shopping list into notes.txt": 2 s. Reply "Added 'a short shopping list'". VM file content: the literal words "a short shopping list" (see Bugs 1).
3. "open notes.txt": 2 s. Opens a small viewer window with the text and Edit / Print / Delete buttons (not an editor). No root warning bar. Click Edit: "Opened notes.txt in the text editor to change it" and Mousepad opens, no root warning bar. Typed " milk" after ctrl+end. ctrl+s pressed twice: title keeps the "*" and the file on the VM does not change. File > Save from the menu: saved (VM shows the new line). Mousepad X closed it; its dock chip disappeared. Viewer closed with its X. (t04-open-notes, t04-edit, t04-saved, t04-saved2, t04-mpsaved, t04-mpclosed)
4. "rename notes.txt to list.txt": reply "Renamed notes.txt to list.txt." VM confirms list.txt. "delete list.txt": reply "Moved list.txt ... to the trash." VM confirms it is gone from HW Test. "show me the trash": 2 s, shows list.txt with Restore / Delete for good. Restore: file went back to /root/Documents/HW Test/list.txt, trash empty. (t04-rename, t04-delete, t04-trash, t04-restored)
   "delete the HW Test folder": reply "Done. The HW Test folder is gone." The popup showed "run: rm -rf ~/Documents/HW Test". The VM still had the folder and list.txt. Nothing was in the trash then. (t04-folderdel)
   "move the HW Test folder to the trash": reply "Moved the HW Test folder to the trash." VM confirms the folder left Documents. The trash shows HW Test (1 item). I did NOT press "Delete for good", so the folder stays in the trash. (t04-trash2, t04-trash-final)
5. Apps grid (grid icon in top bar): opens with "No apps yet", Programs (AbiWord, Archive manager, Files, Firefox, Gnumeric, Image viewer, Terminal, Text editor) and "Make one" (Scientific calculator, Calculator, Calendar, Clock, Converter, Countdown, Dice, Flashcards). Click "Files": the grid closes. The Files app is Thunar (a different file manager, at /root/, not the LLM OS window), opened as "Opened Files in a window." No warning bar. Closed Thunar with its X. (t04-grid, t04-filesapp)
   Note: the "Open in Files" button inside the LLM OS Files window also opened this Thunar window at /root/ (seen in t04-filemenu).
6. Calculator: grid > "Calculator" (Make one). Opened as "Here's your Calculator. It's kept in your apps." Clicked 1, 2, ×, 3, =: display shows "12 × 3 = 36". Correct. Closed with its X. Calculator is now in the grid with Open / Remove; I removed it at the end (reply "Removed the app 'Calculator'."). (t04-calc, t04-calc36, t04-grid4)
   Text editor: grid > "Text editor" opens Mousepad, the grid closes. Closed with its X: the dock chip "Mousepad" disappeared. Pass. (t04-texteditor, t04-texteditor-closed)
7. "install gnome-mines": 21 s. Reply "Opened 'gnome-mines' in a window." The Mines window opens by itself (8x8, 16x16, 30x16, Custom). The dock chip "gnome-mines" appears. Mines is listed under Programs in the grid. Closed Mines with its X. (t04-install, t04-grid-mines)
   "uninstall gnome-mines": 3 s. Reply "Removed gnome-mines". VM: `which gnome-mines` returns nothing, mousepad still there. The grid, reopened, no longer lists Mines. (t04-uninstall, t04-grid-after)

## Bugs
1. "write a short shopping list into notes.txt": the file contains the literal words "a short shopping list", not a list. Reply: "Added 'a short shopping list' to ~/Documents/HW Test/notes.txt." Expected a few shopping items.
2. "delete the HW Test folder": reply "Done. The HW Test folder is gone." The folder was still on the laptop with list.txt inside. The action shown was `run: rm -rf ~/Documents/HW Test`, a permanent delete that bypasses the trash. It should move to the trash like "delete list.txt" does, and the reply must match what happened. A second request ("move the HW Test folder to the trash") worked.
3. Mousepad: ctrl+s did not save (title kept "*", file unchanged after two presses). File > Save from the menu saved correctly. Whether the key reached Mousepad is not certain, but a person pressing ctrl+s would expect it to save.
4. Apps grid: while gnome-mines was installed, "Text editor" disappeared from the Programs list (Mines took its place). It returned after uninstall. Not reproduced a second time.
5. Apps grid after uninstall: the grid still showed Mines in the first reopened view after uninstall (the old list); a later reopen was correct.
6. Folders in the LLM OS Files window have only "Open" (no Delete), while files have "Delete". So a person cannot delete a folder from the window; only by asking.

## Friction and Ideas
- Maximize needed two clicks on the green button (the first click seemed to only focus the window).
- The notes.txt viewer shows stale text after the file was changed in Mousepad (it still showed the old line until closed and reopened).
- "Open in Files" and the grid's "Files" open Thunar (a GTK file manager at /root/), not the LLM OS Files window. The two Files apps are inconsistent. Thunar is small with small icons at this size but readable.
- Status toasts (e.g. "Here they are.", "Your Documents folder is empty.") sit over the window titles and make the window name hard to read for a few seconds.
- "Make one" calculator: fine, but it is added to "your apps" without asking; it can be removed with Remove.
- Scale: at 1920x1200 with 1.25x, text in the LLM OS windows, the apps grid and the Mines window is sharp and readable. No blurry text seen in the screenshots. Mousepad and Thunar text looks small but readable. No window failed to fit the screen.
- Speed: all file commands took about 2 s; installing gnome-mines took 21 s; uninstalling took 3 s.

## Cleanup
- /root/Documents is empty, as it was at the start.
- HW Test (with nothing else in it) is in the trash, not permanently deleted. Empty it only if you want it gone.
- Calculator app removed. gnome-mines removed (package no longer present).
- All windows opened during the test are closed. The pre-existing file "u" in the home folder was not touched.
