@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 请用 .NET 8 打包 Windows 程序：
echo   dotnet publish windows\CursorTokenTray\CursorTokenTray.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o dist
echo.
where dotnet >nul 2>&1
if errorlevel 1 (
  echo 未找到 dotnet，请先安装 .NET 8 SDK。
  exit /b 1
)
dotnet publish windows\CursorTokenTray\CursorTokenTray.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o dist
if errorlevel 1 exit /b 1
echo 产物: %~dp0dist\CursorTokenTray.exe
pause
