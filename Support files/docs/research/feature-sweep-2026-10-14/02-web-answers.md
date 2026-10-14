# 02 web-answers

## Task and verdict

Ask the computer to look things up online, the way a person would, and judge the answers.

**Verdict: PARTLY.** Answers come back fast and the French president answer is right and sourced. But the weather answer is off by several degrees with no source shown, the Tokyo request never gives a number (it only opens a search page), and the Ask-mode answer is a clipped Wikipedia snippet.

## Steps

Screenshots are in `run/sweep/shots/`.

1. **Start state.** Desk with a "While you were away" window (LLM OS 1.8.5 installed) and the request box set to "Do". Left as found. Screenshot `02-start.png`.

2. **"what's the weather in Phoenix today"** (Do mode).
   - Expected: today's forecast, with a source.
   - Got: "Today in Phoenix, Arizona: clear, high 80°F, low 56°F, 0% chance of rain. Now 72°F." Shown as a card with History and Close. No source, no link.
   - Time: **2 s** to answer.
   - Check: National Weather Service forecast for Phoenix on Oct 14 2026 shows high about 78°F, low about 59°F, and a reading of 63°F at 8:51 AM. wttr.in at 11:19 MST showed 67°F now, high 78, low 65. So the answer's high (80), low (56) and current temp (72) are each off by a few degrees. The conditions (clear, no rain) match. Screenshot `02-weather.png`.

3. **"search the web for the population of Tokyo"** (Do mode).
   - Expected: a population figure in the reply, with a source.
   - Got: reply text "Opened Firefox searching for 'the population of Tokyo'." Firefox opened full screen on DuckDuckGo. The DuckDuckGo "Search Assist" box says Tokyo city proper was over 14 million in 2023 and the Greater Tokyo Area had 33 million in 2025, with Wikipedia and World Population Review as sources. The reply never gave the number, and the state reply stayed the same for over 30 s.
   - Time: reply **3 s** (but it is only "opened a page"). No figure in the reply.
   - I closed Firefox with its X button (1257, 22). Screenshots `02-tokyo.png`, `02-tokyo-20s.png`, `02-tokyo-after.png`, `02-after-close-firefox.png`.

4. **"who is the current president of France"** (Do mode).
   - Got: "Emmanuel Macron is the current president of France." It appeared as a bar above the request box. A separate "Sources" window opened listing "President of France - Wikipedia" as a link. The "Sources" window sat on top of the "While you were away" window.
   - Time: **62 s** to answer. This is the slowest of the four and is past the 30 s mark, though well under 2 min.
   - Correct. Sourced with a visible link. Closed the Sources window with its X. Screenshots `02-france.png`, `02-france-15s.png`.

5. **Ask mode.** Clicked the "Do" switch at (404, 743). It changed to "Ask" and the tooltip read "Do: it acts on what you say (click for Ask: answers only, no actions, faster)." Asked "what is the capital of Australia".
   - Got: "As Australia's capital , Canberra is the most important centre for much of Australia's political reportage and thus all the major media ... (source: en.wikipedia.org)". The answer is Canberra, which is right, but the sentence is a clipped Wikipedia snippet (it begins mid-thought and has a stray space before the comma) and does not state the capital plainly. The source is a bare domain, not a link.
   - Time: **2 s**.
   - Closed the card with Close, then clicked "Ask" to switch back. The switch shows "Do" again. Screenshots `02-mode-toggle.png`, `02-ask-capital.png`, `02-back-to-do.png`.

## Bugs

1. **Weather figures wrong, no source shown.** Typed: "what's the weather in Phoenix today". Saw: high 80°F, low 56°F, now 72°F, no source. Should be: close to the NWS forecast (about 78 high, 59 low, low 60s now), with a named source the person can open.
2. **Tokyo population never answered.** Typed: "search the web for the population of Tokyo". Saw: "Opened Firefox searching for 'the population of Tokyo'." and a full-screen browser. Should be: the population figure in the reply, with a source, or at least the figure quoted from the results page. The person has to read the search page themselves.
3. **Ask-mode answer reads as a fragment.** Typed (Ask mode): "what is the capital of Australia". Saw: "As Australia's capital , Canberra is ..." with a bare "(source: en.wikipedia.org)". Should be: "Canberra." with a clickable source.
4. **Sources not clickable in the answer card.** The weather and Ask answers show a domain in text (or nothing), while the France answer opened a separate Sources window. Inconsistent.

## Friction

- Firefox opened full screen for the Tokyo search and hid the LLM OS desk and request box. A person would not know how to get back except by closing the browser window.
- The Sources window opened on top of "While you were away" and covered its text. It has no obvious connection to the answer until you look at it.
- France took 62 s. The person is left waiting without any progress line in the answer area (only the busy state).
- The Do/Ask switch's tooltip is clear and useful. Clicking it switches between the two; there is no visible "Ask" label until you click.
- The "While you were away" window was already on screen at the start and stays open. Left it as found.

## Ideas

- For a factual question, put the answer in the reply itself (for the Tokyo case, "about 14 million in the city proper, 33 million in Greater Tokyo, per Wikipedia") and link the source in the card.
- Show a source link on every web answer, the same way the France answer does, so a person can check it without a second window.
- Show a short progress line while a lookup runs (for example "Searching...") in the answer area, so 60 s does not feel dead.
- Open search results in a normal window, not full screen, so the request box stays visible.
- Ask-mode answers should be written as full sentences: "The capital of Australia is Canberra."
