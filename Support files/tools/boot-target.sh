#!/bin/bash
# Boot the built target disk headless for automated tests, with the same
# devices the user's launcher provides (virtio-gpu, virtio-sound, fw_cfg time
# zone) but no window and no host audio. Console on run/tser.sock, log in
# run/boot-serial.log.  usage: tools/boot-target.sh [image] [ram_mb]
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
IMG=${1:-build/work/target.qcow2}
RAM=${2:-4096}
CPUS=${LLMOS_CPUS:-4}
FW=/opt/homebrew/share/qemu
# host-GPU mode test: LLMOS_HOSTGPU_URL=http://10.0.2.2:8080 (a llama-server
# must already be listening on the Mac's 127.0.0.1:8080)
HOST_ARGS=""
[ -n "${LLMOS_HOSTGPU_URL:-}" ] && HOST_ARGS="-fw_cfg name=opt/llmos/model_url,string=$LLMOS_HOSTGPU_URL -fw_cfg name=opt/llmos/model_id,string=${LLMOS_HOSTGPU_ID:-ministral-3-3b}"
# LLMOS_TESTSHELL=1: the serial line is a plain root shell (tests drive the desk with `llmos say`)
[ "${LLMOS_TESTSHELL:-0}" = 1 ] && HOST_ARGS="$HOST_ARGS -fw_cfg name=opt/llmos/testshell,string=1"
# LLMOS_MIC=1: the launcher's microphone bridge is this computer's microphone (tools/fake-mic-bridge.py)
[ "${LLMOS_MIC:-0}" = 1 ] && HOST_ARGS="$HOST_ARGS -fw_cfg name=opt/llmos/mic,string=1"
# LLMOS_EXTRA_DRIVE=file.qcow2: a second disk (installer tests)
[ -n "${LLMOS_EXTRA_DRIVE:-}" ] && HOST_ARGS="$HOST_ARGS -drive file=$LLMOS_EXTRA_DRIVE,format=qcow2,if=virtio"
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 1
rm -f run/boot-serial.log
# a SHIPPED image is never written to: tests of dist/ images run on a
# throwaway overlay (build/work test disks are booted directly so that state
# persists across the reboot leg). LLMOS_KEEP_OVERLAY=1 boots the previous
# overlay again (a "reboot" of the same test installation).
# a SHIPPED image (anything under dist/, however the path is written) is never booted directly: tests run on a
# throwaway overlay. build/work test disks are booted directly so state persists across the reboot leg.
case "$(cd "$(dirname "$IMG")" 2>/dev/null && pwd)/" in "$PWD/dist/"*)
  if [ "${LLMOS_KEEP_OVERLAY:-0}" != 1 ] || [ ! -f run/target-overlay.qcow2 ]; then
    rm -f run/target-overlay.qcow2 run/llmos-vars.fd
    qemu-img create -f qcow2 -b "$(cd "$(dirname "$IMG")" && pwd)/$(basename "$IMG")" -F qcow2 run/target-overlay.qcow2 >/dev/null
  fi
  IMG=run/target-overlay.qcow2 ;;
  *) rm -f run/llmos-vars.fd ;;
esac
[ -f run/llmos-vars.fd ] || cp $FW/edk2-arm-vars.fd run/llmos-vars.fd
qemu-system-aarch64 -machine virt -accel hvf -cpu host -smp "$CPUS" -m "$RAM" \
  -drive if=pflash,format=raw,readonly=on,file=$FW/edk2-aarch64-code.fd \
  -drive if=pflash,format=raw,file=run/llmos-vars.fd \
  -drive file="$IMG",format=qcow2,if=virtio,discard=unmap \
  -nic user,model=virtio-net-pci \
  -device virtio-gpu-pci -device virtio-keyboard-pci -device virtio-tablet-pci \
  -audiodev none,id=snd0 -device virtio-sound-pci,audiodev=snd0 \
  -fw_cfg name=opt/llmos/tz,string=America/Phoenix $HOST_ARGS \
  -display none -monitor unix:run/tmon.sock,server=on,wait=off \
  -chardev socket,id=ser0,path=run/tser.sock,server=on,wait=off,logfile="$PWD/run/boot-serial.log",logappend=on -serial chardev:ser0 \
  -daemonize -pidfile run/target.pid && echo "target VM pid $(cat run/target.pid)"
tools/vm-lifetime.sh run/target.pid    # never longer than 3 h, whatever happens to the test driving it
