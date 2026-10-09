#!/bin/bash
# Build a complete, current release into dist/ — the one way to make dist/ match the OS source.
#   tools/release.sh                 build both images, both ISOs, checksums, RELEASE.json
#   tools/release.sh arm64|x86       build just that architecture's image + ISO (skip the other)
#   tools/release.sh [arch] --smoke  also run the dictation + live-ISO smokes on the fresh artifacts
#
# After this, `tools/check-fresh.py` reports FRESH. Run it whenever the OS source (src/) changes; changes under
# dist/setup/ or tools/ do not need it. The images/ISOs are build outputs, not source (they are gitignored).
set -euo pipefail
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
SMOKE=0; ARCH=all
for a in "$@"; do case "$a" in
  --smoke) SMOKE=1 ;; arm64|x86|all) ARCH="$a" ;;
  *) echo "usage: tools/release.sh [all|arm64|x86] [--smoke]"; exit 2 ;;
esac; done
step() { printf '\n==== %s (%s) ====\n' "$1" "$(date +%H:%M:%S)"; }

# Pre-check before any build: VERSION and __init__.py must agree (install.sh stamps the image from one,
# build-iso.sh and release-json.py read the other). Abort here rather than ship mismatched artifacts.
if ! python3 tools/test-version.py; then
    echo "ABORT: version mismatch between VERSION and src/rootfs/usr/lib/llmos/llmos/__init__.py. Fix it, then re-run." >&2
    exit 1
fi

if [ "$ARCH" = all ] || [ "$ARCH" = arm64 ]; then
    step "arm64 image"; tools/build-image.sh
    step "arm64 ISO";   tools/build-iso.sh arm64
fi
if [ "$ARCH" = all ] || [ "$ARCH" = x86 ]; then
    step "x86-64 image"; tools/build-image-x86.sh   # fetches + verifies the signed boot chain first
    step "x86-64 ISO";   tools/build-iso.sh x86
fi

step "checksums + manifest (authoritative, over whatever is in dist/)"
( cd dist && shasum -a 256 *.qcow2 *.iso models/*.gguf 2>/dev/null > SHA256SUMS )
python3 tools/release-json.py
( cd dist && shasum -a 256 -c SHA256SUMS )

if [ "$SMOKE" = 1 ]; then
    step "dictation smoke (arm64)"; tools/dictate-smoke.sh arm64 | tail -3
    python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null || true
    step "live-ISO smoke (arm64)";  tools/isosmoke.sh arm64 | tail -4
    python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null || true
fi

step "freshness"; python3 tools/check-fresh.py
step "done"; tools/cleanup.sh >/dev/null 2>&1 || true
echo "dist/ is current. (tools/check-fresh.py confirms; run it any time.)"
