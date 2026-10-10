#!/bin/bash
# realrun-nightly.sh: run ONE task suite per night as a real user in a fresh test VM,
# then triage the failures into docs/tasks/queue.md. The VM is always quit on exit.
#   usage: tools/realrun-nightly.sh --run [suite.json]   (no argument: the nightly rotation)
#   without --run: print the chosen suite path and exit 0, no boot
#   NIGHTLY_DRY=1          print the chosen suite path and exit 0, no boot (same as no --run)
#   NIGHTLY_DATE=YYYY-MM-DD  use this date instead of today (tests)
# Output: run/realrun-nightly/<YYYY-MM-DD>/ (records) and .../triage (bundles)
set -u

# -h/--help anywhere in the arguments: print usage and exit before anything else
for a in "$@"; do
  case "$a" in
    -h|--help)
      echo "usage: realrun-nightly.sh [--run] [suite.json]"
      echo "  --run boots the nightly test VM and runs the suite; without it only the chosen suite path is printed"
      echo "  NIGHTLY_DRY=1 prints the chosen suite path and exits (no boot)"
      echo "  NIGHTLY_DATE=YYYY-MM-DD uses this date instead of today (tests)"
      exit 0 ;;
  esac
done

# --run is required to boot; without it the script only prints the chosen suite
RUN=0
if [ "${1:-}" = "--run" ]; then RUN=1; shift; fi

# resolve a suite argument before leaving the caller's directory
ARG=""
if [ $# -ge 1 ]; then
  ARG=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1") || exit 1
fi
cd "$(dirname "$0")/.." || exit 1

TODAY=${NIGHTLY_DATE:-$(date +%Y-%m-%d)}

# 1. choose the suite: fixed rotation over tools/tasks/*.json (schema files excluded)
if [ -n "$ARG" ]; then
  SUITE=$ARG
else
  SUITE=$(python3 -c '
import datetime, glob, os, sys
today = datetime.date.fromisoformat(sys.argv[1])
files = sorted(p for p in glob.glob(os.path.join("tools", "tasks", "*.json"))
               if "schema" not in os.path.basename(p).lower())
if not files:
    sys.exit(1)
print(files[((today - datetime.date(2026, 1, 1)).days) % len(files)])
' "$TODAY") || { echo "no suite files in tools/tasks"; exit 1; }
fi
if [ ! -f "$SUITE" ]; then
  echo "no such suite: $SUITE"
  exit 1
fi
if [ "${NIGHTLY_DRY:-0}" = 1 ]; then
  echo "$SUITE"
  exit 0
fi
if [ "$RUN" != 1 ]; then
  echo "add --run to boot the nightly test VM"
  echo "$SUITE"
  exit 0
fi

# 2. time guard: estimate from tasklib (sum of timeout_s x 0.4), refuse before booting
MINUTES=$(python3 -c '
import math, sys
sys.path.insert(0, "tools")
import tasklib
print(math.ceil(tasklib.estimate_minutes(tasklib.load(sys.argv[1])["tasks"])))
' "$SUITE") || { echo "suite does not load: $SUITE"; exit 1; }
if [ "$MINUTES" -gt 170 ]; then
  echo "suite too long: $SUITE estimates $MINUTES min (limit 170), not booting"
  exit 2
fi

OUT="run/realrun-nightly/$TODAY"
mkdir -p "$OUT" || exit 1

# 3. the VM is always quit when this script ends, whatever happened
quit_vm() {
  python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null || true
}
trap quit_vm EXIT

# 4. boot the target in test-shell mode and wait (max 300 s) for the shell to answer
env LLMOS_TESTSHELL=1 /bin/bash tools/boot-target.sh dist/llmos-arm64.qcow2 4096 || { echo "boot failed"; exit 3; }
UP=0
DEADLINE=$(( $(date +%s) + 300 ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  UP_OUT=$(tools/tsh "echo up" 30 2>/dev/null)
  if printf '%s\n' "$UP_OUT" | grep -qx 'up'; then UP=1; break; fi
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "boot never came up within 300 s"
  exit 3
fi

# 5. onboard (same command as tools/calc-smoke.sh line 21)
ONBOARD='cd /usr/lib/llmos && python3 -c "from llmos import config; config.settings.set(\"onboarded\", True)"; cd /; sleep 25; llmos desk-state | grep -o "\"screen\": \"[a-z]*\""'
tools/tsh "$ONBOARD" 120 || true

# 6. run the suite once as a real user, then triage whatever failed
python3 tools/realrun.py "$SUITE" --run --outdir "$OUT" --repeat 1
RR=$?
python3 tools/triage.py "$OUT" --suite "$SUITE" --out "$OUT/triage" --queue docs/tasks/queue.md || true
echo "realrun-nightly: suite $SUITE exit $RR, output $OUT"
exit $RR
