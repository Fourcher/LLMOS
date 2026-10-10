#!/bin/bash
# Wrapper: runs tools/realuser-smoke.py from the Support files folder with the same arguments.
cd "$(dirname "$0")/.." && exec python3 tools/realuser-smoke.py "$@"
