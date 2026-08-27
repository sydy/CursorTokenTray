#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

echo "Python / PyInstaller 打包已弃用。改用 Swift 打包脚本。"
chmod +x macos/scripts/package_app.sh
./macos/scripts/package_app.sh
echo "产物: $(pwd)/macos/dist/CursorTokenTray.app"
echo "运行: open macos/dist/CursorTokenTray.app"
