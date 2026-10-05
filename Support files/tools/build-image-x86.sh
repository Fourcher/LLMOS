#!/bin/bash
# Build dist/llmos-x86_64.qcow2 (real-computer image: lts kernel, firmware,
# BIOS+UEFI GRUB) on this Apple Silicon Mac using QEMU's x86 emulation (TCG).
# Slow (~30-60 min) because every guest instruction is emulated; the result is
# what an ordinary PC or laptop boots. Same flow as build-image.sh otherwise.
set -eu
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
ISO=build/cache/alpine-virt-3.24.2-x86_64.iso
KERNEL=build/cache/x86iso/boot/vmlinuz-virt
INITRD=build/cache/x86iso/boot/initramfs-virt
DISK=build/work/build-x86.qcow2
LOG=build/work/build-x86-serial.log
V="python3 tools/vmctl.py"

echo "==> payload"
python3 -m compileall -q src/rootfs/usr/lib/llmos/llmos
find src/rootfs -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
chmod 0755 src/rootfs/usr/bin/llmos src/rootfs/usr/bin/llmos-model-run src/rootfs/usr/libexec/llmos-login src/rootfs/usr/libexec/llmos-desk src/rootfs/etc/init.d/llmos-*
(cd src/rootfs && tar --format=ustar -cf ../../build/work/payload.tar .)

echo "==> host http server"
curl -s -o /dev/null http://127.0.0.1:8765/src/install.sh || {
    nohup python3 -m http.server 8765 --bind 127.0.0.1 --directory "$PWD" > run/httpd.log 2>&1 &
    echo $! > run/httpd.pid; sleep 1; }

echo "==> x86 build VM (TCG)"
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/xmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null || true
sleep 1; rm -f "$DISK" "$LOG"
qemu-img create -f qcow2 "$DISK" 16G >/dev/null
qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072 \
  -kernel "$KERNEL" -initrd "$INITRD" \
  -append "modules=loop,squashfs,sd-mod,usb-storage,sr-mod quiet console=ttyS0,115200" \
  -cdrom "$ISO" \
  -display none -monitor unix:run/xmon.sock,server=on,wait=off \
  -chardev socket,id=ser0,path=run/xser.sock,server=on,wait=off,logfile="$PWD/$LOG",logappend=on -serial chardev:ser0 \
  -nic user,model=virtio-net-pci \
  -drive file="$DISK",format=qcow2,if=virtio,discard=unmap \
  -daemonize -pidfile run/xbuild.pid
tools/vm-lifetime.sh run/xbuild.pid 7200
$V wait "$LOG" 'localhost login:' 600 >/dev/null
$V run run/xser.sock "$LOG" "root" '# $' 30 >/dev/null
$V run run/xser.sock "$LOG" "setup-interfaces -a -r >/dev/null 2>&1; udhcpc -i eth0 -q -n >/dev/null 2>&1; wget -qO /tmp/install.sh http://10.0.2.2:8765/src/install.sh && echo FETCHED" 'FETCHED' 120 >/dev/null

echo "==> installing (slow under emulation)"
M=$($V mark "$LOG")
$V send run/xser.sock "PAYLOAD=http://10.0.2.2:8765 sh /tmp/install.sh 2>&1 | tee /tmp/install.log"
$V wait "$LOG" 'LLMOS_INSTALL_OK|HASH MISMATCH|not enough disk|ERROR|GRUB config has no' 5400 --from "$M" | grep -E '^==>|LLMOS_INSTALL_OK|MISMATCH|ERROR|not enough|GRUB|/dev/vda3'
grep -q LLMOS_INSTALL_OK <(tail -c 4000 "$LOG") || { echo "INSTALL FAILED"; exit 1; }

echo "==> power off"
$V send run/xser.sock "poweroff"
for i in $(seq 1 60); do ps -p "$(cat run/xbuild.pid)" >/dev/null 2>&1 || break; sleep 2; done
ps -p "$(cat run/xbuild.pid)" >/dev/null 2>&1 && { echo "build VM did not stop"; exit 1; }

echo "==> compact into dist/"
mkdir -p dist
qemu-img convert -O qcow2 "$DISK" dist/llmos-x86_64.qcow2
(cd dist && { shasum -a 256 llmos-arm64.qcow2 2>/dev/null; shasum -a 256 llmos-x86_64.qcow2; ls models/*.gguf >/dev/null 2>&1 && shasum -a 256 models/*.gguf; } > SHA256SUMS && cat SHA256SUMS)
qemu-img info dist/llmos-x86_64.qcow2 | grep -E 'virtual size|disk size'
echo "==> done"
