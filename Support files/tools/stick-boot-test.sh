#!/bin/bash
# End-to-end test of a USB stick made by LLM OS Setup, with no real stick involved:
#   1. a disk-image file attached as a raw block device (/dev/diskN, like a stick) stands in for the stick
#   2. Setup writes the real x86-64 image onto it through its own web API (fake-authopen stands in for the
#      macOS password prompt), checking the image against dist/SHA256SUMS first and the stick afterwards
#   3. a virtual PC (QEMU, x86-64, UEFI or BIOS firmware) starts from that disk plugged in as a USB stick, and
#      the test checks LLM OS came up running live from the USB medium
#   secureboot: UEFI with Secure Boot enforced and Microsoft's keys enrolled (Debian's OVMF build), as on an
#   ordinary Windows PC; the test also checks the kernel came up locked down by Secure Boot.
# usage: tools/stick-boot-test.sh [uefi|bios|secureboot]
set -u
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
MODE=${1:-uefi}; FW=/opt/homebrew/share/qemu; V="python3 tools/vmctl.py"
SER=run/sser.sock; LOG=run/stick-boot.log; MON=run/smon.sock; PID=run/sticktest.pid
fail() { echo "!! $*"; cleanup; exit 1; }
cleanup() {
  python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null
  [ -n "${SETUP_PID:-}" ] && kill "$SETUP_PID" 2>/dev/null
  sleep 1; [ -n "${RAM:-}" ] && hdiutil detach "$RAM" -quiet 2>/dev/null
  rm -f "${IMG:-}"
}
mkdir -p run
SIZE=$(stat -f %z dist/llmos-x86_64.iso)
IMG=run/stick.img; rm -f "$IMG"
mkfile -n $(( SIZE / 1048576 + 128 ))m "$IMG"      # sparse: the image plus 128 MiB
RAM=$(hdiutil attach -imagekey diskimage-class=CRawDiskImage -nomount "$IMG" 2>/dev/null | awk 'NR==1{print $1}')
[ -b "$RAM" ] || fail "couldn't attach the stand-in stick"
echo "==> stand-in stick: $RAM ($(( SIZE / 1048576 + 128 )) MiB, backed by $IMG)"

echo "==> Setup writes dist/llmos-x86_64.iso onto it"
OUT=$(mktemp)
LLMOS_SETUP_NO_BROWSER=1 LLMOS_SETUP_TEST_DEVICE="${RAM/disk/rdisk}" LLMOS_SETUP_TEST_SIZE=16000000000 \
  LLMOS_SETUP_AUTHOPEN="$PWD/tools/fake-authopen.py" python3 dist/setup/llmos-setup.py > "$OUT" 2>&1 &
SETUP_PID=$!
for _ in $(seq 1 50); do grep -q "paste this address" "$OUT" && break; sleep 0.2; done
URL=$(grep -oE "http://127\.0\.0\.1:[0-9]+/#[^)]+" "$OUT" | head -1); BASE=${URL%%/#*}; TOKEN=${URL##*#}
[ -n "$TOKEN" ] || fail "Setup did not start: $(cat "$OUT")"
api() { curl -s -H "X-LLMOS-Token: $TOKEN" ${2:+-H "Content-Type: application/json" -d "$2"} "$BASE$1"; }
api /api/write '{"drive":"test"}' | grep -q '"ok": true' || fail "write refused: $(api /api/write '{"drive":"test"}')"
t0=$(date +%s); last=""
while :; do
  st=$(api /api/progress); ph=$(echo "$st" | python3 -c "import json,sys; print(json.load(sys.stdin)['phase'])")
  [ "$ph" != "$last" ] && echo "    $ph ($(( $(date +%s) - t0 )) s)"; last=$ph
  case "$ph" in done) break ;; error|cancelled) fail "write ended: $st" ;; esac
  [ $(( $(date +%s) - t0 )) -gt 1800 ] && fail "write took too long"
  sleep 1
done
{ kill "$SETUP_PID"; wait "$SETUP_PID"; } 2>/dev/null; SETUP_PID=""
echo "==> written and read back in $(( $(date +%s) - t0 )) s"
hdiutil detach "$RAM" -quiet; RAM=""

echo "==> a virtual PC ($MODE firmware) starts from it as a USB stick"
rm -f "$LOG"; FWARGS=""
MACHINE=q35
if [ "$MODE" = uefi ]; then
  rm -f run/stick-vars.fd; cp $FW/edk2-i386-vars.fd run/stick-vars.fd
  FWARGS="-drive if=pflash,format=raw,readonly=on,file=$FW/edk2-x86_64-code.fd -drive if=pflash,format=raw,file=run/stick-vars.fd"
elif [ "$MODE" = secureboot ]; then
  [ -f build/cache/ovmf/OVMF_CODE_4M.secboot.fd ] || tools/fetch-secureboot.sh >/dev/null
  rm -f run/stick-vars.fd; cp build/cache/ovmf/OVMF_VARS_4M.ms.fd run/stick-vars.fd
  MACHINE=q35,smm=on
  FWARGS="-global driver=cfi.pflash01,property=secure,value=on -drive if=pflash,format=raw,unit=0,readonly=on,file=build/cache/ovmf/OVMF_CODE_4M.secboot.fd -drive if=pflash,format=raw,unit=1,file=run/stick-vars.fd"
fi
qemu-system-x86_64 -machine $MACHINE -accel tcg,thread=multi -cpu max -smp 4 -m 3072 $FWARGS \
  -device qemu-xhci,id=xhci -drive if=none,id=stick,file="$IMG",format=raw -device usb-storage,bus=xhci.0,drive=stick,bootindex=1 \
  -nic user,model=virtio-net-pci -device virtio-vga -audiodev none,id=snd0 \
  -fw_cfg name=opt/llmos/tz,string=America/Phoenix -fw_cfg name=opt/llmos/testshell,string=1 \
  -display none -monitor unix:$MON,server=on,wait=off \
  -chardev socket,id=ser0,path=$SER,server=on,wait=off,logfile="$PWD/$LOG",logappend=on -serial chardev:ser0 \
  -daemonize -pidfile $PID || fail "qemu did not start"
t0=$(date +%s)
$V wait "$LOG" 'LLM OS test shell' 1200 >/dev/null || { tail -c 2000 "$LOG" | tr -d '\r' | tail -15; fail "no LLM OS within 1200 s"; }
echo "==> LLM OS up after $(( $(date +%s) - t0 )) s"
$V run "$SER" "$LOG" 'echo "live medium: $(grep " /run/live " /proc/mounts | cut -d" " -f1-3)"; echo "medium bus: $(for d in /sys/block/sd*; do [ -e "$d" ] && echo "$(basename $d) $(readlink -f $d | grep -o usb[0-9]* | head -1)"; done | tr "\n" " ")"; grep -E "^(VERSION|MEDIUM)=" /etc/llmos-release; echo "firmware: $([ -d /sys/firmware/efi ] && echo UEFI || echo BIOS)"; echo "secure boot: $(dmesg | grep -o "Secure boot enabled" | head -1 || true)$(dmesg | grep -qi "secure boot disabled" && echo disabled)"; echo "lockdown: $(cat /sys/kernel/security/lockdown 2>/dev/null)"; echo "kernel: $(uname -r)"; echo STICK_""CHECK' '^STICK_CHECK' 240 --quiet 1 \
  | tr -d '\r' | grep -E '^(live medium|medium bus|firmware|secure boot|lockdown|kernel):|^(VERSION|MEDIUM)='
cleanup
echo "==> done"
