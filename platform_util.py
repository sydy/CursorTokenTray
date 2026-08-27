"""跨平台小工具：路径、字体、光标、工作区、弹窗定位。"""

from __future__ import annotations

import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def app_config_dir() -> Path:
    if IS_WIN:
        return Path(os.environ.get("APPDATA", Path.home())) / "CursorTokenTray"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "CursorTokenTray"
    return Path.home() / ".config" / "CursorTokenTray"


def ui_font_family() -> str:
    if IS_MAC:
        return "PingFang SC"
    return "Microsoft YaHei UI"


def ui_font_candidates() -> tuple[str, ...]:
    if IS_MAC:
        return (
            "PingFang SC",
            "Hiragino Sans GB",
            "Helvetica Neue",
            ".AppleSystemUIFont",
            "Arial",
        )
    return ("Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI")


def cursor_pos() -> tuple[int, int]:
    if IS_WIN:
        return _cursor_pos_win()
    if IS_MAC:
        return _cursor_pos_mac()
    return 100, 100


def work_area() -> tuple[int, int, int, int]:
    """当前光标所在屏的工作区（Tk 坐标：原点左上，y 向下）。返回 left, top, right, bottom。"""
    if IS_WIN:
        return _work_area_win()
    if IS_MAC:
        return _work_area_mac()
    return 0, 0, 1920, 1040


def place_tray_popup(win, width: int, height: int, gap: int = 10) -> None:
    """托盘/菜单栏附近放置无边框弹窗。width/height 必须是屏幕像素。"""
    from dpi_util import set_physical_geometry

    cx, cy = cursor_pos()
    left, top, right, bottom = work_area()
    px = cx - width // 2
    px = max(left + 8, min(px, right - width - 8))
    if IS_MAC:
        py = top + gap
        if py + height > bottom - 8:
            py = max(top + 8, bottom - height - 8)
    else:
        py = bottom - height - gap
        if py < top + 8:
            py = top + 8
    set_physical_geometry(win, width, height, int(px), int(py))


def mouse_left_down() -> bool:
    if IS_WIN:
        try:
            import ctypes

            return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:
            return False
    if IS_MAC:
        try:
            from AppKit import NSEvent

            return bool(int(NSEvent.pressedMouseButtons()) & 1)
        except Exception:
            return False
    return False


def show_already_running() -> None:
    if IS_WIN:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "CursorToken 已在后台运行。\n请查看右下角系统托盘（或点 ^ 展开隐藏图标）。",
                "CursorToken 剩余进度",
                0x40,
            )
            return
        except Exception:
            pass
    if IS_MAC:
        try:
            import subprocess

            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'display alert "CursorToken 剩余进度" message '
                    '"已经在运行。请看屏幕最上方菜单栏右侧（Wi‑Fi / 控制中心旁边）的圆环图标，'
                    '不是 iPhone 状态栏，也没有 Dock 图标。\\n\\n'
                    '若仍看不到：点菜单栏 「•••」或「控制中心」展开隐藏项；'
                    '或打开「活动监视器」结束 CursorTokenTray 后再启动一次。" as informational',
                ],
                check=False,
                capture_output=True,
                timeout=8,
            )
            return
        except Exception:
            pass
    print("CursorToken 已在运行，请查看系统托盘或菜单栏。")


def become_foreground_app() -> None:
    """把当前进程临时变成普通 GUI（会出 Dock 图标）。

    不要遍历已有 NSWindow / 不要和 Tk 一起用。菜单栏设置窗走 macos_settings，
    只改 ActivationPolicy 并前置自己那一扇窗。
    """
    if not IS_MAC:
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
    except Exception:
        pass


def set_dock_visible(visible: bool) -> None:
    """仅用于独立设置进程：显示或隐藏 Dock 图标。"""
    if not IS_MAC:
        return
    if visible:
        become_foreground_app()
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass


def show_error_alert(title: str, message: str) -> None:
    if IS_MAC:
        try:
            import subprocess

            def _q(text: str) -> str:
                return text.replace("\\", "\\\\").replace('"', '\\"')

            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display alert "{_q(title)}" message "{_q(message)}" as critical',
                ],
                check=False,
                capture_output=True,
                timeout=8,
            )
            return
        except Exception:
            pass
    print(f"{title}: {message}")


def window_center_pos(screen_w: int, screen_h: int, win_w: int, win_h: int) -> tuple[int, int]:
    x = max(40, (int(screen_w) - int(win_w)) // 2)
    y = max(48, (int(screen_h) - int(win_h)) // 3)
    return x, y


def log_path() -> Path:
    if IS_MAC:
        return Path.home() / "Library" / "Logs" / "CursorTokenTray.log"
    return app_config_dir() / "app.log"


def app_log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} [{os.getpid()}] {message}"
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, file=sys.stderr, flush=True)
    except Exception:
        pass


def install_crash_logging() -> None:
    """把未捕获异常写进日志。本地 `快速启动.command` 以前把 stderr 丢进 /dev/null。"""

    def _hook(exc_type, exc, tb) -> None:
        app_log(f"UNCAUGHT {getattr(exc_type, '__name__', exc_type)}: {exc}")
        app_log("".join(traceback.format_exception(exc_type, exc, tb)).rstrip())

    sys.excepthook = _hook

    def _thread_hook(args) -> None:
        name = args.thread.name if args.thread is not None else "?"
        app_log(f"THREAD {name} {getattr(args.exc_type, '__name__', args.exc_type)}: {args.exc_value}")
        if args.exc_type is not None:
            app_log(
                "".join(
                    traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
                ).rstrip()
            )

    threading.excepthook = _thread_hook


def hidden_popen_kwargs() -> dict:
    """Windows 子进程不要闪出控制台。其它平台为空。"""
    if not IS_WIN:
        return {}
    import subprocess

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flags} if flags else {}


def copy_text(text: str) -> bool:
    """复制到剪贴板。macOS 用 pbcopy，避免托盘进程再碰 Tk。"""
    if IS_MAC:
        try:
            import subprocess

            subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=False,
                timeout=3,
            )
            return True
        except Exception as exc:
            app_log(f"pbcopy failed: {exc}")
            return False
    return False


def show_native_status(title: str, body: str) -> None:
    """macOS 状态用系统对话框，菜单栏进程里禁止创建 Tk。"""
    if not IS_MAC:
        return

    def _show() -> None:
        app_log("native status dialog")
        try:
            from AppKit import NSAlert, NSInformationalAlertStyle

            alert = NSAlert.alloc().init()
            alert.setMessageText_(title)
            alert.setInformativeText_(body)
            alert.setAlertStyle_(NSInformationalAlertStyle)
            alert.addButtonWithTitle_("好")
            alert.runModal()
            return
        except Exception as exc:
            app_log(f"NSAlert failed: {exc}")
        show_error_alert(title, body)

    try:
        from Foundation import NSOperationQueue, NSThread

        if bool(NSThread.isMainThread()):
            _show()
            return
        NSOperationQueue.mainQueue().addOperationWithBlock_(_show)
        return
    except Exception:
        pass
    try:
        from PyObjCTools import AppHelper

        AppHelper.callLater(0.15, _show)
    except Exception:
        threading.Thread(target=_show, daemon=True, name="native-status").start()


def _cursor_pos_win() -> tuple[int, int]:
    import ctypes

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def _cursor_pos_mac() -> tuple[int, int]:
    try:
        from Quartz import CGEventCreate, CGEventGetLocation

        loc = CGEventGetLocation(CGEventCreate(None))
        return int(loc.x), int(loc.y)
    except Exception:
        try:
            from AppKit import NSEvent, NSScreen

            pt = NSEvent.mouseLocation()
            primary_h = float(NSScreen.screens()[0].frame().size.height)
            return int(pt.x), int(primary_h - pt.y)
        except Exception:
            return 100, 48


def _work_area_win() -> tuple[int, int, int, int]:
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    monitor = user32.MonitorFromPoint(pt, 2)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        r = info.rcWork
        return int(r.left), int(r.top), int(r.right), int(r.bottom)

    rect = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _work_area_mac() -> tuple[int, int, int, int]:
    """把 Cocoa visibleFrame（原点左下）转成 Tk 工作区。"""
    try:
        from AppKit import NSScreen

        screens = list(NSScreen.screens() or [])
        if not screens:
            return 0, 24, 1440, 900
        primary_h = float(screens[0].frame().size.height)
        cx, cy = _cursor_pos_mac()
        chosen = screens[0]
        for screen in screens:
            f = screen.frame()
            left = float(f.origin.x)
            top = primary_h - float(f.origin.y) - float(f.size.height)
            right = left + float(f.size.width)
            bottom = top + float(f.size.height)
            if left <= cx < right and top <= cy < bottom:
                chosen = screen
                break
        vis = chosen.visibleFrame()
        left = int(vis.origin.x)
        height = int(vis.size.height)
        width = int(vis.size.width)
        cocoa_bottom = float(vis.origin.y)
        top = int(round(primary_h - cocoa_bottom - height))
        right = left + width
        bottom = top + height
        return left, top, right, bottom
    except Exception:
        return 0, 24, 1440, 900
