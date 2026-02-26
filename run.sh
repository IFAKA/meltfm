#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; }
info() { echo -e "  ${CYAN}→${RESET} $1"; }
warn() { echo -e "  ${YELLOW}!${RESET} $1"; }

# ─── Parse flags ──────────────────────────────────────────────────────────────
FORCE_BUILD=0
for arg in "$@"; do
  case "$arg" in
    --build|-b) FORCE_BUILD=1 ;;
  esac
done

# ─── Find uv ──────────────────────────────────────────────────────────────────
UV=""
for candidate in \
    "$(command -v uv 2>/dev/null || true)" \
    "$HOME/.local/bin/uv" \
    "$HOME/.cargo/bin/uv" \
    "/opt/homebrew/bin/uv" \
    "/usr/local/bin/uv"; do
  if [[ -x "$candidate" ]]; then
    UV="$candidate"
    break
  fi
done

if [[ -z "$UV" ]]; then
  fail "uv not found. Run ./setup.sh first, or install uv:"
  info "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# ─── Frontend build ───────────────────────────────────────────────────────────
DIST_DIR="$SCRIPT_DIR/web/dist"

if [[ $FORCE_BUILD -eq 1 ]] || [[ ! -d "$DIST_DIR" ]] || [[ -z "$(ls -A "$DIST_DIR" 2>/dev/null)" ]]; then
  if ! command -v node &>/dev/null; then
    fail "Node.js not found. Run ./setup.sh first."
    exit 1
  fi
  info "Building frontend..."
  cd "$SCRIPT_DIR/web"
  npm install --silent
  npm run build --silent
  cd "$SCRIPT_DIR"
  ok "Frontend built"
else
  ok "Frontend already built (use --build to rebuild)"
fi

# ─── Cleanup ACE-Step on exit ─────────────────────────────────────────────────
cleanup() {
  echo ""
  info "Shutting down ACE-Step (port 8001)..."
  lsof -ti :8001 | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT

# ─── Run ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}♪  meltfm${RESET}  →  http://localhost:$(grep "^WEB_PORT=" "$SCRIPT_DIR/.env" 2>/dev/null | cut -d= -f2 || echo 8888)"
echo ""

exec "$UV" run python radio.py
