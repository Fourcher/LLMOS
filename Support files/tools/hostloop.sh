#!/bin/bash
# hostloop.sh: run every host test (tools/test-*.py) from "Support files/".
# Tells real failures apart from macOS /Volumes outages, where access to
# /Volumes/Files is refused for about a minute.
#
# Usage: bash tools/hostloop.sh [--skip <name>]...
#   --skip <name>  skip a known flake (basename such as test-foo.py, or the path)
# Env:   HOSTLOOP_SLEEP  seconds between outage waits (default 30)
#
# Exit: 1 if any test failed on its re-run, 2 if only outages, else 0.

SLEEP_S="${HOSTLOOP_SLEEP:-30}"
SKIPS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --skip)
      if [ -z "$2" ]; then echo "HOSTLOOP: --skip needs a name"; exit 3; fi
      SKIPS+=("$2"); shift 2 ;;
    *) echo "HOSTLOOP: unknown argument $1"; exit 3 ;;
  esac
done

is_skipped() {
  local t="$1" s
  for s in ${SKIPS[@]+"${SKIPS[@]}"}; do
    if [ "$s" = "$t" ] || [ "$s" = "$(basename "$t")" ]; then return 0; fi
  done
  return 1
}

# run_test <file> <stderr-file>; returns the test's exit status
run_test() {
  python3 "$1" >/dev/null 2>"$2" </dev/null
  return $?
}

n=0; f=0; o=0
ERRF="$(mktemp)"
trap 'rm -f "$ERRF"' EXIT
for t in tools/test-*.py; do
  [ -e "$t" ] || continue
  if is_skipped "$t"; then continue; fi
  n=$((n + 1))
  run_test "$t" "$ERRF"
  if [ $? -eq 0 ]; then continue; fi

  if [ ! -r "$t" ] || grep -q "Operation not permitted" "$ERRF"; then
    # Outage: wait until the file is readable and the tree answers a probe,
    # up to 6 steps of SLEEP_S, then re-run once.
    waited=0
    while { [ ! -r "$t" ] || ! ls tools >/dev/null 2>&1; } && [ "$waited" -lt 6 ]; do
      sleep "$SLEEP_S"
      waited=$((waited + 1))
    done
  fi

  # Flake check: one re-run (immediate, or after an outage wait).
  run_test "$t" "$ERRF"
  if [ $? -eq 0 ]; then continue; fi
  if [ ! -r "$t" ] || grep -q "Operation not permitted" "$ERRF"; then
    echo "OUTAGE $t"
    o=$((o + 1))
  else
    echo "FAIL $t"
    f=$((f + 1))
  fi
done

echo "HOSTLOOP: $n run, $f failed, $o outage"
if [ "$f" -gt 0 ]; then exit 1; fi
if [ "$o" -gt 0 ]; then exit 2; fi
exit 0
