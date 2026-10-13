#!/usr/bin/env python3
"""Host-side unit test for tools._screen_after: it returns as soon as the page key changes (max 0.8 s),
waits the full 0.8 s when the page does not change, when the key raises, or when there is no ctx.
Only the screen reader (control.describe) and the ctx are faked; the real _screen_after and _page_key run.
Run: python3 tools/test-screen-after.py  (no VM needed)."""
import os
import sys
import time
from unittest.mock import patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import tools, control


class FakeCtx:
    """app_read() shows page A until `change_at` seconds after creation, then page B.
    change_at=None: never changes. raise_after=True: raises on every call after the first snapshot."""
    def __init__(self, change_at=None, raise_after=False):
        self.t0 = time.monotonic()
        self.change_at = change_at
        self.raise_after = raise_after
        self.calls = 0

    def app_read(self):
        self.calls += 1
        if self.raise_after and self.calls > 1:
            raise RuntimeError("bridge gone")
        page = "B" if (self.change_at is not None and time.monotonic() - self.t0 >= self.change_at) else "A"
        return {"text": f"page {page}", "controls": ["OK"]}


def timed_after(ctx, before):
    t = time.monotonic()
    with patch.object(control, "describe", return_value="SCREEN"):
        out = tools._screen_after(ctx=ctx, before=before)
    assert out == "SCREEN", out
    return time.monotonic() - t


failures = []


def check(name, elapsed, lo, hi):
    ok = lo <= elapsed <= hi
    print(f"{'ok' if ok else 'FAIL'} {name}: {elapsed:.2f} s (expected {lo:.2f}-{hi:.2f} s)")
    if not ok:
        failures.append(name)


# 1. page changes at 0.2 s -> returns early (about 0.2-0.3 s, never more than 0.4 s)
ctx = FakeCtx(change_at=0.2)
before = tools._page_key(ctx)
assert before == ("page A", repr(["OK"])), before
t = timed_after(ctx, before)
check("page changes at 0.2 s", t, 0.15, 0.4)

# 2. page never changes (typing into the same page) -> full 0.8 s as today
ctx = FakeCtx(change_at=None)
before = tools._page_key(ctx)
t = timed_after(ctx, before)
check("page never changes", t, 0.75, 0.95)

# 3. key raises after the snapshot -> treated as unchanged -> full 0.8 s
ctx = FakeCtx(raise_after=True)
before = tools._page_key(ctx)
assert before is not None
t = timed_after(ctx, before)
check("key raises", t, 0.75, 0.95)

# 4. no ctx -> full 0.8 s as today
t = timed_after(None, None)
check("ctx None", t, 0.75, 0.95)

# 5. no page snapshot (no read bridge) -> full 0.8 s as today
t = timed_after(object(), None)
check("no snapshot", t, 0.75, 0.95)

if failures:
    print("FAILED: " + ", ".join(failures))
    sys.exit(1)
print("all good")
