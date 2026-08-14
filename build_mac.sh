#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/3] 安装依赖..."
python3 -m pip install -r requirements.txt pyinstaller -q

echo "[2/3] 打包 macOS .app..."
python3 -m PyInstaller --noconfirm CursorTokenTray.macos.spec

echo "[3/3] 完成"
echo "产物: $(pwd)/dist/CursorTokenTray.app"
echo "运行: open dist/CursorTokenTray.app"
echo "可将 .app 拖到 /Applications；开机自启会指向该可执行文件。"
