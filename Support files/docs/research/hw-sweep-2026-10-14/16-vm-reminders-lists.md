# 16. Reminders, timers, alarms, lists and History (VM)

## Task
Reminders, timer, alarm, shopping and packing lists, and History, tested on the VM by asking and clicking.

**Verdict: PARTLY.** Reminders, the timer, the alarm, the lists and the topic split in History all work. The bugs: an internal code in a reply, the weekly reminder losing its repeat, a packing list that does not appear where the reply says it does, Wikipedia citation markup in an answer, and a 91-second answer.

Times are wall-clock from the `say` call to the reply (`waitreply`). Start of test 02:33:22, end about 02:41.

## Steps

1. **"set a 2 minute timer for the pasta"**: reply in 2 s. "Timer set — 2 minutes (the pasta), it rings at 02:35." Screenshot `t1`.
2. **"remind me to call the dentist tomorrow at 9am"**: reply in 2 s. "Reminder set for tomorrow at 09:00: call the dentist."
3. **"wake me up at 7am"**: reply in 2 s. "Reminder set for 07:00: Alarm." It is called a reminder, not an alarm, and the item is named "Alarm" with no time-of-day wording.
4. **"remind me every Monday to take out the bins"**: reply in 13 s. "Reminder set for Monday at 9:00 AM to take out the bins." The user gave no time, and the app picked 9:00 AM without asking.
5. **"what are my reminders"**: reply in 5 s, and a "Scheduled" window opened. It listed all four with correct times: 2 minutes (the pasta) Thu 15 Oct 02:35; call the dentist Fri 16 Oct 09:00; Alarm Thu 15 Oct 07:00; Take out the bins Mon 19 Oct 09:00. The bins row shows one date only, with no "every Monday". Screenshot `t2`.
6. **Pasta timer goes off**: I waited for 02:35. At 02:35:26 nothing had happened. It had fired by my next poll (about 02:36). A "Time's up: your 2 minutes (the pasta) timer is done." dialog with an OK button appeared, and the same line was added to "While you were away". Screenshot `t4`. The timer was still listed in the Scheduled window until I clicked OK, then it disappeared. Clicked OK at 02:36:55 (`t6`).
7. **"cancel the dentist reminder"**: reply in 5 s. "Cancelled: call the dentist." The item left the Scheduled window. An "Open now" card ("Scheduled / on the desk", with a Close button) also appeared. Screenshot `t7`.
8. **Alarm Cancel button** (clicked at 1208,151): the row greyed out, then the reply appeared 3 s later as "Cancelled: the alarm reminder (997544) for 07:00 Thu 15 Oct." Screenshots `t8`, `t9`.
9. **"add bread, butter and jam to my shopping list"**: reply in 6 s. "Added to your shopping list." The Shopping window showed bread, butter, jam.
10. **"show my shopping list"**: reply in 5 s. "Shopping: bread, butter, jam." Screenshot `l2`.
11. **Tick off butter by clicking it**: first I clicked the word "butter". Nothing happened. Then I clicked its "Done" button, which struck it through, moved it to the bottom and showed an Undo button. Screenshots `l3`, `l4`.
12. **"remove jam from my shopping list"**: reply in 5 s, "Removed." Jam went. Screenshot `l5`.
13. **"clear my shopping list"**: reply in 5 s, "Removed." The Shopping window showed "(nothing on this list)". Screenshot `l6`.
14. **"make a packing list for a weekend camping trip"**: reply in 8 s. The reply text says "The list is shown", and the answer lists 10 items. But no list was visible. Only a "Packing" button appeared inside the Shopping window. Screenshot `p1`.
15. **Clicked the "Packing" button**: a Packing window opened with all 10 items, each with Done and Remove buttons. A speech toast at the top also repeated the list and was cut off mid-word ("...Pack a waterproof rain jacke"). Screenshot `p2`.
16. **"what's the capital of France"**: reply in 2 s. "Paris[b] is the capital and largest city of France, with an estimated city population of 2.04 million ... (source: en.wikipedia.org)". Wikipedia footnote markers are in the text.
17. **"and of Germany?"**: reply in **91 s** (slow). "Berlin is the capital of Germany." It understood the question was about capitals.
18. **"write me a haiku about autumn"**: reply in 8 s, a three-line haiku. Screenshot `h1`.
19. **History button** (on the haiku reply card): the Conversations window opened behind the Packing window. Clicked its edge to bring it forward (`h3`). Topics were separate: "write me a haiku about autumn" (NOW), "what's the capital of France" (2x, with the Berlin answer inside it), and "make a packing list..." and so on. The haiku did not join the France topic. This part works as the brief asks.
20. **Cleanup**: cancelled the bins reminder by asking ("cancel the bins reminder", reply in 3 s, "Cancelled: Take out the bins."). Cleared the packing list by asking ("clear my packing list", reply "Removed."). Closed Packing, Scheduled, Conversations and the Open now card. Forgot my own test topics in Conversations (these are gone). Final state: the Scheduled window said "Nothing scheduled." and the desk shows only "While you were away", which was already open when I started.

## Bugs

1. **Alarm cancel reply shows an internal code.** I clicked Cancel on the alarm and saw "Cancelled: the alarm reminder (997544) for 07:00 Thu 15 Oct." The number 997544 is an internal ID. It should say "Cancelled: the 7:00 alarm." (Screenshot `t9`.)
2. **The weekly bins reminder lost its repeat.** I typed "remind me every Monday to take out the bins". The Scheduled list shows "Take out the bins, Mon 19 Oct 09:00" with no sign it repeats. It should show "Every Monday, 9:00 AM". Also, the app chose 9:00 AM without asking, though the user gave no time.
3. **Packing list not shown.** The reply says "The list is shown", but nothing opened. The list was only reachable through a small "Packing" button inside the Shopping window, which said "(nothing on this list)". The list should open in its own window when made.
4. **Wikipedia citation markup in an answer.** "Paris[b] ... [4] ... (source: en.wikipedia.org)". Citation brackets and the source line should be stripped before the reply is shown. The History preview shows "Paris[b]" as well.
5. **Speech toast cut off.** The packing reply in the toast stops at "rain jacke". The toast text needs to fit or scroll.
6. **Expired timer stays in the Scheduled list** until the "Time's up" dialog is clicked OK. It should drop off when it fires.
7. **Germany answer took 91 seconds.** A one-line capital question should not take that long. (The answer was right: "Berlin is the capital of Germany.")
8. **Timer name is awkward.** The timer is listed as "2 minutes (the pasta)". It should be "Pasta timer" or "Pasta (2 min)".
9. **Alarm named "Alarm".** The wake-up is listed as "Alarm, Thu 15 Oct 07:00", and the reply called it a "Reminder". It should read "Wake up, 7:00 AM".

## Friction

- Clicking the item name on a shopping list did nothing. Only the "Done" button ticks it off. A person would click the name first.
- "remove jam" and "clear my shopping list" both answer just "Removed." They should say which item went, or "Cleared your shopping list."
- The "Open now" card appeared after cancelling the dentist reminder, with a Close button, and it stayed on the desk until I closed it.
- After I clicked History, the Conversations window opened behind the Packing window and I had to click its edge to bring it forward.
- In Conversations, "Forget" deletes a topic immediately with no confirmation.

## Ideas

- Give recurring reminders a "Repeats every Monday" line in the Scheduled window and in the reply.
- If a time is missing ("take out the bins" with no time), ask for one.
- Show the packing list in a window when it is made, the way the shopping list does.
- Strip citation markers like [b] and [4] from answers.
- Ask "Are you sure?" before Forget.
- Let a tap or click on a list item's name tick it off.
