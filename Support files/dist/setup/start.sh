#!/bin/sh
# Starts LLM OS Setup (llmos-setup.py, next to this file) with Python 3.8 or newer: one already on this computer,
# or else a private copy of the official standalone build (python-build-standalone), fetched once (about 25 MB)
# into this user's cache and used only after its SHA-256 matches the published one. Nothing is installed.
# usage: start.sh mac|linux   (the Start Here files call it)
cd "$(dirname "$0")" || exit 1
KIND=${1:-linux}
say() { printf '  %s\n' "$*"; }
works() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; }
hold() { [ "$KIND" = mac ] && { printf '\n  Press Return to close this window. '; read -r _; }; }
sha256() { { shasum -a 256 "$1" 2>/dev/null || sha256sum "$1" 2>/dev/null || openssl dgst -sha256 -r "$1"; } | awk '{print $1; exit}'; }

if [ "$KIND" = mac ]; then
    printf '\033]0;LLM OS Setup\007'; clear 2>/dev/null
    CACHE=${LLMOS_PY_CACHE:-"$HOME/Library/Caches/LLM OS Setup"}
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then TARGET=aarch64-apple-darwin; SUM=9e01f63bbb08576cd9c8bc2d0564d098cb30c8453a0cd4bcf6aef458f6d2a147
    else TARGET=x86_64-apple-darwin; SUM=b4dad38ba6a344555ccb71a1b08caad0a6c0dda88c5803658bc95bd7f04e9f5c; fi
    # Apple's /usr/bin/python3 is only a placeholder until the Command Line Tools are installed (running it then
    # pops up an installer), so it is tried only when they are.
    CANDIDATES="/opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3"
    xcode-select -p >/dev/null 2>&1 && CANDIDATES="$CANDIDATES /usr/bin/python3"
else
    CACHE=${LLMOS_PY_CACHE:-"${XDG_CACHE_HOME:-$HOME/.cache}/llmos-setup"}
    case "$(uname -m)" in
        aarch64|arm64) TARGET=aarch64-unknown-linux-gnu; SUM=6e9641400f8debd9b7924b27b5ff0662c372852382e291a76c450c7b67414cf6 ;;
        *)             TARGET=x86_64-unknown-linux-gnu; SUM=4595c5589fff7bf0cb158d9a88a797e0d791fa33830770fcb7bf3f4b104feeae ;;
    esac
    CANDIDATES="python3 /usr/bin/python3 /usr/local/bin/python3"
fi
URL=${LLMOS_PY_URL:-"https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.13.16%2B20261003-$TARGET-install_only_stripped.tar.gz"}
SUM=${LLMOS_PY_SHA256:-$SUM}
PRIVATE="$CACHE/python/bin/python3"

PY=""
[ -x "$PRIVATE" ] && works "$PRIVATE" && PY=$PRIVATE
if [ -z "$PY" ] && [ -z "${LLMOS_PY_SKIP_SYSTEM:-}" ]; then
    for c in $CANDIDATES; do
        if command -v "$c" >/dev/null 2>&1 && works "$c"; then PY=$c; break; fi
    done
fi

if [ -z "$PY" ]; then
    say "Getting Python for this setup (one time, about 25 MB)..."
    part="$CACHE/python.tar.gz.part"
    fetch() {
        if command -v curl >/dev/null 2>&1; then curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$part" "$URL"
        elif command -v wget >/dev/null 2>&1; then wget -O "$part" "$URL"
        else say "Neither curl nor wget is available to download it."; return 1; fi
    }
    if mkdir -p "$CACHE" && fetch; then
        if [ "$(sha256 "$part")" = "$SUM" ]; then
            rm -rf "$CACHE/python" && tar -xzf "$part" -C "$CACHE" && works "$PRIVATE" && PY=$PRIVATE
        else
            say "The download didn't match its published checksum, so it wasn't used."
        fi
    fi
    rm -f "$part"
fi

if [ -z "$PY" ]; then
    echo
    if [ "$KIND" = mac ]; then
        say "Setup needs Python, which Apple provides for free."
        say "A window will ask to install the \"command line developer tools\": click Install,"
        say "wait for it to finish, then open Start Here again."
        [ -z "${LLMOS_PY_NO_FALLBACK:-}" ] && xcode-select --install >/dev/null 2>&1
    else
        say "Setup needs Python 3. Connect to the internet and run Start Here again,"
        say "or install it first (for example: sudo apt install python3), then run Start Here again."
    fi
    hold
    exit 1
fi

exec "$PY" llmos-setup.py
