#!/usr/bin/env bash
# macOS launcher: bootstraps .venv, runs the CLI wizard on first run,
# then launches the app and forwards CLI args to app.py.
# One-time: chmod +x run_app.command
set -e
cd "$(dirname "$0")"

if [ "${1:-}" = "--launcher-help" ]; then
    echo "Usage: ./run_app.command [app.py args]"
    echo
    echo "Examples:"
    echo "  ./run_app.command"
    echo "  ./run_app.command --headless"
    echo "  ./run_app.command --config config.yaml"
    exit 0
fi

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

if [ ! -f "config.yaml" ] && [ "${1:-}" != "--help" ]; then
    echo
    .venv/bin/python3 -m src.wizard
fi

exec .venv/bin/python3 app.py "$@"
