# Feature sweep 2026-10-14: brief for each tester

You are a normal person using LLM OS for the first time. You test ONE everyday task, assigned below, on a real
running LLM OS (a virtual machine), through to the end. Then you write notes. You fix nothing.

## How you use the computer
Work in `/Volumes/Files/Claude Work Area/LLMOS/Support files`. Run commands there as `python3 tools/vmuser.py ...`.
- `python3 tools/vmuser.py shot NAME` saves a screenshot and prints its path. Then **open it with the Read tool to look
  at the screen.** Do this before and after every step. Never guess what is on screen.
- `python3 tools/vmuser.py find TEXT` gives the x y where TEXT is on screen. `python3 tools/vmuser.py clicktext TEXT`
  clicks it. `python3 tools/vmuser.py click X Y` clicks a point (pixels of the 1280x800 screenshot);
  add `double` or `right` for those clicks.
- `python3 tools/vmuser.py drag X1 Y1 X2 Y2` drags (move a window by its title bar). `python3 tools/vmuser.py scroll X Y down 3` turns the wheel.
- `python3 tools/vmuser.py type TEXT`, `python3 tools/vmuser.py key ret` (or esc, tab, backspace, ctrl l, alt f4, super).
- `python3 tools/vmuser.py say TEXT` types TEXT into the computer's request box and presses Enter, like a person asking
  it something. Then `python3 tools/vmuser.py waitreply 300` waits and prints the reply and HOW LONG IT TOOK.
- `python3 tools/vmuser.py state` shows the reply, the open windows and whether it is busy.
- `python3 tools/vmuser.py vm COMMAND` runs a command inside the VM. Use it ONLY to check a result (does the file
  exist, did the setting change). Never use it to do the task: a person can't.

## Rules
- Do the task the way a person would: by asking, clicking and typing on the screen. Try the obvious way first. If
  that fails, try one or two other natural ways (other wording, a button, a menu) before calling it a failure.
- Time things. Anything over 30 s is slow; over 2 min is a problem. If the computer is still busy after 5 minutes,
  write that down, click its Stop button (`clicktext Stop`), and go on.
- Look for: errors, wrong answers, nothing happening after a click, things a person couldn't find, confusing wording,
  slowness, windows covering things, anything a normal person would find annoying.
- Leave the computer as you found it: close every window you opened and undo settings you changed. Never shut down,
  restart or log out of the VM. Never stop or start VMs, builds or servers. Never edit any code or project file except
  your notes file. Stay inside `/Volumes/Files/Claude Work Area/LLMOS`.
- The screen passphrase, if the lock screen appears, is: correct horse battery
- Spend at most about 20 minutes.

## Your notes
Write `docs/research/feature-sweep-2026-10-14/NN-NAME.md` (the number and name given in your task). In it:
1. **Task** and **Verdict**: WORKS / PARTLY / BROKEN.
2. **Steps**: each thing you did, what you expected, what happened, and how long it took. Name the screenshot.
3. **Bugs**: each with the exact words you typed or clicked, what you saw, and what should have happened.
4. **Friction**: anything slow, confusing, hard to find or annoying, even if it worked.
5. **Ideas**: short suggestions.
Then reply with five lines at most: the verdict and the worst problems.
