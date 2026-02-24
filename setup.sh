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
ALIAS_LINE="alias radio='${SCRIPT_DIR}/radio'  # personal-radio"
ZSHRC="$HOME/.zshrc"

echo ""
echo -e "${BOLD}  ♪  Personal Radio — Setup${RESET}"
echo -e "  ─────────────────────────────────────────"
echo ""

# ─── 1. Assert macOS + arm64 ──────────────────────────────────────────────────
echo -e "${BOLD}[1/5] Checking platform...${RESET}"

if [[ "$(uname)" != "Darwin" ]]; then
    fail "This app requires macOS."
    echo ""
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    fail "This app requires Apple Silicon (arm64). Detected: $(uname -m)"
    echo ""
    exit 1
fi

ok "macOS arm64 (Apple Silicon)"

# ─── 2. Assert Homebrew ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/5] Checking Homebrew...${RESET}"

if ! command -v brew &>/dev/null; then
    fail "Homebrew not found."
    info "Install it from: https://brew.sh"
    info "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
    exit 1
fi

ok "Homebrew at $(command -v brew)"

# ─── 3. Install uv if missing ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3/5] Checking uv...${RESET}"

if ! command -v uv &>/dev/null; then
    warn "uv not found — installing via curl installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    if ! command -v uv &>/dev/null; then
        fail "uv install failed. Try manually:"
        info "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        info "  Then add ~/.local/bin to your PATH"
        echo ""
        exit 1
    fi
    ok "uv installed at $(command -v uv)"
else
    ok "uv at $(command -v uv) ($(uv --version 2>/dev/null | head -1))"
fi

# ─── 4. Create directory structure + install deps ─────────────────────────────
echo ""
echo -e "${BOLD}[4/5] Setting up project...${RESET}"

mkdir -p "$SCRIPT_DIR/radios/default/tracks"
mkdir -p "$SCRIPT_DIR/radios/default/favorites"
ok "radios/default/ structure created"

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
echo -e "${BOLD}[5/5] Installing shell alias...${RESET}"

if grep -qF "# personal-radio" "$ZSHRC" 2>/dev/null; then
    ok "alias 'radio' already in $ZSHRC"
else
    echo "" >> "$ZSHRC"
    echo "$ALIAS_LINE" >> "$ZSHRC"
    ok "alias 'radio' added to $ZSHRC"
    warn "Run 'source ~/.zshrc' or open a new terminal to use it"
fi

# ─── Batteries check ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Checking batteries (external tools)...${RESET}"
echo ""

BATTERIES_OK=true

# Ollama binary
if command -v ollama &>/dev/null; then
    ok "Ollama installed at $(command -v ollama)"
else
    fail "Ollama not installed"
    info "Install: https://ollama.com/download"
    BATTERIES_OK=false
fi

# Ollama daemon
if curl -sf http://localhost:11434/api/tags &>/dev/null; then
    ok "Ollama daemon running (localhost:11434)"
else
    fail "Ollama daemon not running"
    info "Start it: ollama serve"
    BATTERIES_OK=false
fi

# llama3.2:3b model
if command -v ollama &>/dev/null && ollama list 2>/dev/null | grep -q "llama3.2:3b"; then
    ok "llama3.2:3b model available"
else
    fail "llama3.2:3b model not found"
    info "Pull it: ollama pull llama3.2:3b"
    BATTERIES_OK=false
fi

# ACE-Step server
if curl -sf http://localhost:8000/health &>/dev/null; then
    ok "ACE-Step server running (localhost:8000)"
else
    fail "ACE-Step server NOT running"
    echo ""
    echo -e "  ${YELLOW}Start it:${RESET}"
    echo -e "    cd ~/ACE-Step"
    echo -e "    PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 python infer-api.py"
    echo ""

    if [[ ! -d "$HOME/ACE-Step" ]]; then
        echo -e "  ${YELLOW}ACE-Step not found. One-time install (~20-40GB download):${RESET}"
        echo ""
        echo -e "    git clone https://github.com/ace-step/ACE-Step-1.5.git ~/ACE-Step"
        echo -e "    cd ~/ACE-Step && pip install -e ."
        echo -e "    PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 python infer-api.py"
        echo -e "    # First run downloads model weights — needs ~40 min + internet"
        echo ""
    fi

    BATTERIES_OK=false
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "  ─────────────────────────────────────────"

if [[ "$BATTERIES_OK" == "true" ]]; then
    echo -e ""
    echo -e "  ${GREEN}${BOLD}All systems go.${RESET} Start your radio:"
    echo -e "    ${BOLD}radio${RESET}"
else
    echo -e ""
    echo -e "  ${YELLOW}${BOLD}Setup done — start the batteries listed above, then:${RESET}"
    echo -e "    ${BOLD}radio${RESET}  (or: uv run python radio.py)"
fi

echo ""
echo -e "  ${CYAN}Uninstall:${RESET} ${BOLD}./uninstall.sh${RESET}"
echo ""
