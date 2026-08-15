#!/bin/bash
cd "$(dirname "$0")"
LOG="${HOME}/Library/Logs/CursorTokenTray.log"
mkdir -p "$(dirname "$LOG")"
echo "---- $(date '+%Y-%m-%dT%H:%M:%S') 快速启动 ----" >>"$LOG"
if command -v python3 >/dev/null 2>&1; then
  nohup python3 main.py >>"$LOG" 2>&1 &
  echo "已在后台启动（pid $!）"
  echo "日志：$LOG"
  exit 0
fi
echo "未找到 Python 3，请先安装：https://www.python.org/downloads/macos/"
exit 1
