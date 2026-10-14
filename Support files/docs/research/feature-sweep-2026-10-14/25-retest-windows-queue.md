# 25 retest-windows-queue

## Task
Retest of the window and queue fixes from 07-windows.md and 10-reminders-queue.md: two windows staying open together,
dragging a window off the bottom, maximize and restore, a quick answer during a slow story, Waiting and Stop, and
Delete in a Files window updating by itself.

## Verdict
WORKS. All five checks pass. Remaining problems are small: the restored window moves to a different spot, the stopped
story card has no marker of its own (only a toast), and the Delete button sends the file to the trash.

## Steps

Screenshots are in `run/sweep/shots/` (prefix `rt25-`).

1. **Two windows stay open.** Said "open settings" (2 s, `rt25-1-settings`), then "show my files" (2 s, `rt25-1-files`).
   Settings stayed open next to Home. Window list: While you were away, Settings, Home. **PASS.**
2. **Drag past the bottom.** Dragged Home's title bar from (700,119) to (700,790). The title bar stopped at about y 779
   and stayed on screen (`rt25-2-drag`). Grabbed it again at (700,779) and dragged it up to y 300; it moved (`rt25-2b-regrab`).
   **PASS.**
3. **Maximize and restore.** Maximize at (1161,300) filled the screen (`rt25-3-max`). Restore at (1205,77) brought Home back
   fully on screen at x 25 to 803, y 278 to 772 (`rt25-3-restore`). **PASS.** It did not return to its pre-maximize spot
   (x 445 to 1223); see Friction.
4. **Quick answer during a slow story, then Waiting and Stop.**
   - Said "write a 300-word story about a dragon", then 3 s later "what time is it". The answer "It's 1:32 PM on
     Wednesday, October 14, 2026." appeared at once as a notice at the top, and the story kept writing (`rt25-4-time`,
     busy still true). The answer came within about 2 s of asking; I did not time it to the second.
   - Said "write a haiku about rain". A toast said "Added to the queue", and the reply card showed Waiting with
     "1. write a haiku about rain" and a ✕ (`rt25-4-queue`).
   - Clicked Stop at (812,674). The story stopped mid-sentence ("For centuries") and a toast said "Stopped. 1 waiting
     request cancelled too." (`rt25-4-stop`). State: busy false, queued 0. **PASS.**
5. **Delete in Files updates by itself.**
   - Said "make a text file called rt25.txt". Reply: "Made ~/Documents/rt25.txt."
   - Said "show my documents". The Home window was replaced by "~/Documents" listing rt25.txt (0 B) and zz-sweep3.txt
     (`rt25-5-docs`).
   - Clicked Delete on rt25.txt at (754,409). The row vanished at once with no reload; the window kept zz-sweep3.txt
     (`rt25-5-delete`). Toast: "Moved rt25.txt to the trash." **PASS.**
   - zz-sweep3.txt was left alone. It was made by another tester.

Closing: closed the ~/Documents window at (777,300) and Settings at (1233,89). Only "While you were away" remains, as at
the start (`rt25-end`). rt25.txt is in the Trash, since Delete moves files there and I did not empty it.

## Bugs
None that break a check. Minor:
1. **Restore after maximize does not go back to the old spot.** Home was at x 445 to 1223, y 278 to 772 before maximize
   (`rt25-1-files`, `rt25-2b-regrab`). After restore it was at x 25 to 803 (`rt25-3-restore`). It is on screen, but it
   moved. Expected: the pre-maximize size and place.
2. **The stopped story card has no "stopped" note of its own.** After Stop, the text ends at "For centuries" with only
   the Close and History buttons (`rt25-4-stop`). The toast says it stopped, but the card does not. Expected: a small
   "Stopped" line under the text, so the card alone says what happened.

## Friction
- "show my documents" replaced the open Home window instead of opening a second window. Test 1 passed because Settings
  and Home were both opened by name, but a person who opens two folders may expect both to stay.
- The Delete button says "Delete", but the notice says "Moved … to the trash". Calling the button "Move to Trash" would
  match what happens.
- The time answer and the Waiting toast stack on top of each other at the top of the screen (`rt25-4-queue`). Readable,
  but crowded.

## Ideas
- Restore a maximized window to its exact pre-maximize size and place.
- Add a "Stopped" line to a reply card that was stopped.
- Let a second folder open in its own window, the way Settings and Home do.
- Call the Delete button "Move to Trash" (or empty the trash when the person asks).
