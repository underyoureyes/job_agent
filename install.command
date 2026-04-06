#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
#  Job Agent — First-time installer
#  Double-click this file once to set everything up.
#  After it finishes, use "Job Agent.command" to launch the app.
# ──────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC}  $*"; }
info() { echo -e "${BLUE}→${NC}  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}   $*"; }
fail() { echo -e "${RED}✗${NC}  $*"; }
hr()   { echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

hr
echo -e "${BOLD}  Job Agent — Installer${NC}"
hr
echo ""

# ── Step 1: Find or install Python 3.10+ ─────────────────────────────────────
info "Checking for Python 3.10+…"

PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info[:2] >= (3,10))" 2>/dev/null || echo "False")
        if [ "$VER" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -n "$PYTHON" ]; then
    ok "Python found: $($PYTHON --version)"
else
    warn "Python 3.10+ not found — attempting to install automatically…"
    echo ""

    # ── Try Homebrew ──────────────────────────────────────────────────────────
    if ! command -v brew &>/dev/null; then
        echo -e "${BOLD}Homebrew (Mac package manager) is not installed.${NC}"
        echo "  Homebrew is needed to install Python automatically."
        echo ""
        read -rp "  Install Homebrew now? (recommended — takes ~2 min) [y/N]: " INSTALL_BREW
        if [[ "$INSTALL_BREW" =~ ^[Yy]$ ]]; then
            info "Installing Homebrew…"
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add Homebrew to PATH for Apple Silicon
            if [ -f "/opt/homebrew/bin/brew" ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            fi
            ok "Homebrew installed"
        else
            echo ""
            echo "  Alternative: download Python manually from:"
            echo "  https://www.python.org/downloads/"
            echo ""
            echo "  After installing Python, double-click install.command again."
            echo ""
            read -rp "Press Enter to close…"
            exit 1
        fi
    fi

    info "Installing Python 3.12 via Homebrew…"
    brew install python@3.12
    # Homebrew Python is not on PATH by default; link it
    BREW_PREFIX=$(brew --prefix)
    PYTHON="$BREW_PREFIX/bin/python3.12"
    if [ ! -f "$PYTHON" ]; then
        PYTHON=$(brew --prefix python@3.12)/bin/python3.12
    fi
    ok "Python installed: $($PYTHON --version)"
fi

echo ""

# ── Step 2: Create virtual environment ───────────────────────────────────────
VENV=".venv"
if [ -d "$VENV" ]; then
    info "Virtual environment already exists — skipping creation"
else
    info "Creating virtual environment…"
    "$PYTHON" -m venv "$VENV"
    ok "Virtual environment created"
fi

source "$VENV/bin/activate"
echo ""

# ── Step 3: Install Python dependencies ──────────────────────────────────────
info "Installing Python packages (this takes a minute on first run)…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Python packages installed"
echo ""

# ── Step 4: Install Playwright browsers ──────────────────────────────────────
info "Installing Playwright browser (Chromium)…"
playwright install chromium 2>&1 | tail -3
ok "Playwright ready"
echo ""

# ── Step 5: Set up .env ───────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    info "Creating .env from template…"
    cp .env.example .env
    warn ".env created — you must fill in your API keys before using the app."
    warn "Open the .env file in any text editor and add your Anthropic API key."
    echo ""
fi

# ── Step 6: Set up base CV ───────────────────────────────────────────────────
if [ ! -f "base_cv.md" ] && [ -f "base_cv.md.example" ]; then
    cp base_cv.md.example base_cv.md
    warn "base_cv.md created from example — replace it with your own CV content."
    echo ""
fi

# ── Step 7: Make launchers executable ────────────────────────────────────────
chmod +x "Job Agent.command" 2>/dev/null || true
chmod +x "install.command"   2>/dev/null || true

# ── Done ──────────────────────────────────────────────────────────────────────
hr
echo ""
ok "Installation complete!"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. Open ${BOLD}.env${NC} in a text editor and add your API keys:"
echo -e "       • ${YELLOW}ANTHROPIC_API_KEY${NC}  (required for scoring & tailoring)"
echo -e "       • ${YELLOW}REED_API_KEY${NC}       (for Reed job scanning)"
echo -e "       • ${YELLOW}ADZUNA_APP_ID${NC} / ${YELLOW}ADZUNA_APP_KEY${NC}  (for Adzuna scanning)"
echo ""
echo -e "  2. Replace ${BOLD}base_cv.md${NC} with your own CV."
echo ""
echo -e "  3. Double-click ${BOLD}\"Job Agent.command\"${NC} to start the app."
echo ""
hr
echo ""
read -rp "Press Enter to close…"
