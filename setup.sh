#!/usr/bin/env bash
set -euo pipefail

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALIAS_LINE="alias radio='${SCRIPT_DIR}/radio'  # ai-radio"
ZSHRC="$HOME/.zshrc"
ACESTEP_DIR="$HOME/ACE-Step"

echo ""
echo -e "${BOLD}  ♪  ai-radio — Setup${RESET}"
echo -e "  ─────────────────────────────────────────"
echo ""

# ─── 1. Assert macOS + arm64 ──────────────────────────────────────────────────
echo -e "${BOLD}[1/7] Checking platform...${RESET}"

if [[ "$(uname)" != "Darwin" ]]; then
    fail "This app requires macOS."
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    fail "This app requires Apple Silicon (arm64). Detected: $(uname -m)"
    exit 1
fi

ok "macOS arm64 (Apple Silicon)"

# ─── 2. Assert Homebrew ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/7] Checking Homebrew...${RESET}"

if ! command -v brew &>/dev/null; then
    fail "Homebrew not found — install it first:"
    info '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi

ok "Homebrew at $(command -v brew)"

# ─── 3. Install uv + python@3.12 ──────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3/7] Checking uv + Python...${RESET}"

if ! command -v uv &>/dev/null; then
    warn "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uv &>/dev/null; then
    fail "uv install failed. Try: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

ok "uv $(uv --version 2>/dev/null | head -1)"

# python@3.12 needed for ACE-Step (requires <3.13)
if ! command -v python3.12 &>/dev/null; then
    warn "python3.12 not found — installing via Homebrew (needed for ACE-Step)..."
    brew install python@3.12
fi

ok "python3.12 at $(command -v python3.12)"

# ─── 4. Install project deps ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[4/7] Setting up project...${RESET}"

mkdir -p "$SCRIPT_DIR/radios/default/tracks"
mkdir -p "$SCRIPT_DIR/radios/default/favorites"
ok "radios/default/ structure ready"

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    ok ".env created from .env.example"
else
    ok ".env already exists"
fi

cd "$SCRIPT_DIR"
uv sync
ok "Python deps installed in .venv/"

# ─── 5. Shell alias ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[5/7] Installing shell alias...${RESET}"

if grep -qF "# ai-radio" "$ZSHRC" 2>/dev/null; then
    ok "alias 'radio' already in $ZSHRC"
else
    echo "" >> "$ZSHRC"
    echo "$ALIAS_LINE" >> "$ZSHRC"
    ok "alias 'radio' added to $ZSHRC"
    warn "Run 'source ~/.zshrc' or open a new terminal to use it"
fi

# ─── 6. Ollama setup ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[6/7] Setting up Ollama...${RESET}"

if ! command -v ollama &>/dev/null; then
    warn "Ollama not found — installing via Homebrew..."
    brew install ollama
fi

ok "Ollama at $(command -v ollama)"

# Start Ollama daemon if not running
if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
    warn "Ollama daemon not running — starting in background..."
    ollama serve &>/dev/null &
    sleep 3
fi

if curl -sf http://localhost:11434/api/tags &>/dev/null; then
    ok "Ollama daemon running"
else
    fail "Ollama daemon failed to start. Run: ollama serve"
    exit 1
fi

# Pull model if missing
OLLAMA_MODEL=$(grep "^OLLAMA_MODEL=" "$SCRIPT_DIR/.env" | cut -d= -f2 || echo "llama3.2:3b")
if ! ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
    warn "$OLLAMA_MODEL not found — pulling (this may take a few minutes)..."
    ollama pull "$OLLAMA_MODEL"
fi

ok "$OLLAMA_MODEL model ready"

# ─── 7. ACE-Step setup ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[7/7] Setting up ACE-Step...${RESET}"

if [[ ! -d "$ACESTEP_DIR" ]]; then
    warn "ACE-Step not found — cloning..."
    git clone https://github.com/ace-step/ACE-Step-1.5.git "$ACESTEP_DIR"
fi

ok "ACE-Step at $ACESTEP_DIR"

# Set up ACE-Step venv with python3.12 if not done
if [[ ! -d "$ACESTEP_DIR/venv" ]]; then
    warn "ACE-Step venv not found — installing (this takes a few minutes)..."
    python3.12 -m venv "$ACESTEP_DIR/venv"
    source "$ACESTEP_DIR/venv/bin/activate"
    pip install -e "$ACESTEP_DIR" --quiet
    deactivate
    ok "ACE-Step installed"
else
    ok "ACE-Step venv ready"
fi

# Check if ACE-Step API is already running
if curl -sf http://localhost:8001/health &>/dev/null; then
    ok "ACE-Step server already running (localhost:8001)"
else
    warn "ACE-Step server not running"
    echo ""
    echo -e "  ${YELLOW}${BOLD}Start ACE-Step in a separate terminal:${RESET}"
    echo ""
    echo -e "    ${BOLD}cd ~/ACE-Step && ./start_api_server_macos.sh${RESET}"
    echo ""
    echo -e "  First run downloads model weights (~20-40 GB). Wait for:"
    echo -e "  ${CYAN}API will be available at: http://127.0.0.1:8001${RESET}"
    echo ""
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo -e "  ─────────────────────────────────────────"
echo ""

if curl -sf http://localhost:8001/health &>/dev/null; then
    echo -e "  ${GREEN}${BOLD}All systems go.${RESET} Start your radio:"
    echo -e "    ${BOLD}radio${RESET}"
else
    echo -e "  ${YELLOW}${BOLD}Almost there.${RESET} Start ACE-Step first (see above), then:"
    echo -e "    ${BOLD}radio${RESET}  (or: uv run python radio.py)"
fi

echo ""
echo -e "  ${CYAN}Uninstall:${RESET} ${BOLD}./uninstall.sh${RESET}"
echo ""
