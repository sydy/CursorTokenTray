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
- **多账号**：保存多个 Cursor 会话，托盘显示当前账号；其余账号后台刷新并独立告警
- 个人套餐与企业 / 团队套餐兼用：个人按 included usage 百分比；企业账号走 [用量页](https://cursor.com/dashboard/usage) 的金额计费（已用 / 额度）
- 中文设置窗口（账号列表、Token、刷新间隔、告警、通知、显示模式、开机自启）
- 默认每 10 分钟刷新（可配置）
- 开机自启（默认开启；Windows 写 Startup 快捷方式，macOS 写 LaunchAgent）

悬浮框字段顺序示例：剩余 → 计划 → 金额（企业）→ 明细 → 重置 → **预计可用** → 趋势 → 更新时间。  
预计可用按本周期已用比例与已过天数估算，并与重置日对比提示「可撑过本周期」或「可能提前耗尽」。企业 / 团队账号打开 [用量页](https://cursor.com/dashboard/usage)，个人账号仍打开账单页。

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

1. 双击 **`build.bat`**（需已安装 Python）生成 `dist\CursorTokenTray.exe`
2. 运行 `dist\CursorTokenTray.exe`
3. 可将该 exe 拷到任意位置使用；开机自启会指向该 exe

### macOS

1. 运行 **`./build_mac.sh`**（需已安装 Python 3）生成 `dist/CursorTokenTray.app`
2. 将 `.app` 拖到「应用程序」
3. 开机自启会指向该 app 内的可执行文件

## GitHub Actions 自动编译

仓库使用 **GitHub Actions**（`.github/workflows/build.yml`）在每次推送 / PR 时：

1. 在 Ubuntu 跑单元测试
2. 在 `windows-latest` 打出 `CursorTokenTray-windows.zip`（单文件 exe）
3. 在 `macos-latest` 打出 `CursorTokenTray-macos.zip`（`.app`）

合入 `main` 后可在两处下载程序包：

- **[Releases / Latest](https://github.com/sydy/CursorTokenTray/releases/tag/latest)**（随每次合入覆盖，不占 Actions 制品配额）
- 对应 run 的 **Artifacts**（保留 1 天；若制品配额尚未重算，这里可能暂时没有）

PR 不上传制品。打 `v*` 标签（例如 `v1.0.0`）会创建正式 GitHub Release 并挂上这两个 zip。  
也可在仓库 **Actions** 页点 **Run workflow** 手动触发。

## 获取 Token

### 方式一：浏览器登录并导入（推荐）

1. 托盘 / 菜单栏右键 → **设置…**
2. 优先点 **从 Cursor 导入**（读取本机已登录的 Cursor 应用，不依赖浏览器 Cookie）
3. 若未登录 Cursor 应用，再点 **Safari 登录** / **Firefox 登录**，在对应浏览器登录 [cursor.com](https://cursor.com/dashboard)
4. 工具会校验用量并写入 Token（已有同一账号则更新，新账号会加入列表并切换为当前）

若浏览器里已经登录，可直接点 **仅导入 Cookie**。同一浏览器通常只能登录一个 Cursor 账号；要加第二个号，请先在浏览器换号登录再导入，或手动粘贴另一个 Token。

**Windows**：优先 Firefox；Chrome / Edge 部分新版可能启用 App-Bound Cookie 加密导致无法读取。

**macOS**：优先 Safari / Firefox。Safari 若读不到，到「系统设置 → 隐私与安全性 → 完全磁盘访问权限」打开 CursorTokenTray。Chrome 系仍会尝试钥匙串解密，失败时请改用 Safari / Firefox。

### 方式二：手动粘贴

1. 浏览器登录 [cursor.com/dashboard](https://cursor.com/dashboard/usage)（个人账号也可打开 [Spending](https://cursor.com/dashboard/spending)）
2. 按 `F12` → **Application**（Safari 为「存储」）→ **Cookies** → `https://cursor.com`
3. 复制 `WorkosCursorSessionToken` 的值
4. 托盘 / 菜单栏右键 → **设置…** → 粘贴并保存

## 配置文件位置

Windows：`%APPDATA%\CursorTokenTray\config.json`  
macOS：`~/Library/Application Support/CursorTokenTray/config.json`  
用量历史：同目录 `usage_history.<账号ID>.jsonl`（旧版单文件 `usage_history.jsonl` 会在首次启动时归到当时那个账号）

## 说明

- 圆环颜色：剩余 &gt;50% 绿，20–50% 黄，&lt;20% 红
- Windows：若托盘图标在溢出区，可拖到任务栏常显
- 这是 **macOS 菜单栏**应用，不是 iOS；没有 Dock 图标，圆环在屏幕**最上方**菜单栏右侧（Wi‑Fi / 控制中心旁边），并带剩余百分比文字
- macOS：若看不到图标，点菜单栏「•••」或「控制中心」展开隐藏项；也可在「活动监视器」结束 CursorTokenTray 后重新打开
- 首次打开若立刻提示「已在后台运行」，多半是旧进程还在，先在活动监视器里退出再启动
- macOS 点「设置…」会在**当前菜单栏进程**弹出系统原生设置窗（不用 Tk，也不另起子进程）。打开时 Dock 可能短暂出现图标，关掉后消失；菜单栏圆环应还在
- 升级后请先在「活动监视器」结束旧的 CursorTokenTray，再打开新下载的 `.app`，不要两个版本叠着跑
- Token 过期后请重新导入或粘贴；飞出层会提示并可一键打开设置
