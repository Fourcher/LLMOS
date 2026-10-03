#!/bin/sh
# Run LLM OS on an Apple Silicon Mac (or any arm64 host with QEMU).
#
#   brew install qemu llama.cpp      # llama.cpp is optional: enables host-GPU mode
#   ./run-llmos.sh
#
# The OS runs in the window that opens (its graphical desk); this terminal
# shows a spare text console (press Enter here to use it). Quit by saying
# `shutdown` in the window, or with Ctrl-A then X in this terminal.
#
# Host-GPU mode (macOS, default when llama.cpp is installed): the on-device
# model runs on the Mac's GPU (Metal) instead of the VM's CPU cores -- several
# times faster. The model file is fetched once from the lab's official repo,
# verified against the SHA-256 in catalog.json, served on 127.0.0.1 only, and
# reached by the guest over the VM's private link. Nothing leaves the Mac.
#   LLMOS_HOST_GPU=0        force the model to run inside the VM instead
#   LLMOS_MODEL=<id>        which model to serve (ids: see catalog.json)
set -eu
cd "$(dirname "$0")"

IMG=${LLMOS_IMAGE:-llmos-arm64.qcow2}
CPUS=${LLMOS_CPUS:-4}
VARS=${IMG%.qcow2}.vars.fd   # UEFI variable store, created on first run
HOSTGPU=${LLMOS_HOST_GPU:-auto}
MODEL_ID=${LLMOS_MODEL:-ministral-3-3b}

if ! command -v qemu-system-aarch64 >/dev/null 2>&1; then
    echo "qemu-system-aarch64 not found. Install it with:  brew install qemu" >&2
    exit 1
fi
[ -f "$IMG" ] || { echo "image not found: $IMG" >&2; exit 1; }

FW=$(dirname "$(dirname "$(command -v qemu-system-aarch64)")")/share/qemu
[ -f "$VARS" ] || cp "$FW/edk2-arm-vars.fd" "$VARS"

case "$(uname -s)" in
  Darwin) ACCEL="-accel hvf"; AUDIO="-audiodev coreaudio,id=snd0"; DISPLAY_OPT="-display cocoa,show-cursor=on,zoom-to-fit=on" ;;
  Linux)  ACCEL="-accel kvm";  AUDIO="-audiodev pa,id=snd0";        DISPLAY_OPT="-display gtk,zoom-to-fit=on" ;;
  *)      ACCEL="-accel tcg";  AUDIO="-audiodev none,id=snd0";      DISPLAY_OPT="-display none" ;;
esac
[ "${LLMOS_HEADLESS:-0}" = 1 ] && DISPLAY_OPT="-display none"

# host time zone -> guest (read by the OS at boot; change it later by just
# asking, e.g. "set my time zone to Tokyo")
TZNAME=${TZ:-$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')}
# the Mac's language, to pre-select it at first run (en, fr, zh, ...)
LANGCODE=$(printf '%s' "${LLMOS_LANG:-${LANG:-en}}" | cut -c1-2 | tr 'A-Z' 'a-z')

# ---------------------------------------------------------------- host-GPU mode
HOST_ARGS=""
HOSTPID=""
fetch_verified() {  # file repo sha256 -> models/file, or fails
    if [ -f "models/$1" ] && [ "$(shasum -a 256 "models/$1" | cut -d' ' -f1)" = "$3" ]; then
        return 0
    fi
    echo "fetching $1 from huggingface.co/$2 (one time, verified by SHA-256) ..."
    curl -L --fail --progress-bar -o "models/$1.part" "https://huggingface.co/$2/resolve/main/$1" || return 1
    if [ "$(shasum -a 256 "models/$1.part" | cut -d' ' -f1)" != "$3" ]; then
        echo "checksum mismatch for $1 -- discarded" >&2; rm -f "models/$1.part"; return 1
    fi
    mv "models/$1.part" "models/$1"
}
if [ "$HOSTGPU" != 0 ] && [ "$(uname -s)" = Darwin ] && [ -f catalog.json ] \
   && command -v llama-server >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    eval "$(python3 -c '
import json, sys
m = next((x for x in json.load(open("catalog.json")) if x["id"] == sys.argv[1]), None)
if m:
    for k in ("file", "repo", "sha256", "draft_file", "draft_repo", "draft_sha256"):
        print("M_%s=%s" % (k.upper(), repr(m.get(k, ""))))
' "$MODEL_ID")"
    if [ -z "${M_FILE:-}" ]; then
        echo "unknown LLMOS_MODEL '$MODEL_ID' (see catalog.json); running the model inside the VM" >&2
    else
        mkdir -p models
        if fetch_verified "$M_FILE" "$M_REPO" "$M_SHA256" \
           && { [ -z "$M_DRAFT_FILE" ] || fetch_verified "$M_DRAFT_FILE" "$M_DRAFT_REPO" "$M_DRAFT_SHA256"; }; then
            SPEC=""
            [ -n "$M_DRAFT_FILE" ] && SPEC="--spec-type draft-mtp -md models/$M_DRAFT_FILE"
            # a free local port for the model server (something else, e.g. a
            # media player, may already hold 8080 on this Mac)
            PORT=""
            for p in ${LLMOS_MODEL_PORT:-} 8080 8090 8095 18080 28080; do
                [ -n "$p" ] || continue
                if ! lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then PORT=$p; break; fi
            done
            PORT=${PORT:-8080}
            # shellcheck disable=SC2086
            llama-server -m "models/$M_FILE" --host 127.0.0.1 --port "$PORT" --jinja -c 16384 \
                -ngl 99 -np 1 --no-webui --cache-reuse 256 $SPEC > host-model.log 2>&1 &
            HOSTPID=$!
            i=0
            while [ $i -lt 120 ] && ! curl -s "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q ok; do
                sleep 1; i=$((i + 1))
            done
            if curl -s "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q ok; then
                HOST_ARGS="-fw_cfg name=opt/llmos/model_url,string=http://10.0.2.2:$PORT -fw_cfg name=opt/llmos/model_id,string=$MODEL_ID"
                echo "host-GPU mode: $MODEL_ID served on this Mac's GPU (port $PORT)"
            else
                echo "the host model server did not start (see host-model.log); using the VM's CPU instead" >&2
                kill "$HOSTPID" 2>/dev/null; HOSTPID=""
            fi
        fi
    fi
fi
# the VM needs the model's RAM only when it runs the model itself
RAM=${LLMOS_RAM:-$([ -n "$HOST_ARGS" ] && echo 3072 || echo 6144)}

# ---------------------------------------------------------------- microphone
# QEMU on macOS cannot capture audio, so voice input reaches the guest through
# a tiny bridge that streams the Mac's microphone over the VM's private link
# (push-to-talk only: the mic is open only while the OS is listening).
MICPID=""
if [ "$(uname -s)" = Darwin ] && [ -f mic-bridge.py ] && command -v ffmpeg >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    python3 mic-bridge.py > mic-bridge.log 2>&1 &
    MICPID=$!
    echo "voice input: microphone bridge running (say 'voice' at the prompt)"
elif [ "$(uname -s)" = Darwin ]; then
    echo "voice input needs ffmpeg:  brew install ffmpeg   (optional)"
fi
trap 'kill "$HOSTPID" "$MICPID" 2>/dev/null' EXIT INT TERM

# shellcheck disable=SC2086
qemu-system-aarch64 \
  -machine virt -cpu host $ACCEL -smp "$CPUS" -m "$RAM" \
  -drive if=pflash,format=raw,readonly=on,file="$FW/edk2-aarch64-code.fd" \
  -drive if=pflash,format=raw,file="$VARS" \
  -drive file="$IMG",format=qcow2,if=virtio,discard=unmap \
  -nic user,model=virtio-net-pci \
  -device virtio-gpu-pci,xres="${LLMOS_WIDTH:-1440}",yres="${LLMOS_HEIGHT:-900}" -device virtio-keyboard-pci -device virtio-tablet-pci \
  $AUDIO -device virtio-sound-pci,audiodev=snd0 \
  $DISPLAY_OPT \
  -fw_cfg name=opt/llmos/tz,string="${TZNAME:-UTC}" -fw_cfg name=opt/llmos/lang,string="${LANGCODE:-en}" $HOST_ARGS \
  -serial mon:stdio -monitor none \
  "$@"
