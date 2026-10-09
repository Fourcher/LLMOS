#!/bin/bash
# timed-sweep.sh: boot the target VM in test-shell mode, send each owner phrase
# to the assistant, time each reply, write run/timed-sweep.tsv, then stop the VM.
# usage: tools/timed-sweep.sh PHRASES_FILE [IMG]
set -u

PHRASES_FILE=${1:?usage: tools/timed-sweep.sh PHRASES_FILE [IMG]}
case "$PHRASES_FILE" in /*) ;; *) PHRASES_FILE="$PWD/$PHRASES_FILE" ;; esac
[ -f "$PHRASES_FILE" ] || { echo "no such phrases file: $PHRASES_FILE"; exit 2; }
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files" || exit 1
IMG=${2:-dist/llmos-arm64.qcow2}
mkdir -p run

# Stop the VM on any exit.
stop_vm() { python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null || true; }

LLMOS_TESTSHELL=1 tools/boot-target.sh "$IMG" 4096
trap stop_vm EXIT

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

TSV="run/timed-sweep.tsv"
printf 'n\tseconds\tphrase\treply\n' > "$TSV"

n=0
while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in
        ''|'#'*) continue ;;
    esac
    n=$((n + 1))
    phrase="$line"
    esc=$(printf '%s' "$phrase" | sed 's/"/\\"/g')

    # Reset the assistant's conversation state before each phrase.
    R "llmos desk-ctl testreset >/dev/null 2>&1; true" "Z$n" 30 >/dev/null

    t0=$(date +%s)
    reply=$(R "llmos say \"$esc\" | grep -o '\"reply\": \"[^\"]*\"'" "S$n" 240)
    t1=$(date +%s)
    secs=$((t1 - t0))

    reply=$(printf '%s' "$reply" | tr '\t\r\n' '   ' | cut -c1-300)
    printf '%s\t%s\t%s\t%s\n' "$n" "$secs" "$phrase" "$reply" >> "$TSV"
    echo "[$n] ${secs}s  $phrase"
done < "$PHRASES_FILE"

# Summary.
rows=$(tail -n +2 "$TSV" | grep -c .)
fast=$(tail -n +2 "$TSV" | awk -F'\t' '$2<=3' | grep -c .)
slow=$(tail -n +2 "$TSV" | awk -F'\t' '$2>3' | grep -c .)
echo "timed-sweep: $rows phrase(s), $fast took <=3 s, $slow took >3 s"
echo "phrases over 3 s, slowest first:"
tail -n +2 "$TSV" | awk -F'\t' '$2>3' | sort -t$'\t' -k2,2nr | cut -f1-3 | sed 's/^/  /'
echo "results: $TSV"

exit 0
