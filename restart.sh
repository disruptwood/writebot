#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Install / update dependencies
if [ -f venv/bin/pip ]; then
    venv/bin/pip install -q -r requirements.txt
else
    python3 -m venv venv
    venv/bin/pip install -q -r requirements.txt
fi

# Ensure data dir exists
mkdir -p data

# Restart via systemd
sudo systemctl restart writebot
sleep 2
sudo systemctl status writebot --no-pager
