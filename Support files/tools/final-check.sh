#!/bin/bash
# Final verification of the shipped images, end to end, one VM at a time:
#   arm64: desk first boot/lock/away  -> console first boot in host-GPU mode +
#          email -> whole-disk installer
#   x86:   BIOS + UEFI boot smoke (host-GPU) -> dual-boot installer
# Needs a Metal llama-server on the Mac for the host-GPU legs
# (LLMOS_HOSTGPU_URL, default http://10.0.2.2:8080). Logs in run/final-*.log.
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
export LLMOS_HOSTGPU_URL=${LLMOS_HOSTGPU_URL:-http://10.0.2.2:8080}
t0=$(date +%s)
step() { printf '\n#### %s (%s)\n' "$1" "$(date +%H:%M:%S)"; }
step "arm64 desk smoke";        tools/desk-smoke.sh > run/final-desk.log 2>&1;            grep -E '^  ->|^====|reply|screen' run/final-desk.log | cut -c1-160 | tail -12
step "arm64 console + email";   (tools/acceptance.sh distsmoke; tools/acceptance.sh email) > run/final-console.log 2>&1; grep -vE '^\s*$|^\[vmctl|^78› › $' run/final-console.log | cut -c1-160 | tail -30
step "arm64 whole-disk install"; tools/install-test.sh arm64 > run/final-install-arm64.log 2>&1; grep -E '^  ->|^====|took' run/final-install-arm64.log
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/tmon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null
step "x86 BIOS smoke";          tools/x86smoke.sh bios > run/final-x86-bios.log 2>&1;      grep -E '^  ->|took|lts|BOOTX64' run/final-x86-bios.log
step "x86 UEFI smoke";          tools/x86smoke.sh uefi > run/final-x86-uefi.log 2>&1;      grep -E '^  ->|took|lts|BOOTX64' run/final-x86-uefi.log
python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('run/ymon.sock');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null
step "x86 dual-boot install";   tools/install-test.sh x86 > run/final-install-x86.log 2>&1; grep -E '^  ->|^====|took|EFI' run/final-install-x86.log
step "checksums";               (cd dist && shasum -a 256 -c SHA256SUMS)
echo; echo "all legs finished in $(( ($(date +%s) - t0) / 60 )) min; VMs left running: $(pgrep -c -f qemu-system)"
