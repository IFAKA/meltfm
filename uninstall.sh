#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSHRC="$HOME/.zshrc"

echo ""
echo -e "${BOLD}  ♪  Personal Radio — Uninstall${RESET}"
echo -e "  ─────────────────────────────────────────"
echo ""
echo -e "  This will:"
echo -e "    1. Remove the 'radio' alias from ${ZSHRC}"
echo -e "    2. Delete ${SCRIPT_DIR}"
echo -e "    3. Nothing else — zero system traces"
echo ""
echo -e "  ${YELLOW}Your tracks and taste profiles will be gone.${RESET}"
echo ""
read -r -p "  Are you sure? (yes/no) " confirm
echo ""

if [[ "$confirm" != "yes" && "$confirm" != "y" ]]; then
    echo -e "  Cancelled."
    echo ""
    exit 0
fi

# ── Remove alias from .zshrc ──────────────────────────────────────────────────
if grep -qF "# personal-radio" "$ZSHRC" 2>/dev/null; then
    # Remove the alias line (and the blank line before it if any)
    grep -vF "# personal-radio" "$ZSHRC" > "${ZSHRC}.tmp" && mv "${ZSHRC}.tmp" "$ZSHRC"
    echo -e "  ${GREEN}✓${RESET} Alias removed from ${ZSHRC}"
else
    echo -e "  ${GREEN}✓${RESET} No alias found in ${ZSHRC} (already clean)"
fi

# ── Delete project folder ─────────────────────────────────────────────────────
# Must cd out first so we're not inside the folder being deleted
cd "$HOME"
rm -rf "$SCRIPT_DIR"
echo -e "  ${GREEN}✓${RESET} Deleted ${SCRIPT_DIR}"

echo ""
echo -e "  ${GREEN}${BOLD}Uninstalled. Zero traces.${RESET}"
echo -e "  Run 'source ~/.zshrc' to remove 'radio' from your current shell."
echo ""
