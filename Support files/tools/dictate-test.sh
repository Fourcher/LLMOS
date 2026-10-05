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
want="Please remember to water the plants on Thursday."
rm -f /tmp/typed.txt /tmp/preenter.txt
foot -a dictate-target sh -c 'read -r line; printf "%s\n" "$line" > /tmp/typed.txt' &
sleep $((4 * ${SLOW:-1}))
llmos dictate
sleep ${SLOW:-1}
# nothing must have run yet: dictation types the words but never presses Enter (so a terminal does not run them)
cp -f /tmp/typed.txt /tmp/preenter.txt 2>/dev/null || true
[ -s /tmp/preenter.txt ] && { echo "FAIL: a line was entered before Return was pressed"; exit 1; }
wtype -k Return
sleep $((2 * ${SLOW:-1}))
got=$(cat /tmp/typed.txt 2>/dev/null || echo NOTHING)
echo "TYPED_INTO_TERMINAL: $got"
[ "$got" = "$want" ] || { echo "FAIL: typed text does not match what was spoken (wanted: $want)"; exit 1; }
echo "DICTATE_OK"
