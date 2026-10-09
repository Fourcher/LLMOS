#!/bin/bash
# Make the zip to give someone LLM OS: what they need and nothing else.
#
#   LLM OS/
#     Start Here (Mac).command    Start Here (Windows).bat    Start Here (Linux).sh
#     Support files/              LLM OS Setup, the two ISOs (PCs and Intel Macs / ARM), checksums, the guide
#
# usage: tools/package.sh [output.zip]      (default: <repo>/packages/LLM OS <version>.zip)
# Never writes to the Desktop or anywhere outside the project working folder.
# Refuses to package images that don't match the source they were built from (tools/check-fresh.py [--built-commit]).
set -euo pipefail
cd "/Volumes/Files/Claude Work Area/LLMOS/Support files"
TOP=..
VER=$(cat VERSION)
OUT=${1:-"$TOP/packages/LLM OS $VER.zip"}
mkdir -p "$(dirname "$OUT")"
# dist/ must be exactly what its recorded commit builds (later source merges are fine: they ship in the next release)
python3 tools/check-fresh.py >/dev/null || python3 tools/check-fresh.py --built-commit || { python3 tools/check-fresh.py; echo "!! rebuild first (tools/release.sh), then package"; exit 1; }
for f in dist/llmos-x86_64.iso dist/llmos-arm64.iso dist/SHA256SUMS dist/setup/llmos-setup.py dist/setup/index.html \
         dist/setup/start.sh dist/setup/start.ps1 "$TOP/Start Here (Mac).command" "$TOP/Start Here (Windows).bat" "$TOP/Start Here (Linux).sh"; do
    [ -f "$f" ] || { echo "!! missing: $f"; exit 1; }
done

STAGE=build/package; rm -rf "$STAGE"; P="$STAGE/LLM OS"; S="$P/Support files"
mkdir -p "$S/dist/setup"
cp -p "$TOP/Start Here (Mac).command" "$TOP/Start Here (Windows).bat" "$TOP/Start Here (Linux).sh" "$P/"
cp -p LICENSE VERSION "$S/"
cp -p dist/README.md dist/VERSION dist/RELEASE.json "$S/dist/"
cp -p dist/setup/llmos-setup.py dist/setup/index.html dist/setup/start.sh dist/setup/start.ps1 "$S/dist/setup/"
grep -E ' (llmos-x86_64|llmos-arm64)\.iso$' dist/SHA256SUMS > "$S/dist/SHA256SUMS"
ln -s "$PWD/dist/llmos-x86_64.iso" "$S/dist/llmos-x86_64.iso"        # zip stores what a link points to
ln -s "$PWD/dist/llmos-arm64.iso" "$S/dist/llmos-arm64.iso"

rm -f "$OUT"
echo "==> zipping (about $(du -shL "$P" | cut -f1)); the ISOs are already compressed, so they are stored as they are"
( cd "$STAGE" && zip -r -0 -q -X "$OLDPWD/$STAGE/out.zip" "LLM OS" -x '*.DS_Store' )
mv "$STAGE/out.zip" "$OUT"
rm -rf "$STAGE"
echo "==> $OUT ($(du -h "$OUT" | cut -f1))"
