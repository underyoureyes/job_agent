#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
#  build_dist.sh — package Job Agent for distribution
#  Usage:  bash build_dist.sh
#  Output: dist/Job_Agent_YYYYMMDD.zip  (ready to AirDrop / send)
#
#  The zip contains two macOS .app bundles:
#    "Install Job Agent.app"  — run once to set everything up
#    "Job Agent.app"          — daily launcher
# ──────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

VERSION=$(date +%Y%m%d)
DIST_DIR="dist"
PKG_NAME="Job Agent"
OUT_ZIP="$DIST_DIR/${PKG_NAME// /_}_${VERSION}.zip"
STAGE="$DIST_DIR/stage/$PKG_NAME"

echo "→  Cleaning previous build…"
rm -rf "$DIST_DIR/stage"
mkdir -p "$STAGE"

# ── Helper: build a minimal .app bundle ──────────────────────────────────────
# Usage: make_app <AppName> <script_inside_package> <icon_emoji>
# The executable opens a Terminal window and runs the given script.
make_app() {
    local APP_LABEL="$1"          # display name, e.g. "Install Job Agent"
    local SCRIPT_NAME="$2"        # script file at package root, e.g. install.command
    local APP_DIR="$STAGE/${APP_LABEL}.app"
    local MACOS_DIR="$APP_DIR/Contents/MacOS"
    local RES_DIR="$APP_DIR/Contents/Resources"
    local BUNDLE_ID="com.jobagent.$(echo "$APP_LABEL" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')"

    mkdir -p "$MACOS_DIR" "$RES_DIR"

    # ── Info.plist ────────────────────────────────────────────────────────────
    cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>             <string>${APP_LABEL}</string>
    <key>CFBundleDisplayName</key>      <string>${APP_LABEL}</string>
    <key>CFBundleIdentifier</key>       <string>${BUNDLE_ID}</string>
    <key>CFBundleVersion</key>          <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundleExecutable</key>       <string>launcher</string>
    <key>CFBundleIconFile</key>         <string>AppIcon</string>
    <key>CFBundlePackageType</key>      <string>APPL</string>
    <key>LSMinimumSystemVersion</key>   <string>12.0</string>
    <key>LSUIElement</key>              <false/>
    <key>NSHighResolutionCapable</key>  <true/>
</dict>
</plist>
PLIST

    # ── Launcher executable ───────────────────────────────────────────────────
    # Resolves the app's own location at runtime so the zip can be placed
    # anywhere on the recipient's Mac.
    cat > "$MACOS_DIR/launcher" <<'LAUNCHER'
#!/bin/bash
# Resolve the package root (three levels up from Contents/MacOS/)
APP_DIR="$(cd "$(dirname "$0")/../../../" && pwd)"
SCRIPT="$APP_DIR/SCRIPT_PLACEHOLDER"

if [ ! -f "$SCRIPT" ]; then
    osascript -e 'display alert "Script not found" message "Could not find the launch script. Make sure all files from the zip are in the same folder." as critical'
    exit 1
fi

chmod +x "$SCRIPT"

osascript <<APPLES
tell application "Terminal"
    activate
    set w to do script "cd \"$APP_DIR\" && bash \"$SCRIPT\""
    set custom title of w to "WINDOW_TITLE_PLACEHOLDER"
end tell
APPLES
LAUNCHER

    # Fill in the placeholders
    sed -i '' "s|SCRIPT_PLACEHOLDER|${SCRIPT_NAME}|g"    "$MACOS_DIR/launcher"
    sed -i '' "s|WINDOW_TITLE_PLACEHOLDER|${APP_LABEL}|g" "$MACOS_DIR/launcher"
    chmod +x "$MACOS_DIR/launcher"

    # ── Icon: generate a coloured .icns using macOS built-in tools ───────────
    _make_icon "$RES_DIR/AppIcon.icns" "$APP_LABEL"
}

# ── Icon generation (Python + sips + iconutil — all built into macOS) ────────
_make_icon() {
    local OUT="$1"
    local LABEL="$2"
    local TMP=$(mktemp -d)

    # Pick colour: blue for launcher, green for installer
    local BG="#1d4ed8"
    [[ "$LABEL" == *Install* ]] && BG="#15803d"

    # Draw a 1024×1024 PNG with the first letter of each word
    local INITIALS
    INITIALS=$(echo "$LABEL" | awk '{for(i=1;i<=NF;i++) printf substr($i,1,1)}' | head -c 2)

    python3 - "$TMP/icon_1024.png" "$BG" "$INITIALS" <<'PYEOF'
import sys, struct, zlib, math

out_path, bg_hex, text = sys.argv[1], sys.argv[2], sys.argv[3]
SIZE = 1024

# Parse hex colour
r = int(bg_hex[1:3], 16)
g = int(bg_hex[3:5], 16)
b = int(bg_hex[5:7], 16)

# --- minimal PNG writer (no Pillow needed) ---
def png_chunk(tag, data):
    c = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', c)

def write_png(path, pixels, w, h):
    raw = b''
    for row in pixels:
        raw += b'\x00' + bytes(row)
    compressed = zlib.compress(raw, 9)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(png_chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)))
        f.write(png_chunk(b'IDAT', compressed))
        f.write(png_chunk(b'IEND', b''))

# Build pixel grid: rounded-rect background + simple pixel-letter
pixels = []
cx, cy = SIZE // 2, SIZE // 2
radius = int(SIZE * 0.22)   # corner radius

for y in range(SIZE):
    row = []
    for x in range(SIZE):
        # Rounded rectangle test
        dx = max(abs(x - cx) - (SIZE // 2 - radius - 1), 0)
        dy = max(abs(y - cy) - (SIZE // 2 - radius - 1), 0)
        inside = (dx*dx + dy*dy) <= radius*radius
        if inside:
            row += [r, g, b]
        else:
            row += [15, 23, 42]   # dark navy outside
    pixels.append(row)

write_png(out_path, pixels, SIZE, SIZE)
PYEOF

    # Convert to .icns using macOS iconutil
    local ICONSET="$TMP/AppIcon.iconset"
    mkdir -p "$ICONSET"
    for sz in 16 32 64 128 256 512 1024; do
        sips -z $sz $sz "$TMP/icon_1024.png" --out "$ICONSET/icon_${sz}x${sz}.png" &>/dev/null
    done
    # Retina sizes
    for sz in 16 32 64 128 256 512; do
        local sz2=$((sz * 2))
        sips -z $sz2 $sz2 "$TMP/icon_1024.png" --out "$ICONSET/icon_${sz}x${sz}@2x.png" &>/dev/null
    done

    iconutil -c icns "$ICONSET" -o "$OUT" 2>/dev/null || true
    rm -rf "$TMP"
}

# ── Copy source files ─────────────────────────────────────────────────────────
echo "→  Copying source files…"
cp -r src               "$STAGE/src"
cp    requirements.txt  "$STAGE/"
cp    ".env.example"    "$STAGE/"
cp    "install.command" "$STAGE/"
cp    "Job Agent.command" "$STAGE/"
[ -f "base_cv.md.example" ] && cp "base_cv.md.example" "$STAGE/"
[ -f README.md ]            && cp README.md "$STAGE/"

# Make the raw .command files executable (fallback if .app doesn't work)
chmod +x "$STAGE/install.command"
chmod +x "$STAGE/Job Agent.command"

# ── Remove dev artefacts ──────────────────────────────────────────────────────
echo "→  Removing dev artefacts…"
find "$STAGE/src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/src" -name "*.pyc"  -delete 2>/dev/null || true
find "$STAGE"     -name ".DS_Store" -delete 2>/dev/null || true
find "$STAGE"     -name "*.db"   -delete 2>/dev/null || true

# ── Build .app bundles ────────────────────────────────────────────────────────
echo "→  Building Install Job Agent.app…"
make_app "Install Job Agent" "install.command"

echo "→  Building Job Agent.app…"
make_app "Job Agent" "Job Agent.command"

# ── Zip ───────────────────────────────────────────────────────────────────────
echo "→  Creating zip…"
mkdir -p "$DIST_DIR"
cd "$DIST_DIR/stage"
zip -r -q "../../$OUT_ZIP" "$PKG_NAME" \
    --exclude "*.DS_Store" \
    --exclude "*/__pycache__/*"
cd ../..

SIZE=$(du -sh "$OUT_ZIP" | cut -f1)
rm -rf "$DIST_DIR/stage"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓  $OUT_ZIP  ($SIZE)"
echo ""
echo "  What the recipient sees after unzipping:"
echo "    📁 Job Agent/"
echo "       🟢 Install Job Agent.app   ← run once"
echo "       🔵 Job Agent.app           ← daily launcher"
echo "       📄 .env.example, src/, …"
echo ""
echo "  First-launch note:"
echo "  macOS may say 'unidentified developer'."
echo "  Fix: right-click the .app → Open → Open."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
