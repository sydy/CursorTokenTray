# Cursor Token 剩余进度（系统托盘 / 菜单栏）

Windows 系统托盘、macOS 菜单栏小工具：拉取 Cursor 套餐用量，用**圆形进度条**显示**剩余百分比**。

> 使用非官方 Dashboard 接口，接口或 Cookie 可能变更；Token 请勿分享。

## 功能

- 托盘 / 菜单栏圆形进度（显示剩余 %）；支持圆环 / 纯数字 / 仅色点
- **左键**：打开状态飞出层（多次点击只打开，不关闭；悬停不弹出）
- **失焦 / Esc**：关闭飞出层
- **右键**：Windows 为系统原生菜单，macOS 为原生菜单栏菜单（刷新 / 用量报表 / 设置 / 退出）
- 飞出层快捷操作：复制摘要 / 刷新 / 报表 / Spending / 设置
- 飞出层打开期间随后台刷新实时更新
- 近 7 日剩余趋势折线与日均消耗
- Token 过期检测、一键打开设置并聚焦 Token 输入框
- 多档额度告警（默认 50/20/5）与耗尽风险通知
- **多账号**：保存多个 Cursor 会话，托盘显示当前账号；其余账号后台刷新并独立告警
- 个人套餐与企业 / 团队套餐兼用：个人按 included usage 百分比；企业账号走 [用量页](https://cursor.com/dashboard/usage) 的金额计费（已用 / 额度）
- 中文设置窗口（Windows 为 WinForms，macOS 为 SwiftUI；账号列表、Token、刷新间隔、告警、通知、显示模式、开机自启）
- **用量报表**：打开窗口时增量拉取 [Usage 页](https://cursor.com/dashboard/usage) 按次明细，本地缓存；总览、按日趋势、按模型排行、明细表与 CSV 导出。默认当前账号，团队管理员可切全员
- 默认每 10 分钟刷新（可配置）
- 开机自启（默认开启；Windows 写当前用户注册表 `Run` 项，macOS 用 `SMAppService` / LaunchAgent）

悬浮框字段顺序示例：剩余 → 计划 → 金额（企业）→ 明细 → 重置 → **预计可用** → 趋势 → 更新时间。  
预计可用按本周期已用比例与已过天数估算，并与重置日对比提示「可撑过本周期」或「可能提前耗尽」。企业 / 团队账号打开 [用量页](https://cursor.com/dashboard/usage)，个人账号仍打开账单页。

## 环境

- Windows 10/11 或 **macOS 13+**
- 发布包为原生程序：Windows 是 .NET 8 单文件 exe，macOS 是 Swift 菜单栏 `.app`
- 配置兼容旧版 Python 工具：仍读写同一份 `config.json`

仓库里的 Python 源码仅作夹具对照与历史实现，**已弃用**。`快速启动.bat` / `快速启动.command` / `build.bat` / `build_mac.sh` 会提示并转向原生工程。日常请用下面的原生程序。

配置里的 Session Token 在磁盘上加密保存：Windows 用当前用户 DPAPI，macOS 用钥匙串里的 AES-GCM 包装密钥。旧版明文 `config.json` 会在下次保存时自动升级；若回退到更早的原生版本，需要重新导入 Token。

## 开发运行

### Windows（C# / .NET 8）

```powershell
dotnet run --project windows/CursorTokenTray/CursorTokenTray.csproj -c Release
```

核心解析单测（不含 WinForms）：

```powershell
dotnet test windows/CursorTokenCore.Tests/CursorTokenCore.Tests.csproj
```

### macOS（Swift）

```bash
swift run --package-path macos CursorTokenTray
```

或打包成 `.app`：

```bash
./macos/scripts/package_app.sh
open macos/dist/CursorTokenTray.app
```

核心解析单测：

```bash
swift test --package-path macos
```

图标会出现在屏幕右上角菜单栏。首次从 Safari 导入 Cookie 时，如读不到请到「系统设置 → 隐私与安全性 → 完全磁盘访问权限」打开 CursorTokenTray。

本地运行日志：`~/Library/Logs/CursorTokenTray.log`。

夹具（Python / Swift / C# 共用）在 `fixtures/`。

## 使用已打包版本

### Windows

1. 从 [Releases / Latest](https://github.com/sydy/CursorTokenTray/releases/tag/latest) 下载 `CursorTokenTray-windows.zip`
2. 解压运行 `CursorTokenTray.exe`
3. 可将该 exe 拷到任意位置使用；开机自启会指向该 exe

本地发布：

```powershell
dotnet publish windows/CursorTokenTray/CursorTokenTray.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o dist
```

### macOS

1. 下载 `CursorTokenTray-macos.zip`，解压后将 `.app` 拖到「应用程序」（也可先放在下载文件夹）
2. 双击打开。若弹出「已损坏 / 移到废纸篓」：**点「取消」，不要移到废纸篓**
3. 打开 **系统设置 → 隐私与安全性**，拉到下面的安全性，点 **「仍要打开」**，再输入本机密码。这就是以前右键打开时那次放行，只是 Sequoia 以后不再允许用右键绕过
4. 若设置里没有「仍要打开」，再双击 zip 里的 **`首次打开.command`**（系统会用「来自互联网，要打开吗」那种确认）。仍不行再在终端执行：

```bash
xattr -cr /Applications/CursorTokenTray.app
open /Applications/CursorTokenTray.app
```

路径按实际位置改。放行一次之后就可以正常打开。  
5. 开机自启会注册本机登录项（`SMAppService`）

本地打包：`./macos/scripts/package_app.sh`

## GitHub Actions 自动编译

仓库使用 **GitHub Actions**（`.github/workflows/build.yml`）在每次推送 / PR 时：

1. 在 Ubuntu 跑 Python 夹具测试与 C# 核心测试
2. 在 `macos-latest` 跑 Swift 测试
3. 在 `windows-latest` 打出 `CursorTokenTray-windows.zip`（.NET 8 单文件 exe）
4. 在 `macos-latest` 打出 `CursorTokenTray-macos.zip`（Swift `.app`）

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

**Windows**：可从 **Cursor 应用**或 **Firefox** 导入。Chrome / Edge 使用 App-Bound Cookie 加密，本工具无法读取，请改用 Firefox 或手动粘贴。

**macOS**：优先 Cursor 应用、Safari / Firefox。Safari 若读不到，到「系统设置 → 隐私与安全性 → 完全磁盘访问权限」打开 CursorTokenTray。设置窗会检测权限并提供跳转。Chrome 系仍会尝试钥匙串解密，失败时请改用 Safari / Firefox。

### 方式二：手动粘贴

1. 浏览器登录 [cursor.com/dashboard](https://cursor.com/dashboard/usage)（个人账号也可打开 [Spending](https://cursor.com/dashboard/spending)）
2. 按 `F12` → **Application**（Safari 为「存储」）→ **Cookies** → `https://cursor.com`
3. 复制 `WorkosCursorSessionToken` 的值
4. 托盘 / 菜单栏右键 → **设置…** → 粘贴并保存

## 配置文件位置

Windows：`%APPDATA%\CursorTokenTray\config.json`  
macOS：`~/Library/Application Support/CursorTokenTray/config.json`  
用量历史：同目录 `usage_history.<账号ID>.jsonl`（旧版单文件 `usage_history.jsonl` 会在首次启动时归到当时那个账号）  
用量明细缓存：同目录 `usage_events.<账号ID>.jsonl`（团队全员为 `usage_events.<账号ID>.team.jsonl`）

## 说明

- 圆环颜色：剩余 &gt;50% 绿，20–50% 黄，&lt;20% 红
- Windows：托盘、右键菜单、状态飞出层、设置都在**同一个 .NET 8 进程**里用 WinForms 完成（`NotifyIcon` + 系统菜单），不依赖 Python / Tk。若图标在溢出区，可拖到任务栏常显
- 这是 **macOS 菜单栏**应用，不是 iOS；没有 Dock 图标，圆环在屏幕**最上方**菜单栏右侧（Wi‑Fi / 控制中心旁边），并带剩余百分比文字
- macOS：若看不到图标，点菜单栏「•••」或「控制中心」展开隐藏项；也可在「活动监视器」结束 CursorTokenTray 后重新打开
- 首次打开若立刻提示「已在后台运行」，多半是旧进程还在，先在活动监视器里退出再启动
- macOS 点「设置…」会在**当前菜单栏进程**弹出系统原生设置窗（不用 Tk，也不另起子进程）。打开时 Dock 可能短暂出现图标，关掉后消失；菜单栏圆环应还在
- 升级后请先在「活动监视器」结束旧的 CursorTokenTray，再打开新下载的 `.app`，不要两个版本叠着跑
- Token 过期后请重新导入或粘贴；飞出层会提示并可一键打开设置
