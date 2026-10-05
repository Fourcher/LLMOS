#!/bin/bash
# Test the zip tools/package.sh makes, the way someone receiving it would use it on a Mac: unzip it like Finder
# does (ditto), check the top level is just the three Start Here files and one folder, open Start Here (Mac), and
# check Setup comes up, verifies the USB image inside the unzipped copy against its checksum, and lists drives.
# usage: tools/test-package.sh [zip]   (default: build a fresh one in a temporary folder)
set -u
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
fails=0; ok() { echo "  ok   $*"; }; bad() { echo "  FAIL $*"; fails=$((fails + 1)); }
W=$(mktemp -d); trap 'pkill -f "$W/" 2>/dev/null; rm -rf "$W"' EXIT
ZIP=${1:-}
if [ -z "$ZIP" ]; then ZIP="$W/LLM OS.zip"; tools/package.sh "$ZIP" >/dev/null || { echo "!! packaging failed"; exit 1; }; fi
echo "unzipping $(basename "$ZIP") ($(du -h "$ZIP" | cut -f1)) like Finder does"
ditto -x -k "$ZIP" "$W/x" || { echo "!! unzip failed"; exit 1; }
TOP="$W/x/LLM OS"
got=$(cd "$TOP" && ls -1 | tr '\n' '|')
[ "$got" = "Start Here (Linux).sh|Start Here (Mac).command|Start Here (Windows).bat|Support files|" ] && ok "top level: three Start Here files and Support files" || bad "top level: $got"
[ -x "$TOP/Start Here (Mac).command" ] && [ -x "$TOP/Start Here (Linux).sh" ] && ok "the launchers are still executable after unzipping" || bad "launchers lost their executable bit"
grep -q $'\r$' "$TOP/Start Here (Windows).bat" && ok "the Windows launcher kept its Windows line endings" || bad "Windows line endings lost"
( cd "$TOP/Support files/dist" && shasum -a 256 -c SHA256SUMS >/dev/null 2>&1 ) && ok "both ISOs match their checksums" || bad "ISO checksum mismatch"

echo "opening Start Here (Mac) from the unzipped copy"
LOG="$W/setup.log"
LLMOS_SETUP_NO_BROWSER=1 TERM=dumb /bin/bash "$TOP/Start Here (Mac).command" < /dev/null > "$LOG" 2>&1 &
for _ in $(seq 1 75); do grep -q "paste this address" "$LOG" && break; sleep 0.2; done
URL=$(grep -oE "http://127\.0\.0\.1:[0-9]+/#[^)]+" "$LOG" | head -1); BASE=${URL%%/#*}; TOKEN=${URL##*#}
[ -n "$TOKEN" ] && ok "Setup is open" || { bad "Setup did not open: $(tail -3 "$LOG")"; exit 1; }
api() { curl -s -H "X-LLMOS-Token: $TOKEN" "$BASE$1"; }
state=""
for _ in $(seq 1 120); do
    state=$(api /api/status | python3 -c "import json,sys; print(json.load(sys.stdin)['usb']['state'])")
    [ "$state" = running ] || break; sleep 0.5
done
[ "$state" = ok ] && ok "Setup verified the USB image in the unzipped copy against its checksum" || bad "image state: $state"
api /api/drives | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if 'drives' in d else 1)" && ok "Setup lists USB drives" || bad "no drive list"
curl -s -o /dev/null -w "%{http_code}" "$BASE/" | grep -q 200 && ok "the page loads" || bad "page"
[ $fails = 0 ] && echo "all good" || echo "$fails FAILED"
exit $fails
