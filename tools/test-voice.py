#!/usr/bin/env python3
"""Host-side test of the speech-to-text model selection and dictation helpers (llmos/voice.py): the voice
catalogue, forgiving model names, falling back to the shipped Base model when the chosen one is missing,
switching and removing, and cleaning whisper's non-speech tags out of dictated text. No microphone, no
network. Run: python3 tools/test-voice.py"""
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_SHARE = os.path.join(ROOT, "src/rootfs/usr/share/llmos")
tmp = tempfile.mkdtemp(prefix="llmos-voice-")
share, lib = os.path.join(tmp, "share"), os.path.join(tmp, "lib")
os.makedirs(os.path.join(share, "voice"))
os.makedirs(lib)
shutil.copy(os.path.join(SRC_SHARE, "voice-catalog.json"), share)
open(os.path.join(share, "voice", "ggml-base.bin"), "wb").write(b"base")    # the shipped model
os.environ.update({"LLMOS_SHARE": share, "LLMOS_LIB": lib, "LLMOS_HOME": tmp, "LLMOS_ETC": os.path.join(tmp, "etc")})
os.environ.pop("WAYLAND_DISPLAY", None)
sys.path.insert(0, os.path.join(ROOT, "src/rootfs/usr/lib/llmos"))
from llmos import config, voice  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


print("the catalogue")
cat = voice.voice_catalog()
check([m["id"] for m in cat] == ["tiny", "base", "small", "turbo"], f"four whisper models, smallest to best: {[m['id'] for m in cat]}")
check(all(m["repo"] == "ggerganov/whisper.cpp" and m["file"].endswith(".bin") for m in cat), "all from ggerganov/whisper.cpp, ggml files")
check(all(re.fullmatch(r"[0-9a-f]{64}", m.get("sha256") or "") for m in cat), "every voice model's SHA-256 is pinned in the catalogue")
base = voice.voice_by_id("base")
check(base and base.get("shipped") and len(base["sha256"]) == 64, "Base ships with the OS and is pinned by SHA-256")
check(json.load(open(os.path.join(SRC_SHARE, "voice-catalog.json")))[3]["file"] == "ggml-large-v3-turbo-q5_0.bin",
      "the best model is Whisper large-v3-turbo (q5_0)")

print("forgiving names")
for said, want in (("turbo", "turbo"), ("large v3 turbo", "turbo"), ("the best", "turbo"), ("most accurate", "turbo"),
                   ("whisper small", "small"), ("fastest", "tiny"), ("Base", "base"), ("nonsense", None)):
    got = voice.voice_by_id(said)
    check((got["id"] if got else None) == want, f"'{said}' -> {want}")

print("what is in use")
check(voice.active_voice()["id"] == "base", "with nothing chosen, Base is used")
config.settings.set("voice_model", "turbo")
check(voice.active_voice()["id"] == "base", "the chosen model is not downloaded yet -> falls back to Base")
check(voice.model_path().endswith("/voice/ggml-base.bin"), "model_path points at the shipped Base file")
try:
    voice.use_voice("turbo")
    check(False, "switching to a model that is not downloaded is refused")
except ValueError:
    check(True, "switching to a model that is not downloaded is refused")

# pretend Turbo was downloaded (the real download verifies its SHA-256 first)
os.makedirs(voice.VOICE_DIR_DL, exist_ok=True)
open(os.path.join(voice.VOICE_DIR_DL, "ggml-large-v3-turbo-q5_0.bin"), "wb").write(b"turbo")
check({m["id"] for m in voice.installed_voice()} == {"base", "turbo"}, "Base and the downloaded Turbo are installed")
check(voice.use_voice("turbo")["id"] == "turbo" and voice.active_voice()["id"] == "turbo", "use_voice switches to Turbo")
check(voice.model_path().endswith("ggml-large-v3-turbo-q5_0.bin"), "transcription now uses the Turbo file")

print("removing")
try:
    voice.remove_voice("base")
    check(False, "the shipped Base cannot be removed")
except ValueError:
    check(True, "the shipped Base cannot be removed (it is the fallback)")
voice.remove_voice("turbo")
check(voice.active_voice()["id"] == "base" and config.settings.get("voice_model") == "base", "removing the active model falls back to Base")

print("dictated text is clean")
for raw, want in (("[BLANK_AUDIO]", ""), (" Hello there. [MUSIC] ", "Hello there."), ("(music) Buy milk.", "Buy milk."),
                  ("Call  Sam\n tomorrow", "Call Sam tomorrow"), ("[ Silence ]", "")):
    check(voice.clean_transcript(raw) == want, f"{raw!r} -> {want!r}")

print("typing is a safe no-op without a Wayland session")
check(voice.type_text("hello") is False, "no WAYLAND_DISPLAY: type_text does nothing and says so")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
