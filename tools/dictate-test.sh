#!/bin/sh
# In-VM end-to-end test of system-wide dictation (fetched by tools/dictate-smoke.sh from the host). The host runs
# tools/fake-mic-bridge.py, so the OS's own recording path hears a real spoken sentence. A terminal that
# captures one typed line is focused; `llmos dictate` records, transcribes and types into it.
set -a; . /run/llmos/display.env; set +a
echo "wtype: $(command -v wtype || echo MISSING)"
echo "session: WAYLAND_DISPLAY=$WAYLAND_DISPLAY XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
python3 -c "import sys; sys.path.insert(0,'/usr/lib/llmos'); from llmos import voice; m=voice.active_voice(); print('voice model in use:', m and m['name'], '->', voice.model_path())"
echo "--- direct transcription of the test sentence (no typing)"
python3 -c "import sys; sys.path.insert(0,'/usr/lib/llmos'); from llmos import voice; print('heard:', repr(voice.transcribe('/tmp/dict-speech.wav', keep=True)))"
echo "--- dictation into a focused terminal"
rm -f /tmp/typed.txt
foot -a dictate-target sh -c 'read -r line; printf "%s\n" "$line" > /tmp/typed.txt' &
sleep 4
llmos dictate
sleep 1
wtype -k Return
sleep 2
echo "TYPED_INTO_TERMINAL: $(cat /tmp/typed.txt 2>/dev/null || echo NOTHING)"
