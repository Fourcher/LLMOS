#!/bin/bash
# Build dist/llmos-arm64.qcow2 from scratch:
#   fresh 16 GB disk -> boot the official Alpine ISO under QEMU/HVF ->
#   run src/install.sh inside it (served from this directory over HTTP) ->
#   power off -> compact the disk into dist/ -> write SHA256SUMS.
# Takes ~10 minutes; most of it is apk downloads and copying the model.
set -eu
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
FW=/opt/homebrew/share/qemu
ISO=build/cache/alpine-virt-3.24.2-aarch64.iso
DISK=build/work/build-disk.qcow2
LOGDIR=${LLMOS_LOGDIR:-"/Volumes/Files/Claude Work Area/LLMOS/Support files/run/build-logs"}   # never the Mac's own disk
mkdir -p "$LOGDIR"
LOG="$LOGDIR/build-serial.log"
trap 'cp "$LOG" build/work/ 2>/dev/null || true' EXIT
V="python3 tools/vmctl.py"

echo "==> payload"
python3 -m compileall -q src/rootfs/usr/lib/llmos/llmos
find src/rootfs -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
chmod 0755 src/rootfs/usr/bin/llmos src/rootfs/usr/bin/llmos-model-run src/rootfs/usr/libexec/llmos-login src/rootfs/usr/libexec/llmos-desk src/rootfs/etc/init.d/llmos-*
(cd src/rootfs && tar --format=ustar --uid 0 --gid 0 --uname root --gname root -cf ../../build/work/payload.tar .)   # system files belong to root, not to the Mac user who built them

echo "==> host http server"
curl -s -o /dev/null http://127.0.0.1:8765/src/install.sh || {
    nohup python3 -m http.server 8765 --bind 127.0.0.1 --directory "$PWD" > run/httpd.log 2>&1 &
    echo $! > run/httpd.pid; sleep 1; }

echo "==> build VM"
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/bmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null || true
sleep 1; rm -f "$DISK" "$LOG"
qemu-img create -f qcow2 "$DISK" 16G >/dev/null
qemu-system-aarch64 -machine virt -accel hvf -cpu host -smp 4 -m 4096 \
  -bios $FW/edk2-aarch64-code.fd \
  -display none -monitor unix:run/bmon.sock,server=on,wait=off \
  -chardev socket,id=ser0,path=run/bser.sock,server=on,wait=off,logfile="$LOG",logappend=on -serial chardev:ser0 \
  -nic user,model=virtio-net-pci \
  -drive file="$DISK",format=qcow2,if=virtio,discard=unmap \
  -device virtio-scsi-pci -drive if=none,id=cd,file=$ISO,format=raw,media=cdrom,readonly=on -device scsi-cd,drive=cd \
  -daemonize -pidfile run/build.pid
tools/vm-lifetime.sh run/build.pid 7200
$V wait "$LOG" 'localhost login:' 120 >/dev/null
$V run run/bser.sock "$LOG" "root" '# $' 20 >/dev/null
$V run run/bser.sock "$LOG" "setup-interfaces -a -r >/dev/null 2>&1; udhcpc -i eth0 -q -n >/dev/null 2>&1; wget -qO /tmp/install.sh http://10.0.2.2:8765/src/install.sh && echo FETCHED" 'FETCHED' 60 >/dev/null

echo "==> installing (this is the slow part)"
M=$($V mark "$LOG")
$V send run/bser.sock "PAYLOAD=http://10.0.2.2:8765 sh /tmp/install.sh 2>&1 | tee /tmp/install.log"
$V wait "$LOG" 'LLMOS_INSTALL_OK|HASH MISMATCH|not enough (free )?disk|ERROR|fatal:|INSTALL FAILED' 900 --from "$M" | grep -E '^==>|LLMOS_INSTALL_OK|MISMATCH|ERROR|not enough|/dev/vda2'
grep -q LLMOS_INSTALL_OK <(tail -c 4000 "$LOG") || { echo "INSTALL FAILED"; exit 1; }

echo "==> power off"
$V send run/bser.sock "poweroff"
for i in $(seq 1 30); do ps -p "$(cat run/build.pid)" >/dev/null 2>&1 || break; sleep 1; done
ps -p "$(cat run/build.pid)" >/dev/null 2>&1 && { echo "build VM did not stop"; exit 1; }

echo "==> compact into dist/"
mkdir -p dist
qemu-img convert -O qcow2 "$DISK" dist/llmos-arm64.qcow2
cp src/rootfs/usr/share/llmos/catalog.json dist/catalog.json   # used by the launcher's host-GPU mode
(cd dist && { shasum -a 256 llmos-arm64.qcow2; ls models/*.gguf >/dev/null 2>&1 && shasum -a 256 models/*.gguf; } > SHA256SUMS && cat SHA256SUMS)
qemu-img info dist/llmos-arm64.qcow2 | grep -E 'virtual size|disk size'
echo "==> done"
