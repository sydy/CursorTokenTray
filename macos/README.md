# macOS 菜单栏（Swift）

SwiftPM 工程：`CursorTokenCore` 可测试的领域逻辑，`CursorTokenTray` 为 LSUIElement 菜单栏应用。

```bash
swift test
swift run CursorTokenTray
./scripts/package_app.sh
```

读取现有 `~/Library/Application Support/CursorTokenTray/config.json`。Token 用钥匙串中的 AES-GCM 包装密钥加密后写入。从 Safari 导入 Cookie 需要完全磁盘访问权限（设置窗会检测并提供跳转）。

从 GitHub Releases 下载的 zip 带隔离属性。若提示「已损坏」，先点取消，到「系统设置 → 隐私与安全性」点「仍要打开」并输入密码（Sequoia 取消了右键打开放行）。没有该按钮时再运行 `首次打开.command`，或：

```bash
xattr -cr CursorTokenTray.app
open CursorTokenTray.app
```
