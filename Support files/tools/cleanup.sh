#!/bin/bash
# Tidy up after building and testing. Nothing here touches source or the shipped images/ISOs in dist/.
#   tools/cleanup.sh            stop test VMs + helpers, drop scratch disks and test artifacts (screenshots,
#                               logs, overlays). Safe and fast; everything here regenerates on the next run.
#   tools/cleanup.sh --models   also remove model files kept only for evaluation (big, re-downloadable),
#                               keeping the default model the build and smokes need.
#   tools/cleanup.sh --cache    also empty build/cache (the Alpine ISOs + model fetch cache); the next build
#                               re-downloads them.
#   tools/cleanup.sh --dist     also drop the built images/ISOs in dist/ (reclaimable; tools/release.sh
#                               rebuilds them). The small tracked files (RELEASE.json, catalog, setup) stay.
#   tools/cleanup.sh --all      --models, --cache and --dist together.
set -u
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
MODELS=0; CACHE=0; DIST=0
for a in "$@"; do case "$a" in
  --models) MODELS=1 ;; --cache) CACHE=1 ;; --dist) DIST=1 ;; --all) MODELS=1; CACHE=1; DIST=1 ;;
  *) echo "unknown option: $a"; exit 2 ;;
esac; done


# stop any test VMs and helper processes this project started
for s in tmon ymon bmon xmon; do
  python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/$s.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null && echo "stopped VM on $s"
done
sleep 2
for p in run/host-model-8080.pid run/host-model-8081.pid run/httpd.pid run/llama.pid run/llama-exp.pid run/fake-mic.pid run/isotest.pid run/x86test.pid run/build.pid run/xbuild.pid; do
  [ -f "$p" ] && kill "$(cat "$p")" 2>/dev/null && echo "stopped $(basename "$p" .pid)"; rm -f "$p"
done
left=$(pgrep -fl 'qemu-system|llama-server|mic-bridge|http.server 8765' | cut -c1-70)
[ -n "$left" ] && echo "still running (stop by hand if unexpected):" && echo "$left"

# scratch disks + test artifacts (keep run/origin.git — the local git remote — and the test speech sample)
rm -f build/work/*.qcow2 build/work/*.tar build/work/*.log
find run -maxdepth 1 -type f \( -name '*.qcow2' -o -name '*.raw' -o -name '*.fd' -o -name '*.png' -o -name '*.ppm' \
  -o -name '*.log' -o -name '*.sock' -o -name '*.pid' \) -delete 2>/dev/null

if [ "$MODELS" = 1 ]; then
  keep_model=""; keep_whisper=""
  [ -f src/rootfs/usr/share/llmos/preinstall.env ] && . src/rootfs/usr/share/llmos/preinstall.env && keep_model="$MODEL_FILE" && keep_whisper="$WHISPER_FILE"
  echo "keeping the default model ($keep_model) and voice model ($keep_whisper); removing evaluation-only models"
  for f in models/*.gguf; do [ -f "$f" ] && [ "$(basename "$f")" != "$keep_model" ] && rm -f "$f" && echo "  removed $f"; done
  rm -f models/server-*.log models/fetch.log models/fetch.txt
  for f in build/cache/*.gguf; do [ -f "$f" ] && [ "$(basename "$f")" != "$keep_model" ] && rm -f "$f" && echo "  removed $f"; done
fi
if [ "$DIST" = 1 ]; then
  rm -f dist/*.qcow2 dist/*.iso
  echo "dropped the built images/ISOs from dist/ (rebuild with tools/release.sh)"
fi
if [ "$CACHE" = 1 ]; then
  rm -f build/cache/*.iso build/cache/*.gguf build/cache/*.bin build/cache/x86iso build/cache/*.sha256
  echo "emptied build/cache (re-downloaded on the next build)"
fi

echo "sizes now:"; du -sh dist build models run 2>/dev/null
echo "reclaimable: models eval files $(du -sh models 2>/dev/null | cut -f1) (tools/cleanup.sh --models), build cache $(du -sh build/cache 2>/dev/null | cut -f1) (--cache)"
