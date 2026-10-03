"""Voice in and out, entirely on this machine: speech-to-text with whisper.cpp,
speech out with espeak-ng. The microphone is only open while you are talking
(push-to-talk), and audio never leaves the computer.

Microphone sources, in order:
  1. a real capture device (ALSA) -- real hardware, or QEMU on Linux hosts
  2. the launcher's mic bridge on the host (QEMU's macOS audio backend
     cannot capture, so the macOS launcher streams raw mic audio in)
"""
import array
import math
import os
import shutil
import socket
import subprocess
import tempfile
import time
import wave

from . import config, i18n

MODEL = os.path.join(config.SHARE, "voice", "ggml-base.bin")
BRIDGE = ("10.0.2.2", 8766)
RATE = 16000
CHUNK = 1600  # 0.1 s of 16-bit mono


def _rms(buf):
    a = array.array("h", buf)
    if not a:
        return 0
    return math.sqrt(sum(x * x for x in a) / len(a))


def _vad_collect(read, max_s=15, silence_s=1.2, wait_s=6):
    """Read 0.1 s chunks until the speaker has spoken and then paused."""
    frames, noise, speaking, quiet = [], [], False, 0.0
    t0 = time.time()
    while time.time() - t0 < max_s:
        buf = read()
        if not buf:
            break
        level = _rms(buf)
        if len(noise) < 3:
            noise.append(level)
            continue
        floor = max(sum(noise) / len(noise) * 3, 400)
        if level > floor:
            speaking, quiet = True, 0.0
        elif speaking:
            quiet += 0.1
        frames.append(buf)
        if speaking and quiet >= silence_s:
            break
        if not speaking and time.time() - t0 > wait_s:
            return b""
    return b"".join(frames) if speaking else b""


def _alsa_capture_available():
    if not shutil.which("arecord"):
        return False
    p = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
    return "card" in p.stdout


def _record_alsa():
    p = subprocess.Popen(["arecord", "-q", "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        return _vad_collect(lambda: p.stdout.read(CHUNK * 2))
    finally:
        p.terminate()


def _record_bridge():
    try:
        s = socket.create_connection(BRIDGE, timeout=1.5)
    except OSError:
        return None
    try:
        s.settimeout(3)
        s.sendall(b"START\n")

        def read():
            data = b""
            while len(data) < CHUNK * 2:
                part = s.recv(CHUNK * 2 - len(data))
                if not part:
                    break
                data += part
            return data
        return _vad_collect(read)
    except OSError:
        return None
    finally:
        try:
            s.sendall(b"STOP\n")
        except OSError:
            pass
        s.close()


def available():
    return os.path.exists(MODEL) and shutil.which("whisper-cli") is not None


def _bridge_available():
    try:
        socket.create_connection(BRIDGE, timeout=0.5).close()
        return True
    except OSError:
        return False


def listen():
    """Record one utterance. Returns a WAV path, '' if nothing was said,
    or None if there is no microphone at all.

    The host bridge is tried first: under QEMU a virtual sound card exists
    but its capture side is silent on macOS, so the bridge is the only path
    that carries a real microphone there. On real hardware there is no bridge
    and ALSA is used."""
    pcm = None
    if _bridge_available():
        pcm = _record_bridge()
    if pcm is None and _alsa_capture_available():
        pcm = _record_alsa()
    if pcm is None:
        return None
    if not pcm:
        return ""
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="llmos-voice-")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return path


def transcribe(wav_path):
    lang = i18n.lang_code(config.llm_language())
    lang = lang if len(lang) == 2 else "auto"
    p = subprocess.run(["whisper-cli", "-m", MODEL, "-f", wav_path, "-l", lang, "-nt", "-np",
                        "-t", str(os.cpu_count() or 2)], capture_output=True, text=True)
    try:
        os.unlink(wav_path)
    except OSError:
        pass
    return " ".join(p.stdout.split()).strip()


def speak(text):
    if not shutil.which("espeak-ng"):
        return
    lang = i18n.lang_code(config.llm_language())
    voice = {"zh": "cmn", "ja": "ja"}.get(lang, lang if len(lang) == 2 else "en")
    subprocess.Popen(["espeak-ng", "-v", voice, "-s", "165", text[:1200]],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
