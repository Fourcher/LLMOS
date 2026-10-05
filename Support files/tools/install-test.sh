#!/bin/bash
# Verify the installer in QEMU.
#   tools/install-test.sh x86      "dual boot": a disk laid out like an Intel Mac
#                                  (EFI partition + APFS-typed partition + free
#                                  space); LLM OS boots from a second disk (the
#                                  "USB stick"), installs itself into the free
#                                  space, then the machine boots from the first disk
#   tools/install-test.sh arm64    "whole disk": the arm64 image installs itself
#                                  onto a blank second disk, then boots from it
# The serial line is the test shell; requests go through the desk's control socket.
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
ARCH=${1:-x86}
V="python3 tools/vmctl.py"; FW=/opt/homebrew/share/qemu
sh() { tools/tsh "$1" "${2:-120}" | grep -vE '^\s*$|^\[vmctl|^# $|^~ # $'; }
mkfake() {   # a 24 GB "Mac" disk: ESP 300 MB (with an Apple folder), APFS 6 GB, rest free
  rm -f run/fakemac.raw run/fakemac.qcow2
  qemu-img create -f raw run/fakemac.raw 24G >/dev/null
  python3 - <<'EOF'
import subprocess, struct
# GPT via sfdisk is not available on macOS; write the table with QEMU's guest later.
EOF
}

if [ "$ARCH" = x86 ]; then
  S=run/yser.sock; L=run/x86-boot.log; MON=run/ymon.sock
  python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null; sleep 1
  rm -f run/fakemac.qcow2 run/x86-overlay.qcow2 run/x86-vars.fd "$L"
  qemu-img create -f qcow2 run/fakemac.qcow2 24G >/dev/null
  qemu-img create -f qcow2 -b "$PWD/dist/llmos-x86_64.qcow2" -F qcow2 run/x86-overlay.qcow2 >/dev/null
  cp $FW/edk2-i386-vars.fd run/x86-vars.fd
  boot() {   # $1 = "both" (fake disk + stick) or "disk" (fake disk only)
    drives="-drive file=run/fakemac.qcow2,format=qcow2,if=virtio"
    [ "$1" = both ] && drives="$drives -drive file=run/x86-overlay.qcow2,format=qcow2,if=virtio"
    # shellcheck disable=SC2086
    qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072 \
      -drive if=pflash,format=raw,readonly=on,file=$FW/edk2-x86_64-code.fd -drive if=pflash,format=raw,file=run/x86-vars.fd \
      $drives -nic user,model=virtio-net-pci -device virtio-vga -device virtio-keyboard-pci -device virtio-tablet-pci \
      -smbios type=1,manufacturer="Apple Inc.",product="MacBookPro14,,1" \
      -fw_cfg name=opt/llmos/tz,string=America/Phoenix -fw_cfg name=opt/llmos/testshell,string=1 \
      ${LLMOS_HOSTGPU_URL:+-fw_cfg name=opt/llmos/model_url,string=$LLMOS_HOSTGPU_URL -fw_cfg name=opt/llmos/model_id,string=ministral-3-3b} \
      -display none -monitor unix:$MON,server=on,wait=off \
      -chardev socket,id=ser0,path=$S,server=on,wait=off,logfile="$PWD/$L",logappend=on -serial chardev:ser0 \
      -daemonize -pidfile run/x86test.pid
  }
  tsh() { python3 tools/vmctl.py run $S $L "$1; echo DONE_\"\"9" "^DONE_9" "${2:-120}" --quiet 1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' | grep -vE "^\s*$|DONE_|^# $|^~ # $|^\[vmctl"; }
  echo "==== x86: boot the stick next to a Mac-like disk"
  boot both
  $V wait $L 'LLM OS test shell' 600 >/dev/null && echo "  -> booted from the stick"
  echo "--- lay out the Mac-like disk (ESP + APFS-typed partition + free space)"
  tsh 'printf "label: gpt\nsize=300MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name=EFI\nsize=6GiB, type=7C3457EF-0000-11AA-AA11-00306543ECAC, name=Macintosh\n" | sfdisk -q /dev/vda && mkfs.vfat -F 32 /dev/vda1 >/dev/null && mkdir -p /mnt/e && mount /dev/vda1 /mnt/e && mkdir -p /mnt/e/EFI/APPLE && echo apple > /mnt/e/EFI/APPLE/dummy && umount /mnt/e && sfdisk -l /dev/vda | tail -3' 120
  tsh 'for i in $(seq 1 90); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; ls /run/llmos/desk.sock' 200
  echo "--- ask for the installation"
  tsh 'llmos say "install LLM OS on this computer" | python3 -c "import json,sys; s=json.load(sys.stdin); w=[x for x in s[\"windows\"] if \"Install\" in x[\"title\"] or \"install\" in x[\"title\"]]; print(\"\\n\".join(w[0][\"rows\"]) if w else s); print(\"ACTIONS\", w[0][\"actions\"] if w else [])"' 300
  token=$(grep -o 'confirmed [0-9a-f]\{8\}' "$L" | tail -1 | cut -d' ' -f2)
  echo "  -> plan token: ${token:-NONE}"
  [ -z "$token" ] && exit 1
  echo "--- install (copying ~3.5 GB under emulation: several minutes)"
  t0=$(date +%s)
  tsh "llmos say \"install llm os: confirmed $token\" | head -c 900; echo" 2400
  echo "  -> took $(( $(date +%s) - t0 )) s"
  tsh 'sfdisk -l /dev/vda | tail -4; ls /mnt/llmos-install 2>/dev/null | head -2; mount /dev/vda1 /mnt/e 2>/dev/null; find /mnt/e/EFI -maxdepth 2 | head; umount /mnt/e 2>/dev/null; true' 60
  python3 tools/screendump.py $MON run/shot-install-x86.png
  echo "--- power off, boot from the Mac-like disk alone"
  tsh 'sync; poweroff' 10 >/dev/null
  for i in $(seq 1 60); do pgrep -f 'run/x86-overlay.qcow2' >/dev/null || break; sleep 2; done   # emulation is slow to halt
  rm -f "$L"; boot disk
  if $V wait $L 'LLM OS test shell' 600 >/dev/null; then
    echo "  -> booted from the installed system"
    tsh 'grep " / " /proc/mounts | cut -d" " -f1; cat /etc/llmos/settings.json | head -c 200; echo; uname -r; efibootmgr 2>/dev/null | head -3' 60
    sleep 20; python3 tools/screendump.py $MON run/shot-installed-x86.png
  else
    echo "  -> FAILED to boot from the installed disk"; tail -c 1500 "$L"
  fi
  python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null
else
  S=run/tser.sock; L=run/boot-serial.log; MON=run/tmon.sock
  echo "==== arm64: whole-disk install onto a blank second disk"
  rm -f run/blank.qcow2; qemu-img create -f qcow2 run/blank.qcow2 20G >/dev/null
  LLMOS_TESTSHELL=1 LLMOS_EXTRA_DRIVE=run/blank.qcow2 tools/boot-target.sh dist/llmos-arm64.qcow2 4096 >/dev/null
  $V wait $L 'LLM OS test shell' 300 >/dev/null && echo "  -> booted"
  sh 'for i in $(seq 1 60); do [ -S /run/llmos/desk.sock ] && break; sleep 2; done; ls /run/llmos/desk.sock' 200
  sh 'llmos say "erase the whole disk and install LLM OS on it" | python3 -c "import json,sys; s=json.load(sys.stdin); w=[x for x in s[\"windows\"] if \"nstall\" in x[\"title\"]]; print(\"\\n\".join(w[0][\"rows\"]) if w else s); print(\"ACTIONS\", w[0][\"actions\"] if w else [])"' 300
  token=$(grep -o 'confirmed [0-9a-f]\{8\}' "$L" | tail -1 | cut -d' ' -f2)
  echo "  -> plan token: ${token:-NONE}"; [ -z "$token" ] && exit 1
  t0=$(date +%s)
  sh "llmos say \"install llm os: confirmed $token\" | head -c 900; echo" 1200
  echo "  -> took $(( $(date +%s) - t0 )) s"
  sh 'sfdisk -l /dev/vdb | tail -4' 30
  python3 tools/screendump.py $MON run/shot-install-arm64.png
  sh 'sync; poweroff' 10 >/dev/null; sleep 8
  echo "--- boot the new disk alone"
  LLMOS_TESTSHELL=1 tools/boot-target.sh run/blank.qcow2 4096 >/dev/null
  if $V wait $L 'LLM OS test shell' 300 >/dev/null; then
    echo "  -> booted from the installed disk"
    sh 'grep " / " /proc/mounts | cut -d" " -f1; uname -r; ls /boot/efi/EFI' 60
    sleep 15; python3 tools/screendump.py $MON run/shot-installed-arm64.png
  else
    echo "  -> FAILED to boot from the installed disk"; tail -c 1500 "$L"
  fi
  python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.recv(999);s.sendall(b'quit\n')" 2>/dev/null
fi
