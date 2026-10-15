# 22 VM: windows and everyday requests (1.8.9.36, virtual machine)

## Task
Everyday window handling, memory, models/voices and a 2-minute reminder, tested on the VM with `tools/vmuser.py`
(version confirmed 1.8.9.36 before starting).

## Verdict
PARTLY. Windows, live folder updates, minimize, Lock entry, models, voices and memory all work. The reminder
"in 2 minutes" is stored for Fri 16 Oct 00:02 instead of 2 minutes from now, and the reply still says
"2 minutes from now". That is a real bug.

## Steps
1. **"show my pictures" / "show my documents" / "what's open"** (first run, Pictures and Documents sent in parallel
   by mistake, so the Pictures window was replaced). Re-run in order: "show my pictures" (about 2 s, 8 items),
   then "show my documents" (about 2 s, Pictures window closed and Documents opened), then "what's open" (about 2 s).
   Result: "Open now" window appears on top, fully visible, listing "While you were away" and "~/Documents".
   Screenshots: s1a_pictures, s1b_documents, s1c_whats_open, s2_pictures_open, s3a_documents_open.
2. **Live folder update.** With the Pictures window open, `cp chime.wav /root/Pictures/test22.wav` made
   `test22.wav` (23.7 KB) appear in the window within 10 s. Removing it made it disappear within 10 s.
   Screenshots: s2b_file_added, s2c_file_removed.
3. **Minimize.** Documents window minimized with its minimize control (the VM uses a "-" button top right, not a
   yellow button). It went to a chip "~/Documents" bottom left. After 30 s it was still minimized.
   Screenshots: s3b_after_minimize_click, s3c_minimized_30s.
4. **Lock.** Power symbol top right opens a "Power" window with Lock, Sleep, Restart, Shut down. Lock exists.
   Nothing pressed; window closed with its X. Screenshot: s4_power_menu.
5. **Reminder + story.** "set a reminder in 2 minutes to stretch" answered in 25 s (wait time included the
   reply): "Reminder set for **2 minutes from now** to stretch." Set at about 04:43:22 by the stored timestamp.
   Then "write a 150 word story about a robot" answered fully (about 25 s). Story is fine.
   - Stored in `/root/.llmos/tasks.json`: `"when": "now+00:02:00"`, `"next": 1792134120`, `"desc": "Fri 16 Oct 00:02"`.
     Converted: 1792134120 = Fri Oct 16 00:02:00. It should have been about 04:45:22 on 15 Oct.
   - No "Time's up / Reminder: stretch" appeared by 04:46:40 (about 80 s after it should have rung). It was
     never going to ring at the right time.
   - Cancelled with "cancel the stretch reminder": "Cancelled: stretch." The existing "take out the bins"
     reminder is untouched.
   Screenshots: s5a_reminder_set, s5b_story_done, s5c_reminder_check, s5d_reminder_recheck.
6. **Models / voices.** "what models can I use?" answered in 3 s: lists "Ministral 3 3B (in use)", Hermes 3 3B
   (download 2.0 GB), and others, about this computer. "which voices can you speak with?" answered in 2 s:
   one eSpeak voice, English, plus Whisper Base for listening. Screenshots: s6a_models, s6b_voices.
7. **Memory.** "remember that my favourite colour is green": "Got it, I'll remember that." `store.facts()`
   shows `User's favourite colour is green` (added 2026-10-15). "forget my favourite colour": "Forgot your
   favourite colour." `store.facts()` no longer has it. Screenshot: s7_forget.

Cleanup: Models and Power windows closed, Open now and ~/Documents windows closed. Left as found: the
"While you were away" panel (it was open at the start). Reminder "stretch" cancelled. "take out the bins"
reminder unchanged. Lock/Sleep/Restart/Shut down not pressed.

## Bugs
- **Reminder time wrong (main bug).** Said: "set a reminder in 2 minutes to stretch". Reply: "Reminder set for
  2 minutes from now to stretch." Stored: due Fri 16 Oct 00:02 (about 19 h later, not 2 minutes). Should be
  due at about 04:45 on 15 Oct and ring then. The reply claimed the wrong time.
- **Setup slip on my side (not a bug in LLM OS):** I sent the first Pictures and Documents requests in parallel,
  so the sequence was not as the brief describes. Re-ran them in order; the final results above are from the
  ordered run.

## Friction and Ideas
- Minimize control is a "-" button, not a yellow dot; fine, but the brief's wording may not match the VM look.
- The "Time's up: your Eggs (1 minute) timer is done" alert from an earlier run stays in "While you were away"
  and was there at the start. It is not cleared by checking the desk; it is harmless but cluttered.
- The reminder reply should read back the real due time (e.g. "due 04:45") so a wrong time is visible.
