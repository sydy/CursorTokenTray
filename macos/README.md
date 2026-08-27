# macOS 菜单栏（Swift）

SwiftPM 工程：`CursorTokenCore` 可测试的领域逻辑，`CursorTokenTray` 为 LSUIElement 菜单栏应用。

```bash
swift test
swift run CursorTokenTray
./scripts/package_app.sh
```

读取现有 `~/Library/Application Support/CursorTokenTray/config.json`。

从 GitHub Releases 下载的 zip 带隔离属性，直接双击会提示「已损坏」。请先运行解压目录里的 `首次打开.command`，或：

```bash
xattr -cr CursorTokenTray.app
open CursorTokenTray.app
```
