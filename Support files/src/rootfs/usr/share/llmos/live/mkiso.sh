#!/bin/sh
# Runs INSIDE a booted LLM OS image (over the test shell) and turns the
# installed system into a live ISO: the boot loaders (x86: BIOS GRUB, and for
# UEFI the Microsoft-signed shim + Debian-signed GRUB, so PCs with Secure Boot
# on start it; arm64: GRUB for UEFI), the kernel, a small initramfs with
# src/live/init, the whole system as a zstd squashfs, and the model file
# stored uncompressed.
# The ISO is written raw onto the second disk (/dev/vdb); the host trims
# it to the size the ISO's own volume descriptor declares.
#   usage: sh mkiso.sh <version> <arch: x86_64|aarch64> [cmdline-extras]
set -eu
VER=$1; ARCH=$2; EXTRA=${3:-}
W=/var/tmp/isobuild; ISO=$W/iso; rm -rf "$W"; mkdir -p "$ISO/boot/grub" "$ISO/llmos/models"   # on disk: /tmp is RAM
echo "==> packages"
apk add -q xorriso grub mtools squashfs-tools dosfstools 2>&1 | tail -2 || true
SBD=/usr/share/llmos/secureboot
case "$ARCH" in
    x86_64)  apk add -q grub-bios 2>&1 | tail -1 || true; KFLAVOR=lts; KVER=$(cat $SBD/kernel-version 2>/dev/null) ;;
    aarch64) apk add -q grub-efi 2>&1 | tail -1 || true; KFLAVOR=virt; KVER=$(ls /lib/modules | grep -- "-virt" | head -1) ;;
    *) echo "unknown arch $ARCH"; exit 2 ;;
esac
[ -n "$KVER" ] && [ -d "/lib/modules/$KVER" ] || { echo "no kernel modules for '$KVER' found"; exit 2; }
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
    x86_64)
        for f in shimx64.efi gcdx64.efi mmx64.efi; do [ -s "$SBD/$f" ] || { echo "missing $SBD/$f"; exit 2; }; done
        # BIOS: GRUB's El Torito image and its modules (BIOS has no Secure Boot)
        mkdir -p "$ISO/boot/grub/i386-pc" "$ISO/.disk"
        cp /usr/lib/grub/i386-pc/*.mod /usr/lib/grub/i386-pc/*.lst "$ISO/boot/grub/i386-pc/"
        grub-mkimage -O i386-pc-eltorito -p /boot/grub -o "$ISO/boot/grub/i386-pc/eltorito.img" biosdisk iso9660
        # UEFI: Microsoft-signed shim (BOOTX64.EFI) -> Debian-signed GRUB for removable media, which finds this
        # medium by /.disk/info and reads /boot/grub/grub.cfg; MokManager rides along as shim expects
        echo "LLM OS $VER x86_64" > "$ISO/.disk/info"
        mkfs.vfat -C -n LLMOS_EFI "$ISO/efi.img" 8192 >/dev/null
        mmd -i "$ISO/efi.img" ::/EFI ::/EFI/BOOT
        mcopy -i "$ISO/efi.img" "$SBD/shimx64.efi" ::/EFI/BOOT/BOOTX64.EFI
        mcopy -i "$ISO/efi.img" "$SBD/gcdx64.efi" ::/EFI/BOOT/grubx64.efi
        mcopy -i "$ISO/efi.img" "$SBD/mmx64.efi" ::/EFI/BOOT/mmx64.efi
        # the same layout grub-mkrescue makes (CD and USB stick, BIOS and UEFI), with this EFI image
        xorriso -as mkisofs -graft-points -V LLMOS \
            -b boot/grub/i386-pc/eltorito.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
            --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
            --efi-boot efi.img -efi-boot-part --efi-boot-image \
            --protective-msdos-label \
            -o "$W/llmos.iso" -r "$ISO" --sort-weight 0 / --sort-weight 1 /boot 2>&1 | grep -iE "error|fail" || true
        ;;
    aarch64) grub-mkrescue -o "$W/llmos.iso" "$ISO" -d /usr/lib/grub/arm64-efi -- -volid LLMOS ;;
esac
[ -s "$W/llmos.iso" ] || { echo "ISO build failed"; exit 2; }
ls -la "$W/llmos.iso"
echo "==> writing the ISO to the output disk"
dd if="$W/llmos.iso" of=/dev/vdb bs=4M conv=fsync 2>&1 | tail -1
sync
echo "ISO_BYTES=$(stat -c %s "$W/llmos.iso")"
echo "==> mkiso done"
