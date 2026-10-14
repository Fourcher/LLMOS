# 10 reminders-queue

## Task
Time-based things (reminders, timers, listing and cancelling them) and doing several things at once (a slow
request with two more queued behind it, the ✕ on a waiting request, and Stop).

## Verdict
PARTLY. Reminders and timers are set, listed, cancelled and go off on screen. The queue shows waiting requests and
the ✕ removes one, but quick answers never appear on screen while the slow one runs, and Stop silently throws away
everything still waiting.

## Steps
Times are from the wall clock (`date`) and the screenshots. Screenshots are in `run/sweep/shots/`.

1. Start state (11:59:27): desk, nothing busy. Window "While you were away" already open (LLM OS 1.8.5 installed).
   Kept as found. Shot `t10-start.png`.
2. "remind me to stretch in 2 minutes" (said 11:59:30). Reply in 2 s: "Reminder set for 12:01: stretch." Shot `t10-remind-set.png`.
   Expected: a reminder about 2 minutes away. Result: correct time, 12:01.
3. "set a timer for 1 minute" (said 11:59:38). Reply in 2 s: "Timer set — 1 minutes, it rings at 12:00." Shot `t10-timer-set.png`.
4. "what are my reminders?" (said 11:59:44). Reply in 14 s: "12:00: Stretch" and "12:01: Reminder to stretch".
   The Scheduled window (opened by itself) showed "stretch, Wed 14 Oct 12:01" and "1 minutes, Wed 14 Oct 12:00".
   Shot `t10-list.png`. The names do not match between the answer and the window (see Bugs).
5. Waited for 12:00. At 12:00:07 and 12:00:30 nothing on screen had gone off (`t10-at-1200.png`, `t10-1200-plus20.png`).
   At 12:01:48 the timer and the reminder had both gone off: the "While you were away" window had gained
   "Time's up: your 1 minutes timer is done." and "Reminder: stretch", and a small toast "Reminder: stretch" showed at top
   centre. The reply bar also showed the list. Shot `t10-1202.png`. I did not screenshot the moment the timer
   itself fired, so I cannot say exactly when it rang or whether it made a sound (the VM has no audio check).
6. "what are my reminders?" again at 12:01:56 (reply in 8 s): "No reminders are currently scheduled." At that moment the
   Scheduled window still listed both fired items. By 12:02:04 it read "Nothing scheduled." Shot `t10-list2.png`.
7. "remind me to drink water in 5 minutes" (12:02:11): "Reminder set for 12:07: drink water." Then "what are my
   reminders?" listed "Drink water (scheduled for 12:07 today)". Shot `t10-list3.png`.
8. Removed it: clicked the Cancel button beside "drink water" in the Scheduled window at (1208,151). Asked again:
   "No reminders scheduled." Shot `t10-after-cancel.png`.
9. Queue test. "write a 300-word story about a dragon" at 12:02:50. Three seconds later "what time is it":
   reply "It's 12:02 PM on Wednesday, October 14, 2026." in under 5 s, while the story was still running.
   Then "write a haiku about rain" at 12:02:58: the toast "Added to the queue: I'll start it when the current request
   is done." and a Waiting list with "1. write a haiku about rain" and a ✕. Shot `t10-queue-busy.png`.
10. Clicked the ✕ on the haiku at (969,637) at about 12:03. The Waiting list went away on screen at once (`t10-after-x.png`).
    The state field still said queued: 1 for about 5 s and then showed 0 once the story finished. The story finished
    about 30 s after it started (12:03:17 wait returned). Shot `t10-dragon-done.png`. The haiku never ran.
11. Stop test. "write a 300-word story about a dragon" (about 12:03:50). "write a haiku about rain" queued. Then "tell me a joke",
    which was answered at once: "Why did the bread stay home? It was feeling a little crumby." Waiting showed only the
    haiku, with a ✕ and a Stop button. Shot `t10-stop-setup.png`.
12. Clicked Stop at 12:04:12, about 20 s into the story. The story stopped mid-sentence ("...its entrance guarded by a
    stone lion carved") with no note that it was stopped. The haiku was dropped: the queue went to 0, nothing ran, and
    no message said so. Shots `t10-after-stop.png`, `t10-after-stop2.png`.
13. Opened History (Conversations window). The topic "tell me a joke" (2x) had the joke and the dragon story under it.
    "what time is it" (12:02) was its own topic. "write a 300-word story about a dragon" (12:03) was listed with Continue.
    No haiku entry. Shot `t10-history.png`.
14. Closed the Conversations window and the Scheduled window. Only "While you were away" is left, as it was at the
    start. Shot `t10-close1.png`. Left the test conversations in History (they are the test's own records; not forgotten).

## Bugs
1. **Quick answers vanish from the screen while a slow request runs.** Typed "what time is it" (12:02:55) at once while
   the dragon story was running. The state reply showed "It's 12:02 PM on Wednesday, October 14, 2026." but the panel
   showed only the streaming story and the answer never appeared on screen. The same happened with "tell me a joke"
   at 12:04. Expected: the time shows at once, next to or above the story, and stays visible.
2. **Stop drops the waiting requests silently.** Clicked Stop while the dragon was running with "write a haiku about
   rain" waiting. The story stopped, the haiku was discarded with no message and is not in History. Expected: either
   run the waiting request next, or say "Stopped. 1 waiting request was cancelled."
3. **Stop leaves no trace on the story.** The story just ends mid-sentence with no "Stopped" note. Expected: a clear
   stopped marker.
4. **Timer and reminder names do not match.** "remind me to stretch in 2 minutes" was saved as "stretch"
   (Scheduled window) / "Reminder to stretch" (list answer). The 1-minute timer is named "1 minutes" in Scheduled and
   shown as "Stretch" in the list answer at 12:00. A person would read "12:00: Stretch" as the stretch reminder.
   Expected: each item has one name; a timer says "1 minute" and is listed as a timer.
5. **Scheduled window lags the answers.** After the 12:00 timer and the 12:01 reminder had fired, the reply said "No reminders
   are currently scheduled" (12:01:56) while the window still listed both for about 10 s. A fired timer also stayed in the
   list until about 12:02:04.
6. **History merges unrelated requests.** The joke and the dragon story sit under one topic named "tell me a joke (2x)".
   The topic name follows the first request, not the one that was answered.
7. **Timer alert is easy to miss.** When the timer and reminder went off (about 12:01), the only on-screen sign I saw was the
   small top-centre toast "Reminder: stretch". The timer's "Time's up" line only appeared inside the "While you were away"
   window, which was already on screen and not raised. I did not capture the moment the timer rang, so I cannot
   confirm whether a timer makes a sound or shows a bigger alert.

## Friction
- The timer rang about 30 to 90 s later than its time (it had not rung at 12:00:30; it had at 12:01:48). I did not catch
  the exact moment, so treat this as a suspicion.
- The "what are my reminders?" answer takes 8 to 14 s, slower than setting a reminder (2 s).
- The ✕ in the queue is small and sits at the right edge of the Waiting row; it was easy to find, once seen.
- Stop was easy to find (it is next to History and Close).
- The "While you were away" window stays on top of the desk after every reminder fires, so the alerts pile up in it.

## Ideas
- Say the time of a quick answer on screen (or keep it in the panel) even while a slow request runs.
- When Stop is pressed, keep the waiting requests and run them next, or tell the user what was dropped.
- Put the timer and reminder names through one format ("Timer: 1 minute", "Reminder: stretch") in every list.
- Raise a bigger alert on screen (a card, not only a toast) when a timer rings, and sound one if the machine has sound on.
- Show a waiting count next to Stop ("2 waiting") so the queue is visible without opening the panel.
