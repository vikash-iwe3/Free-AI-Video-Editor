#!/usr/bin/env bash
# Free AI Video Editor launcher (Linux / macOS)
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
echo "Installing / updating dependencies..."
python3 -m pip install -q -r requirements.txt
[ "$1" = "asr" ] && python3 -m pip install -q -r requirements-asr.txt
echo "Starting Free AI Video Editor at http://127.0.0.1:8137"
python3 app.py
