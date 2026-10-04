#!/bin/bash
# In-VM end-to-end test of system-wide dictation (Super+D). The host runs tools/fake-mic-bridge.py, which
# streams a real spoken sentence (made with macOS `say`) into the guest's own recording path at 10.0.2.2:8766;
# inside the VM a terminal that captures one typed line is focused, `llmos dictate` records, transcribes with
# the active whisper model and types into it through the compositor (wtype), and the captured line is read
# back. Leaves the VM running (quit via run/tmon.sock).
#   usage: tools/dictate-smoke.sh [image]        (needs run/dict-speech.wav: 16 kHz mono speech)
cd "/Volumes/Files/Claude Work Area/LLMOS"
IMG=${1:-dist/llmos-arm64.qcow2}
[ -f run/dict-speech.wav ] || { say -o /tmp/dict.aiff "Please remember to water the plants on Thursday." && \
    afconvert -f WAVE -d LEI16@16000 -c 1 /tmp/dict.aiff run/dict-speech.wav; }

echo "### dictation smoke $(date '+%H:%M:%S') on $IMG"
pkill -f "fake-mic-bridge.py" 2>/dev/null; sleep 0.5
nohup python3 tools/fake-mic-bridge.py run/dict-speech.wav --port 8766 > run/fake-mic.log 2>&1 &
echo $! > run/fake-mic.pid
curl -s -o /dev/null http://127.0.0.1:8765/src/install.sh || {
    nohup python3 -m http.server 8765 --bind 127.0.0.1 --directory "$PWD" > run/httpd.log 2>&1 & echo $! > run/httpd.pid; }
curl -s http://127.0.0.1:8081/health 2>/dev/null | grep -q ok || {
    nohup llama-server -m models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf --host 127.0.0.1 --port 8081 --jinja -c 16384 \
        --cache-type-k q8_0 --cache-type-v q8_0 > run/llama.log 2>&1 & echo $! > run/llama.pid
    for i in $(seq 1 30); do curl -s http://127.0.0.1:8081/health | grep -q ok && break; sleep 2; done; }
sleep 1; head -1 run/fake-mic.log

OFF=$(python3 tools/vmctl.py mark run/boot-serial.log 2>/dev/null || echo 0)
LLMOS_TESTSHELL=1 LLMOS_HOSTGPU_URL=http://10.0.2.2:8081 tools/boot-target.sh "$IMG" 4096 >/dev/null
# type nothing until this boot's own shell banner appears (the log keeps earlier boots too)
python3 tools/vmctl.py wait run/boot-serial.log 'LLM OS test shell' 300 --from "$OFF" >/dev/null && echo "--- test shell up"
echo "--- waiting for the desk session"
tools/tsh 'for i in $(seq 1 120); do [ -S /run/llmos/desk.sock ] && [ -f /run/llmos/display.env ] && break; sleep 2; done; echo "desk: $([ -S /run/llmos/desk.sock ] && echo up || echo DOWN)"; cat /run/llmos/display.env; cat /etc/llmos-release | head -2' 300
echo "--- the dictation test inside the VM"
tools/tsh 'cd /tmp && wget -qO dictate-test.sh http://10.0.2.2:8765/tools/dictate-test.sh && wget -qO dict-speech.wav http://10.0.2.2:8765/run/dict-speech.wav && sh /tmp/dictate-test.sh' 300
python3 tools/screendump.py run/tmon.sock run/shot-dictate.png >/dev/null 2>&1 && echo "[shot run/shot-dictate.png]"
echo "### done $(date '+%H:%M:%S')"
