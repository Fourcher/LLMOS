#!/usr/bin/env python3
"""Host test of the test-shell control command `testreset-min` (desk.py): a sibling of `testreset` that only closes the
open app windows and starts a new topic. It must not touch settings and must not cancel or reschedule screen blanking.
Reads the desk.py source and checks the branch text. Run: python3 tools/test-testreset-min.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py")
src = open(SRC, encoding="utf-8").read()

fails = []


def check(cond, label):
    if cond:
        print("ok " + label)
    else:
        print("FAIL " + label)
        fails.append(label)


# the branch: from its `elif` line to the next `elif cmd` (the `rect` branch that follows it)
START_MARK = 'elif cmd == "testreset-min"'
start = src.find(START_MARK)
check(start != -1, "testreset-min branch exists")
if start == -1:
    print("FAIL testreset-min branch missing")
    sys.exit(1)
end = src.find("elif cmd ", start + len(START_MARK))
branch = src[start:end] if end != -1 else src[start:]
head_line = branch.split("\n", 1)[0]

# (a) gated by _fwcfg("testshell")
check('_fwcfg("testshell")' in head_line, 'testreset-min is gated by _fwcfg("testshell")')

# (b) no settings writes/resets, no config.settings write, no blanking / dpms / screensaver call
forbidden = ["settings.set", "settings.reset", "config.settings", "dpms", "screensaver", "start_idle", "blank"]
body = branch.split("\n", 1)[1]   # the lines under the elif (its comment line is not code)
hits = [tok for tok in forbidden if tok in body]
check(not hits, "branch body has no settings, config.settings, blanking, dpms or screensaver call" + (" (found: %s)" % ", ".join(hits) if hits else ""))

# (c) same window-close and new-topic helpers as testreset
check("self.close_window(wid)" in branch and "for wid in list(self.windows):" in branch,
      "branch closes open windows with the testreset helper self.close_window (loop over self.windows)")
check("self.chat().new_topic()" in branch,
      "branch starts a new topic with the testreset helper self.chat().new_topic()")

# (d) a dialog left open by the previous task is declined first, so it cannot block the next one
first_stmt = body.lstrip().split("\n", 1)[0].strip()
check(first_stmt == "self.decline_dialogs()",
      "branch calls self.decline_dialogs() as its first statement, before the window-close loop")
check("self.push_status()" in body and body.index("self.push_status()") < body.index("out = {\"ok\": True}"),
      "branch calls self.push_status() just before out = {\"ok\": True}")

if fails:
    print("FAIL %d check(s): %s" % (len(fails), "; ".join(fails)))
    sys.exit(1)
print("all good")
