#!/usr/bin/env python3
"""Grab the guest's framebuffer through QEMU's monitor socket and save it as
PNG (no third-party libraries).  usage: screendump.py MONITOR.sock OUT.png"""
import os
import socket
import struct
import sys
import time
import zlib


def monitor(sock_path, cmd):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    s.settimeout(3)
    try:
        s.recv(4096)
    except socket.timeout:
        pass
    s.sendall((cmd + "\n").encode())
    time.sleep(1.5)
    try:
        s.recv(4096)
    except socket.timeout:
        pass
    s.close()


def ppm_to_png(ppm_path, png_path):
    data = open(ppm_path, "rb").read()
    # P6 header: magic, width, height, maxval (whitespace separated, comments possible)
    tokens, i = [], 0
    while len(tokens) < 4:
        while data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            while data[i:i + 1] not in (b"\n", b""):
                i += 1
            continue
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        tokens.append(data[i:j])
        i = j
    i += 1
    w, h = int(tokens[1]), int(tokens[2])
    pixels = data[i:i + w * h * 3]
    raw = b"".join(b"\x00" + pixels[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    open(png_path, "wb").write(png)
    # crude content stats: fraction of non-black pixels and distinct colours
    nonblack = sum(1 for k in range(0, len(pixels), 3 * 97) if pixels[k:k + 3] != b"\x00\x00\x00")
    colours = len(set(pixels[k:k + 3] for k in range(0, len(pixels), 3 * 997)))
    return w, h, nonblack / max(1, len(pixels) // (3 * 97)), colours


if __name__ == "__main__":
    sock, out = sys.argv[1], sys.argv[2]
    # QEMU's monitor splits arguments on spaces: dump into a space-free path
    ppm = os.path.join("/private/tmp/claude-501/-Volumes-Files-Claude-Work-Area-LLMOS/86625566-deaf-4867-9565-8f3b6d502142/scratchpad",
                       os.path.basename(out) + ".ppm")
    if os.path.exists(ppm):
        os.unlink(ppm)
    monitor(sock, f"screendump {ppm}")
    for _ in range(20):
        if os.path.exists(ppm) and os.path.getsize(ppm) > 100:
            break
        time.sleep(0.5)
    w, h, frac, colours = ppm_to_png(ppm, out)
    os.unlink(ppm)
    print(f"{out}: {w}x{h}, non-black {frac:.0%}, ~{colours} distinct colours sampled")
