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

# (c2) both testreset branches clear the last reply, so a task never starts with the previous task's reply
TR_START = 'elif cmd == "testreset" and _fwcfg("testshell")'
tr_start = src.find(TR_START)
tr_end = src.find("elif cmd ", tr_start + len(TR_START)) if tr_start != -1 else -1
tr_branch = src[tr_start:tr_end] if tr_end != -1 else (src[tr_start:] if tr_start != -1 else "")
check(tr_start != -1 and 'self.last_reply = ""' in tr_branch,
      'testreset branch body contains self.last_reply = ""')
check('self.last_reply = ""' in body,
      'testreset-min branch body contains self.last_reply = ""')

# (d) a dialog left open by the previous task is declined first, so it cannot block the next one
first_stmt = body.lstrip().split("\n", 1)[0].strip()
check(first_stmt == "self.decline_dialogs()",
      "branch calls self.decline_dialogs() as its first statement, before the window-close loop")
check("self.push_status()" in body and body.index("self.push_status()") < body.index("out = {\"ok\": True}"),
      "branch calls self.push_status() just before out = {\"ok\": True}")

# (e) both reset branches close the external program windows, skipping the desk, and SIGTERM the launched programs
for label, br in (("testreset", tr_branch), ("testreset-min", branch)):
    check("wm.windows()" in br, label + " reads the open program windows with wm.windows()")
    check('wm.act("close", aid)' in br, label + ' closes program windows with wm.act("close", aid)')
    check('a != "org.llmos.desk"' in br, label + ' skips the desk window (org.llmos.desk)')
    check("wm.force_quit(aid)" in br, label + " force-quits windows still open after the poll")
    check("for pid in list(self.apps):" in br and "self.close_app(pid)" in br,
          label + " calls self.close_app(pid) over self.apps")
    check("self._focus_desk()" in br, label + " refocuses the desk with self._focus_desk()")

# (f) the focus control command and the helper: the helper holds the wlrctl focus, gtkwin.present and the input focus
focus_start = src.find('elif cmd == "focus"')
focus_branch = src[focus_start:src.find("elif cmd ", focus_start + 10)] if focus_start != -1 else ""
check("self._focus_desk()" in focus_branch and "wlrctl" not in focus_branch,
      'the "focus" branch calls self._focus_desk()')
h_start = src.find("def _focus_desk(self):")
h_body = src[h_start:src.find("\n    def ", h_start + 10)] if h_start != -1 else ""
check(h_start != -1 and "app_id:org.llmos.desk" in h_body and "gtkwin.present()" in h_body
      and "getElementById('in')" in h_body, "_focus_desk() holds the wlrctl focus, gtkwin.present and the input focus")

# (g) run the testreset-min close block against stubs: only firefox is closed, the desk is never touched
import textwrap
blk_start = branch.find("try:                          # program windows")
blk_end = branch.find("self._focus_desk()\n") + len("self._focus_desk()\n")
if blk_start != -1 and blk_end > blk_start:
    code = textwrap.dedent(" " * 16 + branch[blk_start:blk_end])
    import time as _time

    class WM:
        PROCS = {"firefox": "firefox", "org.xfce.mousepad": "mousepad"}   # the programs wm.py maps (a subset)

        def __init__(self):
            self.open = ["org.llmos.desk", "firefox"]
            self.acted = []
            self.forced = []
        def windows(self):
            return list(self.open)
        def act(self, what, target):
            self.acted.append((what, target))
            if what == "close" and target in self.open:
                self.open.remove(target)
            return True, ""
        def force_quit(self, target):
            self.forced.append(target)
            return True, ""

    class Desk:
        def __init__(self):
            self.apps = {101: {}, 102: {}}
            self.closed = []
            self.focused = 0
        def close_app(self, pid):
            self.closed.append(pid)
        def _focus_desk(self):
            self.focused += 1

    wm_stub = WM()
    desk_stub = Desk()
    sleeps = []
    clock = [0.0]   # a fake clock that advances only on sleep, so a window that never closes ends the poll
    def _sleep(s):
        sleeps.append(s)
        clock[0] += s
    time_stub = type("T", (), {"time": staticmethod(lambda: clock[0]), "sleep": staticmethod(_sleep)})
    never_kill_line = [l for l in src.splitlines() if l.startswith("NEVER_KILL = ")][0]
    never_kill = eval(never_kill_line.split("=", 1)[1])
    g = {"wm": wm_stub, "time": time_stub, "self": desk_stub, "sys": sys, "NEVER_KILL": never_kill}
    try:
        exec(compile(code, "<testreset-min-close>", "exec"), g)
        ran = True
    except Exception as e:
        print("FAIL close block raised: %r" % (e,))
        ran = False
    check(ran and wm_stub.acted == [("close", "firefox")],
          'stub run: act("close") called only for firefox (acted=%s)' % (wm_stub.acted,))
    check(ran and "org.llmos.desk" in wm_stub.open and not wm_stub.forced,
          "stub run: the desk window is never closed and nothing is force-quit once firefox is gone")
    check(ran and desk_stub.closed == [101, 102] and desk_stub.focused == 1,
          "stub run: close_app over both launched pids, then the desk is refocused once")
    check(ran and sleeps == [0.2],
          "stub run: the poll takes one 0.2 s step, then stops once firefox is gone (sleeps=%s)" % (sleeps,))
    wm_none = WM()
    wm_none.open = ["org.llmos.desk"]
    sleeps.clear()
    g2 = {"wm": wm_none, "time": time_stub, "self": Desk(), "sys": sys, "NEVER_KILL": never_kill}
    exec(compile(code, "<testreset-min-close>", "exec"), g2)
    check(not sleeps and not wm_none.acted,
          "stub run: no external windows -> no act, no delay (sleeps=%s)" % (sleeps,))

    # (h) leftover windows that a close did not clear: force-quit only the known programs, log the unknown ones
    import io
    import contextlib

    def run_leftover(open_list):
        wm_left = WM()
        wm_left.open = list(open_list)   # the stub close does nothing, so the window stays open
        wm_left.act = lambda what, target: (True, "")
        sleeps.clear()
        clock[0] = 0.0
        err = io.StringIO()
        gl = {"wm": wm_left, "time": time_stub, "self": Desk(), "sys": sys, "NEVER_KILL": never_kill}
        with contextlib.redirect_stderr(err):
            exec(compile(code, "<testreset-min-close>", "exec"), gl)
        return wm_left, err.getvalue()

    wm_ff, err_ff = run_leftover(["org.llmos.desk", "firefox"])
    check(wm_ff.forced == ["firefox"] and "testreset left" not in err_ff,
          "stub leftover firefox: force_quit called once with firefox (forced=%s)" % (wm_ff.forced,))
    wm_py, err_py = run_leftover(["org.llmos.desk", "python3"])
    check(wm_py.forced == [] and "desk: testreset left python3 open (unknown program)" in err_py,
          "stub leftover python3: force_quit not called and logged (forced=%s, stderr=%r)" % (wm_py.forced, err_py))
    wm_mp, err_mp = run_leftover(["org.llmos.desk", "org.xfce.mousepad"])
    check(wm_mp.forced == ["org.xfce.mousepad"] and "testreset left" not in err_mp,
          "stub leftover org.xfce.mousepad: force_quit called once with org.xfce.mousepad (forced=%s)" % (wm_mp.forced,))
else:
    check(False, "testreset-min close block located for the stub run")

if fails:
    print("FAIL %d check(s): %s" % (len(fails), "; ".join(fails)))
    sys.exit(1)
print("all good")
