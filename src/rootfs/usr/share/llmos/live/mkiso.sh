#!/bin/sh
# Runs INSIDE a booted LLM OS image (over the test shell) and turns the
# installed system into a live ISO: GRUB (BIOS + UEFI on x86, UEFI on
# arm64), the kernel, a small initramfs with src/live/init, the whole
# system as a zstd squashfs, and the model file stored uncompressed.
# The ISO is written raw onto the second disk (/dev/vdb); the host trims
# it to the size the ISO's own volume descriptor declares.
#   usage: sh mkiso.sh <version> <arch: x86_64|aarch64> [cmdline-extras]
set -eu
VER=$1; ARCH=$2; EXTRA=${3:-}
W=/var/tmp/isobuild; ISO=$W/iso; rm -rf "$W"; mkdir -p "$ISO/boot/grub" "$ISO/llmos/models"   # on disk: /tmp is RAM
echo "==> packages"
apk add -q xorriso grub mtools squashfs-tools dosfstools 2>&1 | tail -2 || true
case "$ARCH" in
    x86_64)  apk add -q grub-bios grub-efi 2>&1 | tail -1 || true; KFLAVOR=lts ;;
    aarch64) apk add -q grub-efi 2>&1 | tail -1 || true; KFLAVOR=virt ;;
    *) echo "unknown arch $ARCH"; exit 2 ;;
esac
KVER=$(ls /lib/modules | grep -- "-$KFLAVOR" | head -1)
[ -n "$KVER" ] || { echo "no $KFLAVOR kernel modules found"; exit 2; }
echo "==> kernel $KVER"
cp /boot/vmlinuz-$KFLAVOR "$ISO/boot/vmlinuz"
echo "==> live initramfs"
mkdir -p /etc/mkinitfs/features.d
printf 'kernel/fs/overlayfs\nkernel/fs/squashfs\nkernel/drivers/block/loop.ko*\nkernel/fs/isofs\nkernel/drivers/cdrom\nkernel/drivers/scsi/sr_mod.ko*\n' > /etc/mkinitfs/features.d/llmoslive.modules
mkinitfs -o "$W/initramfs.gz" -F "ata base ide scsi usb virtio ext4 nvme mmc kms cdrom squashfs llmoslive" "$KVER" >/dev/null
mkdir -p "$W/ird"; (cd "$W/ird" && gzip -dc "$W/initramfs.gz" | cpio -idm --quiet 2>/dev/null)
cp "$(dirname "$0")/init" "$W/ird/init"; chmod 0755 "$W/ird/init"
(cd "$W/ird" && find . | cpio -o -H newc --quiet | gzip -9 > "$ISO/boot/initramfs-live")
rm -rf "$W/ird" "$W/initramfs.gz"
echo "==> release stamp"
printf 'VERSION=%s\nBUILD=%s\nARCH=%s\nMEDIUM=live\n' "$VER" "$(date +%Y-%m-%d)" "$ARCH" > /etc/llmos-release
mkdir -p /etc/llmos; apk list -I 2>/dev/null | sort > /etc/llmos/packages.txt || true
echo "==> system squashfs (the model is stored beside it, uncompressed)"
MODELS=/var/lib/llmos/models
if [ -d "$MODELS" ]; then for f in "$MODELS"/*.gguf; do [ -f "$f" ] && { ln "$f" "$ISO/llmos/models/" 2>/dev/null || cp "$f" "$ISO/llmos/models/"; }; done; fi
# the live root gets its own fstab (the installed one names the build disk's partitions) and no time zone
printf 'proc /proc proc defaults 0 0\nsysfs /sys sysfs defaults 0 0\ntmpfs /tmp tmpfs nodev,nosuid,size=512M 0 0\n' > /tmp/live-fstab
mksquashfs / "$ISO/llmos/root.sfs" -comp zstd -Xcompression-level 3 -b 256K -noappend -no-progress -quiet \
    -wildcards -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*' 'mnt/*' 'media/*' 'var/cache/apk/*' 'var/log/*' 'var/lib/llmos/models/*' 'var/lib/llmos/vault.img' \
       'boot/efi/*' 'root/.cache/*' 'home/*/.cache/*' 'var/cache/llmos/*' 'var/tmp/*' 'etc/llmos/settings.json' 'etc/llmos/timezone' 'etc/fstab' 'etc/localtime' \
       'var/lib/llmos/data/*' lost+found
mkdir -p "$ISO/llmos/etc"; cp /tmp/live-fstab "$ISO/llmos/etc/fstab"
echo "==> grub"
sed -e "s|@@CMDLINE@@|llmos.live=1 quiet $EXTRA|" "$(dirname "$0")/grub.cfg" > "$ISO/boot/grub/grub.cfg"
case "$ARCH" in
    x86_64)  grub-mkrescue -o "$W/llmos.iso" "$ISO" -- -volid LLMOS ;;
    aarch64) grub-mkrescue -o "$W/llmos.iso" "$ISO" -d /usr/lib/grub/arm64-efi -- -volid LLMOS ;;
esac
ls -la "$W/llmos.iso"
echo "==> writing the ISO to the output disk"
dd if="$W/llmos.iso" of=/dev/vdb bs=4M conv=fsync 2>&1 | tail -1
sync
echo "ISO_BYTES=$(stat -c %s "$W/llmos.iso")"
echo "==> mkiso done"
