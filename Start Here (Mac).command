#!/bin/bash
# LLM OS Setup: double-click this file to start.
S="$(dirname "$0")/Support files/dist/setup/start.sh"
if [ ! -f "$S" ]; then
    printf '\n  The "Support files" folder must stay next to this file.\n  Keep the LLM OS folder together, then try again.\n\n'
    read -r -p "  Press Return to close this window. " _
    exit 1
fi
exec /bin/bash "$S" mac
