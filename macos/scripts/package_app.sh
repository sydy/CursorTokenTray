#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"
swift build -c release --product CursorTokenTray
BIN="$(swift build -c release --show-bin-path)/CursorTokenTray"
DIST="$ROOT/dist/CursorTokenTray.app"
rm -rf "$DIST"
mkdir -p "$DIST/Contents/MacOS" "$DIST/Contents/Resources"
cp "$BIN" "$DIST/Contents/MacOS/CursorTokenTray"
cp "$ROOT/Resources/Info.plist" "$DIST/Contents/Info.plist"
if [[ -f "$REPO/assets/app_icon.icns" ]]; then
  cp "$REPO/assets/app_icon.icns" "$DIST/Contents/Resources/AppIcon.icns"
  /usr/libexec/PlistBuddy -c 'Add :CFBundleIconFile string AppIcon' "$DIST/Contents/Info.plist" 2>/dev/null || true
elif [[ -f "$REPO/assets/app_icon.png" ]] && command -v sips >/dev/null; then
  ICONSET="$ROOT/dist/AppIcon.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z "$s" "$s" "$REPO/assets/app_icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    sips -z "$d" "$d" "$REPO/assets/app_icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$DIST/Contents/Resources/AppIcon.icns"
  /usr/libexec/PlistBuddy -c 'Add :CFBundleIconFile string AppIcon' "$DIST/Contents/Info.plist" 2>/dev/null || true
fi
chmod +x "$DIST/Contents/MacOS/CursorTokenTray"
echo "Built $DIST"
