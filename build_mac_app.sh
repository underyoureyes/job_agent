#!/bin/bash
# build_mac_app.sh — Build a standalone Mac .app using PyInstaller
# =================================================================
# Run this ONCE to create the .app bundle your son can double-click.
#
# Prerequisites (run these first):
#   pip install pyinstaller python-docx docx2pdf anthropic \
#               requests beautifulsoup4 rich lxml
#
# Usage:
#   chmod +x build_mac_app.sh
#   ./build_mac_app.sh
#
# Output: dist/Job Agent.app
#         dist/Job Agent.app can be dragged to /Applications

set -e

# Always run from the directory containing this script
cd "$(dirname "$0")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Job Agent — Mac App Builder"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Python
python3 --version || { echo "Python 3 not found"; exit 1; }

# Check PyInstaller
if ! python3 -m PyInstaller --version &>/dev/null; then
    echo "Installing PyInstaller…"
    pip install pyinstaller
fi

# Check required packages
echo "Checking dependencies…"
pip install python-docx docx2pdf anthropic requests beautifulsoup4 rich lxml --quiet

# Clean previous build
rm -rf build/ dist/

# Create a simple app icon (plain .icns — replace with a real icon if desired)
# If you have an icon file, place it at icon.icns in this directory.
ICON_ARG=""
if [ -f "icon.icns" ]; then
    ICON_ARG="--icon=icon.icns"
fi

echo ""
echo "Building .app bundle…"
echo "(This takes 1–2 minutes)"
echo

# Bundle .env with all details but strip OUTPUT_DIR (it points to this machine)
# Named "bundled.env" so PyInstaller can include it as a plain file in the bundle root.
grep -v "^OUTPUT_DIR=" .env > bundled.env

# Collect optional data files — only included if they exist.
# These are seeded into ~/Library/Application Support/JobAgent/ on first launch
# so the user doesn't need to upload their CV or templates manually.
OPTIONAL_DATA=()
[ -f "base_cv.md" ]                     && OPTIONAL_DATA+=(--add-data "base_cv.md:.")
[ -f "src/cv_style.json" ]              && OPTIONAL_DATA+=(--add-data "src/cv_style.json:.")
[ -f "src/cover_letter_template.docx" ] && OPTIONAL_DATA+=(--add-data "src/cover_letter_template.docx:.")
[ -f "src/cover_letter_style.json" ]    && OPTIONAL_DATA+=(--add-data "src/cover_letter_style.json:.")

python3 -m PyInstaller \
    --name "Job Agent" \
    --windowed \
    --onedir \
    --noconfirm \
    $ICON_ARG \
    --add-data "src/config.py:." \
    --add-data "src/tracker.py:." \
    --add-data "src/job_scanner.py:." \
    --add-data "src/cv_tailor.py:." \
    --add-data "src/document_processor.py:." \
    --add-data "src/doc_generator.py:." \
    --add-data "src/review_queue.py:." \
    --add-data "src/main.py:." \
    --add-data "src/cv_template.docx:." \
    --add-data "bundled.env:." \
    --add-data "docs:docs" \
    "${OPTIONAL_DATA[@]}" \
    --hidden-import "tkinter" \
    --hidden-import "tkinter.ttk" \
    --hidden-import "tkinter.filedialog" \
    --hidden-import "tkinter.messagebox" \
    --hidden-import "tkinter.scrolledtext" \
    --hidden-import "docx" \
    --hidden-import "docx.shared" \
    --hidden-import "docx.enum.text" \
    --hidden-import "docx.oxml" \
    --hidden-import "docx.oxml.ns" \
    --hidden-import "anthropic" \
    --hidden-import "bs4" \
    --hidden-import "rich" \
    --collect-all "docx" \
    --collect-all "anthropic" \
    src/app.py

# Clean up temp env file
rm -f bundled.env

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Build complete!"
echo ""
echo "  The app includes pre-configured details, API keys, and the"
echo "  existing CV — no upload needed on first launch."
echo ""
echo "  App location:  dist/Job Agent.app"
echo ""
echo "  To install:"
echo "  1. Open Finder → Go to this folder"
echo "  2. Open the 'dist' folder"
echo "  3. Drag 'Job Agent.app' to your Applications folder"
echo "  4. Double-click to open"
echo ""
echo "  First launch: macOS may show a security warning."
echo "  Fix: System Settings → Privacy & Security → Open Anyway"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
