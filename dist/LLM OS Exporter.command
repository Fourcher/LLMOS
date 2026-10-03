#!/bin/bash
# macOS: double-click to open the LLM OS Exporter (needs Python 3, which macOS offers to install if missing)
cd "$(dirname "$0")/exporter" && exec python3 exporter.py
