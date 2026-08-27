#!/bin/bash
cd "$(dirname "$0")"
echo "Python 启动脚本已弃用。请使用原生 macOS 应用："
echo "  1. 从 GitHub Releases 下载 CursorTokenTray-macos.zip"
echo "  2. 或: swift run --package-path macos CursorTokenTray"
echo "  3. 或: ./macos/scripts/package_app.sh && open macos/dist/CursorTokenTray.app"
echo
if [[ -d macos/dist/CursorTokenTray.app ]]; then
  echo "发现 macos/dist/CursorTokenTray.app，正在打开..."
  open macos/dist/CursorTokenTray.app
  exit 0
fi
if [[ -d /Applications/CursorTokenTray.app ]]; then
  open /Applications/CursorTokenTray.app
  exit 0
fi
exit 1
