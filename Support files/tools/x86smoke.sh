#!/bin/bash
# Smoke test of the shipped x86-64 image under QEMU's x86 emulation, with the
# model served by the Mac (host-GPU mode, so the test is not bottlenecked by
# emulated inference): boot with SeaBIOS or UEFI, take the serial console,
# go through the first-run wizard, time two requests, inspect the system.
#   usage: tools/x86smoke.sh [bios|uefi]
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
V="python3 tools/vmctl.py"; S=run/yser.sock; L=run/x86-boot.log
MODE=${1:-bios}
printf '\n======== x86-64 image: %s boot, host-GPU mode, 3 GB VM ========\n' "$MODE"
LLMOS_HOSTGPU_URL=${LLMOS_HOSTGPU_URL:-http://10.0.2.2:8080} tools/boot-x86.sh "$MODE"
t0=$(date +%s)
$V wait "$L" 'Press Enter to use it here' 400 | tr -d '\r' | grep -aE 'GRUB|rror|served by the host' | head -4
echo "  -> serial console offered after $(( $(date +%s) - t0 )) s"
M=$($V mark "$L"); $V send $S ""
# with the desk already on screen the console offers to wait; Enter takes over
$V wait "$L" 'press Enter to do it here|language should I use' 180 --from "$M" >/dev/null
if tail -c 400 "$L" | grep -q 'press Enter to do it here'; then sleep 1; $V send $S ""; fi
$V wait "$L" 'language should I use' 180 --from "$M" | tr -d '\r' | grep -aE 'served by the host|Welcome' | head -3
M=$($V mark "$L"); for a in "" Jordan "" 1 y n ""; do $V send $S "$a"; sleep 1.5; done
$V wait "$L" 'All set' 240 --from "$M" >/dev/null && echo "  -> onboarded ($MODE, host-GPU)"
sleep 12
for q in "how much disk space do I have?" "what is 12 times 34?"; do
  t0=$(date +%s); tools/xrun "$q" 400 | tail -4; echo "   (${q:0:30}… took $(( $(date +%s) - t0 )) s)"; echo "----"
done
tools/xrun "settings" 90
tools/xrun '!uname -r; cat /run/llmos/model_url; echo "services started: $(rc-status -s 2>/dev/null | grep -c started)"; ls /boot/efi/EFI/BOOT/; head -2 /proc/asound/cards; ls /dev/dri/' 90 | tail -12
