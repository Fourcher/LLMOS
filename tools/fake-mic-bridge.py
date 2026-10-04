#!/usr/bin/env python3
"""A stand-in for dist/mic-bridge.py, for tests: listens on 127.0.0.1:8766 (the guest reaches it as
10.0.2.2:8766) and, on START, streams a WAV file as if it were the microphone -- a moment of room noise for
the voice-activity detector to calibrate on, then the speech, then silence so it knows the speaker stopped.
Paced in real time, 16 kHz mono 16-bit, exactly like the real bridge. Serves every connection, so the
dictation path can be exercised repeatedly. usage: tools/fake-mic-bridge.py speech.wav [--port 8766]"""
import argparse
import array
import random
import socket
import threading
import time
import wave

ap = argparse.ArgumentParser()
ap.add_argument("wav")
ap.add_argument("--port", type=int, default=8766)
opts = ap.parse_args()

w = wave.open(opts.wav)
assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, "need 16 kHz mono 16-bit"
SPEECH = w.readframes(w.getnframes())
CHUNK = 3200                         # 0.1 s of 16-bit mono at 16 kHz, what voice.py reads per step


def room_noise(seconds):
    a = array.array("h", (random.randint(-60, 60) for _ in range(int(16000 * seconds))))
    return a.tobytes()


def serve(conn):
    try:
        line = b""
        while not line.endswith(b"\n"):
            part = conn.recv(64)
            if not part:
                return
            line += part
        if line.strip() != b"START":
            return
        stream = room_noise(0.5) + SPEECH + bytes(16000 * 2 * 3)      # noise, speech, 3 s of silence
        for i in range(0, len(stream), CHUNK):
            conn.sendall(stream[i:i + CHUNK])
            time.sleep(0.1)
    except OSError:
        pass
    finally:
        conn.close()


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", opts.port))
srv.listen(4)
print(f"fake mic bridge on 127.0.0.1:{opts.port}, serving {opts.wav} ({len(SPEECH) / 32000:.1f} s of speech)", flush=True)
while True:
    c, _ = srv.accept()
    threading.Thread(target=serve, args=(c,), daemon=True).start()
