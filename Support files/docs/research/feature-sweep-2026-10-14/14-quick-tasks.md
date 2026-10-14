# 14 quick-tasks

## Task
Everyday quick requests in the normal Do mode, one at a time, timed. Each question was typed into the request box (`vmuser.py say`) and the reply was read with `waitreply`. Time is the "took N s" value printed for each request.

## Verdict
PARTLY

The quick facts (percent, unit conversion, weekday, date) were right and fast. Lists and window actions worked. The moving-house to-do request failed on the first wording and only worked on a second, reworded request. The disk-space reply did not contain the numbers, and the Shopping window closed silently when the Storage window opened.

## Steps

| # | Said | Took | Reply | Right? | Did the thing? | Screenshot |
|---|------|------|-------|--------|----------------|-----------|
| 0 | (start state) | - | Desk clear, no windows, Do mode | - | - | 14-start |
| 1 | what's 15% of 80 | 2 s | "15% of 80 is 12." | Yes | n/a | - |
| 2 | convert 5 miles to kilometres | 2 s | "5 miles is 8.05 kilometres." | Yes (8.047) | n/a | - |
| 3 | what day of the week is Christmas this year | 2 s | "Christmas is on a Friday (25 December 2026)." | Yes | n/a | - |
| 4 | add milk to my shopping list | 2 s | "Added to your shopping list." Shopping window opened | Yes | Yes | 14-after-milk |
| 5 | show my shopping list | 2 s | "Shopping: milk." Window shows milk with Done / Remove | Yes | Yes | 14-show-list |
| 6 | what's the date | 2 s | "It's 12:23 PM on Wednesday, October 14, 2026." | Yes | n/a | - |
| 7 | how much disk space do I have | 2 s | "Here's the storage." Storage window opened: 9.0 GB free of 15.5 GB | Window yes, reply no numbers | Yes (window) | 14-disk |
| 8 | close all windows | 2 s | "Done." Desk empty | Yes | Yes | 14-close-all |
| 9 | make a to-do list for moving house | 2 s | "Here's your To-do. It's kept in your apps; say 'open to-do' any time." To-do window opened EMPTY ("0 left") | No: nothing added | No | 14-todo |
| 9b | add book movers and pack the kitchen to my to-do list (second try, one wording change) | 2 s | "Added to your to-do list." Window shows one item: "book movers and pack the kitchen" | Partly: one item, not a list | Yes, but as one line; a second To-do window opened, the first stayed blank | 14-todo-retry |
| 10 | explain what a VPN is in one sentence | 8 s | One sentence: encrypts your connection, routes through a secure server, hides real IP and location | Yes (a little loose on "from networks") | n/a | 14-vpn |

No request took over 30 s. The slowest was the VPN explanation at 8 s.

## Cleanup
- Removed the to-do item "book movers and pack the kitchen" (Remove button). Screenshot 14-cleanup1.
- Removed "milk" from Shopping (Remove button). Screenshot 14-cleanup3. Shopping now shows "(nothing on this list)".
- Closed the blank To-do window (X), the Shopping window (X). Desk clear, state shows no windows. Screenshot 14-final.
- The Storage window was closed by "close all windows" in step 8. No settings were changed. Storage's "Empty the trash" and "Clear caches" buttons were not pressed.
- The Shopping and To-do lists still exist but are empty. There is no UI here to delete a list itself.

## Bugs
1. **To-do list for moving house gives an empty list.** Typed: `make a to-do list for moving house`. Saw: reply "Here's your To-do..." and a To-do window with no items and "0 left". Expected: a list of moving-house tasks (pack boxes, book movers, change address, and so on), or at least a clear message that it could not make one. A user would think it worked and see nothing.
2. **Reworded to-do request makes one long item.** Typed: `add book movers and pack the kitchen to my to-do list`. Saw: a single item "book movers and pack the kitchen". Expected: two items, "book movers" and "pack the kitchen". The request also opened a second To-do window and left the first one empty, so there are now two To-do windows.
3. **Disk space reply has no numbers.** Typed: `how much disk space do I have`. Saw: reply "Here's the storage." The numbers appear only in the Storage window (9.0 GB free of 15.5 GB). Expected: the reply says the free amount, for example "You have 9.0 GB free of 15.5 GB."
4. **Shopping window closed without a word.** After step 6 the Shopping window was open. After step 7 (disk space) only Storage was open and state listed windows ["Storage"]. Expected: Shopping stays open, or the reply says it was closed. I had to reopen the list with "show my shopping list" to remove milk.
5. **Stale reply bubble.** The reply bubble at the bottom kept "Shopping: milk." after the milk was removed. Minor.

## Friction
- The to-do request first answered "Here's your To-do" as if it had done the job, even though it had nothing in it. The wrong success message is the main trap.
- Closing a window with the X sometimes left it on screen for a moment after state already showed it gone. Waiting 2 s before the screenshot fixed it.
- The To-do window's "Shopping" and "Lists" chips show the list is shared, but it is not clear what they do.
- "close all windows" answered "Done." with no detail, which is fine.

## Ideas
- For list requests with no items named, ask what to put on the list, or offer a starter list the user can accept.
- Put the figures in the reply text itself ("9.0 GB free of 15.5 GB") rather than pointing at a window.
- Split "add X and Y to my to-do list" into two items, or ask.
- Reuse the open To-do window instead of opening a second one.
- Keep a list window open when an unrelated window opens, or say which one closed.
