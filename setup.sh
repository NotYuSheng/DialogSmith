#!/usr/bin/env bash
#
# Cross-platform setup for Linux / macOS (Windows users: run setup.bat).
# Creates a venv, installs pinned dependencies, and processes your Telegram
# export into a training-ready ShareGPT dataset.
#
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

PYTHON="${PYTHON:-python3}"

echo "[1/4] Creating virtual environment (venv)..."
"$PYTHON" -m venv venv

echo "[2/4] Installing dependencies (this can take a while)..."
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt

echo "[3/4] Preparing .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "      Created .env from .env.example — edit it to enable optional LLM validation."
fi

echo "[4/4] Processing Telegram export (data/result.json -> data/chat_sharegpt.json)..."
mkdir -p data
if [ ! -f data/result.json ]; then
  echo "      data/result.json not found. Place your Telegram export there, then re-run." >&2
  exit 1
fi
./venv/bin/python -m ingest --source telegram

cat <<'EOF'

All steps completed successfully.

Next, activate the environment and launch training:

  source venv/bin/activate
  llamafactory-cli train configs/train_lora.yaml

See README.md for export/merge and inference instructions.
EOF
