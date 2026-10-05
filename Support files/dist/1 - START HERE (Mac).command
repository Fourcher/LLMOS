#!/bin/bash
# LLM OS Setup for a Mac — double-click this file to start.
#
# If macOS says it "cannot be opened" or "Apple could not verify" it: right-click (or Control-click) this file,
# choose Open, then click Open again. Or open System Settings → Privacy & Security and click "Open Anyway".
cd "$(dirname "$0")" || exit 1
clear
printf '\n  LLM OS Setup\n  ------------\n  Starting the setup page in your web browser…\n\n'

# Find a Python 3 that really runs. macOS keeps a placeholder at /usr/bin/python3 that only works once
# Apple's free Command Line Tools are installed, so real installs are tried first.
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    if [ -x "$c" ] && "$c" -c "import sys" 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ] && /usr/bin/xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 -c "import sys" 2>/dev/null; then
    PY=/usr/bin/python3
fi

if [ -z "$PY" ]; then
    cat <<'EOF'
  One thing first: this setup needs Python 3, which Apple provides for free.

  A window will now ask whether to install the "command line developer tools".
  Click "Install" and wait for it to finish (a few minutes), then double-click
  this START HERE file again.

EOF
    /usr/bin/xcode-select --install 2>/dev/null
    read -r -p "  Press Return to close this window. " _
    exit 0
fi

exec "$PY" setup/llmos-setup.py
