# Cursor Token 剩余进度（系统托盘）

Windows 系统托盘小工具：拉取 Cursor 套餐用量，用**圆形进度条**显示**剩余百分比**。

> 使用非官方 Dashboard 接口，接口或 Cookie 可能变更；Token 请勿分享。

## 功能

- 系统托盘圆形进度（显示剩余 %）；支持圆环 / 纯数字 / 仅色点
- **左键**：打开状态飞出层（多次点击只打开，不关闭；悬停不弹出）
- **失焦 / Esc**：关闭飞出层
- **右键**：矢量菜单（刷新 / Spending / 设置 / 退出）
- 飞出层快捷操作：复制摘要 / 刷新 / Spending / 设置
- 飞出层打开期间随后台刷新实时更新
- 近 7 日剩余趋势折线与日均消耗
- Token 过期检测、一键打开设置并聚焦 Token 输入框
- 多档额度告警（默认 50/20/5）与耗尽风险通知
- 中文设置窗口（Token、刷新间隔、告警、通知、显示模式、开机自启）
- 默认每 10 分钟刷新（可配置）
- 开机自启（默认开启）

悬浮框字段顺序示例：剩余 → 计划 → 明细 → 重置 → **预计可用** → 趋势 → 更新时间。  
预计可用按本周期已用比例与已过天数估算，并与重置日对比提示「可撑过本周期」或「可能提前耗尽」。

## 环境

- Windows 10/11
- Python 3.10+（开发运行）或已打包的 `.exe`

## 开发运行

双击 **`快速启动.bat`** 即可后台启动（无黑框）。

或手动运行：

```powershell
cd "D:\wwwroot\token剩余进度插件"
python -m pip install -r requirements.txt
python main.py
```

建议用 `pythonw main.py` 运行，不弹出控制台窗口。

## 使用已打包版本

1. 双击 **`build.bat`**（需已安装 Python）生成 `dist\CursorTokenTray\`
2. 运行 `dist\CursorTokenTray\CursorTokenTray.exe`
3. 可将整个 `CursorTokenTray` 文件夹拷到任意位置使用；开机自启会指向该 exe

## 获取 Token

### 方式一：浏览器登录并导入（推荐）

1. 托盘右键 → **设置…**
2. 点击 **浏览器登录并导入**
3. 在打开的浏览器中登录 [cursor.com](https://cursor.com/dashboard)
4. 工具会自动读取本机 **Firefox / Chrome / Edge** 的 `WorkosCursorSessionToken`，并立即校验用量

若浏览器里已经登录，可直接点 **仅导入 Cookie**。

> 部分新版 Chrome 可能启用 App-Bound Cookie 加密导致无法读取；可改用 Firefox / Edge，或使用下方手动方式。

### 方式二：手动粘贴

1. 浏览器登录 [cursor.com/dashboard](https://cursor.com/dashboard/spending)
2. 按 `F12` → **Application** → **Cookies** → `https://cursor.com`
3. 复制 `WorkosCursorSessionToken` 的值
4. 托盘右键 → **设置…** → 粘贴并保存

## 配置文件位置

`%APPDATA%\CursorTokenTray\config.json`  
用量历史：`%APPDATA%\CursorTokenTray\usage_history.jsonl`

## 说明

- 圆环颜色：剩余 &gt;50% 绿，20–50% 黄，&lt;20% 红
- 若托盘图标在溢出区，可拖到任务栏常显
- Token 过期后请重新粘贴；飞出层会提示并可一键打开设置
