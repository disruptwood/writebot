#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID=$(pgrep -f "python.*-m bot" || true)
[ -n "$PID" ] && kill "$PID" && sleep 1

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PYTHON_BIN="${SCRIPT_DIR}/venv/bin/python3"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"

nohup "$PYTHON_BIN" -m bot > /tmp/writebot.log 2>&1 &
echo "Started with PID $!"
sleep 1
tail -5 /tmp/writebot.log
