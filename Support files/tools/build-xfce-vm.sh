#!/bin/bash
# Build the comparison machine for the parity review: stock Alpine 3.24 (aarch64) installed to disk with Alpine's own
# tools, then `setup-desktop xfce` -- exactly what an Alpine user gets -- with LightDM logging in user "user" (password
# "user") automatically. Nothing from LLM OS is in it. Output: build/work/xfce.qcow2 (kept for tools/xfce-vm.sh).
# usage: tools/build-xfce-vm.sh
set -u
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
FW=/opt/homebrew/share/qemu
ISO=build/cache/alpine-virt-3.24.2-aarch64.iso
DISK=build/work/xfce.qcow2
LOG=run/xfce-build.log
V="python3 tools/vmctl.py"
S=run/xfser.sock; MON=run/xfmon.sock
quit() { python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; }
boot() {   # $1 = with-cd | disk
  local cd=""
  [ "$1" = with-cd ] && cd="-device virtio-scsi-pci -drive if=none,id=cd,file=$ISO,format=raw,media=cdrom,readonly=on -device scsi-cd,drive=cd"
  cp $FW/edk2-arm-vars.fd run/xfce-vars.fd      # fresh each boot: the disk's removable fallback path is what starts it
  # shellcheck disable=SC2086
  qemu-system-aarch64 -machine virt -accel hvf -cpu host -smp 4 -m 4096 \
    -drive if=pflash,format=raw,readonly=on,file=$FW/edk2-aarch64-code.fd -drive if=pflash,format=raw,file=run/xfce-vars.fd \
    -drive file="$DISK",format=qcow2,if=virtio $cd -nic user,model=virtio-net-pci \
    -device virtio-gpu-pci -device qemu-xhci -device usb-kbd -device usb-tablet \
    -audiodev none,id=snd0 -device virtio-sound-pci,audiodev=snd0 \
    -display none -monitor unix:$MON,server=on,wait=off \
    -chardev socket,id=ser0,path=$S,server=on,wait=off,logfile="$PWD/$LOG",logappend=on -serial chardev:ser0 \
    -daemonize -pidfile run/xfce.pid
}
sh_() { $V run $S "$LOG" "$1; echo XF_DONE_\"\"7" "^XF_DONE_7" "${2:-300}" --quiet 1 | tr -d '\r' | grep -v "XF_DONE"; }

quit; sleep 1; rm -f "$LOG"
if [ "${SKIP_INSTALL:-0}" != 1 ]; then
rm -f "$DISK"; mkdir -p build/work && qemu-img create -f qcow2 "$DISK" 12G >/dev/null
echo "==> 1/3 install stock Alpine to disk (setup-disk, sys mode)"
boot with-cd
$V wait "$LOG" 'localhost login:' 180 >/dev/null || { echo "no login prompt"; exit 1; }
$V run $S "$LOG" "root" '# $' 20 >/dev/null
sh_ "setup-interfaces -a -r >/dev/null 2>&1; udhcpc -i eth0 -q -n >/dev/null 2>&1; setup-apkrepos -c -1 >/dev/null 2>&1; cat /etc/apk/repositories" 120
sh_ "ERASE_DISKS=/dev/vda setup-disk -m sys -s 0 /dev/vda 2>&1 | tail -3" 900
# the firmware's fallback path (the boot entry setup-disk writes is not always kept): a stock removable-media copy
sh_ "mkdir -p /mnt/esp && mount /dev/vda1 /mnt/esp && mkdir -p /mnt/esp/EFI/BOOT && cp \$(ls /mnt/esp/EFI/*/grub*.efi | head -1) /mnt/esp/EFI/BOOT/BOOTAA64.EFI && ls -R /mnt/esp/EFI | head; umount /mnt/esp" 60
sh_ "poweroff" 10 >/dev/null
for _ in $(seq 1 60); do pgrep -f "file=$DISK" >/dev/null || break; sleep 2; done
fi

echo "==> 2/3 first boot from disk; Alpine's own desktop: setup-desktop xfce"
boot disk
$V wait "$LOG" 'login:' 240 >/dev/null || { echo "installed system did not boot"; tail -c 1500 "$LOG"; exit 1; }
$V run $S "$LOG" "root" '# $' 20 >/dev/null
sh_ "setup-interfaces -a -r >/dev/null 2>&1; rc-service networking restart >/dev/null 2>&1; udhcpc -i eth0 -q -n >/dev/null 2>&1; setup-apkrepos -c -1 >/dev/null 2>&1; apk update >/dev/null 2>&1; echo net ok" 180
sh_ "adduser -D user && echo user:user | chpasswd && for g in audio video input netdev plugdev; do addgroup user \$g 2>/dev/null; done; echo user ok" 60
sh_ "setup-desktop xfce 2>&1 | tail -5" 1800
# log the test user in automatically (the comparison is about the desktop, not the greeter)
sh_ "mkdir -p /etc/lightdm/lightdm.conf.d && printf '[Seat:*]\nautologin-user=user\nautologin-session=xfce\n' > /etc/lightdm/lightdm.conf.d/50-autologin.conf; addgroup -S autologin 2>/dev/null; addgroup user autologin; apk info | grep -E '^(xfce4|thunar|firefox|lightdm|mousepad|ristretto|xfce4-terminal|pipewire|networkmanager|blueman|pavucontrol|xfce4-notifyd)' | sort | tr '\n' ' '" 60
sh_ "apk info > /root/packages.txt; wc -l < /root/packages.txt; sync; poweroff" 30
for _ in $(seq 1 60); do pgrep -f "file=$DISK" >/dev/null || break; sleep 2; done

echo "==> 3/3 boot to the XFCE desktop"
boot disk
sleep 90
python3 tools/screendump.py $MON run/xfce-desktop.png
echo "==> built: $DISK  (screenshot run/xfce-desktop.png; VM left running on $MON / $S)"
