@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 安装依赖...
python -m pip install -r requirements.txt pyinstaller -q
if errorlevel 1 (
  echo pip 安装失败
  exit /b 1
)

echo [2/3] 打包 onedir...
python -m PyInstaller --noconfirm CursorTokenTray.spec
if errorlevel 1 (
  echo 打包失败
  exit /b 1
)

echo [3/3] 完成
echo 产物目录: %~dp0dist\CursorTokenTray\
echo 运行: dist\CursorTokenTray\CursorTokenTray.exe
pause
