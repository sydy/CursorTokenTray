@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Python 启动脚本已弃用。请使用原生 Windows 程序：
echo   1. 从 GitHub Releases 下载 CursorTokenTray-windows.zip
echo   2. 或: dotnet run --project windows\CursorTokenTray\CursorTokenTray.csproj -c Release
echo.
if exist "%~dp0dist\CursorTokenTray.exe" (
  echo 发现 dist\CursorTokenTray.exe，正在启动...
  start "" "%~dp0dist\CursorTokenTray.exe"
  exit /b 0
)
if exist "%~dp0windows\CursorTokenTray\bin\Release\net8.0-windows\win-x64\CursorTokenTray.exe" (
  start "" "%~dp0windows\CursorTokenTray\bin\Release\net8.0-windows\win-x64\CursorTokenTray.exe"
  exit /b 0
)
pause
exit /b 1
