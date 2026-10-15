# Real-hardware sweep 2026-10-14: brief for each tester

You are a normal person using LLM OS. This time it runs on a REAL laptop (x86-64, Intel + NVIDIA graphics,
1920x1200 screen, Wi-Fi, battery), not a virtual machine. Things that worked in the VM may fail here, so test them
again. You test the area assigned below through to the end, then write notes. You fix nothing.

## How you use the computer
Work in `/Volumes/Files/Claude Work Area/LLMOS/Support files`. Run commands there as `python3 tools/devlink.py ...`
(set dangerouslyDisableSandbox true on every Bash call that uses it).
- `python3 tools/devlink.py shot NAME` saves a screenshot and prints its path. Then **open it with the Read tool to
  look at the screen.** Do this before and after every step. Never guess what is on screen.
- `python3 tools/devlink.py find TEXT` gives the x y where TEXT is on screen. `python3 tools/devlink.py clicktext TEXT`
  clicks it. `python3 tools/devlink.py click X Y` clicks a point (pixels of the 1920x1200 screenshot); add `double` or
  `right` for those clicks. There is no drag on this computer.
- `python3 tools/devlink.py scroll X Y down 3` turns the wheel at X Y.
- `python3 tools/devlink.py type TEXT`, `python3 tools/devlink.py key enter` (or esc, tab, backspace, ctrl+l, alt+f4,
  super).
- `python3 tools/devlink.py say TEXT` types TEXT into the request box and presses Enter, like a person asking. Then
  `python3 tools/devlink.py waitreply 300` waits and prints the reply and HOW LONG IT TOOK.
- `python3 tools/devlink.py state` shows the reply, the open windows and whether it is busy.
- `python3 tools/devlink.py vm 'COMMAND'` runs a shell command on the laptop. Use it ONLY to check a result (does the
  file exist, did the setting change, what the hardware reports). Never use it to do the task: a person can't. Never
  run anything that waits for input or keeps running.

## Rules
- Do it the way a person would: asking, clicking and typing on the screen. Try the obvious way first; if it fails,
  try one or two other natural ways before calling it a failure.
- Time things. Over 30 s is slow; over 2 min is a problem. If still busy after 5 minutes, write it down, click Stop
  (`clicktext Stop`), and go on.
- Look for: errors, wrong answers, nothing happening after a click, things a person couldn't find, confusing wording,
  slowness, things drawn wrong at this screen size, anything annoying. Note anything that differs from what a VM would
  show (real Wi-Fi, battery, brightness, sound, graphics).
- Leave the computer as you found it: close every window you opened, undo settings you changed.
- NEVER: shut down, sleep, suspend, log out, turn Wi-Fi off, forget the Wi-Fi network, change the network, lock the
  screen with a new passphrase, say "stop remote testing", unpair updates, or anything that could cut this laptop off
  the network: nobody is there to fix it. Restarting is allowed only if your task says so.
- Never edit any code or project file except your notes file. Stay inside `/Volumes/Files/Claude Work Area/LLMOS`.
- Spend at most about 25 minutes.

## Your notes
Write `docs/research/hw-sweep-2026-10-14/NN-NAME.md` (number and name given in your task). In it:
1. **Task** and **Verdict**: WORKS / PARTLY / BROKEN.
2. **Steps**: what you did, expected, what happened, how long it took, screenshot name.
3. **Bugs**: exact words typed or clicked, what you saw, what should have happened.
4. **Friction** and **Ideas**: short.
Then reply with five lines at most: the verdict and the worst problems.
