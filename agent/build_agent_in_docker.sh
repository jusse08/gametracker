#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="/out/agent"
SRC_DIR="/src/agent"

mkdir -p "$OUT_DIR"
cd "$SRC_DIR"

echo "[agent-builder] Installing Python dependencies..."
python -m pip install --upgrade "pip<25" "setuptools<70" wheel || true
pip install --no-cache-dir \
  "requests>=2.31,<2.33" \
  "websocket-client>=1.8,<1.9" \
  "psutil>=5.9,<6.0" \
  "pystray>=0.19,<0.20" \
  "Pillow>=9.2,<10.0" \
  "pyinstaller>=5.6,<6.0"

echo "[agent-builder] Building GameTrackerAgent.exe..."
pyinstaller --noconfirm --clean --onefile --noconsole --name GameTrackerAgent agent.py

EXE_PATH="$(find "$SRC_DIR/dist" -type f -name 'GameTrackerAgent.exe' | head -n 1 || true)"
if [[ -z "$EXE_PATH" ]]; then
  echo "[agent-builder] ERROR: GameTrackerAgent.exe was not produced"
  exit 1
fi

cp "$EXE_PATH" "$OUT_DIR/GameTrackerAgent.exe"

echo "[agent-builder] Build complete: $OUT_DIR/GameTrackerAgent.exe"
