#!/bin/bash
# Build dist/llmos-<arch>.iso (live + installer) from the shipped image:
# boot the image on a throw-away overlay with a blank raw "output" disk
# attached, run src/live/mkiso.sh inside, then trim the output disk to the
# ISO's declared size. arm64 builds under HVF in a few minutes; x86-64 is
# emulated and takes longer.
#   usage: tools/build-iso.sh [arm64|x86]      (default arm64)
set -eu
cd "/Volumes/Files/Claude Work Area/LLMOS"
A=${1:-arm64}; VER=$(cat VERSION)
case "$A" in
    arm64) IMG=dist/llmos-arm64.qcow2; ARCH=aarch64; OUT=dist/llmos-arm64.iso; SER=run/tser.sock; LOG=run/boot-serial.log; MON=run/tmon.sock ;;
    x86)   IMG=dist/llmos-x86_64.qcow2; ARCH=x86_64; OUT=dist/llmos-x86_64.iso; SER=run/yser.sock; LOG=run/x86-boot.log; MON=run/ymon.sock ;;
    *) echo "usage: $0 [arm64|x86]"; exit 2 ;;
esac
RAW=run/iso-out-$A.qcow2
rm -f "$RAW"; qemu-img create -q -f qcow2 "$RAW" 8G      # grows only with what is written
V="python3 tools/vmctl.py"
echo "==> booting $IMG with the output disk attached"
if [ "$A" = arm64 ]; then
    LLMOS_TESTSHELL=1 LLMOS_EXTRA_DRIVE="$RAW" tools/boot-target.sh "$IMG" 4096 >/dev/null
else
    LLMOS_TESTSHELL=1 LLMOS_EXTRA_DRIVE="$RAW" tools/boot-x86.sh bios >/dev/null
fi
$V wait "$LOG" 'LLM OS test shell' 600 >/dev/null && echo "  -> test shell up"
# the three live files travel over the serial line (base64, small): the image may predate them
python3 - "$SER" "$LOG" <<'PY'
import base64, subprocess, sys
ser, log = sys.argv[1], sys.argv[2]
subprocess.run(["python3", "tools/vmctl.py", "run", ser, log, "mkdir -p /tmp/live; echo MK", "^MK", "30", "--quiet", "1"], capture_output=True)
for name in ("init", "grub.cfg", "mkiso.sh"):
    b = base64.b64encode(open(f"src/live/{name}", "rb").read()).decode()
    for i in range(0, len(b), 600):
        subprocess.run(["python3", "tools/vmctl.py", "run", ser, log, f"printf %s '{b[i:i+600]}' >> /tmp/live/{name}.b64; echo OK_{i}", f"^OK_{i}", "30", "--quiet", "1"], capture_output=True)
    subprocess.run(["python3", "tools/vmctl.py", "run", ser, log, f"base64 -d /tmp/live/{name}.b64 > /tmp/live/{name}; rm /tmp/live/{name}.b64; wc -c /tmp/live/{name}", "^[0-9]+ /tmp", "30", "--quiet", "1"], capture_output=True)
PY
echo "==> building the ISO inside the VM (version $VER, $ARCH)"
python3 tools/vmctl.py run "$SER" "$LOG" "sh /tmp/live/mkiso.sh $VER $ARCH 2>&1 | tail -40; echo DONE_\"\"ISO" "^DONE_ISO" 5400 --quiet 1 | grep -vE '^\s*$' | tail -30
BYTES=$(tail -c 20000 "$LOG" | tr -d '\r' | grep -ao 'ISO_BYTES=[0-9]*' | tail -1 | cut -d= -f2)
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 2
if [ -z "$BYTES" ]; then echo "!! mkiso did not report a size; check $LOG"; exit 1; fi
echo "==> extracting the ISO ($BYTES bytes) from the output disk"
qemu-img convert -O raw "$RAW" "$RAW.raw" && rm -f "$RAW"
python3 - "$RAW.raw" "$BYTES" "$OUT" <<'PY'
import os, struct, sys
raw, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
with open(raw, "rb") as f:
    f.seek(32768); pvd = f.read(2048)
assert pvd[1:6] == b"CD001", "not an ISO9660 image on the output disk"
blocks = struct.unpack("<I", pvd[80:84])[0]
assert blocks * 2048 == n, (blocks * 2048, n)
with open(raw, "rb") as src, open(out, "wb") as dst:
    remaining = n
    while remaining:
        chunk = src.read(min(16 << 20, remaining)); dst.write(chunk); remaining -= len(chunk)
os.remove(raw)
print(f"{out}: {n} bytes")
PY
(cd dist && shasum -a 256 "$(basename "$OUT")" >> SHA256SUMS && sort -u -k2 SHA256SUMS -o SHA256SUMS)
echo "==> done: $OUT"
