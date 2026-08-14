#!/bin/bash
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  nohup python3 main.py >/dev/null 2>&1 &
  exit 0
fi
echo "未找到 Python 3，请先安装：https://www.python.org/downloads/macos/"
exit 1
