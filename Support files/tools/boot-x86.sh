#!/bin/bash
# Boot the x86-64 image under QEMU's emulation for testing, either with
# SeaBIOS (default) or UEFI (OVMF).  usage: tools/boot-x86.sh [bios|uefi] [image]
# Console on run/yser.sock, monitor on run/ymon.sock, log run/x86-boot.log.
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
MODE=${1:-bios}
IMG=${2:-dist/llmos-x86_64.qcow2}
FW=/opt/homebrew/share/qemu
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/ymon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 1
rm -f run/x86-boot.log run/x86-overlay.qcow2
# test on a throwaway overlay so the shipped image stays pristine
qemu-img create -f qcow2 -b "$(cd "$(dirname "$IMG")" && pwd)/$(basename "$IMG")" -F qcow2 run/x86-overlay.qcow2 >/dev/null
# host-GPU mode test (same fw_cfg keys as the launcher): LLMOS_HOSTGPU_URL=http://10.0.2.2:8080
HOST_ARGS=""
[ -n "${LLMOS_HOSTGPU_URL:-}" ] && HOST_ARGS="-fw_cfg name=opt/llmos/model_url,string=$LLMOS_HOSTGPU_URL -fw_cfg name=opt/llmos/model_id,string=${LLMOS_HOSTGPU_ID:-ministral-3-3b}"
# LLMOS_TESTSHELL=1: plain root shell on the serial line; LLMOS_EXTRA_DRIVE=file.qcow2: a second disk
[ "${LLMOS_TESTSHELL:-0}" = 1 ] && HOST_ARGS="$HOST_ARGS -fw_cfg name=opt/llmos/testshell,string=1"
# LLMOS_MIC=1: the launcher's microphone bridge is this computer's microphone (tools/fake-mic-bridge.py)
[ "${LLMOS_MIC:-0}" = 1 ] && HOST_ARGS="$HOST_ARGS -fw_cfg name=opt/llmos/mic,string=1"
[ -n "${LLMOS_EXTRA_DRIVE:-}" ] && HOST_ARGS="$HOST_ARGS -drive file=$LLMOS_EXTRA_DRIVE,format=qcow2,if=virtio"
FWARGS=""
if [ "$MODE" = uefi ]; then
    rm -f run/x86-vars.fd; cp $FW/edk2-i386-vars.fd run/x86-vars.fd
    FWARGS="-drive if=pflash,format=raw,readonly=on,file=$FW/edk2-x86_64-code.fd -drive if=pflash,format=raw,file=run/x86-vars.fd"
fi
# shellcheck disable=SC2086
qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072 $FWARGS \
  -drive file=run/x86-overlay.qcow2,format=qcow2,if=virtio \
  -nic user,model=virtio-net-pci \
  -device virtio-vga -device virtio-keyboard-pci -device virtio-tablet-pci \
  -audiodev none,id=snd0 -device intel-hda -device hda-duplex,audiodev=snd0 \
  -fw_cfg name=opt/llmos/tz,string=America/Phoenix $HOST_ARGS \
  -display none -monitor unix:run/ymon.sock,server=on,wait=off \
  -chardev socket,id=ser0,path=run/yser.sock,server=on,wait=off,logfile="$PWD/run/x86-boot.log",logappend=on -serial chardev:ser0 \
  -daemonize -pidfile run/x86test.pid && echo "x86 test VM ($MODE) pid $(cat run/x86test.pid)"
tools/vm-lifetime.sh run/x86test.pid
