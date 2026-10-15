# 20. Closing windows never deletes or moves files (VM, 1.8.9.35)

## Task
Close windows (Open now list, Show/Close, "close window <path>", Escape) must never delete or move files. Timer rings during an answer.

**Verdict: PARTLY.** No file was lost or moved by any close action. But the Open now window was hidden behind other windows, the Files row had no Show button, and the timer-during-story test could not be proven because the story finished first.

## Steps
Baseline: VERSION=1.8.9.35. Pictures had 9 items, .Trash had 13 items (incl. folder "Sweep Test").

1. "take a screenshot" -> saved screenshot-20261015-041427.png, about 2 s. Looked fine.
   "show my pictures" -> "9 items in ~/Pictures", about 2 s. Window ~/Pictures opened.
   Clicked thumbnail screenshot-20261014-121905.png -> opened in its own window, with the file path at the bottom.
2. "what's open" -> reply "Open now: While you were away, screenshot-20261015-041427.png, ~/Pictures, screenshot-20261014-121905.png", about 2 s.
   BUG: the Open now window was not visible on the desk. It was under the ~/Pictures window. Only after I dragged ~/Pictures aside did it show, with Close on each row and no Show (these are files, so Show is not expected).
   My first attempt to close the picture window with its X hit the ~/Pictures title bar instead (that window covered the X). Harmless.
   Clicked Close on the picture row -> the picture window closed, the Open now row went away, the list updated. Files unchanged.
   Clicked Close on the screenshot row -> closed, list updated. Files unchanged.
   Pictures still had all 8 other items after both closes.
3. "open files" -> a "Home" folder window (6 items in ~), about 2 s.
   "what's open" -> Open now listed "Home" with a Close button only. BUG/FRICTION: no Show button on the Files row, although the brief expects one.
   Clicked Close on Home -> closed, nothing changed in /root.
4. "close window file:/root/Pictures/nothing-here.png" -> "That window is already closed." Nothing deleted, Pictures and Trash counts unchanged.
5. Clicked the title of the Open now window, pressed Escape -> Open now closed, and only that window. Nothing deleted. ("While you were away" stayed.)
6. "set a 1 minute timer for the eggs" at 04:16:09 (VM clock), reply "Timer set - Eggs (1 minute), it rings in 1 minute (04:17)", about 2 s.
   "write a 200 word story about a fox" sent at 04:16:18. The story was complete when I looked at 04:17:05, so it had finished BEFORE the timer rang. The timer test during writing is therefore inconclusive (I did not catch the story mid-write).
   At 04:17:05 the state had no Time's up window. At 04:17:29 it showed "Time's up: your Eggs (1 minute) timer is done" as a popup and in the While you were away list. The ring came at about 04:17:05-04:17:29, so it was late by up to ~25 s if the timer was due at 04:17:00. Not measured exactly.
   Dismissed with OK.

Cleanup: closed the Time's up popup, the story window, the Pictures window, the Open now window and the reply card. "While you were away" was open before I started and was left as found.
"delete screenshot-20261015-041427.png" -> "Moved screenshot-20261015-041427.png from ~/Pictures to the trash." This was my screenshot only. I did not empty the trash (the trash holds other testers' items). Pictures now has its original 8 items; Trash has 14 items (13 + mine).

## Bugs
- Open now window opened behind the ~/Pictures window and was not visible until that window was moved. Expected: the list is on top when asked.
- Files program window listed as "Home" with Close only. Expected a Show button, as the brief describes.
- Timer popup appeared up to ~25 s after the due time (04:17 due; not seen at 04:17:05, seen at 04:17:29). Expected to ring at 04:17:00.
- Timer during story: not tested properly. The story was already finished when the timer rang.

## Friction and Ideas
- The "take a screenshot" text stays in the picture window's request box. Minor.
- Open now should list the window stacking order or bring itself to the front.
