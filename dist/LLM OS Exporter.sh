#!/bin/sh
# Linux: run this (or double-click it where the file manager allows) to open the LLM OS Exporter
cd "$(dirname "$0")/exporter" && exec python3 exporter.py
