"""跨平台小工具：路径、字体、光标、工作区、弹窗定位。"""

from __future__ import annotations

import os
import sys
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
    """托盘/菜单栏附近放置无边框弹窗。"""
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
    win.geometry(f"{width}x{height}+{int(px)}+{int(py)}")


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
                    '"CursorToken 已在菜单栏运行。请查看屏幕右上角。" as informational',
                ],
                check=False,
                capture_output=True,
                timeout=8,
            )
            return
        except Exception:
            pass
    print("CursorToken 已在运行，请查看系统托盘或菜单栏。")


def set_dock_visible(visible: bool) -> None:
    """macOS：设置窗出现时显示 Dock 图标，关闭后回到纯菜单栏。"""
    if not IS_MAC:
        return
    try:
        from AppKit import (
            NSApp,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )

        if visible:
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            NSApp.activateIgnoringOtherApps_(True)
        else:
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


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
