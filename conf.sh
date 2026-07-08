#!/bin/bash

set -euo pipefail

REPO_DIR="/home/dwemer/omnivoice-tts"
VENV_DIR="$REPO_DIR/venv"
PORT=8021

if [ ! -d "$REPO_DIR" ]; then
    echo "Error: OmniVoice TTS is not installed at $REPO_DIR"
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Error: Python venv is missing. Run $REPO_DIR/ddistro_install.sh first."
    exit 1
fi

cd "$REPO_DIR"
source "$VENV_DIR/bin/activate"

port_in_use() {
    python - "$PORT" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

omnivoice_healthy() {
    python - <<'PY'
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8021/health", timeout=2) as response:
        body = response.read(4096).decode("utf-8", errors="replace")
    raise SystemExit(0 if response.status == 200 and '"model":"k2-fsa/OmniVoice"' in body else 1)
except Exception:
    raise SystemExit(1)
PY
}

while true; do
    if [ -t 1 ]; then
        clear
    fi
    cat << EOF
Multilingual OmniVoice TTS

Service port: 127.0.0.1:8021
Install path: $REPO_DIR
Web panel: http://127.0.0.1/OmniVoice/

1. Show doctor/status
2. Run verification smoke test
3. List installed languages
4. Set active language
5. List/audit prepared voices
6. Import one CHIM VoiceID
7. Calibrate one VoiceID
8. Build full selected-language CHIM library
9. Export voices to another TTS engine
10. Uninstall runtime (preserve voices)
0. Exit

EOF

    if ! read -r -p "Select an option: " selection; then
        exit 0
    fi
    selection="${selection//$'\r'/}"
    selection="${selection//$'\xef\xbb\xbf'/}"

    case "$selection" in
        1)
            python omnivoice_cli.py doctor
            if port_in_use; then
                if omnivoice_healthy; then
                    echo "Port $PORT: in use by healthy OmniVoice"
                else
                    echo "Port $PORT: in use by another or unhealthy service"
                fi
            else
                echo "Port $PORT: free"
            fi
            read -r -p "Press ENTER to continue." _
            ;;
        2)
            read -r -p "Language id/alias, or leave blank for active language: " lang
            lang="${lang//$'\r'/}"
            lang="${lang//$'\xef\xbb\xbf'/}"
            if [ -n "$lang" ]; then
                python omnivoice_cli.py verify --language "$lang" --write-library-report
            else
                python omnivoice_cli.py verify --write-library-report
            fi
            read -r -p "Press ENTER to continue." _
            ;;
        3)
            python omnivoice_cli.py languages
            read -r -p "Press ENTER to continue." _
            ;;
        4)
            read -r -p "Language id/alias (for example sk, es, fr, pt-br): " lang
            python omnivoice_cli.py set-language "$lang" --live-if-running
            read -r -p "Press ENTER to continue." _
            ;;
        5)
            read -r -p "Language id/alias or all [all]: " lang
            lang="${lang:-all}"
            python omnivoice_cli.py voices --language "$lang" --write-report
            read -r -p "Press ENTER to continue." _
            ;;
        6)
            read -r -p "Language id/alias: " lang
            read -r -p "CHIM VoiceID to import: " voice
            python omnivoice_cli.py import-chim --language "$lang" --voice "$voice"
            read -r -p "Press ENTER to continue." _
            ;;
        7)
            read -r -p "Language id/alias: " lang
            read -r -p "VoiceID to calibrate: " voice
            python omnivoice_cli.py calibrate --language "$lang" --voice "$voice"
            read -r -p "Press ENTER to continue." _
            ;;
        8)
            read -r -p "Language id/alias: " lang
            echo "This can take a long time and uses CUDA heavily."
            read -r -p "Type YES to build/calibrate the full library: " confirm
            if [ "$confirm" = "YES" ]; then
                python omnivoice_cli.py import-chim --language "$lang" --all
                python omnivoice_cli.py build-library --language "$lang" --all
            else
                echo "Canceled."
            fi
            read -r -p "Press ENTER to continue." _
            ;;
        9)
            read -r -p "Language id/alias: " lang
            read -r -p "Target [zip/chatterbox/pockettts/xtts]: " target
            target="${target:-zip}"
            read -r -p "Export one VoiceID, or leave blank to export all: " voice
            if [ -n "$voice" ]; then
                python omnivoice_cli.py export --language "$lang" --target "$target" --voice "$voice"
            else
                echo "Exporting all voices is explicit because it can overwrite a lot of speaker names."
                read -r -p "Type YES to export all runtime-ready voices: " confirm
                if [ "$confirm" = "YES" ]; then
                    python omnivoice_cli.py export --language "$lang" --target "$target" --all
                else
                    echo "Canceled."
                fi
            fi
            read -r -p "Press ENTER to continue." _
            ;;
        10)
            echo "This removes the runtime venv, but keeps voices/reports by default."
            read -r -p "Type YES to uninstall runtime: " confirm
            if [ "$confirm" = "YES" ]; then
                python omnivoice_cli.py uninstall --yes
            else
                python omnivoice_cli.py uninstall
            fi
            read -r -p "Press ENTER to continue." _
            ;;
        0)
            exit 0
            ;;
        *)
            echo "Invalid selection."
            sleep 1
            ;;
    esac
done
