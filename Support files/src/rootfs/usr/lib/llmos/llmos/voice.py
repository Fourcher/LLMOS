"""Voice in and out, entirely on this machine: speech-to-text with whisper.cpp,
speech out with espeak-ng. The microphone is only open while you are talking
(push-to-talk), and audio never leaves the computer.

Microphone sources, in order:
  1. a real capture device (ALSA) -- real hardware, or QEMU on Linux hosts
  2. the launcher's mic bridge on the host (QEMU's macOS audio backend
     cannot capture, so the macOS launcher streams raw mic audio in)
"""
import array
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import wave

from . import config, i18n

# Speech-to-text models (whisper.cpp ggml files). The one in use is the `voice_model` setting; Whisper Base
# ships with the OS, the others are downloaded on request and verified by SHA-256 before use (a catalogue
# entry with no pinned hash is checked against the hash Hugging Face publishes for the exact file).
VOICE_CATALOG = os.path.join(config.SHARE, "voice-catalog.json")
VOICE_DIR_SHIPPED = os.path.join(config.SHARE, "voice")
VOICE_DIR_DL = os.path.join(config.MODELS, "voice")
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


def _alsa_capture_device():
    """The first card that can capture, as plughw:CARD,DEVICE -- `arecord` defaults to card 0, which on many
    machines (HDMI-first laptops, a USB mic as card 1) has no microphone. None when nothing can capture."""
    if not shutil.which("arecord"):
        return None
    p = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
    m = re.search(r"card (\d+):.*?device (\d+):", p.stdout)
    return f"plughw:{m.group(1)},{m.group(2)}" if m else ("default" if "card" in p.stdout else None)


def _alsa_capture_available():
    return _alsa_capture_device() is not None


def _read_deadline(stream, n, deadline):
    """Read up to n bytes, giving up at the deadline so a stalled capture device never hangs the recording."""
    import select
    left = deadline - time.time()
    if left <= 0:
        return b""
    r, _, _ = select.select([stream], [], [], min(left, 0.5))
    return stream.read(n) if r else b" "      # a non-empty filler keeps the VAD loop ticking toward max_s


def _record_alsa():
    dev = _alsa_capture_device() or "default"
    p = subprocess.Popen(["arecord", "-q", "-D", dev, "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 20
        return _vad_collect(lambda: _read_deadline(p.stdout, CHUNK * 2, deadline))
    finally:
        p.terminate()


def _record_bridge():
    try:
        s = socket.create_connection(BRIDGE, timeout=1.5)
    except OSError:
        return None
    try:
        s.settimeout(3)
        from . import system
        secret = system.launcher_value("mic")
        s.sendall(b"START " + secret.encode() + b"\n" if secret else b"START\n")

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


# ------------------------------------------------------------------ voice models

def voice_catalog():
    cat = config.load_json(VOICE_CATALOG, [])
    return cat if isinstance(cat, list) else []


def voice_by_id(vid):
    vid = re.sub(r"[^a-z0-9.\- ]", "", str(vid or "").lower()).strip()
    if not vid:
        return None
    for m in voice_catalog():
        if m["id"] == vid:
            return m
    # forgiving names: "large v3 turbo", "whisper small", "the best one"
    hits = [m for m in voice_catalog() if vid in m["name"].lower() or vid in m["id"]]
    if not hits and vid in ("best", "the best", "large", "large v3", "large-v3", "large v3 turbo", "accurate", "most accurate"):
        hits = [m for m in voice_catalog() if m["id"] == "turbo"]
    if not hits and vid in ("fastest", "smallest", "lightest"):
        hits = [m for m in voice_catalog() if m["id"] == "tiny"]
    return hits[0] if len(hits) == 1 else None


def voice_path(m):
    """Where a voice model's file lives: the shipped one under /usr/share, downloaded ones beside the
    language models."""
    shipped = os.path.join(VOICE_DIR_SHIPPED, m["file"])
    if os.path.exists(shipped):
        return shipped
    return os.path.join(VOICE_DIR_DL, m["file"])


def installed_voice():
    return [m for m in voice_catalog() if os.path.exists(voice_path(m))]


def active_voice():
    """The voice model in use: the owner's choice if it is on disk, otherwise Base, otherwise any installed."""
    want = config.settings.get("voice_model") or "base"
    inst = installed_voice()
    for m in inst:
        if m["id"] == want:
            return m
    for m in inst:
        if m["id"] == "base":
            return m
    return inst[0] if inst else None


def model_path():
    m = active_voice()
    return voice_path(m) if m else os.path.join(VOICE_DIR_SHIPPED, "ggml-base.bin")


def _hf_sha(repo, fname):
    """The SHA-256 Hugging Face publishes for one file (its LFS object id); a file with none is refused."""
    from . import web
    st, _ctype, _final, body = web.fetch(f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true",
                                         max_bytes=3_000_000, timeout=25)
    if st != 200:
        raise RuntimeError(f"could not read {repo} on Hugging Face (HTTP {st})")
    for f in json.loads(body.decode("utf-8", "replace")):
        if str(f.get("path", "")).split("/")[-1] == fname:
            oid = ((f.get("lfs") or {}).get("oid") or "").replace("sha256:", "").strip().lower()
            if re.fullmatch(r"[0-9a-f]{64}", oid):
                return oid
    raise RuntimeError(f"Hugging Face publishes no SHA-256 for {fname}; not downloading an unverifiable file")


def download_voice(vid, progress=None):
    """Fetch a voice model and verify it before it is ever used."""
    m = voice_by_id(vid)
    if not m:
        raise ValueError(f"unknown voice model '{vid}'")
    sha = (m.get("sha256") or "").lower() or _hf_sha(m["repo"], m["file"])
    if os.path.exists(voice_path(m)):
        from . import models
        if models.verified(voice_path(m), sha, progress):
            return m
        if not voice_path(m).startswith(VOICE_DIR_DL):
            raise RuntimeError(f"the {m['name']} file that came with the system is damaged (its SHA-256 does not match)")
        os.unlink(voice_path(m))        # a damaged or replaced download is never used: it is fetched again
    need = m["size"] / 1024 ** 3 + 0.3
    os.makedirs(VOICE_DIR_DL, exist_ok=True)
    st = os.statvfs(VOICE_DIR_DL)
    free = st.f_bavail * st.f_frsize / 1024 ** 3
    if free < need:
        raise ValueError(f"not enough free disk: need {need:.1f} GB, have {free:.1f} GB")
    dest = os.path.join(VOICE_DIR_DL, m["file"])
    part = dest + ".part"
    url = f"https://huggingface.co/{m['repo']}/resolve/main/{m['file']}"
    cmd = ["curl", "-sSL", "--fail", "-C", "-", "--retry", "3", "-o", part, url]
    if config.settings.get("tor"):
        cmd[1:1] = ["--socks5-hostname", "127.0.0.1:9050"]
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
    while p.poll() is None:
        if progress:
            try:
                progress("download", os.path.getsize(part), m["size"])
            except OSError:
                pass
        time.sleep(1)
    if p.returncode != 0:
        raise RuntimeError("download failed: " + (p.stderr.read().strip() or f"curl exit {p.returncode}")[:300])
    h = hashlib.sha256()
    total, done = os.path.getsize(part), 0
    with open(part, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
            done += len(block)
            if progress:
                progress("verify", done, total)
    if h.hexdigest() != sha:
        os.unlink(part)
        raise RuntimeError(f"checksum mismatch for {m['file']}: the file was deleted and nothing was used")
    os.replace(part, dest)
    from . import models
    models._mark_verified(dest, sha)
    return m


def use_voice(vid):
    m = voice_by_id(vid)
    if not m:
        raise ValueError(f"unknown voice model '{vid}'")
    if not os.path.exists(voice_path(m)):
        raise ValueError(f"{m['name']} is not downloaded yet; download it first")
    config.settings.set("voice_model", m["id"])
    return m


def remove_voice(vid):
    m = voice_by_id(vid)
    if not m:
        raise ValueError(f"unknown voice model '{vid}'")
    if m.get("shipped"):
        raise ValueError(f"{m['name']} ships with the OS and stays as the fallback")
    path = os.path.join(VOICE_DIR_DL, m["file"])
    if os.path.exists(path):
        os.unlink(path)
    if config.settings.get("voice_model") == m["id"]:
        config.settings.set("voice_model", "base")
    return m


def available():
    return os.path.exists(model_path()) and shutil.which("whisper-cli") is not None


def _bridge_available():
    """The VM launcher's microphone bridge, only when this boot was given one (fw_cfg opt/llmos/mic): on real
    hardware or in another VM, whatever answers at that address is not this computer's microphone."""
    from . import system
    if not system.launcher_says("mic"):
        return False
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


def transcribe(wav_path, keep=False):
    lang = i18n.lang_code(config.llm_language())
    lang = lang if len(lang) == 2 else "auto"
    p = subprocess.run(["whisper-cli", "-m", model_path(), "-f", wav_path, "-l", lang, "-nt", "-np",
                        "-t", str(os.cpu_count() or 2)], capture_output=True, text=True)
    if not keep:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
    return clean_transcript(p.stdout)


# whisper marks non-speech with bracketed tags; none of them belong in typed text
_NONSPEECH = re.compile(r"\[(?:BLANK_AUDIO|MUSIC|NOISE|SILENCE|INAUDIBLE|APPLAUSE|LAUGHTER|[ _A-Z]{3,})\]|\((?:music|silence|noise|inaudible)\)", re.I)


def clean_transcript(raw):
    return " ".join(_NONSPEECH.sub(" ", raw or "").split()).strip()


# ------------------------------------------------------------------ system-wide dictation

def type_text(text):
    """Type text at the cursor of whatever window has focus -- a field on the desk, a terminal, a browser --
    through the compositor's virtual keyboard (wtype, wlroots). Returns True if it was typed."""
    if not text or not shutil.which("wtype") or not os.environ.get("WAYLAND_DISPLAY"):
        return False
    try:
        return subprocess.run(["wtype", "--", text], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def chime():
    wav = os.path.join(config.SHARE, "chime.wav")
    if os.path.exists(wav) and shutil.which("aplay"):
        subprocess.Popen(["aplay", "-q", wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def dictate(notify=None):
    """Record one utterance, transcribe it with the chosen voice model, and type it where the owner is.
    Returns (text, note): text is what was heard ('' if nothing, None if it could not run)."""
    if not available():
        return None, "no speech model is installed"
    if notify:
        notify("listening")
    wav = listen()
    if wav is None:
        return None, "no microphone was found"
    if not wav:
        return "", "nothing was heard"
    if notify:
        notify("transcribing")
    text = transcribe(wav)
    if not text:
        return "", "nothing was heard"
    return text, ("typed" if type_text(text) else "heard, but nothing could be typed (no focused field or no wtype)")


def speak(text):
    if not shutil.which("espeak-ng"):
        return
    lang = i18n.lang_code(config.llm_language())
    voice = {"zh": "cmn", "ja": "ja"}.get(lang, lang if len(lang) == 2 else "en")
    subprocess.Popen(["espeak-ng", "-v", voice, "-s", "165", text[:1200]],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
