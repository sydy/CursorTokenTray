# Windows 原生托盘（C# / .NET 8）

与 `macos/` Swift 菜单栏应用并列。配置文件仍是 `%APPDATA%\CursorTokenTray\config.json`。Token 用当前用户 DPAPI 加密后写入；开机自启写入 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`。

```powershell
dotnet test CursorTokenCore.Tests\CursorTokenCore.Tests.csproj
dotnet run --project CursorTokenTray\CursorTokenTray.csproj
dotnet publish CursorTokenTray\CursorTokenTray.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```
