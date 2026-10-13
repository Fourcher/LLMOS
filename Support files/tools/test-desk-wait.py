#!/usr/bin/env python3
"""Host test of the test-shell control command `wait` (desk.py). `wait` must not return while a request queued by
say() is still running, even when its fast paths finish before `busy` is set. Structural checks read the desk.py
source; the behaviour check runs the wait branch itself against a stub. Run: python3 tools/test-desk-wait.py"""
import os
import queue
import sys
import textwrap
import threading
import time

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


def slice_between(start_mark, end_mark):
    s = src.find(start_mark)
    if s == -1:
        return ""
    e = src.find(end_mark, s + len(start_mark))
    return src[s:e] if e != -1 else src[s:]


# (a) say(): the counter goes up before the request is queued
say_body = slice_between("    def say(self, text, done=None, chat=\"main\"):", "    # tools that finish")
inc = say_body.find("self._req_pending += 1")
put = say_body.find("self.requests.put((text, done, chat))")
check(inc != -1 and put != -1 and inc < put, "say() increments _req_pending before requests.put")
check("with self._pending_lock:" in say_body[:put], "say() increments under _pending_lock")

# (b) _worker(): the counter goes down inside its finally, under the lock, never below 0
worker_body = slice_between("    def _worker(self):", "    def _app_question(self, low):")
fin = worker_body.find("finally:")
dec = worker_body.find("self._req_pending = max(0, self._req_pending - 1)")
check(fin != -1 and dec != -1 and dec > fin, "_worker() decrements _req_pending inside its finally")
check("with self._pending_lock:" in worker_body[fin:dec], "_worker() decrements under _pending_lock")

# (c) __init__ defines the counter and its lock
check("self._req_pending = 0" in src and "self._pending_lock = threading.Lock()" in src,
      "__init__ defines _req_pending and _pending_lock")

# (d) stop_all() drops queued requests: each one must be counted off too
stop_body = slice_between("    def stop_all(self):", "    def lock(self):")
check("self._req_pending = max(0, self._req_pending - 1)" in stop_body, "stop_all() counts off the requests it drops")

# (e) the wait branch: 3 s grace on _req_pending / busy / last_reply, then wait for idle
wait_start = src.find('elif cmd == "wait":')
wait_end = src.find("elif cmd == ", wait_start + 10)
wait_branch = src[wait_start:wait_end] if wait_end != -1 else src[wait_start:]
check(wait_start != -1, "wait branch exists")
check("start_reply = self.last_reply" in wait_branch, "wait branch remembers last_reply at entry")
check("range(30)" in wait_branch and "time.sleep(0.1)" in wait_branch, "wait branch has a 3 s grace polling every 0.1 s")
check("self._req_pending > 0 or self.busy or self.last_reply != start_reply" in wait_branch,
      "grace ends when a request is pending, busy, or the reply changed")
check("self._req_pending == 0 and not self.busy and self.requests.empty()" in wait_branch,
      "wait branch waits for pending == 0, not busy, queue empty")
check("time.sleep(0.25)" in wait_branch, "idle loop polls every 0.25 s")

# (f) behaviour: run the wait branch against a stub. A request is pending from 0.5 s to 1.5 s:
# wait must return after about 1.5 s, not at once.
body = wait_branch.split("\n", 1)[1]
body = textwrap.dedent(body)
code = "def _wait_probe(self, arg):\n    out = None\n" + textwrap.indent(body, "    ") + "    return out\n"
ns = {"time": time}
exec(compile(code, "<wait-branch>", "exec"), ns)
wait_fn = ns["_wait_probe"]


class Stub:
    def __init__(self):
        self.busy = False
        self.last_reply = ""
        self.requests = queue.Queue()
        self._req_pending = 0
        self._pending_lock = threading.Lock()

    def _state(self):
        return {"pending": self._req_pending}


def run_case(schedule):
    """schedule: list of (delay_s, new_pending) applied from a helper thread; returns (elapsed, state, pending_trace)."""
    stub = Stub()
    trace = []

    def driver():
        t0 = time.time()
        for delay, val in schedule:
            time.sleep(max(0.0, t0 + delay - time.time()))
            with stub._pending_lock:
                stub._req_pending = val
            trace.append((round(time.time() - t0, 2), val))
    th = threading.Thread(target=driver, daemon=True)
    th.start()
    t = time.time()
    out = wait_fn(stub, "10")
    elapsed = time.time() - t
    th.join()
    return elapsed, out, trace


# case 1: request starts at 0.5 s, finishes at 1.5 s
elapsed, out, trace = run_case([(0.5, 1), (1.5, 0)])
print("case1 pending trace %s elapsed %.2f s" % (trace, elapsed))
check(1.3 <= elapsed <= 2.6 and out == {"pending": 0}, "wait returns after the request ends (~1.5 s), not at once")

# case 2: nothing starts: wait returns after the 3 s grace, no longer
elapsed, out, trace = run_case([])
print("case2 nothing queued elapsed %.2f s" % elapsed)
check(2.8 <= elapsed <= 5.0 and out == {"pending": 0}, "nothing started: returns after the 3 s grace")

# (g) the done counter: incremented in _worker's finally under the lock, reported by _state()
check("self._req_done = 0" in src, "__init__ defines _req_done")
dinc = worker_body.find("self._req_done += 1")
check(fin != -1 and dinc > fin and "with self._pending_lock:" in worker_body[fin:dinc],
      "_worker() increments _req_done inside its finally, under _pending_lock")
state_body = slice_between("    def _state(self):", "    def _control_conn(self, conn):")
check('"done": self._req_done' in state_body, "_state() reports done")


# (h) behaviour: wait "10 after 3" with done already 5 (> 3) skips the grace and returns at once
class DoneStub(Stub):
    def __init__(self):
        Stub.__init__(self)
        self._req_done = 5

    def _state(self):
        return {"done": self._req_done}


done_stub = DoneStub()
t = time.time()
out_done = wait_fn(done_stub, "10 after 3")
el_done = time.time() - t
check(el_done < 0.5 and out_done == {"done": 5}, "wait N after M with done > M returns at once (%.2f s)" % el_done)

# (i) wait "N after M" with nothing new: the grace lasts to the timeout (here 3 s), not a fixed 3 s
none_stub = DoneStub()
none_stub._req_done = 2
t = time.time()
wait_fn(none_stub, "3 after 2")
el_none = time.time() - t
check(2.7 <= el_none <= 3.3, "wait N after M with nothing new: returns at the timeout (%.2f s)" % el_none)


# (j) the real _control_conn, driven through a fake socket that captures the written response
import io  # noqa: E402
import json  # noqa: E402

_ROOT = os.path.join(HERE, "..", "src", "rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import desk  # noqa: E402


class FakeConn:
    def __init__(self, line):
        self._in = io.StringIO(line + "\n")
        self.sent = []

    def settimeout(self, s):
        pass

    def makefile(self, mode, encoding=None):
        return self._in

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        pass


def ctl_case(line, schedule, done0=0):
    """Run desk._control_conn("wait ...") on a Desk.__new__ stub. schedule: (delay_s, pending, done) applied by a
    helper thread. Returns (elapsed, parsed response)."""
    d = desk.Desk.__new__(desk.Desk)
    d.busy = False
    d.last_reply = ""
    d.requests = queue.Queue()
    d._pending_lock = threading.Lock()
    d._req_pending = 0
    d._req_done = done0
    d._state = lambda: {"done": d._req_done, "busy": d.busy}
    conn = FakeConn(line)

    def driver():
        t0 = time.time()
        for delay, pending, done in schedule:
            time.sleep(max(0.0, t0 + delay - time.time()))
            with d._pending_lock:
                d._req_pending = pending
                d._req_done = done

    th = threading.Thread(target=driver, daemon=True)
    th.start()
    t = time.time()
    d._control_conn(conn)
    elapsed = time.time() - t
    th.join()
    resp = json.loads(conn.sent[-1].decode()) if conn.sent else None
    return elapsed, resp


# j1: the typed line reaches say() late (4 s), runs 0.5 s: wait returns when its turn is done, not at 3 s
el, resp = ctl_case("wait 10 after 3", [(4.0, 1, 3), (4.5, 0, 4)], done0=3)
check(4.2 <= el <= 4.8 and resp == {"done": 4, "busy": False}, "line arrives at 4 s: returns after its turn (%.2f s)" % el)

# j2: the line never arrives: returns at the timeout (3 s), neither earlier nor later
el, resp = ctl_case("wait 3 after 3", [], done0=3)
check(2.7 <= el <= 3.3 and resp["done"] == 3, "line never arrives: returns at the 3 s timeout (%.2f s)" % el)

# j3: timeout 0 and negative: returns at once
el0, resp0 = ctl_case("wait 0 after 3", [], done0=3)
eln, respn = ctl_case("wait -2 after 3", [], done0=3)
check(el0 < 0.3 and eln < 0.3 and resp0 is not None and respn is not None,
      "timeout 0 / negative: returns at once (%.2f s, %.2f s)" % (el0, eln))

# j4: already advanced (done 5 > after 3): returns at once
el, resp = ctl_case("wait 10 after 3", [], done0=5)
check(el < 0.3 and resp["done"] == 5, "done already past after: returns at once (%.2f s)" % el)

# j5: no "after": the fixed 3 s grace is unchanged (nothing started: returns after about 3 s)
el, resp = ctl_case("wait 10", [], done0=0)
check(2.7 <= el <= 3.5 and resp is not None, "no after: 3 s grace unchanged (%.2f s)" % el)

print("all good" if not fails else "FAILED: %d" % len(fails))
sys.exit(1 if fails else 0)
