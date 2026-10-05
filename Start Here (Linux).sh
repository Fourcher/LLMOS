#!/bin/sh
# LLM OS Setup. In the file manager: right-click this file and choose "Run as a Program" (or "Run").
# In a terminal:  sh "Start Here (Linux).sh"
S="$(dirname "$0")/Support files/dist/setup/start.sh"
if [ ! -f "$S" ]; then
    echo "  The 'Support files' folder must stay next to this file. Keep the LLM OS folder together, then try again."
    exit 1
fi
exec /bin/sh "$S" linux
