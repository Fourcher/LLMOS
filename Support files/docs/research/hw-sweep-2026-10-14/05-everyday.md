# 05 Everyday requests and speed (tester 05)

## Task
Everyday requests on the real laptop (i7-1260P, Ministral 3 3B on CPU, 1920x1200): quick answers, thinking answers, a saved note and its delete, shopping list and reminders, a long story with a second question and Stop, a web search, and CPU/stutter while a long answer writes.

## Verdict
PARTLY. Quick answers, reasoning answers, the saved note, the shopping list and the reminders all work and are fast (1-3 s for lists and reminders). Three things are broken on this hardware: (1) the whole app is drawn in a 250x250 px block at the top-left of the 1920x1200 screen, so most text and buttons are clipped or off-screen; (2) I could not find or reach any Stop control, so the Stop test was NOT done; (3) "next friday" gives a Monday, and "show me the trash" / "open my trash" answer with shell advice instead of opening the Trash.

## Steps
Times are measured from the request to the reply (a polling loop, not devlink waitreply, unless noted). Screenshots are in run/sweep/shots/ with the dev-t05-* prefix.

0. Start: the screen had a "While you were away" panel (Updated). Closed it with its red button. The app occupies only the top-left 250x250 px of the screen (t05-start, t05-after-close). Expected: the app fills the 1920x1200 screen.
1. "what time is it": 2 s. "It's 10:00 PM on Wednesday, October 14, 2026." Laptop clock: 05:00 UTC, which is 22:00 Pacific. Correct.
   "what's 15% of 80": 2 s. "15% of 80 is 12." Correct.
   "what's the weather like": the first try gave back the previous answer (waitreply printed "15% of 80 is 12." and only later the state changed). On the second try, 2-10 s: "Today in Phoenix, Arizona: clear, high 77°F, low 56°F, 0% chance of rain. Now 66°F. (Source: Open-Meteo forecast, open-meteo.com.)" It picked Phoenix without asking where I am. (t05-weather)
   "what's the date next friday": 12 s, "Friday is October 19, 2026." Wrong: October 19, 2026 is a Monday (today is Wednesday October 14, so Friday is October 16 or 23). Second try, 10 s: "Next Friday is **October 26, 2026**." Also wrong: October 26 is a Monday. The model gave two different wrong dates. The "**" bold marks are in the reply text.
   "flip a coin": 16 s, "Heads or tails." (text only, not a real flip; fine for a person).
2. "explain how a rainbow forms in two sentences": 24 s. Two sentences, sun, raindrops, refraction and dispersion, colours listed. Good.
   "give me three dinner ideas with chicken": 48 s. Three recipes with steps. Good, a bit long.
   "what's the capital of Australia and why isn't it Sydney": 28 s. Canberra, chosen in 1908 to settle the NSW and Victoria rivalry. Correct. The answer cites "ovolohotels.com" (a hotel marketing blog) as its source, and a Sources panel opened. A government or encyclopedia source would be better. (t05-capital panel "Sources")
3. "write a short thank-you note to my neighbour and save it as hwnote.txt": 18 s. Good note, signed "Jordan", reply "Saved as ~/Documents/hwnote.txt." VM: /root/Documents/hwnote.txt exists, content matches (324 bytes).
   "delete hwnote.txt": 1 s, "Moved hwnote.txt from ~/Documents to the trash." VM: Documents is empty. Good.
4. "add milk and eggs to my shopping list": 2 s, "Added to your shopping list." "show my shopping list": 1 s, "Shopping: milk, eggs." (A Shopping panel opens.)
   "remind me to stretch in 20 minutes": 2 s, "Reminder set for 22:24: stretch." Correct (it was 22:04). "what are my reminders": 1 s, "Scheduled: stretch (Wed 14 Oct 22:24)." (Scheduled panel opens.)
   "cancel the stretch reminder": 1 s, "Cancelled: stretch." "what are my reminders": "Nothing is scheduled."
   "clear my shopping list": 1 s, "Removed." Unclear what was removed. "show my shopping list": "Nothing on it yet." VM: tasks.json and notes.json are [] again.
5. Queue and Stop: "tell me a long story about a lighthouse" was asked at about 22:05. Its prompt prefill was long: llama log shows 2048 tokens at 39 s, 6144 at 152 s, 8192 at 223 s (about 37 tokens/s), then decoding at about 4.2-4.3 tokens/s. The answer started about 4 min after I asked and finished on its own after 468 s total (10,292 tokens, not truncated). Note: the reply bubble on screen only shows the last reply; the story text itself is only visible in the chat log, not in the 250 px window.
   While it was still prefilling, "what time is it" was asked: answered in about 2 s, "It's 10:05 PM on Wednesday, October 14, 2026." So a short question does not wait for the story.
   STOP NOT TESTED. I could not find a Stop control: `devlink find Stop` and `clicktext Stop` say NOT FOUND. The request bar's right button is clipped off the 250 px area. I tried, in order: a click on the clipped edge of the send button (243,132); a click on the blue orb (66,132); the Esc key; Tab, Tab, Enter; and typing "stop" + Enter. None stopped the story. Typing "stop" was queued (queued 1) and was answered "Done." after the story had finished. The story therefore was not stopped, and I could not check whether it keeps its text and says it was stopped. About 8 minutes of busy time passed before it finished on its own, well past the 5-minute limit in the brief.
6. Web: "search the web for the population of Japan": 10 s. "Japan's population is approximately **124.6 million** as of the most recent estimates (2024), according to the United Nations Department of Economic and Social Affairs." It gives a source (UN DESA) and the year. Good. The "**" marks are in the reply text.
7. CPU and stutter during the long answer (sampled during the prefill, about 10 s in): top shows 92% user CPU, 7% idle, load average 6.9 (18 during the later prefill). llama-server at 89% of one core with -t 16 threads, RSS about 7.9 GB VSZ. Memory: 13.8 GB used of 15.7 GB, 2.2 GB free, 9 GB cache. During the story I could still close panels (Shopping, Scheduled, Sources) with the mouse and the time question was answered in 2 s, so the UI kept responding. I cannot judge mouse feel from screenshots; no visible freeze was seen.
8. Trash questions: "show me the trash": 5 s, "The systemd trash directory is `/run/user/$(id -u)/trash-1`. Files in it are temporary ... Check `/var/lib/trash/` instead." "open my trash": 9 s, "The persistent trash directory for Jordan's user is `/home/jordan/.local/share/Trash`. Open it with `trash-cli`..." Neither opened a Trash view. The laptop runs as root, not /home/jordan. Tester 04 got a Trash window earlier, so this is intermittent or wording-dependent.
9. Files chip (Files window, t05-files): "7 items in ~." The window is 250 px wide; the sidebar with Trash is not visible, so I could not open the trash to delete hwnote.txt for good.

## Bugs
1. Screen: the app is drawn in a 250x250 px block at the top-left of the 1920x1200 screen (every screenshot from t05-start on). Windows and bubbles overlap and clip each other, and the request bar's right button is off-screen. Expected: the app fills the screen.
2. No Stop control on screen at this size. Esc, a click on the clipped send button, the orb, and Tab+Enter do not stop a reply. Typing "stop" queues it instead.
3. "what's the date next friday": "Friday is October 19, 2026" (a Monday), then "Next Friday is October 26, 2026" (a Monday). Expected: Friday October 16 or 23.
4. "show me the trash" and "open my trash": answered with shell paths (/run/user/..., /home/jordan/.local/share/Trash) instead of showing the Trash. Expected: the Trash view.
5. "what's the weather like": picked Phoenix, Arizona without asking where the user is.
6. waitreply/state: the weather answer was not returned on the first try (the old reply was shown). A person would see a stale answer.
7. "clear my shopping list" replies "Removed." with no detail.
8. The capital answer uses a hotel blog (ovolohotels.com) as its source.
9. Memory: the assistant saved "Today is Wednesday, 2026-10-14, 11:05 MST" as a memory fact (VM memory.json). The time is 22:05 Pacific. A stale "today" fact stored in memory can be wrong later.

## Friction and ideas
- Lists and reminders are fast and clear; "Removed." could say "Cleared the shopping list."
- Long answers (story, dinner ideas) take minutes because the prompt is about 8,000 tokens and prefill runs at about 37 tokens/s on this CPU. The short questions after the story were fast, but I did not measure whether the prompt cache helps a second long request. Idea: keep the chat history short for quick answers, or show "Thinking... about 3 min" with a Stop button that is always visible.
- Long answers show as a small clipped bubble; reading the story needs the chat log. A full-width reply view would help.
- Replies show raw "**" bold marks (weather, date, Japan).
- The weather should ask for the city once, or use the location the owner set.
- Stop: a visible Stop button while busy is the fix; "stop" typed should stop, not queue.
- Date answers should be computed from the real calendar, not from the model.

## Cleanup
- Reminder "stretch" cancelled; shopping list cleared (tasks.json and notes.json are []).
- All windows closed (Shopping, Scheduled, Sources, Files, the "While you were away" panel).
- hwnote.txt is still in the app trash (trash-origins.json maps it back to /root/Documents/hwnote.txt). I could not reach the Trash view at this window size, so I did NOT empty it. "HW Test" from tester 04 is also still in the trash; I left it alone.
- The chat log /root/.llmos/chats/main.jsonl and the memory entries were written by these tests; left in place.
- Screenshots: run/sweep/shots/dev-t05-*.png (kept, named above).
