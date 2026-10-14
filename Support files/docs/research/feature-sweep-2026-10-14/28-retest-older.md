# Retest of older features (28)

**Verdict: PARTLY.** Most everyday tasks work. Two real failures: a shopping list stores "milk and eggs" as one item, and a stopped story gives no "stopped" marker. Delete also does not name the folder in its reply.

Tester: Haiku 5.5, through the screen only. Screenshots are in `run/sweep/shots/` (names below).

## Steps

| # | Step (what I typed or clicked) | Expected | What happened | Time | Screenshot | Result |
|---|---|---|---|---|---|---|
| 1a | "write a short thank-you note to my neighbour and save it as thanks4.txt" | Note shown, "Saved as ~/Documents/thanks4.txt", activity line not stuck | Note shown, "Saved as ~/Documents/thanks4.txt.", activity line "saved ~/Documents/thanks4.txt". `/root/Documents/thanks4.txt` exists, text matches the reply, no square brackets. | 14 s | s1a | PASS |
| 1b | "delete thanks4.txt" | Under 20 s, reply and activity line name ~/Documents, file gone | Reply "Moved thanks4.txt to the trash." Activity line "trash thanks4.txt". File gone from Documents. No folder named. | 3 s | s1b | PARTLY (folder not named) |
| 2 | "what's the weather like" | Names a source, has a temperature | "Today in Phoenix, Arizona: clear, high 76°F ... (Source: Open-Meteo forecast, open-meteo.com.)" | 3 s | s2 | PASS |
| 3 | "search the web for the population of Tokyo" | Number and source | "Tokyo Metropolitan Government: 14.27 million (as of October 1, 2025). (Source: worldpopulationreview.com ...)". A "Sources" window opened (I closed it). | 19 s | s3 | PASS |
| 4a | "make a to-do list for moving house" | List with several real items | 10 items listed in a To-do window (Clean out one room..., Pack fragile items..., etc.). | 8 s | s4a | PASS |
| 4b | "add milk and eggs to my shopping list" | Two separate items: milk, eggs | One item: "milk and eggs". Reply "Added to your shopping list." | 2 s | s4b | FAIL |
| 4c | (retry) "put eggs and butter on my shopping list as separate items" | Separate items | Items "eggs" and "butter" added. Reply came after about 2 min 10 s (progress stuck at "Reading your request 99%" for a while). | about 2 min 10 s | s4c, s4d | PARTLY (split works, very slow) |
| 5 | "open the calculator", then 1 2 × 3 = by clicks | Full keypad incl. 0 . =; result 36 | Full keypad visible. Display "12 × 3 = 36". Closed with X. | under 3 s | s5a, s5b | PASS |
| 6 | "open the text editor", then window X | Dock chip gone within about 3 s | Mousepad opened with a chip "Mousepad ×" bottom-left. After the window X, the chip was gone within 3 s. | 3 s | s6a, s6b | PASS |
| 7 | Speaker icon, then Mute, then Unmute | Panel and icon show muted, then unmuted | Panel "75% · muted" with "Unmute" button; toast "Muted."; back to "Unmuted." and "Mute" button. | instant | s7a, s7b, s7c, s7d | PASS |
| 8 | Lock icon once, then passphrase "correct horse battery" + Enter | Locks at once; unlocks | The "Lock now" tooltip showed and the desk was still visible about 2 s after the one click. `state` then showed the lock screen. Unlock worked; desk back. | about 2 to 3 s to lock | s8a, s8b, s8c | PASS (lock delay noted) |
| 9a | "set a 1 minute timer for the eggs" | Timer set | "Timer set — 1 minute (the eggs), it rings at 16:20." | 2 s | s9a | PASS |
| 9b | "remind me to call mum in 10 minutes" | Reminder set | "Reminder set for 16:29: call mum." | 2 s | s9b | PASS |
| 9c | "what are my reminders" | Names right, not swapped | "[675ce5] Wed 14 Oct 16:20: 1 minute (the eggs)" and "[b7c98e] Wed 14 Oct 16:29: call mum". Names correct. | 2 s | s9c | PASS (friction: IDs in brackets) |
| 9d | Cleanup: Cancel on eggs timer, then Cancel on call mum | Both removed | Eggs timer removed after the first Cancel click, but the list did not refresh for about 3 s. A second click queued "cancel the task 675ce5" and replied "The task ID "675ce5" does not exist". Call mum cancelled with "Cancelled the reminder: "call mum."". | 3 s and 8 s | s9d-s9i | PASS with bugs (see Bugs 3) |
| 10a | "turn on night light" | Warm screen or clear preview/notice | Reply: "Night light is on: it starts at 7 pm and ends at 7 am. The screen just showed it warm for a few seconds as a preview". The screenshot was taken after the warm preview had ended, so I did not see the warmth myself. | 2 s | s10a | PASS (notice) |
| 10b | "turn off night light" | Off | "Night light is off" | 2 s | s10b | PASS |
| 11 | "tell me a long story about a dragon", then Stop while writing | Card shows it was stopped | The card was "thinking..." for about 16 s, then I clicked Stop. The card ends mid-sentence: "...whispering to". No "stopped" note, no "Stopped" label. Looks like a normal finished answer. | about 16 s before Stop | s11a, s11b | FAIL |
| 12a | "what's 15% of 80" | 12 | "15% of 80 is 12." | 3 s | (no shot) | PASS |
| 12b | "write me a haiku about rain" | Not tied to the percent topic | Haiku shown as its own answer, no mention of percent. | 8 s | s12a | PASS |

Cleanup: closed Mousepad, Calculator, Sound, Shopping, Scheduled, Sources and To-do windows. Removed the test shopping items (milk and eggs, eggs, butter) and the 10 to-do items. Cancelled both test reminders. Night light off. Computer unlocked, desk clean (`final`). Not undone: thanks4.txt is in the trash (the delete moved it there; I did not empty the trash).

## Bugs

1. **Shopping list: two items in one line.** Typed: "add milk and eggs to my shopping list". Saw: one item "milk and eggs"; reply "Added to your shopping list." Should be: two items, "milk" and "eggs". Retry with "put eggs and butter on my shopping list as separate items" split correctly, but took about 2 min 10 s.
2. **Stopped story shows no stop.** Typed: "tell me a long story about a dragon"; pressed Stop at about 16 s. Saw: card ends mid-sentence "whispering to" with no note that it was stopped. Should be: card says it was stopped (e.g. "Stopped.").
3. **Cancelling a reminder: stale list and a confusing error.** Clicked Cancel on "1 minute (the eggs)" (row stayed for about 3 s; a second click then sent "cancel the task 675ce5"). Saw: reply "The task ID "675ce5" does not exist in the list. Did you mean something else?" Should be: row disappears at once, no second request for a removed task.
4. **Delete reply does not name the folder.** Typed: "delete thanks4.txt". Saw: "Moved thanks4.txt to the trash." and activity line "trash thanks4.txt". Should be: names ~/Documents (the file's place), e.g. "Moved ~/Documents/thanks4.txt to the trash."
5. **Lock is not instant.** One click on the lock icon. Saw: desk still showing about 2 s, then the lock screen. Should be: locks at once.

## Friction

- Shopping and reminders: slow reply for the split shopping request (about 2 min 10 s, progress "Reading your request 99%").
- Reminder list shows raw IDs in square brackets, e.g. "[675ce5] Wed 14 Oct 16:20: ...". Hard to read.
- Timer name is stored as "1 minute (the eggs)" (the brief's words as a label). Reads awkwardly in the list.
- To-do window and reply text overlap: the window is see-through, so the reply text shows behind it.
- Night light: the warm preview is only a few seconds, and the screenshot after the reply had already missed it. The reply notice is the only proof.
- Cancel buttons in the Scheduled window: no visible feedback for about 3 s after the click.

## Ideas

- Shopping: split "X and Y" into two items when the user lists things, or ask "one item or two?".
- Stopped answers: add a visible "Stopped" line on the card and keep it in History.
- Reminders: show "16:20 · eggs timer" instead of IDs; keep IDs in History only.
- Delete: always name the full path in the reply.
- Show a short "Cancelling…" state on Cancel buttons so the click feels registered.
