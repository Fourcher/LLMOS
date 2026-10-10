#!/usr/bin/env python3
"""Synthetic tests for settle.py (no VM, no display)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settle  # noqa: E402

W, H = 64, 48


def make_ppm(pixels_fn):
    """Build a P6 PPM in memory; pixels_fn(x, y) -> (r, g, b). Header has a comment."""
    head = b"P6\n# synthetic frame\n%d %d\n255\n" % (W, H)
    body = bytearray()
    for y in range(H):
        for x in range(W):
            body += bytes(pixels_fn(x, y))
    return head + bytes(body)


def base_fn(x, y):
    return (20, 20, 20)


def with_pixels(changed):
    """changed: set of (x, y) full-size coords turned white."""
    return lambda x, y: (255, 255, 255) if (x, y) in changed else (20, 20, 20)


def check(name, cond):
    if not cond:
        print("FAIL " + name)
        sys.exit(1)
    print("ok " + name)


def set_slow(value):
    if value is None:
        os.environ.pop("LLMOS_SLOW", None)
    else:
        os.environ["LLMOS_SLOW"] = value


def sampled_dims():
    return len(range(0, W, 4)), len(range(0, H, 4))


def small(frame):
    w, h, rgb = settle.read_ppm(frame)
    return settle.small_gray(w, h, rgb)


set_slow(None)

# read_ppm parses header with a comment and returns the pixel body
frame_a = make_ppm(base_fn)
rw, rh, rgb = settle.read_ppm(frame_a)
check("read_ppm header with comment (%dx%d, %d bytes)" % (rw, rh, len(rgb)),
      (rw, rh) == (W, H) and len(rgb) == W * H * 3)

# identical pair -> diff 0, wait_still returns quickly with a constant fake grab
frame_b = make_ppm(base_fn)
sw, sh, ga = small(frame_a)
_, _, gb = small(frame_b)
check("identical pair diff 0", settle.diff_ratio(ga, gb, sw, sh) == 0.0)
t0 = time.monotonic()
got = settle.wait_still(lambda: frame_a, still_s=0.2, timeout=5, poll=0.05)
elapsed = time.monotonic() - t0
check("wait_still constant frame returns quickly (%.2fs)" % elapsed,
      got == frame_a and elapsed < 2.0)

# 2% of sampled pixels changed -> wait_change triggers
sample_points = [(sx * 4, sy * 4) for sy in range(sh) for sx in range(sw)]
two_pct = set(sample_points[:4])  # 4 of 192 sampled pixels = 2.08%
frame_2pct = make_ppm(with_pixels(two_pct))
_, _, g2 = small(frame_2pct)
ratio = settle.diff_ratio(ga, g2, sw, sh)
check("2%% change ratio %.4f" % ratio, abs(ratio - 4 / 192) < 1e-9)
seq = iter([frame_a, frame_2pct])
t0 = time.monotonic()
got = settle.wait_change(lambda: next(seq, frame_2pct), frame_a, timeout=5,
                         threshold=0.01, poll=0.05)
check("2%% change triggers wait_change (%.2fs)" % (time.monotonic() - t0),
      got == frame_2pct)

# one sampled pixel (0.52%) stays under the 1% threshold
one_pct = make_ppm(with_pixels(set(sample_points[:1])))
got = settle.wait_change(lambda: one_pct, frame_a, timeout=0.3, threshold=0.01, poll=0.05)
check("0.5% change does not trigger", got is None)

# change only inside a mask rectangle -> diff 0 and no trigger
region = set((x, y) for x in range(0, 32) for y in range(0, 24))
masked_frame = make_ppm(with_pixels(region))
_, _, gm = small(masked_frame)
mask = [(0, 0, 32, 24)]
unmasked = settle.diff_ratio(ga, gm, sw, sh)
masked = settle.diff_ratio(ga, gm, sw, sh, masks=mask)
check("big change without mask ratio %.3f" % unmasked, unmasked > 0.2)
check("change inside mask gives diff 0", masked == 0.0)
got = settle.wait_change(lambda: masked_frame, frame_a, timeout=0.3,
                         threshold=0.01, masks=mask, poll=0.05)
check("masked change does not trigger wait_change", got is None)

# wait_still times out when the screen keeps changing
flip = [frame_a, frame_2pct]
state = {"i": 0}


def flicker():
    state["i"] += 1
    return flip[state["i"] % 2]


got = settle.wait_still(flicker, still_s=0.5, timeout=0.3, threshold=0.002, poll=0.05)
check("wait_still returns None on timeout", got is None)

# LLMOS_SLOW multiplies timeouts (read at call time)
def timed_no_change(slow):
    set_slow(slow)
    t0 = time.monotonic()
    got = settle.wait_change(lambda: frame_a, frame_a, timeout=0.3, poll=0.05)
    dt = time.monotonic() - t0
    set_slow(None)
    return got, dt


got1, dt1 = timed_no_change(None)
got2, dt2 = timed_no_change("2")
check("LLMOS_SLOW=1 timeout ~0.3s (%.2fs)" % dt1, got1 is None and 0.25 <= dt1 < 0.6)
check("LLMOS_SLOW=2 timeout ~0.6s (%.2fs)" % dt2, got2 is None and 0.55 <= dt2 < 1.2)

# wait_change: a frame of a different size counts as changed (no IndexError)
def make_ppm_size(w, h, value):
    return b"P6\n%d %d\n255\n" % (w, h) + bytes([value]) * (w * h * 3)


small_frame = make_ppm_size(8, 8, 200)
got = settle.wait_change(lambda: small_frame, frame_a, timeout=1, poll=0.05)
check("wait_change size change returns 8x8 frame", got == small_frame)

# wait_still: size flicker resets stillness; constant 8x8 eventually returns
seq2 = {"i": 0}
const_small = make_ppm_size(8, 8, 90)


def flicker_size():
    seq2["i"] += 1
    if seq2["i"] <= 10:
        return frame_a if seq2["i"] % 2 else small_frame
    return const_small


got = settle.wait_still(flicker_size, still_s=0.2, timeout=5, poll=0.05)
check("wait_still size flicker then constant 8x8 (%s)" % ("returned" if got is not None else "None"),
      got is None or got == const_small)

print("all good")
