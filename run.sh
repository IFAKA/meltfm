#!/bin/bash
cd "$(dirname "$0")"

cleanup() {
  echo "Shutting down ACE-Step (port 8001)..."
  lsof -ti :8001 | xargs kill -9 2>/dev/null
}
trap cleanup EXIT

cd web && npm run build && cd ..
uv run python radio.py
