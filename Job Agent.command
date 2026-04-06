#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
#  Job Agent — launcher
#  Double-click this file to start Job Agent and open it in your browser.
#
#  First run:  creates a virtual environment and installs all dependencies
#              (takes ~1 minute — only happens once).
#  Every run:  starts the server and opens http://localhost:5000
#
#  Requirements: Python 3.10 or later  (https://www.python.org/downloads/)
# ──────────────────────────────────────────────────────────────────────────────

set -e

# ── Move to the folder containing this script ─────────────────────────────────
cd "$(dirname "$0")"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Job Agent"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Check Python 3.10+ ────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info[:2] >= (3,10))")
        if [ "$VER" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌  Python 3.10 or later is required."
    echo ""
    echo "    Download it from: https://www.python.org/downloads/"
    echo ""
    read -rp "Press Enter to close…"
    exit 1
fi

echo "✓  Python: $($PYTHON --version)"

# ── Create virtual environment (first run only) ───────────────────────────────
VENV=".venv"
if [ ! -d "$VENV" ]; then
    echo ""
    echo "⏳  First-time setup — creating virtual environment…"
    "$PYTHON" -m venv "$VENV"
fi

# Activate venv
source "$VENV/bin/activate"

# ── Install / update dependencies (first run installs, later runs are fast) ───
echo "⏳  Checking dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "✓  Dependencies ready"
echo ""

# ── Check .env exists ─────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "⚠️   No .env file found."
    echo "    Copy .env.example to .env and fill in your API keys before using."
    echo ""
fi

# ── Pick a free port (default 5000, fallback 5001/5002) ──────────────────────
PORT=5000
for p in 5000 5001 5002 5003; do
    if ! lsof -i ":$p" &>/dev/null; then PORT=$p; break; fi
done

URL="http://localhost:$PORT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Starting Job Agent on $URL"
echo "  Close this window to stop the server."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Open browser after a short delay ─────────────────────────────────────────
(sleep 2 && open "$URL") &

# ── Start the server ─────────────────────────────────────────────────────────
cd src
python -m uvicorn api.app:app --host 127.0.0.1 --port "$PORT"
