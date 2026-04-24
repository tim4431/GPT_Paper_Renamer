#!/usr/bin/env bash
# macOS launcher: bootstraps .venv, runs the CLI wizard on first run,
# then launches the tray app.
# One-time: chmod +x run_app.command
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python3" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "ERROR: python3 not found. Install Python 3.10+ (e.g. 'brew install python')."
        exit 1
    fi
    echo "Using Python: $(command -v python3) ($(python3 --version))"
    echo "Creating virtual environment in .venv ..."
    python3 -m venv .venv
    echo "Installing dependencies (first run only)..."
    .venv/bin/python3 -m pip install --upgrade pip
    .venv/bin/python3 -m pip install -r requirements.txt
    echo "Setup complete."
fi

if [ ! -f "config.yaml" ]; then
    echo
    .venv/bin/python3 -m src.wizard
fi

exec .venv/bin/python3 app.py
