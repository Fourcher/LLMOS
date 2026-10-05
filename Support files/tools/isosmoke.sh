#!/bin/bash
# Boot a built live ISO headless (UEFI on arm64; BIOS or UEFI on x86) with the
# serial test shell and check that the system really runs from the medium:
# overlay root, llmos.live on the command line, the release stamp, the model
# bind-mounted from the ISO, the desk socket. Leaves the VM running on the usual
# sockets (quit it with tools/cleanup.sh).  usage: tools/isosmoke.sh [arm64|x86 [bios|uefi]]
set -u
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
A=${1:-arm64}; MODE=${2:-uefi}; FW=/opt/homebrew/share/qemu
V="python3 tools/vmctl.py"
tools/vm-lifetime.sh run/isotest.pid 7200 2>/dev/null || true
case "$A" in
  arm64)
    ISO=dist/llmos-arm64.iso; SER=run/tser.sock; LOG=run/boot-serial.log; MON=run/tmon.sock
    python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 1
    rm -f "$LOG" run/iso-vars.fd; cp $FW/edk2-arm-vars.fd run/iso-vars.fd
    qemu-system-aarch64 -machine virt -accel hvf -cpu host -smp 4 -m 4096 \
      -drive if=pflash,format=raw,readonly=on,file=$FW/edk2-aarch64-code.fd -drive if=pflash,format=raw,file=run/iso-vars.fd \
      -device virtio-scsi-pci -drive if=none,id=cd,file="$ISO",format=raw,media=cdrom,readonly=on -device scsi-cd,drive=cd \
      -nic user,model=virtio-net-pci -device virtio-gpu-pci -device virtio-keyboard-pci -device virtio-tablet-pci \
      -audiodev none,id=snd0 -device virtio-sound-pci,audiodev=snd0 \
      -fw_cfg name=opt/llmos/tz,string=America/Phoenix -fw_cfg name=opt/llmos/testshell,string=1 ${LLMOS_HOSTGPU_URL:+-fw_cfg name=opt/llmos/model_url,string=$LLMOS_HOSTGPU_URL} \
      -display none -monitor unix:$MON,server=on,wait=off \
      -chardev socket,id=ser0,path=$SER,server=on,wait=off,logfile="$PWD/$LOG",logappend=on -serial chardev:ser0 \
      -daemonize -pidfile run/isotest.pid && echo "  -> ISO VM ($A) pid $(cat run/isotest.pid)" ;;
  x86)
    ISO=dist/llmos-x86_64.iso; SER=run/yser.sock; LOG=run/x86-boot.log; MON=run/ymon.sock
    python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 1
    rm -f "$LOG"; FWARGS=""
    if [ "$MODE" = uefi ]; then rm -f run/iso-ovmf-vars.fd; cp $FW/edk2-i386-vars.fd run/iso-ovmf-vars.fd; FWARGS="-drive if=pflash,format=raw,readonly=on,file=$FW/edk2-x86_64-code.fd -drive if=pflash,format=raw,file=run/iso-ovmf-vars.fd"; fi
    qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072 $FWARGS \
      -cdrom "$ISO" -boot d -nic user,model=virtio-net-pci -device virtio-vga -device virtio-keyboard-pci -device virtio-tablet-pci \
      -audiodev none,id=snd0 -device intel-hda -device hda-duplex,audiodev=snd0 \
      -fw_cfg name=opt/llmos/tz,string=America/Phoenix -fw_cfg name=opt/llmos/testshell,string=1 ${LLMOS_HOSTGPU_URL:+-fw_cfg name=opt/llmos/model_url,string=$LLMOS_HOSTGPU_URL} \
      -display none -monitor unix:$MON,server=on,wait=off \
      -chardev socket,id=ser0,path=$SER,server=on,wait=off,logfile="$PWD/$LOG",logappend=on -serial chardev:ser0 \
      -daemonize -pidfile run/isotest.pid && echo "  -> ISO VM ($A $MODE) pid $(cat run/isotest.pid)" ;;
  *) echo "usage: $0 [arm64|x86 [bios|uefi]]"; exit 2 ;;
esac
tools/vm-lifetime.sh run/isotest.pid 7200
t0=$(date +%s)
if $V wait "$LOG" 'LLM OS test shell' 900 >/dev/null; then echo "  -> test shell up after $(( $(date +%s) - t0 )) s"; else echo "!! no test shell within 900 s"; tail -c 1500 "$LOG" | tr -d '\r' | tail -12; exit 1; fi
$V run "$SER" "$LOG" 'echo "cmdline: $(cat /proc/cmdline)"; echo "root: $(grep " / " /proc/mounts | cut -d" " -f1-3)"; echo "live medium: $(grep " /run/live " /proc/mounts | cut -d" " -f1-3)"; cat /etc/llmos-release; echo "models: $(ls /var/lib/llmos/models 2>/dev/null | tr "\n" " ")"; for i in $(seq 1 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; echo "desk socket: $([ -S /run/llmos/desk.sock ] && echo yes || echo no)"; free -m | sed -n 2p; echo ISO_""CHECK' '^ISO_CHECK' 240 --quiet 1 | tr -d '\r' | grep -E '^(cmdline|root|live medium|models|desk socket|Mem):|^(VERSION|BUILD|ARCH|MEDIUM)=' | cut -c1-150
