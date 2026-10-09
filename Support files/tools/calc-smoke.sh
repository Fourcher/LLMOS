#!/bin/bash
# calc-smoke.sh: boot the target VM in test-shell mode, drive the calculator
# through the assistant, check the replies and timings, then stop the VM.
set -u

cd "/Volumes/Files/Claude Work Area/LLMOS/Support files" || exit 1
IMG=${1:-dist/llmos-arm64.qcow2}

LLMOS_TESTSHELL=1 tools/boot-target.sh "$IMG" 4096

# Run a command in the VM test shell. The split "OK""tag" keeps the echoed
# command line from matching the expected OK<tag> marker.
R() { python3 tools/vmctl.py run run/tser.sock run/boot-serial.log "$1; echo \"OK\"\"$2\"" "OK$2" "${3:-120}" | tr -d '\r'; }

python3 tools/vmctl.py wait run/boot-serial.log 'test shell' 240 >/dev/null

# Wait for the desk socket.
R 'for i in $(seq 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done' W1 150 >/dev/null

# Finish onboarding without the wizard, then confirm the desk is up.
W2OUT=$(R 'cd /usr/lib/llmos && python3 -c "from llmos import config; config.settings.set(\"onboarded\", True)"; cd /; sleep 25; llmos desk-state | grep -o "\"screen\": \"[a-z]*\""' W2 90)
echo "$W2OUT"
if ! printf '%s' "$W2OUT" | grep -q '"screen": "desk"'; then
    echo "FAIL: desk not on desk screen"
    exit 1
fi

PHRASES=(
    "open the calculator"
    "press 7"
    "close the calculator"
    "open the calculator"
    "press 7 then + then 2 then ="
    "what does the calculator show?"
)

REPLIES=()
TIMES=()
n=0
for p in "${PHRASES[@]}"; do
    n=$((n + 1))
    t0=$(date +%s)
    reply=$(R "llmos say \"$p\" | grep -o '\"reply\": \"[^\"]*\"'" "S$n" 120)
    t1=$(date +%s)
    took=$((t1 - t0))
    echo "PHRASE: $p"
    echo "$reply"
    echo "  took ${took}s"
    REPLIES+=("$reply")
    TIMES+=("$took")
done

FAILS=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }

if [[ "${REPLIES[2]}" == *"Closed"* ]]; then
    pass "phrase 3 reply contains 'Closed'"
else
    fail "phrase 3 reply contains 'Closed'"
fi

if [[ "${REPLIES[4]}" == *"pressed ="* ]]; then
    pass "phrase 5 reply contains 'pressed ='"
else
    fail "phrase 5 reply contains 'pressed ='"
fi

if [[ "${REPLIES[5]}" == *"shows 9"* ]]; then
    pass "phrase 6 reply contains 'shows 9'"
else
    fail "phrase 6 reply contains 'shows 9'"
fi

slow=0
for t in "${TIMES[@]}"; do
    if [ "$t" -gt 20 ]; then slow=1; fi
done
if [ "$slow" -eq 0 ]; then
    pass "every phrase took <= 20 s"
else
    fail "every phrase took <= 20 s (times: ${TIMES[*]} s)"
fi

python3 tools/screendump.py run/tmon.sock run/calc-smoke.png

# Stop the VM.
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')"

if [ "$FAILS" -gt 0 ]; then
    echo "calc-smoke: $FAILS failure(s)"
    exit 1
fi
echo "calc-smoke: all good"
exit 0
