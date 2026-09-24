#!/bin/sh
# Build the LLMOS hybrid (BIOS + UEFI) ISO.
# Runs as root on any Linux host with: curl, mksquashfs, grub-mkrescue,
# xorriso, mtools, cpio, depmod. No virtualization or docker needed.
set -eu

TOP=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$TOP/out}
CACHE=${CACHE:-$TOP/.cache}
MIRROR=${MIRROR:-https://dl-cdn.alpinelinux.org/alpine}
BRANCH=${BRANCH:-edge}
# Model bundled on the ISO so the system works fully offline from first boot.
BUNDLED_MODEL=${BUNDLED_MODEL:-LFM2.5-1.2B-Instruct-Q4_K_M.gguf}
BUNDLED_MODEL_URL=${BUNDLED_MODEL_URL:-https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF/resolve/main/LFM2.5-1.2B-Instruct-Q4_K_M.gguf}
BUNDLED_MODEL_SHA256=${BUNDLED_MODEL_SHA256:-}

ROOT=$OUT/rootfs
ISO=$OUT/iso
INITRD=$OUT/initramfs

step() { printf '\n==> %s\n' "$*"; }

mkdir -p "$OUT" "$CACHE/models" "$CACHE/apk"
[ "$(id -u)" = 0 ] || { echo "build.sh must run as root" >&2; exit 1; }

step "apk-tools"
APK=$CACHE/apk.static
if [ ! -x "$APK" ]; then
	v=$(curl -fsSL "$MIRROR/$BRANCH/main/x86_64/APKINDEX.tar.gz" | tar xzO APKINDEX |
		awk '/^P:apk-tools-static$/{f=1} f&&/^V:/{print substr($0,3);exit}')
	curl -fsSL "$MIRROR/$BRANCH/main/x86_64/apk-tools-static-$v.apk" -o "$CACHE/apkt.apk"
	mkdir -p "$CACHE/apkt" && tar xzf "$CACHE/apkt.apk" -C "$CACHE/apkt" 2>/dev/null || true
	cp "$CACHE/apkt/sbin/apk.static" "$APK"
fi

step "root filesystem"
for m in dev proc sys; do umount -l "$ROOT/$m" 2>/dev/null || true; done
rm -rf "$ROOT"
mkdir -p "$ROOT/etc/apk"
printf '%s/%s/main\n%s/%s/community\n' "$MIRROR" "$BRANCH" "$MIRROR" "$BRANCH" > "$ROOT/etc/apk/repositories"
# Bootstrap the signing keys over TLS, then verify every other package.
"$APK" --root "$ROOT" --initdb --allow-untrusted --update-cache \
	--cache-dir "$CACHE/apk" add alpine-keys >/dev/null
PKGS=$(grep -v '^#' "$TOP/build/packages.txt" | grep -v '^$' | tr '\n' ' ')
"$APK" --root "$ROOT" --cache-dir "$CACHE/apk" add $PKGS

step "llmos files"
cp -a "$TOP/rootfs/." "$ROOT/"
rm -rf "$ROOT/usr/lib/llmos"
mkdir -p "$ROOT/usr/lib/llmos"
cp -a "$TOP/llmos" "$ROOT/usr/lib/llmos/"
cp "$TOP/models.json" "$ROOT/usr/lib/llmos/models.json"
find "$ROOT/usr/lib/llmos" -name __pycache__ -prune -exec rm -rf {} +
cat > "$ROOT/usr/bin/llmos" <<'SH'
#!/bin/sh
export PYTHONPATH=/usr/lib/llmos
exec python3 -m llmos "$@"
SH
chmod 755 "$ROOT/usr/bin/llmos" "$ROOT"/etc/init.d/* "$ROOT"/usr/libexec/llmos/* 2>/dev/null || true

step "system configuration"
mount --bind /dev "$ROOT/dev"; mount -t proc proc "$ROOT/proc"
chroot "$ROOT" /bin/sh -eu <<'SH'
echo llmos > /etc/hostname
for s in devfs dmesg mdev hwdrivers; do rc-update add $s sysinit >/dev/null; done
rc-update del mdev sysinit >/dev/null 2>&1 || true
rc-update add udev sysinit >/dev/null
rc-update add udev-trigger sysinit >/dev/null
rc-update add udev-settle sysinit >/dev/null
for s in modules sysctl hostname bootmisc syslog; do rc-update add $s boot >/dev/null; done
rc-update add nftables boot >/dev/null
rc-update add seatd default >/dev/null
rc-update add llmos default >/dev/null
for s in mount-ro killprocs savecache; do rc-update add $s shutdown >/dev/null; done
# No password logins anywhere. The only interface is the LLMOS shell.
passwd -l root >/dev/null
# Python bytecode for faster start.
python3 -m compileall -q /usr/lib/llmos >/dev/null
SH
umount "$ROOT/proc" "$ROOT/dev"
rm -rf "$ROOT/var/cache/apk/"* "$ROOT/etc/resolv.conf"
: > "$ROOT/etc/resolv.conf"

KV=$(ls "$ROOT/lib/modules" | head -n1)
echo "kernel $KV"

step "initramfs"
rm -rf "$INITRD"
mkdir -p "$INITRD/bin" "$INITRD/etc" "$INITRD/proc" "$INITRD/sys" "$INITRD/dev" "$INITRD/lib/modules/$KV"
cp "$ROOT/bin/busybox.static" "$INITRD/bin/busybox"
cp "$TOP/initramfs/init" "$INITRD/init"; chmod 755 "$INITRD/init"
cp "$TOP/initramfs/modules-early" "$INITRD/etc/modules-early"
M=$ROOT/lib/modules/$KV
( cd "$M" && find kernel/drivers/ata kernel/drivers/block kernel/drivers/cdrom kernel/drivers/scsi \
	kernel/drivers/nvme kernel/drivers/virtio kernel/drivers/usb/host kernel/drivers/usb/storage \
	kernel/drivers/usb/common kernel/drivers/usb/core kernel/drivers/mmc kernel/fs/squashfs \
	kernel/fs/overlayfs kernel/fs/isofs kernel/fs/ext4 kernel/fs/jbd2 kernel/fs/mbcache* kernel/fs/fat \
	kernel/fs/nls kernel/lib kernel/crypto kernel/arch -name '*.ko*' 2>/dev/null |
	cpio -pdm --quiet "$INITRD/lib/modules/$KV" )
find "$INITRD/lib/modules" -name '*.ko.gz' -exec gunzip -f {} +
cp "$M"/modules.order "$M"/modules.builtin* "$INITRD/lib/modules/$KV/" 2>/dev/null || true
sed -i 's/\.ko\.gz$/.ko/' "$INITRD/lib/modules/$KV/modules.order" 2>/dev/null || true
depmod -b "$INITRD" "$KV"
( cd "$INITRD" && find . | cpio -o -H newc --quiet | gzip -9 ) > "$OUT/initramfs.gz"

step "squashfs"
mkdir -p "$ISO/boot/grub" "$ISO/llmos/models"
rm -f "$ISO/llmos/system.sqfs"
mksquashfs "$ROOT" "$ISO/llmos/system.sqfs" -comp zstd -Xcompression-level 15 -noappend -quiet \
	-e boot/initramfs-lts
cp "$ROOT/boot/vmlinuz-lts" "$ISO/boot/vmlinuz"
cp "$OUT/initramfs.gz" "$ISO/boot/initramfs"

step "bundled model"
if [ -n "$BUNDLED_MODEL" ]; then
	[ -f "$CACHE/models/$BUNDLED_MODEL" ] || curl -fL --retry 4 -o "$CACHE/models/$BUNDLED_MODEL" "$BUNDLED_MODEL_URL"
	if [ -n "$BUNDLED_MODEL_SHA256" ]; then
		echo "$BUNDLED_MODEL_SHA256  $CACHE/models/$BUNDLED_MODEL" | sha256sum -c -
	fi
	rm -f "$ISO"/llmos/models/*.gguf
	cp "$CACHE/models/$BUNDLED_MODEL" "$ISO/llmos/models/"
fi

cat > "$ISO/boot/grub/grub.cfg" <<'CFG'
set timeout=2
set default=0
insmod all_video
menuentry "LLMOS" {
	linux /boot/vmlinuz quiet loglevel=3 console=ttyS0,115200 console=tty0
	initrd /boot/initramfs
}
menuentry "LLMOS (text only)" {
	linux /boot/vmlinuz quiet loglevel=3 llmos.text console=ttyS0,115200 console=tty0
	initrd /boot/initramfs
}
menuentry "LLMOS (rescue shell)" {
	linux /boot/vmlinuz llmos.rescue console=ttyS0,115200 console=tty0
	initrd /boot/initramfs
}
CFG

step "iso"
grub-mkrescue -o "$OUT/llmos.iso" "$ISO" -- -volid LLMOS 2>&1 | grep -v '^xorriso : UPDATE' || true
ls -lh "$OUT/llmos.iso"
