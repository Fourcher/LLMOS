#!/usr/bin/env python3
"""Microphone bridge for running LLM OS under QEMU on macOS.

QEMU's macOS audio backend can play sound but cannot capture it, so voice
input has no way into the guest. This tiny helper listens on 127.0.0.1:8766
(which the guest reaches as 10.0.2.2:8766) and, while the guest asks for it,
streams raw 16 kHz mono PCM from the Mac's default microphone using ffmpeg.

The mic is opened only between START and STOP (push-to-talk from inside the
OS), audio goes only to the guest over loopback, and nothing is recorded.

    brew install ffmpeg
    python3 mic-bridge.py        # leave it running while the VM runs
"""
import shutil
import socket
import subprocess
import sys
import threading

HOST, PORT = "127.0.0.1", 8766


def serve(conn):
    proc = None
    try:
        f = conn.makefile("rb")
        line = f.readline().strip()
        if line != b"START":
            return
        proc = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-f", "avfoundation", "-i", ":default",
             "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
        sys.stderr.write("mic open\n")
        while True:
            chunk = proc.stdout.read(3200)
            if not chunk:
                break
            try:
                conn.sendall(chunk)
            except OSError:
                break
    finally:
        if proc:
            proc.terminate()
            sys.stderr.write("mic closed\n")
        conn.close()


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required: brew install ffmpeg")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(1)
    print(f"mic bridge ready on {HOST}:{PORT} (guest sees 10.0.2.2:{PORT}); Ctrl+C to stop")
    while True:
        conn, _ = s.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
