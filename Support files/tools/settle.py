#!/usr/bin/env python3
"""Screen-settle helpers (stdlib only).

read_ppm(path_or_bytes)                -> (w, h, rgb bytes) for binary P6 PPM
small_gray(w, h, rgb, scale=4)         -> (sw, sh, list of 0-255 gray ints)
diff_ratio(a, b, sw, sh, masks=())     -> fraction of sampled pixels differing by > 16
wait_change(grab, before, ...)         -> new frame bytes once the screen changed, or None
wait_still(grab, still_s=1.0, ...)     -> last frame once it stayed still, or None

grab() returns PPM bytes. masks are (x, y, w, h) in FULL-size pixels.
Every timeout is multiplied by float(LLMOS_SLOW or "1").
"""
import os
import sys
import time

SCALE = 4
GRAY_STEP = 16


def _slow():
    try:
        return float(os.environ.get("LLMOS_SLOW", "1"))
    except ValueError:
        return 1.0


def read_ppm(path_or_bytes):
    if isinstance(path_or_bytes, (bytes, bytearray, memoryview)):
        data = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, "rb") as f:
            data = f.read()
    i = 0
    n = len(data)
    tokens = []
    while len(tokens) < 4:
        while i < n and data[i:i + 1].isspace():
            i += 1
        if i < n and data[i:i + 1] == b"#":
            while i < n and data[i:i + 1] not in (b"\n", b"\r"):
                i += 1
            continue
        start = i
        while i < n and not data[i:i + 1].isspace():
            i += 1
        if start == i:
            raise ValueError("truncated PPM header")
        tokens.append(data[start:i])
    if tokens[0] != b"P6":
        raise ValueError("not a binary P6 PPM")
    w, h, maxval = int(tokens[1]), int(tokens[2]), int(tokens[3])
    if maxval != 255:
        raise ValueError("unsupported maxval %d" % maxval)
    i += 1  # exactly one whitespace byte after maxval
    body = data[i:i + w * h * 3]
    if len(body) != w * h * 3:
        raise ValueError("PPM pixel data too short")
    return w, h, body


def small_gray(w, h, rgb, scale=SCALE):
    sw = len(range(0, w, scale))
    sh = len(range(0, h, scale))
    out = []
    for y in range(0, h, scale):
        row = y * w * 3
        for x in range(0, w, scale):
            p = row + x * 3
            r, g, b = rgb[p], rgb[p + 1], rgb[p + 2]
            out.append((r * 30 + g * 59 + b * 11) // 100)
    return sw, sh, out


def _masked(sx, sy, masks):
    fx, fy = sx * SCALE, sy * SCALE
    for (x, y, w, h) in masks:
        if x <= fx < x + w and y <= fy < y + h:
            return True
    return False


def diff_ratio(a, b, sw, sh, masks=()):
    """a, b: small gray lists from small_gray(). Masked pixels are excluded."""
    changed = 0
    counted = 0
    for sy in range(sh):
        for sx in range(sw):
            k = sy * sw + sx
            if masks and _masked(sx, sy, masks):
                continue
            counted += 1
            if abs(a[k] - b[k]) > GRAY_STEP:
                changed += 1
    if counted == 0:
        return 0.0
    return changed / counted


def _small(frame):
    w, h, rgb = read_ppm(frame)
    return small_gray(w, h, rgb)


def wait_change(grab, before, timeout=10, threshold=0.01, masks=(), poll=0.25):
    sw, sh, base = _small(before)
    deadline = time.monotonic() + timeout * _slow()
    while True:
        now = grab()
        nsw, nsh, cur = _small(now)
        if diff_ratio(base, cur, sw, sh, masks) > threshold:
            return now
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll)


def wait_still(grab, still_s=1.0, timeout=20, threshold=0.002, masks=(), poll=0.25):
    start = time.monotonic()
    deadline = start + timeout * _slow()
    last = grab()
    sw, sh, prev = _small(last)
    still_since = time.monotonic()
    while True:
        now_t = time.monotonic()
        if now_t - still_since >= still_s:
            return last
        if now_t >= deadline:
            return None
        time.sleep(poll)
        frame = grab()
        _, _, cur = _small(frame)
        if diff_ratio(prev, cur, sw, sh, masks) >= threshold:
            still_since = time.monotonic()
        prev = cur
        last = frame


if __name__ == "__main__":
    print(__doc__.strip())
    print()
    print("usage: import settle  (this file is a library; no command-line actions)")
    sys.exit(0)
