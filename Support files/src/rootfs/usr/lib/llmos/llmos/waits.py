"""Short polling waits, shared by desk.py and tools.py (no GUI imports here, so tests can load it)."""
import time


def scan_settled(read, limit=3.0, step=0.25, ready=None, default=""):
    """Poll read() every `step` seconds until it gives a ready value that is the same as the previous poll.

    read() returns whatever the caller parses (for example iwctl get-networks text). A value counts as ready when
    ready(value) is true (default: any truthy value). An exception from read() counts as not ready. Gives up after
    `limit` seconds and returns the last value read (or `default` if none could be read), as the old fixed sleep did.
    """
    ready = ready or (lambda v: bool(v))
    end = time.monotonic() + limit
    prev, cur = None, None
    while True:
        try:
            cur = read()
        except Exception:
            cur = None
        if cur is not None and ready(cur) and cur == prev:
            return cur
        prev = cur
        if time.monotonic() >= end:
            return cur if cur is not None else default
        time.sleep(step)


def wait_until(pred, total=15.0, step=0.25):
    """Check pred() every `step` seconds, up to total/step times. True as soon as pred() is true, else False."""
    for _ in range(int(round(total / step))):
        if pred():
            return True
        time.sleep(step)
    return False
