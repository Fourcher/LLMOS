#!/bin/bash
# Secure Boot, end to end, on an ordinary PC's firmware: UEFI with Secure Boot enforced and Microsoft's keys
# enrolled (Debian's OVMF build), the way Windows PCs ship.
#   1. the x86-64 image starts as a "USB stick" (its EFI/BOOT/BOOTX64.EFI is the Microsoft-signed shim)
#   2. LLM OS is asked, in words, to erase a blank disk and install itself there
#   3. the PC restarts from that disk alone, still with Secure Boot enforced
# Each boot must reach LLM OS with the kernel saying Secure Boot is on (and so locked down).
# usage: tools/secureboot-test.sh        (needs dist/llmos-x86_64.qcow2; slow: x86 is emulated)
set -u
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
[ -f build/cache/ovmf/OVMF_CODE_4M.secboot.fd ] || tools/fetch-secureboot.sh >/dev/null
V="python3 tools/vmctl.py"; S=run/sbser.sock; L=run/sb-boot.log; MON=run/sbmon.sock
fails=0; ok() { echo "  ok   $*"; }; bad() { echo "  FAIL $*"; fails=$((fails + 1)); }
quit() { python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; }
tsh() { $V run $S $L "$1; echo DONE_\"\"9" "^DONE_9" "${2:-120}" --quiet 1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' | grep -vE "^\s*$|DONE_|^# $|^~ # $|^\[vmctl"; }
quit; sleep 1
rm -f run/sb-target.qcow2 run/sb-overlay.qcow2 run/sb-vars.fd "$L"
qemu-img create -f qcow2 run/sb-target.qcow2 24G >/dev/null
qemu-img create -f qcow2 -b "$PWD/dist/llmos-x86_64.qcow2" -F qcow2 run/sb-overlay.qcow2 >/dev/null
cp build/cache/ovmf/OVMF_VARS_4M.ms.fd run/sb-vars.fd          # Secure Boot on, Microsoft's keys, kept across boots
boot() {   # $1 = "both" (blank disk + stick) or "disk" (the installed disk alone)
    local drives="-drive file=run/sb-target.qcow2,format=qcow2,if=virtio"
    [ "$1" = both ] && drives="$drives -drive file=run/sb-overlay.qcow2,format=qcow2,if=virtio"
    # shellcheck disable=SC2086
    qemu-system-x86_64 -machine q35,smm=on -accel tcg,thread=multi -cpu max -smp 4 -m 3072 \
      -global driver=cfi.pflash01,property=secure,value=on \
      -drive if=pflash,format=raw,unit=0,readonly=on,file=build/cache/ovmf/OVMF_CODE_4M.secboot.fd \
      -drive if=pflash,format=raw,unit=1,file=run/sb-vars.fd \
      $drives -nic user,model=virtio-net-pci -device virtio-vga \
      -fw_cfg name=opt/llmos/tz,string=America/Phoenix -fw_cfg name=opt/llmos/testshell,string=1 \
      -display none -monitor unix:$MON,server=on,wait=off \
      -chardev socket,id=ser0,path=$S,server=on,wait=off,logfile="$PWD/$L",logappend=on -serial chardev:ser0 \
      -daemonize -pidfile run/sbtest.pid
}
secure() {   # $1 = what booted
    local out; out=$(tsh 'echo "sb=$(dmesg | grep -c "Secure boot enabled")"; echo "lockdown=$(cat /sys/kernel/security/lockdown)"; echo "kernel=$(uname -r)"; grep -E "^(VERSION|MEDIUM)=" /etc/llmos-release; echo "root=$(grep " / " /proc/mounts | cut -d" " -f1)"' 60)
    echo "$out" | sed 's/^/    /'
    echo "$out" | grep -q "^sb=[1-9]" && echo "$out" | grep -q "lockdown=.*\[integrity\]" && ok "$1 under Secure Boot (kernel locked down)" || bad "$1: Secure Boot not confirmed"
}

echo "==== a PC with Secure Boot on starts LLM OS from the stick"
boot both
$V wait $L 'LLM OS test shell' 900 >/dev/null && ok "LLM OS started from the stick" || { bad "no LLM OS from the stick"; tail -c 1500 "$L" | tr -d '\r' | tail -12; quit; exit 1; }
secure "the stick"

echo "==== install onto the blank disk (asked in words)"
tsh 'for i in $(seq 1 120); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; ls /run/llmos/desk.sock' 300 | sed 's/^/    /'
tsh 'llmos say "erase the whole disk and install LLM OS on it" | python3 -c "import json,sys; s=json.load(sys.stdin); w=[x for x in s[\"windows\"] if \"nstall\" in x[\"title\"]]; print(\"\\n\".join(w[0][\"rows\"]) if w else s); print(\"ACTIONS\", w[0][\"actions\"] if w else [])"' 300 | sed 's/^/    /' | head -12
token=$(grep -ao 'confirmed [0-9a-f]\{8\}' "$L" | tail -1 | cut -d' ' -f2)
[ -n "$token" ] && ok "a plan came back (token $token)" || { bad "no install plan"; quit; exit 1; }
t0=$(date +%s)
tsh "llmos say \"install llm os: confirmed $token\" | head -c 700; echo" 2400 | sed 's/^/    /'
echo "    (took $(( $(date +%s) - t0 )) s)"
tsh 'mkdir -p /mnt/e && mount /dev/vda1 /mnt/e 2>/dev/null; find /mnt/e/EFI -type f | sort; echo "--- EFI/debian/grub.cfg:"; cat /mnt/e/EFI/debian/grub.cfg; umount /mnt/e; efibootmgr | grep -i "llm os"' 60 | sed 's/^/    /'
tsh 'sync; poweroff' 10 >/dev/null
for _ in $(seq 1 90); do pgrep -f 'run/sb-overlay.qcow2' >/dev/null || break; sleep 2; done

echo "==== the PC restarts from the installed disk alone, Secure Boot still on"
rm -f "$L"; boot disk
if $V wait $L 'LLM OS test shell' 900 >/dev/null; then
    ok "LLM OS started from the installed disk"
    secure "the installed system"
else
    bad "the installed disk did not start"; tail -c 2000 "$L" | tr -d '\r' | tail -15
fi
quit
[ $fails = 0 ] && echo "all good" || echo "$fails FAILED"
exit $fails
