#!/bin/bash

set -euo pipefail

REPO_DIR="/home/dwemer/omnivoice-tts"
VENV_DIR="$REPO_DIR/venv"
LOG_FILE="$REPO_DIR/logs/server.log"

cd "$REPO_DIR"
mkdir -p logs

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "OmniVoice venv is missing at $VENV_DIR" >> "$LOG_FILE"
    exit 1
fi

source "$VENV_DIR/bin/activate"

PORT_STATUS="$(
python - <<'PY'
import socket
import urllib.request

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    in_use = sock.connect_ex(("127.0.0.1", 8021)) == 0
if in_use:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8021/health", timeout=2) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
        if response.status == 200 and '"model":"k2-fsa/OmniVoice"' in body:
            print("healthy_omnivoice")
        else:
            print("conflict")
    except Exception:
        print("conflict")
else:
    print("free")
PY
)"

if [ "$PORT_STATUS" = "healthy_omnivoice" ]; then
    echo "Port 127.0.0.1:8021 is already served by healthy OmniVoice; leaving it running." >> "$LOG_FILE"
    exit 0
fi

if [ "$PORT_STATUS" = "conflict" ]; then
    echo "Port 127.0.0.1:8021 is already in use; OmniVoice was not started." >> "$LOG_FILE"
    exit 1
fi

{
    echo
    echo "=== OmniVoice TTS start $(date -Iseconds) ==="
    echo "Binding to 127.0.0.1:8021"
} >> "$LOG_FILE"

setsid -f "$VENV_DIR/bin/python" "$REPO_DIR/omnivoice_cli.py" server --host 127.0.0.1 --port 8021 >> "$LOG_FILE" 2>&1 < /dev/null
