# 07 windows

## Task
Handle windows like a normal person: open two windows, drag, stack, click the request bar, maximize and restore, minimize and restore from the bottom, close, test the top-bar panels, ask a slow task and close its reply card, bring it back with the orb, resize from a corner.

## Verdict
PARTLY. Dragging, stacking, maximize/restore, minimize/restore, top-bar panels and the orb-brings-task-back all work. Problems: opening a new window replaces the one already open (Settings and Files do not stay together), Files from the Apps list opens a broken Thunar window, and the Wi-Fi reply contradicts the Network panel.

## Steps

Screenshots are in `/Volumes/Files/Claude Work Area/LLMOS/Support files/run/sweep/shots/` (w0 to w26).

1. Start state (w0): desk with a "While you were away" window already open. I left it alone and did not close it at the end.
2. Said "open settings" (w1). Settings opened in about 2 s. Expected: a second window beside the first. Result: Settings opened.
3. Said "show my files" (w2). Expected: Files opens next to Settings. Result: Settings disappeared and Home opened in its place. Window list: "While you were away" and "Home" only.
4. Said "open settings" again (w3). Settings opened and Home disappeared.
5. Clicked the grid icon at top (808,22) (w4). Expected: the app menu opens beside Settings. Result: an "Apps" window replaced Settings.
6. Clicked "Files" in the Apps list (w5). Expected: Files opens. Result: "Thunar File Manager" opened with an error "Failed to open 'File'. Error when getting information for file '/root/File': No such file or directory." Closed the error and the Thunar window (w6).
7. Said "show my files" again (w7). Home opened and Apps disappeared. The two windows are now "While you were away" and "Home", which satisfies "two windows open".
8. Dragged Home by its title bar from (700,89) to the top edge (700,2) (w8). It stopped just under the top bar, with its top edge at about y=46. It did not reach the top bar.
9. Dragged Home down over the request bar, title bar from (700,69) to (700,700) (w9). The window went in front of the request bar and ran off the bottom of the screen, so its title bar and top row of buttons were visible but the lower part was cut off.
10. Clicked the request bar text at (445,744) (w10). The bar came to the front, above Home, and Home dimmed behind it.
11. Clicked maximize on Home at (1197,700) (w11). Home filled the screen under the top bar. The request bar was hidden behind it.
12. Clicked restore at (1205,77) (w12). Home went back to its old spot at the bottom, partly off the screen, not to its pre-maximize position.
13. Dragged Home from (700,700) to (700,300) (w13), then clicked minimize at (1161,300) (w14). Home went to a "Home" chip at the bottom left.
14. Clicked the "Home" chip at (50,756) (w15). Home came back in place (x 480 to 1259, y 277 to 770).
15. Network icon (1144,23): first click opened a "Network" panel (w16). Second click closed it (w17). Both quick. Opening it replaced Home. The panel says "Connected (cable)" and "This computer has no Wi-Fi; plug in a network cable." The state reply said "Here are the Wi-Fi networks."
16. Sound icon (1192,23): first click opened a "Sound" panel at 100% with the volume buttons and "More sound settings" (w18). Second click closed it (w19). Each click took about 1 s.
17. Said "write a 200-word story about a lighthouse" (w20). Expected: reply card shows writing. Result: the card showed "writing... 4 s / usually ~6 s" with Stop, History and Close buttons.
18. Clicked Close on the reply card at (950,674) while it was writing (w21). The card closed. The state still reported busy.
19. Clicked the orb at (310,744) (w22). The reply card came back at 13 s, still writing, with the text so far. The task was not lost.
20. Waited for it to finish (waitreply 300): 19 s more (w23). The full story is shown in the card, which scrolls. I did not count the words exactly; it looks longer than 200 words.
21. Said "show my files" (w24). Home opened and the "While you were away" window stayed.
22. Dragged Home's bottom-right corner from (1258,559) to (1000,450) (w25). The window resized to x 480 to 1000, y 66 to 450. Its content reflowed: the buttons wrapped and a scroll bar appeared.
23. Clicked Home's X at (975,89) (w26). Home closed. Only "While you were away" remained, which I did not open.

## Bugs

1. Opening a window closes the one already open. Typed "open settings", then "show my files": Settings vanished (w2). Clicking the grid icon also replaced Settings with Apps (w4). A person expects both windows to stay (screen w3 vs w2). Expected: each new window opens beside the others.
2. "Files" in the Apps list opens Thunar File Manager, which fails. Clicked "Files" at (1052,220) (w5). Expected: the same Files window that "show my files" opens (w2, w7). Actual: "Failed to open 'File'" and "/root/File: No such file or directory".
3. Wi-Fi reply contradicts the panel. Clicked the network icon (w16). Reply text: "Here are the Wi-Fi networks." Panel: "This computer has no Wi-Fi; plug in a network cable." Expected: the reply matches the panel.
4. Dragging a window down ends with it off the bottom of the screen (w9). The title bar was at y=700 and the rest was cut off. Expected: the window stops with its whole title row and buttons on screen.
5. Restore after maximize puts the window back in its old spot, partly off the bottom of the screen (w12). Expected: restore to the size and place it had before maximize.
6. The state still says "busy" after the reply card was closed. Clicked Close at (950,674) while it wrote (w21). Expected: the card closed and the task keeps going or stops clearly. The task did finish later, so this is a status detail rather than a lost task.

## Friction

- Dragging a window to the top stops at about y=46, just under the top bar. Fine, but a person may expect it to meet the bar.
- After minimize and restore, the window is partly off the screen. Needs a move before it is usable.
- The reply card's Close button sits at the bottom right of the card, next to History. It is easy to hit by accident while the text is streaming, and the card moves as text grows.
- Opening the Apps grid, then the Files entry, goes through two windows that replace each other.
- The top-bar icon highlight stays on after a panel closes until the mouse moves (w17).

## Ideas

- Keep every opened window on screen (clamp drags so the title bar stays visible).
- Let the new window open beside the others instead of replacing one.
- Make "Files" in the Apps list call the same code as "show my files".
- Have the Wi-Fi answer read from the same state the panel shows.
- On restore, go back to the window's pre-maximize size and position.
