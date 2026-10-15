# VM verify 1.8.9.33: earlier failures (9 checks)

## Task and Verdict
Re-check the 9 earlier failures on the test VM (VERSION=1.8.9.33, confirmed with `grep VERSION /etc/llmos-release`).
Tool: tools/vmuser.py (the VM stand-in for devlink.py).

**Verdict: PARTLY.** 8 of 9 checks pass. Check 1 could not be finished: the file check on the VM was blocked by a
Mac-side hook (see Bugs/Friction). The screen shows the screenshot file still listed in ~/Pictures after the close.

## Steps
0. `vmuser.py wait 90` then version check: 1.8.9.33. The desk showed "Updated: LLM OS 1.8.9.33 ... is installed."
1. SAFETY FIRST. say "take a screenshot": reply "Saved in Pictures as screenshot-20261015-040037.png and copied"
   (2 s). Shot 01-after-screenshot. say "what's open": state reply "Open now: While you were away, screenshot-...png"
   but no "Open now" window appeared on screen (shot 01-whats-open, 01-whats-open-2). Clicked the Close on the
   screenshot's reply card (shot 01-after-close): only the reply card closed; the screenshot window stayed open.
   Then "show my pictures" (check 3) listed screenshot-20261015-040037.png in ~/Pictures (shot 03-pictures).
   The `vm 'ls -la ~/Pictures/'` and `~/.Trash` checks were refused by the Mac hook (not run). PASS on screen, file check not done.
2. say "save it as a PDF" (screenshot window open): "Saved ~/Pictures/screenshot-20261015-040037.pdf (1.7 MB) with: made a PDF
   of it; the original is unchanged." (2 s). PASS.
3. say "show my pictures": "8 items in ~/Pictures." Window ~/Pictures: each thumbnail has its own name under it; names
   readable (two long names cut with "..."). Shot 03-pictures. PASS.
4. say "draw me a cat": a cat photo window opened (caption "Felis catus-cat on snow.jpg"). Reply: "I can't draw new pictures
   on this computer, so here is a real photo instead: Felis catus-cat on snow.jpg (Von.grzanka, CC BY-SA 3.0)." (2 s).
   PASS (honest, no "couldn't finish"). Friction: the reply reads oddly and the credit line is long.
5. say "make a packing list with socks, charger and toothbrush": reply "Added to your packing list." Window Packing with exactly
   socks, charger, toothbrush. Shot 05-packing. PASS.
6. say "set a 1 minute timer for the tea" (at 04:01:45): reply "Timer set — Tea (1 minute), it rings in 1 minute (04:02)." PASS.
   Opened "what are my reminders" with the Scheduled window: Tea row shown (shot 06b). At 04:03 the "Time's up: your Tea
   (1 minute) timer is done" window appeared, and the Scheduled list lost the Tea row at once (shot 06d). Clicked OK:
   reply "Closed.", no other panel opened (shot 06e). PASS.
   Note: timer fired about 1 min late (04:02 due, panel at 04:03; the wait was 30 s steps, so the exact delay is not measured).
7. say "set an alarm for 7am": reply "Alarm set for 07:00." (calls it an alarm). say "what are my reminders": "Alarm (Thu 15 Oct
   07:00)". Clicked Cancel on the Alarm row: reply "Cancelled: Alarm." No number or code. PASS.
8. say "what is the capital of France": "Paris is the capital and largest city of France, ... (source: en.wikipedia.org)".
   No [b] or [4] marks. PASS.
9. Window open (Pictures, cat, Packing, Scheduled, While you were away, screenshot). Clicked the mic: "Listening... speak, then
   pause." and the mic button turned red (shot 09a). key esc: mic back to normal, all 6 windows still open (shot 09b). PASS.

## Cleanup
- Removed socks, charger, toothbrush from Packing (list now "(nothing on this list)").
- Tea timer: fired and gone. Alarm: cancelled.
- "take out the bins" (every Mon 09:00) was already there before this test: left it alone.
- Closed all windows. Pictures left as they are, including the new screenshot-20261015-040037.pdf that check 2 made.

## Bugs
- Check 1 (partial): "what's open" put "Open now: ..." in the reply, but no "Open now" window appeared on screen. The
  reply card still showed the earlier screenshot answer. Expected a window with a Close button per row.
- The Mac-side hook (.claude/hooks/stay-in-project.py) refused `vmuser.py vm 'ls -la ~/Pictures/; ls -la ~/.Trash/'`
  because the text contains ~/ paths. These are VM paths, so this is a false positive for this check. Not bypassed.
  Result: could not confirm on disk that the screenshot file is still there or that nothing went to ~/.Trash.
- Timer delay: due 04:02, "Time's up" shown at 04:03 (not measured more closely).

## Friction and Ideas
- Cat reply: "Felis catus-cat on snow.jpg (Von.grzanka, CC BY-SA 3.0)" is long and odd for a window caption.
- The ~/Pictures list says "8 items" but shows folder + 2 PDFs + 5 PNGs: fine, but a person may count differently.
- Escape stops listening and leaves the answer card up: fine.
