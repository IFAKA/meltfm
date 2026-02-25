#!/bin/bash
cd "$(dirname "$0")"
cd web && npm run build && cd ..
uv run python radio.py
