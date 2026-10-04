#!/bin/sh
# LLM OS Setup for Linux — run this file: double-click it if your file manager offers "Run",
# or in a terminal:  sh "1 - START HERE (Linux).sh"
cd "$(dirname "$0")" || exit 1
printf '\n  LLM OS Setup\n  ------------\n  Starting the setup page in your web browser...\n\n'
if ! command -v python3 >/dev/null 2>&1; then
    echo "  One thing first: this setup needs Python 3. Install it, for example:"
    echo "    sudo apt install python3     (Debian, Ubuntu, Mint)"
    echo "    sudo dnf install python3     (Fedora)"
    echo "  then run this file again."
    exit 1
fi
exec python3 setup/llmos-setup.py
