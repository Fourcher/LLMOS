#!/bin/bash
# Run the host test suites without touching anything outside this project.
# The OS code reads the owner's home (config.home() = $LLMOS_HOME or ~). On the Mac that would be the real
# home folder (Downloads, Music, iCloud Drive ...), so HOME, LLMOS_HOME and TMPDIR all point into run/ here.
#   tools/run-host-tests.sh                 # every tools/test-*.py
#   tools/run-host-tests.sh tools/test-x.py # just these
cd "$(dirname "$0")/.." || exit 1
SANDBOX="$PWD/run/testhome/run-$$"          # one per run: several check workers may run at once
rm -rf "$SANDBOX"; mkdir -p "$SANDBOX/tmp"
trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX" LLMOS_HOME="$SANDBOX" TMPDIR="$SANDBOX/tmp" XDG_CONFIG_HOME="$SANDBOX/.config" XDG_DATA_HOME="$SANDBOX/.local/share" XDG_CACHE_HOME="$SANDBOX/.cache"
[ $# -gt 0 ] && tests=("$@") || tests=(tools/test-*.py)
fail=0
for t in "${tests[@]}"; do
  if ! python3 -c 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[1:], timeout=300, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode)' python3 "$t"; then
    echo "FAIL $t"; fail=$((fail+1))
  fi
done
echo "host suites: ${#tests[@]} run, $fail failed"
[ $fail -eq 0 ]
