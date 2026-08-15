# Cursor Token 剩余进度（系统托盘 / 菜单栏）

Windows 系统托盘、macOS 菜单栏小工具：拉取 Cursor 套餐用量，用**圆形进度条**显示**剩余百分比**。

> 使用非官方 Dashboard 接口，接口或 Cookie 可能变更；Token 请勿分享。

## 功能

- 托盘 / 菜单栏圆形进度（显示剩余 %）；支持圆环 / 纯数字 / 仅色点
- **左键**：打开状态飞出层（多次点击只打开，不关闭；悬停不弹出）
- **失焦 / Esc**：关闭飞出层
- **右键**：Windows 为矢量菜单，macOS 为原生菜单栏菜单（刷新 / Spending / 设置 / 退出）
- 飞出层快捷操作：复制摘要 / 刷新 / Spending / 设置
- 飞出层打开期间随后台刷新实时更新
- 近 7 日剩余趋势折线与日均消耗
- Token 过期检测、一键打开设置并聚焦 Token 输入框
- 多档额度告警（默认 50/20/5）与耗尽风险通知
- 中文设置窗口（Token、刷新间隔、告警、通知、显示模式、开机自启）
- 默认每 10 分钟刷新（可配置）
- 开机自启（默认开启；Windows 写 Startup 快捷方式，macOS 写 LaunchAgent）

悬浮框字段顺序示例：剩余 → 计划 → 明细 → 重置 → **预计可用** → 趋势 → 更新时间。  
预计可用按本周期已用比例与已过天数估算，并与重置日对比提示「可撑过本周期」或「可能提前耗尽」。

## 环境

- Windows 10/11 或 macOS 11+
- Python 3.10+（开发运行）或已打包的 `.exe` / `.app`

## 开发运行

### Windows

双击 **`快速启动.bat`** 即可后台启动（无黑框）。

或手动运行：

```powershell
python -m pip install -r requirements.txt
python main.py
```

建议用 `pythonw main.py` 运行，不弹出控制台窗口。

### macOS

双击 **`快速启动.command`**，或：

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

图标会出现在屏幕右上角菜单栏。首次从 Chrome 导入 Cookie 时，系统可能弹出钥匙串授权，请点「允许」。

本地运行日志：`~/Library/Logs/CursorTokenTray.log`（`快速启动.command` 也会把 stdout/stderr 追加进去）。出问题请先看这份日志。

## 使用已打包版本

### Windows

1. 双击 **`build.bat`**（需已安装 Python）生成 `dist\CursorTokenTray\`
2. 运行 `dist\CursorTokenTray\CursorTokenTray.exe`
3. 可将整个 `CursorTokenTray` 文件夹拷到任意位置使用；开机自启会指向该 exe

### macOS

1. 运行 **`./build_mac.sh`**（需已安装 Python 3）生成 `dist/CursorTokenTray.app`
2. 将 `.app` 拖到「应用程序」
3. 开机自启会指向该 app 内的可执行文件

## GitHub Actions 自动编译

仓库使用 **GitHub Actions**（`.github/workflows/build.yml`）在每次推送 / PR 时：

1. 在 Ubuntu 跑单元测试
2. 在 `windows-latest` 打出 `CursorTokenTray-windows.zip`（onedir + exe）
3. 在 `macos-latest` 打出 `CursorTokenTray-macos.zip`（`.app`）

产物在对应 run 的 **Artifacts** 里下载。打 `v*` 标签（例如 `v1.0.0`）还会自动创建 GitHub Release 并挂上这两个 zip。

也可在仓库 **Actions** 页点 **Run workflow** 手动触发。

## 获取 Token

### 方式一：浏览器登录并导入（推荐）

1. 托盘 / 菜单栏右键 → **设置…**
2. 点击 **浏览器登录并导入**
3. 在打开的浏览器中登录 [cursor.com](https://cursor.com/dashboard)
4. 工具会自动读取本机浏览器的 `WorkosCursorSessionToken`，并立即校验用量

若浏览器里已经登录，可直接点 **仅导入 Cookie**。

**Windows**：Firefox / Chrome / Edge。部分新版 Chrome 可能启用 App-Bound Cookie 加密导致无法读取；可改用 Firefox / Edge。

**macOS**：Safari / Chrome / Edge / Firefox / Brave / Arc。Chrome 系走钥匙串解密；Safari 可能需要在「系统设置 → 隐私与安全性」中授予**完全磁盘访问权限**。

### 方式二：手动粘贴

1. 浏览器登录 [cursor.com/dashboard](https://cursor.com/dashboard/spending)
2. 按 `F12` → **Application**（Safari 为「存储」）→ **Cookies** → `https://cursor.com`
3. 复制 `WorkosCursorSessionToken` 的值
4. 托盘 / 菜单栏右键 → **设置…** → 粘贴并保存

## 配置文件位置

Windows：`%APPDATA%\CursorTokenTray\config.json`  
macOS：`~/Library/Application Support/CursorTokenTray/config.json`  
用量历史：同目录 `usage_history.jsonl`

## 说明

- 圆环颜色：剩余 &gt;50% 绿，20–50% 黄，&lt;20% 红
- Windows：若托盘图标在溢出区，可拖到任务栏常显
- 这是 **macOS 菜单栏**应用，不是 iOS；没有 Dock 图标，圆环在屏幕**最上方**菜单栏右侧（Wi‑Fi / 控制中心旁边），并带剩余百分比文字
- macOS：若看不到图标，点菜单栏「•••」或「控制中心」展开隐藏项；也可在「活动监视器」结束 CursorTokenTray 后重新打开
- 首次打开若立刻提示「已在后台运行」，多半是旧进程还在，先在活动监视器里退出再启动
- macOS 点「设置…」会**另开一个设置进程**（会出现 Dock 图标）；关掉设置窗后 Dock 图标消失，菜单栏图标还在
- 升级后请先在「活动监视器」结束旧的 CursorTokenTray，再打开新下载的 `.app`，不要两个版本叠着跑
- Token 过期后请重新导入或粘贴；飞出层会提示并可一键打开设置
