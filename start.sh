#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PYTHON_BIN="${SCRIPT_DIR}/venv/bin/python3"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"

exec "$PYTHON_BIN" -m bot
