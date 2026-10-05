#!/bin/bash
# Fetch the x86-64 Secure Boot boot chain (Debian's Microsoft-signed shim, signed GRUB and signed kernel, as
# pinned in src/rootfs/usr/share/llmos/secureboot.env) into build/cache, checking every SHA-256. Also fetches
# Debian's OVMF firmware for the tests (a virtual PC with Secure Boot enforced and Microsoft's keys enrolled)
# and unpacks the two files they use into build/cache/ovmf. Safe to run again: verified files are kept.
set -eu
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
mkdir -p build/cache/ovmf
. src/rootfs/usr/share/llmos/secureboot.env
OVMF="debian/pool/main/e/edk2/ovmf_2025.02-8+deb13u1_all.deb 78e0d54df11fc77406cb7a0bc9a39e5bca6d1cbe06556b91d9a73491c52decdf"
fetch() {   # archive-path sha256
    local f="build/cache/$(basename "$1")"
    if [ -f "$f" ] && [ "$(shasum -a 256 "$f" | cut -d' ' -f1)" = "$2" ]; then echo "  ok   $(basename "$1") (cached)"; return; fi
    curl -fsSL --retry 3 -o "$f.part" "https://deb.debian.org/$1"
    [ "$(shasum -a 256 "$f.part" | cut -d' ' -f1)" = "$2" ] || { rm -f "$f.part"; echo "!! HASH MISMATCH: $1"; exit 1; }
    mv "$f.part" "$f"; echo "  ok   $(basename "$1") ($(du -h "$f" | cut -f1), verified)"
}
set -- $SB_DEBS $OVMF
while [ $# -ge 2 ]; do fetch "$1" "$2"; shift 2; done
if [ ! -f build/cache/ovmf/OVMF_CODE_4M.secboot.fd ] || [ ! -f build/cache/ovmf/OVMF_VARS_4M.ms.fd ]; then
    T=$(mktemp -d); (cd "$T" && bsdtar -xf "$OLDPWD/build/cache/$(basename "${OVMF%% *}")" data.tar.xz && bsdtar -xf data.tar.xz \
        ./usr/share/OVMF/OVMF_CODE_4M.secboot.fd ./usr/share/OVMF/OVMF_VARS_4M.ms.fd)
    cp "$T/usr/share/OVMF/OVMF_CODE_4M.secboot.fd" "$T/usr/share/OVMF/OVMF_VARS_4M.ms.fd" build/cache/ovmf/; rm -rf "$T"
fi
echo "  ok   test firmware: build/cache/ovmf/OVMF_CODE_4M.secboot.fd + OVMF_VARS_4M.ms.fd"
