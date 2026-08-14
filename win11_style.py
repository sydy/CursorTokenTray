"""Windows 11 飞出层样式（圆角 + Acrylic/Mica）。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes


# DWM attributes
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3

DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2  # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic（临时窗口/飞出层）
DWMSBT_TABBEDWINDOW = 4

# 不画边框
DWMWA_COLOR_NONE = 0xFFFFFFFE


def apply_win11_flyout(hwnd: int) -> None:
    """给无边框窗口套上 Win11 飞出层观感。"""
    _apply_win11_chrome(hwnd, backdrop=DWMSBT_NONE)


def apply_win11_menu_popup(
    hwnd: int,
    width: int,
    height: int,
    *,
    corner_radius: int = 8,
) -> None:
    """右键菜单：圆角窗口 + 圆角投影区域。"""
    _apply_win11_chrome(hwnd, backdrop=DWMSBT_NONE)
    _apply_rounded_region(hwnd, width, height, corner_radius)


def _apply_rounded_region(hwnd: int, width: int, height: int, radius: int) -> None:
    if not hwnd or width <= 0 or height <= 0:
        return
    try:
        r = max(1, min(radius, min(width, height) // 2))
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
            0,
            0,
            width + 1,
            height + 1,
            r * 2,
            r * 2,
        )
        if rgn:
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


def apply_win11_window(hwnd: int, *, mica: bool = True) -> None:
    """标准设置窗口：深色标题栏 + 圆角 + Mica。"""
    _apply_win11_chrome(
        hwnd,
        backdrop=DWMSBT_MAINWINDOW if mica else DWMSBT_AUTO,
    )


def _apply_win11_chrome(hwnd: int, *, backdrop: int) -> None:
    if not hwnd:
        return
    dwmapi = ctypes.windll.dwmapi

    def _set(attr: int, value: int) -> None:
        v = ctypes.c_int(value)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            attr,
            ctypes.byref(v),
            ctypes.sizeof(v),
        )

    try:
        _set(DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
    except Exception:
        pass
    try:
        _set(DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    except Exception:
        pass
    try:
        _set(DWMWA_SYSTEMBACKDROP_TYPE, backdrop)
    except Exception:
        pass
    try:
        # 细边框贴近系统色
        color = ctypes.c_uint(0x00666666)  # BGR 灰
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_BORDER_COLOR,
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
    except Exception:
        pass


def toplevel_hwnd(win) -> int:
    """tk Toplevel -> HWND。"""
    try:
        win.update_idletasks()
        hwnd = int(win.winfo_id())
        # 部分环境下需取父窗口
        parent = ctypes.windll.user32.GetParent(hwnd)
        return int(parent) if parent else hwnd
    except Exception:
        return 0
