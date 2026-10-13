#!/bin/sh
# LLM OS installer. Runs INSIDE the official Alpine "virt" live ISO and turns
# the target disk into a bootable LLM OS. Every package comes from the official,
# signature-verified Alpine repositories; the model comes from the original
# lab's Hugging Face repo and is checked against its published SHA-256.
#
#   wget -qO- http://10.0.2.2:8765/src/install.sh | sh
#
# Two targets:
#   aarch64  a virtual-machine image (Apple Silicon Macs / arm64 hosts):
#            Alpine's virt kernel, UEFI + GRUB, serial console preferred.
#   x86_64   a real-computer image for ordinary PCs and laptops: Wi-Fi/GPU/
#            sound firmware, CPU microcode, NVMe-capable initramfs, iwd for
#            Wi-Fi, screen console preferred. It starts with Secure Boot on:
#            UEFI boots Debian's Microsoft-signed shim, Debian's signed GRUB
#            and Debian's signed kernel (secureboot.env pins them); BIOS boots
#            Alpine's GRUB. Also boots in QEMU.
#
# PAYLOAD (env) is where src/ and the model cache are served from.
set -eu

PAYLOAD=${PAYLOAD:-http://10.0.2.2:8765}
DISK=${DISK:-/dev/vda}
ARCH=$(apk --print-arch)
ALPINE=v3.24
TARGET=/mnt

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

case "$ARCH" in
  aarch64) SERIAL=ttyAMA0 ;;
  x86_64)  SERIAL=ttyS0 ;;
  *) echo "unsupported arch $ARCH"; exit 1 ;;
esac

log "network + official repositories"
setup-interfaces -a -r >/dev/null 2>&1 || true
cat > /etc/apk/repositories <<EOF
https://dl-cdn.alpinelinux.org/alpine/$ALPINE/main
https://dl-cdn.alpinelinux.org/alpine/$ALPINE/community
EOF
apk update -q
apk add -q sfdisk e2fsprogs dosfstools blkid

# ------------------------------------------------------------------ disk + base
if [ "$ARCH" = aarch64 ]; then
  log "partition + base system on $DISK (VM image: UEFI, virt kernel)"
  export USE_EFI=1 BOOTLOADER=grub DISKLABEL=gpt BOOTFS=vfat BOOT_SIZE=128
  export ROOTFS=ext4 SWAP_SIZE=0 ERASE_DISKS="$DISK"
  # the screen (tty1) last = the kernel's preferred console: the graphical
  # desk starts there; the serial line is a spare text console (llmos-login)
  export KERNELOPTS="quiet loglevel=3 console=$SERIAL console=tty1"
  setup-disk -m sys -s 0 "$DISK"
  mount "${DISK}2" $TARGET
  mount "${DISK}1" $TARGET/boot/efi
  ROOTDEV=${DISK}2; ESPDEV=${DISK}1
else
  log "partition + base system on $DISK (real computer: BIOS + UEFI, lts kernel)"
  # the live kernel loads filesystem drivers on demand only
  modprobe ext4 2>/dev/null || true; modprobe vfat 2>/dev/null || true; modprobe nls_utf8 2>/dev/null || true
  # GPT: BIOS boot partition (for GRUB's core image), EFI system partition, root
  sfdisk --quiet --wipe always --label gpt "$DISK" <<'EOF'
,2M,21686148-6449-6E6F-744E-656564454649
,256M,C12A7328-F81F-11D2-BA4B-00A0C93EC93B
,,L
EOF
  # make sure the kernel has re-read the table and the device nodes exist
  blockdev --rereadpt "$DISK" 2>/dev/null || true
  mdev -s 2>/dev/null || true
  for i in 1 2 3 4 5 6 7 8 9 10; do [ -b "${DISK}3" ] && break; sleep 1; mdev -s 2>/dev/null || true; done
  [ -b "${DISK}3" ] || { echo "partition devices did not appear"; exit 1; }
  mkfs.vfat -F32 -n EFI "${DISK}2" >/dev/null
  mkfs.ext4 -q -L llmos "${DISK}3"
  mount -t ext4 "${DISK}3" $TARGET
  mkdir -p $TARGET/boot/efi
  mount -t vfat "${DISK}2" $TARGET/boot/efi
  ROOTDEV=${DISK}3; ESPDEV=${DISK}2
  mkdir -p $TARGET/etc/apk
  cp -r /etc/apk/keys $TARGET/etc/apk/
  cp /etc/apk/repositories $TARGET/etc/apk/repositories
  apk add --root $TARGET --initdb --keys-dir /etc/apk/keys --repositories-file /etc/apk/repositories -q \
      alpine-base openrc busybox-openrc mkinitfs
  # initramfs: NVMe, SD/eMMC and the framebuffer console must work on a laptop
  cat > $TARGET/etc/mkinitfs/mkinitfs.conf <<'EOF'
features="ata base ide scsi usb virtio ext4 nvme mmc kms"
EOF
  # firmware for the usual laptop Wi-Fi (Intel iwlwifi is inside -intel),
  # Bluetooth and graphics; ~250 MB in total
  apk add --root $TARGET -q intel-ucode amd-ucode grub-bios grub-efi \
      linux-firmware-intel linux-firmware-i915 linux-firmware-amdgpu linux-firmware-radeon \
      linux-firmware-ath9k_htc linux-firmware-ath10k linux-firmware-ath11k linux-firmware-ath12k \
      linux-firmware-qca linux-firmware-rtlwifi linux-firmware-rtw88 linux-firmware-rtw89 \
      linux-firmware-realtek linux-firmware-rtl_nic linux-firmware-rtl_bt linux-firmware-brcm \
      linux-firmware-mediatek linux-firmware-other
  # fstab by UUID (disks get different names on real machines)
  cat > $TARGET/etc/fstab <<EOF
UUID=$(blkid -s UUID -o value "$ROOTDEV")  /         ext4  rw,relatime  0 1
UUID=$(blkid -s UUID -o value "$ESPDEV")   /boot/efi vfat  defaults     0 2
EOF
  cat > $TARGET/etc/network/interfaces <<'EOF'
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
EOF
fi

log "packages (official Alpine $ALPINE, signed)"
cp /etc/apk/repositories $TARGET/etc/apk/repositories
PKGS="
  python3 e2fsprogs dosfstools curl ca-certificates tzdata nano less
  llama-server llama.cpp-cpu
  whisper.cpp
  yt-dlp quickjs-ng mpv
  alsa-utils espeak-ng chafa
  tor cryptsetup nftables
  kbd font-terminus
  cage seatd seatd-launch foot w3m
  eudev udev-init-scripts
  iwd dbus wireless-regdb
  sfdisk lsblk blkid wipefs partx efibootmgr rsync os-prober
  labwc gtk4.0 webkit2gtk-6.0 py3-gobject3 grim wtype at-spi2-core py3-gobject3-atspi
  gst-plugins-good gst-plugins-bad gst-libav
  mesa-dri-gallium mesa-egl mesa-gles mesa-gbm
  font-inter font-jetbrains-mono font-noto font-noto-emoji font-noto-cjk
  font-noto-arabic font-noto-hebrew font-noto-devanagari font-noto-thai
  firefox thunar gvfs udisks2 tumbler ntfs-3g exfatprogs dosfstools
  mousepad ristretto abiword gnumeric xarchiver 7zip
  cups cups-filters avahi bluez
  pipewire wireplumber pipewire-pulse pipewire-alsa pavucontrol
  wlr-randr wlrctl lswt wl-clipboard flatpak mako libnotify swayidle wlopm wlsunset slurp playerctl xdg-desktop-portal xdg-desktop-portal-wlr poppler-utils wf-recorder imagemagick gvfs-mtp gvfs-gphoto2 wvkbd openssh-client openssh-keygen git rsync tesseract-ocr tesseract-ocr-data-eng smartmontools adwaita-icon-theme
  nmap clamav tshark tcpdump nikto john hydra aircrack-ng wireshark zaproxy ffuf
"
# shellcheck disable=SC2086
apk add --root $TARGET --no-cache -q $PKGS

log "LLM OS files"
wget -qO- "$PAYLOAD/build/work/payload.tar" | tar -x -o -C $TARGET     # -o: owned by root here, whoever made the archive
chmod 0755 $TARGET/usr/bin/llmos $TARGET/usr/bin/llmos-model-run $TARGET/usr/libexec/llmos-login $TARGET/usr/libexec/llmos-desk $TARGET/etc/init.d/llmos-*
# byte-compile the package with the target's own python: the build strips __pycache__, and /usr/lib/llmos is root-owned,
# so a desk running as the owner could not write it and would recompile the source on every start. Never fails the install.
chroot $TARGET python3 -m compileall -q -j 0 /usr/lib/llmos/llmos >/dev/null 2>&1 || chroot $TARGET python3 -m compileall -q /usr/lib/llmos/llmos >/dev/null 2>&1 || echo "note: could not precompile (it still works, starts a little slower)"
# the build stamp (`llmos version`, Settings); the version is the payload's own. The ISO build rewrites it with MEDIUM=live.
VER=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' $TARGET/usr/lib/llmos/llmos/__init__.py)
printf 'VERSION=%s\nBUILD=%s\nARCH=%s\nMEDIUM=disk\n' "$VER" "$(date +%Y-%m-%d)" "$ARCH" > $TARGET/etc/llmos-release

log "on-device model (verified)"
mkdir -p $TARGET/var/lib/llmos/models $TARGET/usr/share/llmos/voice
fetch_verify() {  # url dest sha256
  wget -q -O "$2" "$1"
  echo "$3  $2" | sha256sum -c -s || { echo "HASH MISMATCH: $2"; exit 1; }
}
. $TARGET/usr/share/llmos/preinstall.env   # MODEL_FILE MODEL_SHA256 WHISPER_FILE WHISPER_SHA256
fetch_verify "$PAYLOAD/build/cache/$MODEL_FILE" "$TARGET/var/lib/llmos/models/$MODEL_FILE" "$MODEL_SHA256"
fetch_verify "$PAYLOAD/build/cache/$WHISPER_FILE" "$TARGET/usr/share/llmos/voice/$WHISPER_FILE" "$WHISPER_SHA256"

log "search-by-meaning runtime (llama.cpp ${EMBED_LLAMA_COMMIT:-?}, built from source)"
# the target needs a working resolver for the runtime build (GitHub): the live system's, else QEMU's DNS at 10.0.2.3
if [ -s /etc/resolv.conf ] && grep -q nameserver /etc/resolv.conf; then cp /etc/resolv.conf $TARGET/etc/resolv.conf; else echo "nameserver 10.0.2.3" > $TARGET/etc/resolv.conf; fi
# the runtime is built and checked inside the target: it needs /dev, /proc and /sys there (bound again for the bootloader step)
for d in dev proc sys; do mountpoint -q $TARGET/$d || mount --bind /$d $TARGET/$d; done
# Alpine's llama.cpp is too old for EmbeddingGemma 2; a cached build for this commit and architecture is used when the
# build host has one, otherwise it is compiled here from the pinned upstream commit. The build tools leave afterwards.
EMBED_TAR="llama-embed-$EMBED_LLAMA_COMMIT-$ARCH.tar"
mkdir -p $TARGET/usr/lib/llmos/embed
if wget -q -O /tmp/embed.tar "$PAYLOAD/build/cache/$EMBED_TAR" 2>/dev/null && [ -s /tmp/embed.tar ]; then
  tar -x -o -C $TARGET/usr/lib/llmos/embed -f /tmp/embed.tar
else
  BUILD_DEPS="build-base cmake linux-headers git"
  apk add --root $TARGET --no-cache -q $BUILD_DEPS
  chroot $TARGET sh -c "set -e; rm -rf /tmp/lc; git init -q /tmp/lc; cd /tmp/lc; \
    git fetch -q --depth 1 https://github.com/ggml-org/llama.cpp $EMBED_LLAMA_COMMIT; git checkout -q FETCH_HEAD; \
    cmake -B build -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DGGML_NATIVE=OFF \
      -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON -DBUILD_SHARED_LIBS=ON -DCMAKE_INSTALL_RPATH='\$ORIGIN' \
      -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON >/dev/null; \
    cmake --build build --target llama-server -j\$(nproc) >/dev/null; \
    cp build/bin/llama-server build/bin/*.so* /usr/lib/llmos/embed/; rm -rf /tmp/lc"
  apk del --root $TARGET -q $BUILD_DEPS
  ( cd $TARGET/usr/lib/llmos/embed && tar -cf /tmp/embed.tar . )     # (kept by the build host when it collects the cache)
fi
chroot $TARGET /usr/lib/llmos/embed/llama-server --version >/dev/null 2>&1 || { echo "the search-by-meaning runtime does not run"; exit 1; }

log "system configuration"
echo llmos > $TARGET/etc/hostname
printf '127.0.0.1\tllmos localhost\n::1\t\tllmos localhost\n' > $TARGET/etc/hosts

# consoles: the OS runs on the screen (tty1) and on the serial line. Nothing
# else to log in to. Which one starts first is decided by llmos-login from
# the kernel's preferred console.
cat > $TARGET/etc/inittab <<EOF
::sysinit:/sbin/openrc sysinit
::sysinit:/sbin/openrc boot
::wait:/sbin/openrc default
$SERIAL::respawn:/sbin/getty -n -l /usr/libexec/llmos-login -L 115200 $SERIAL vt100
tty1::respawn:/sbin/getty -n -l /usr/libexec/llmos-login 38400 tty1
::ctrlaltdel:/sbin/reboot
::shutdown:/sbin/openrc shutdown
EOF

# nothing to log into with a password: root is locked, the console session
# is started directly by init (see /usr/libexec/llmos-login)
chroot $TARGET passwd -l root >/dev/null
chroot $TARGET dbus-uuidgen --ensure=/etc/machine-id 2>/dev/null || true   # D-Bus needs a machine id
: > $TARGET/etc/motd
printf 'LLM OS\n\n' > $TARGET/etc/issue

# /tmp in RAM; nothing sensitive survives a reboot there
grep -q ' /tmp ' $TARGET/etc/fstab || echo 'tmpfs /tmp tmpfs nosuid,nodev,mode=1777,size=512m 0 0' >> $TARGET/etc/fstab

# Wi-Fi (real hardware): iwd with its own DHCP client
mkdir -p $TARGET/etc/iwd
printf '[General]\nEnableNetworkConfiguration=true\n\n[Network]\nNameResolvingService=none\n' > $TARGET/etc/iwd/main.conf

# services (explicit for both targets; harmless where setup-disk already did it)
chroot $TARGET sh -eu <<'EOF' >/dev/null 2>&1
# udev (eudev) instead of busybox mdev: graphical programs find keyboards,
# mice and touchpads through it, and laptops get proper hotplug
for s in devfs dmesg; do rc-update add $s sysinit; done
rc-update del mdev sysinit 2>/dev/null || true
rc-update del hwdrivers sysinit 2>/dev/null || true
for s in udev udev-trigger udev-settle; do rc-update add $s sysinit; done
rc-update add udev-postmount default
for s in modules hwclock hostname sysctl bootmisc syslog loopback networking; do rc-update add $s boot; done
for s in killprocs mount-ro savecache; do rc-update add $s shutdown; done
rc-update add llmos-hw sysinit
rc-update add llmos-model default
rc-update add llmos-scheduler default
rc-update add llmos-ota default        # idle until the owner pairs it with their computer
rc-update add nftables default
rc-update add acpid default
rc-update add dbus default
rc-update add iwd default
# printing (driverless: modern printers need no driver), finding printers on the network, Bluetooth
for s in cupsd avahi-daemon bluetooth; do rc-update add $s default 2>/dev/null || true; done
# programs that are not Alpine packages (Spotify, VS Code, Zoom…) come from Flathub when asked for
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo 2>/dev/null || true
rc-update add alsa default 2>/dev/null || true
rc-update del crond default 2>/dev/null || true
rc-update del sshd default 2>/dev/null || true
rc-update del chronyd default 2>/dev/null || true
echo 'SYSLOGD_OPTS="-C512"' > /etc/conf.d/syslog     # logs stay in RAM
EOF

# owner account, opt-in at install time (LLMOS_OWNER=1, like PAYLOAD and DISK above); unset, empty or 0 = off.
# Only the account, its device groups, the rootd service and the marker file; the boot chain is unchanged.
if [ "${LLMOS_OWNER:-0}" = 1 ]; then
chroot $TARGET sh -eu <<'EOF' >/dev/null
getent group owner >/dev/null || addgroup -S owner
getent passwd owner >/dev/null || adduser -D -h /home/owner -s /bin/sh -G owner owner
for g in video input audio seat netdev plugdev; do
  getent group $g >/dev/null || addgroup -S $g
  id -nG owner | tr ' ' '\n' | grep -qx "$g" || addgroup owner "$g"
done
rc-update show default 2>/dev/null | grep -qw llmos-rootd || rc-update add llmos-rootd default
rc-update show default 2>/dev/null | grep -qw seatd || rc-update add seatd default
mkdir -p /var/cache/llmos
chown -R owner:owner /var/cache/llmos
mkdir -p /etc/llmos
echo owner > /etc/llmos/owner-user
EOF
fi

log "bootloader"
for d in dev proc sys; do mountpoint -q $TARGET/$d || mount --bind /$d $TARGET/$d; done
if [ "$ARCH" = aarch64 ]; then
  sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=0/' $TARGET/etc/default/grub
  grep -q '^GRUB_TIMEOUT=' $TARGET/etc/default/grub || echo 'GRUB_TIMEOUT=0' >> $TARGET/etc/default/grub
  # setup-disk writes "serial --unit=ttyAMA0", which GRUB rejects with an
  # error at every boot; with a zero timeout GRUB never needs the serial
  # terminal anyway (the firmware console already includes it), so drop it
  sed -i '/^GRUB_SERIAL_COMMAND=/d; /^GRUB_TERMINAL_INPUT=/d; /^GRUB_TERMINAL_OUTPUT=/d' $TARGET/etc/default/grub
  chroot $TARGET grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1
  mkdir -p $TARGET/boot/efi/EFI/BOOT
  cp $TARGET/boot/efi/EFI/alpine/grubaa64.efi $TARGET/boot/efi/EFI/BOOT/BOOTAA64.EFI 2>/dev/null || true
else
  # screen (tty1) last = preferred console on a real computer; net.ifnames=0
  # keeps wired = eth0 and Wi-Fi = wlan0 whatever the hardware
  cat > $TARGET/etc/default/grub <<EOF
GRUB_TIMEOUT=0
GRUB_DISABLE_SUBMENU=y
GRUB_DISABLE_RECOVERY=true
GRUB_CMDLINE_LINUX_DEFAULT="modules=sd-mod,usb-storage,nvme,ext4 quiet loglevel=3 net.ifnames=0 console=$SERIAL console=tty1"
EOF
  # The kernel and the UEFI boot chain come from Debian, signed, so the computer starts with Secure Boot on
  # (secureboot.env pins each package's SHA-256). The kernel keeps the "lts" file names the rest expects.
  log "kernel + Secure Boot boot chain (Debian: Microsoft-signed shim, signed GRUB, signed kernel; verified)"
  . $TARGET/usr/share/llmos/secureboot.env          # SB_KVER SB_DEBS
  apk add -q binutils xz >/dev/null                  # ar + xz to unpack .deb files (this live system only)
  SB=/tmp/secureboot; rm -rf $SB; mkdir -p $SB/root
  set -- $SB_DEBS
  while [ $# -ge 2 ]; do
    deb=$SB/$(basename "$1")
    fetch_verify "$PAYLOAD/build/cache/$(basename "$1")" "$deb" "$2"
    (cd $SB && ar x "$deb" data.tar.xz && xz -dc data.tar.xz | tar -x -C $SB/root && rm -f data.tar.xz "$deb")
    shift 2
  done
  cp $SB/root/boot/vmlinuz-$SB_KVER $TARGET/boot/vmlinuz-lts
  cp $SB/root/boot/config-$SB_KVER $TARGET/boot/config-lts
  mkdir -p $TARGET/lib/modules
  cp -a $SB/root/usr/lib/modules/$SB_KVER $TARGET/lib/modules/
  chroot $TARGET depmod -a $SB_KVER
  SBD=$TARGET/usr/share/llmos/secureboot; mkdir -p $SBD
  cp $SB/root/usr/lib/shim/shimx64.efi.signed $SBD/shimx64.efi
  cp $SB/root/usr/lib/shim/mmx64.efi.signed $SBD/mmx64.efi
  cp $SB/root/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed $SBD/grubx64.efi
  cp $SB/root/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed $SBD/gcdx64.efi
  echo "$SB_KVER" > $SBD/kernel-version
  rm -rf $SB
  chroot $TARGET mkinitfs -c /etc/mkinitfs/mkinitfs.conf -o /boot/initramfs-lts "$SB_KVER" >/dev/null
  # BIOS: Alpine's GRUB in the BIOS boot partition (BIOS has no Secure Boot)
  chroot $TARGET grub-install --target=i386-pc --boot-directory=/boot "$DISK" >/dev/null 2>&1
  # UEFI: the removable path EFI/BOOT/BOOTX64.EFI is the signed shim, which starts the signed GRUB next to it;
  # that GRUB reads EFI/debian/grub.cfg (its built-in place), which hands over to /boot/grub/grub.cfg
  ESP=$TARGET/boot/efi; mkdir -p $ESP/EFI/BOOT $ESP/EFI/debian
  cp $SBD/shimx64.efi $ESP/EFI/BOOT/BOOTX64.EFI
  cp $SBD/grubx64.efi $ESP/EFI/BOOT/grubx64.efi
  cp $SBD/mmx64.efi $ESP/EFI/BOOT/mmx64.efi
  printf '# LLM OS\nsearch --no-floppy --fs-uuid --set=root %s\nset prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n' \
      "$(blkid -s UUID -o value "$ROOTDEV")" > $ESP/EFI/debian/grub.cfg
  chroot $TARGET grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1
  grep -q 'vmlinuz-lts' $TARGET/boot/grub/grub.cfg || { echo "GRUB config has no kernel entry"; exit 1; }
  [ -s $TARGET/boot/initramfs-lts ] && [ -f $TARGET/lib/modules/$SB_KVER/modules.dep ] || { echo "ERROR: kernel install incomplete"; exit 1; }
fi
umount $TARGET/dev $TARGET/proc $TARGET/sys

log "package manifest (for the auditor: every package and version, all from Alpine's signed repos)"
mkdir -p $TARGET/etc/llmos
chroot $TARGET apk list -I 2>/dev/null | sort > $TARGET/etc/llmos/packages.txt || true

log "scrub build traces"
rm -rf $TARGET/var/cache/apk/* $TARGET/root/.ash_history $TARGET/root/.cache $TARGET/tmp/* 2>/dev/null || true
find $TARGET/var/log -type f -exec truncate -s 0 {} + 2>/dev/null || true
sync
fstrim -v $TARGET >/dev/null 2>&1 || true

log "done"
df -h $TARGET | tail -1
# unmount inner mounts first (busybox umount has no -R), then the root
umount "$TARGET/boot/efi" 2>/dev/null || true
umount "$TARGET/boot" 2>/dev/null || true
umount "$TARGET" || umount -l "$TARGET"
echo LLMOS_INSTALL_OK
