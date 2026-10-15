# 08 Models, Stop and queue

## Task
Tester 08, area "models, Stop and queue" (brief: BRIEF.md in this folder). Steps: find Huihui Ornith 1.5 9B in the models window and check its button; use it and time readiness and two answers; switch back to Ministral 3 3B; Stop a long story and check the kept text and stopped line; queue a second request during a long story and check the waiting-requests display and what Stop says about waiting ones; close everything and leave Ministral 3 3B in use.

## Verdict
BLOCKED (not tested). Only step 1 was partly done, and the laptop then stopped answering, so steps 2 to 5 did not run.

## Steps
1. Clicked the model chip "Ministral 3 3B" in the top bar (1366,19). The Models window opened. Shot: `dev-t08-models.png`.
   - Expected: Huihui Ornith 1.5 9B (uncensored) listed as ready to use.
   - Seen in the window's text (via `devlink state`, not the screen): the row reads "Huihui Ornith 1.5 9B (uncensored) (installed)", "huihui-ai ... MIT · 5.6 GB · 8 GB RAM · slow". So it is installed and is not offering a download. Its button label could not be read: it sits below the visible part of the list.
   - Ministral 3 3B shows "IN USE". Its row shows no button.
   - Scrolling the list did not move it. Tried wheel scroll at (1400,600), (1500,800) and on the scrollbar (1880,600), then PageDown, Down keys, and a click plus Space. The screenshot stayed identical each time (`dev-t08-scroll.png` to `dev-t08-scroll5.png`). Esc did not close the window either (`dev-t08-afteresc.png`).
2. Clicked the Models window's red close dot at (946,90) to get it out of the way. The next command returned "refused: the signature does not match the paired key", and from then on every `devlink` call (state and shot) returned "no answer in 40 s". Retried over roughly 15 minutes, including two waits in the background. The laptop never answered again.
3. Steps 2 to 5 (use Ornith, time the answers, switch back, Stop test, queue test) were not run.
4. Cleanup not done: the Models window is probably still open, and Ministral 3 3B is still the model in use (top bar and the "IN USE" label showed it before the failure). Nothing else was changed.

## Bugs
- The Models list does not scroll with the mouse wheel, PageDown or arrow keys on this laptop. The button for the installed Huihui Ornith row can't be reached on a 1920x1200 screen, so a person would not find it either, unless they can scroll. Expected: the list scrolls, and each row shows its button.
- Esc does not close the Models window.
- After I clicked the Models window's close dot, the laptop stopped answering `devlink` (the earlier reply was "refused: the signature does not match the paired key"). I could not tell whether my click caused this or whether it was a separate link problem. Nobody can see the laptop from here, so it needs a look: is remote testing still on, and is the pairing still valid?
- The screenshot after the close click was never captured, so I do not know whether the window closed.

## Friction
- Whole test is blocked by the laptop not answering; no way to recover from this side.
- The brief's "wait up to 5 minutes" rule does not cover a laptop that stops answering entirely.
- I briefly wrote a temp file to /tmp (a `state` output), then deleted it.

## Ideas
- Put the installed-model button in view on open, or make the models list sort installed models first.
- Let Esc close the Models window.
- Show the Ornith button in the state output (it currently lists "(installed)" with no action).
