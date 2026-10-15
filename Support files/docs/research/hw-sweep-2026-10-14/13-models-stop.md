# 13. Models, Stop and queue (real laptop)

## Task
Models window: switch to Huihui Ornith 1.5 9B (uncensored) (already downloaded), ask a question, switch back to Ministral 3 3B, test Stop on a long story, test queueing while busy.

## Verdict
PARTLY. Model switching works, Stop keeps the partial text and says "Stopped.", and quick questions are answered while a long answer runs. But the top bar did not update after the button click, Huihui is very slow on this laptop (a two-sentence answer took about 4 min 40 s), and the card keeps saying "Working" after the answer text is already complete.

## Steps

1. **Find the model.** Clicked the "Ministral 3 3B" chip. The Models window opened. Scrolled the list (clicked inside first, then scroll down 5 per step; about 5 passes). Huihui Ornith 1.5 9B (uncensored) shows INSTALLED with two buttons: "Use" (blue) and "Remove" (red). Expected: a ready-to-use model. Result: as expected. Screenshot `dev-13-models-scroll2`.

2. **Use it by button.** Clicked "Use". A toast said "Switching to huihui-ornith-1.5-9b...". The top bar still said "Ministral 3 3B" for at least 2 min 10 s, even after closing the Models window. The Models window now said "IN USE" for Huihui. The laptop confirmed llama-server was running Huihui (`models/Huihui-Ornith-1.5-9B-abliterated.Q4_K_M.gguf`). Screenshots `dev-13-after-use`, `dev-13-now`, `dev-13-models-closed`, `dev-13-topbar-check`.

3. **Use it by voice.** Said "use the model Huihui Ornith". Reply "Now using Huihui Ornith 1.5 9B (uncensored)." The top bar updated. Time: 16 s. Screenshot `dev-13-say-use`.

4. **Ask the rainbow question.** Said "explain how a rainbow forms in two sentences". Timeline:
   - 0 to 2 min: "Reading your request" (prompt processing) at 42%, then 63%. Model log: about 9,700-token prompt at about 47 tokens/s.
   - About 4 min 41 s: the answer text was on screen (three sentences, not two), and the card was still "Working... · this is taking long; Stop ends it". A Wikiquote window also opened by itself ("About to: real quote ... real quote: rainbow"). Screenshot `dev-13-rainbow-5min`.
   - Stop was clicked at 4 min 51 s (first click hit the status text, not the button; second click on the Stop button worked). Screenshot `dev-13-rainbow-stop2`.
   - Total time to a finished answer: over 4.5 min. Far over the 2 min problem line.
   - Memory during the run (`free -m`, mid-run): 1414 MB used, 6208 MB free, 13115 MB available. Not under 1000 MB. Note: the laptop has 15.7 GB total, so the memory limit in the brief was not a concern here.

5. **Switch back.** Said "use the model Ministral 3 3B". Reply "Now using Ministral 3 3B." Top bar showed Ministral again. Time: 7 s. Screenshot `dev-13-back-ministral`.

6. **Stop on the lighthouse story.** Said "tell me a long story about a lighthouse".
   - Still "thinking" at 6 s, 37 s, 1 min 42 s, 2 min 33 s, 3 min 38 s (no text). Model log: about 9,300-token prompt, prompt processing at about 60 to 74% at 2 min.
   - Text began at about 5 min after asking (02:22 on the clock). Clicked Stop on the button once text was streaming.
   - Result: the card kept the partial text, ended with "— Stopped." Screenshots `dev-13-lighthouse-h`, `dev-13-lighthouse-stopped`.

7. **Queue test.** Said "tell me a long story about a dragon". 5 s later said "what time is it", 3 s later "what's 2 plus 2". Both answered within seconds as small side notes ("what time is it: It's 2:22 AM on Thursday, October 15, 2026." and "what's 2 plus 2: 4"), while the dragon story kept streaming. The time answer was one minute behind the 2:23 clock. The state line showed "queued: 0". Nothing on screen mentioned waiting requests. Clicked Stop on the dragon story; it kept the partial text (ending "...the wisdom of scholars, and") and ended with "— Stopped." No message about waiting requests appeared, because there were none shown. Screenshots `dev-13-queue-a`, `dev-13-queue-stopped`.

Cleanup: closed the dragon and rainbow cards, and closed the Wikiquote window the model opened. The "While you were away" window was there before I started and was left alone. Top bar confirms Ministral 3 3B is the model in use, and the laptop's llama-server runs Ministral 3 3B.

## Bugs
- **Top bar did not update after "Use" in the Models window.** Clicked "Use" on Huihui; the toast said switching, the window said IN USE, but the top bar said Ministral for over 2 min (llama-server was already running Huihui). Voice "use the model Huihui Ornith" updated the bar within 16 s. Expected: the top bar switches when the model is used.
- **Card stays "Working" after the answer is complete.** Rainbow answer text was fully on screen at about 4 min 41 s, with "Reading your request 95%" and "Working... this is taking long; Stop ends it" still showing. Expected: the card should show Done once the text is complete.
- **After Stop, the rainbow card repeats part of the answer.** Before Stop, the answer read as a three-sentence paragraph. After Stop, the card shows the full paragraph followed by a second short line "A rainbow forms when sunlight" and then "— Stopped." Looks like the streamed text is duplicated when Stop is pressed.
- **The model opened a Wikiquote window on its own** for the rainbow question ("About to: real quote ..."). The user did not ask for it, and it stayed open.
- **Huihui is very slow on this laptop** for a short question: about 4.5 min total. Its prompt is about 9,700 tokens, so prompt processing dominates (about 47 tokens/s). Ministral also took about 4 min before text began on the lighthouse story (about 9,300-token prompt, about 60 to 74 tokens/s). Expected: a short question answered in well under 2 min.
- **Stop button hit-test:** `clicktext Stop` clicked the "this is taking long; Stop ends it" status text instead of the Stop button (the word "Stop" appears in the status line too). Clicking the button coordinates worked.
- **Time in a quick answer is one minute behind the clock.** "what time is it" said 2:22 AM at 2:23 on the clock. Minor.

## Friction and Ideas
- Huge prompts (about 9,000 to 10,000 tokens) make every answer wait several minutes on this laptop before any text shows. A progress line that shows the prompt processing ETA would help, but the real fix is a smaller prompt.
- No visible queue. Two quick requests were answered at once, and the screen never showed waiting requests, so "what it says about waiting ones" had nothing to say.
- The rainbow card shows the answer but still says "Working" until Stop. A person would think it is stuck and press Stop, as I did.
- The Models list needed five scroll steps to reach Huihui. A search box or "Installed" filter would help.
