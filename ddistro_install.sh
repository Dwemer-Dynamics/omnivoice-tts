#!/bin/bash

set -euo pipefail

BASE_DIR="${OMNIVOICE_BASE_DIR:-/home/dwemer}"
REPO_URL="${OMNIVOICE_REPO_URL:-https://github.com/Dwemer-Dynamics/omnivoice-tts}"
REPO_DIR="$BASE_DIR/omnivoice-tts"
VENV_DIR="$REPO_DIR/venv"
WEB_LINK="${OMNIVOICE_WEB_LINK:-/var/www/html/OmniVoice}"

echo "=== DwemerDistro OmniVoice TTS setup ==="
echo
echo "This installs the optional Multilingual OmniVoice TTS component."
echo "It uses its own Python venv and listens on 0.0.0.0:8021 for local and LAN clients while installed."
echo

if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git is required to install OmniVoice."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required to install OmniVoice."
    exit 1
fi

mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
    if [ -d "$REPO_DIR" ]; then
        echo "Using existing non-git component directory: $REPO_DIR"
    else
        echo "Cloning OmniVoice component..."
        git clone "$REPO_URL" "$REPO_DIR"
    fi
else
    echo "Updating OmniVoice component..."
    git -C "$REPO_DIR" pull --ff-only
fi

cd "$REPO_DIR"

mkdir -p voices reports logs diagnostics model_cache model_cache/huggingface model_cache/huggingface/hub
chmod +x ddistro_install.sh conf.sh start-gpu.sh omnivoice_cli.py
chmod -R a+rwX voices reports logs diagnostics model_cache languages config.json 2>/dev/null || true
rm -f "$REPO_DIR/start.sh"

if [ "${OMNIVOICE_SKIP_WEB_UI:-0}" = "1" ]; then
    echo "Skipping web UI publishing because OMNIVOICE_SKIP_WEB_UI=1."
elif [ -d "$(dirname "$WEB_LINK")" ]; then
    echo "Publishing web control panel..."
    if ln -sfn "$REPO_DIR/web" "$WEB_LINK" 2>/dev/null; then
        echo "Web UI: $WEB_LINK"
    else
        echo "WARNING: could not create web UI symlink at $WEB_LINK."
        echo "         Run with sufficient permissions or set OMNIVOICE_WEB_LINK."
    fi
else
    echo "Apache web root not found; skipping web UI publishing."
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

source "$VENV_DIR/bin/activate"

echo "Installing Python dependencies..."
if [ "${OMNIVOICE_SKIP_DEPENDENCIES:-0}" = "1" ]; then
    echo "Skipping dependency install because OMNIVOICE_SKIP_DEPENDENCIES=1."
else
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install -r requirements_torch_cuda128.txt
    python -m pip install -r requirements_runtime.txt
    python -m pip check
fi

echo
echo "Running doctor..."
if [ "${OMNIVOICE_SKIP_DOCTOR:-0}" = "1" ]; then
    echo "Skipping doctor because OMNIVOICE_SKIP_DOCTOR=1."
else
    python omnivoice_cli.py doctor || true
fi
