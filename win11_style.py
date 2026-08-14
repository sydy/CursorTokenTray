"""Windows 11 飞出层样式（圆角 + Acrylic/Mica）。其它平台为空操作。"""

from __future__ import annotations

import sys


def apply_win11_flyout(hwnd: int) -> None:
    """给无边框窗口套上 Win11 飞出层观感。"""
    if sys.platform != "win32":
        return
    _apply_win11_chrome(hwnd, backdrop=1)  # DWMSBT_NONE


def apply_win11_menu_popup(
    hwnd: int,
    width: int,
    height: int,
    *,
    corner_radius: int = 8,
) -> None:
    """右键菜单：圆角窗口 + 圆角投影区域。"""
    if sys.platform != "win32":
        return
    _apply_win11_chrome(hwnd, backdrop=1)
    _apply_rounded_region(hwnd, width, height, corner_radius)


def _apply_rounded_region(hwnd: int, width: int, height: int, radius: int) -> None:
    if sys.platform != "win32" or not hwnd or width <= 0 or height <= 0:
        return
    try:
        import ctypes

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
    if sys.platform != "win32":
        return
    _apply_win11_chrome(
        hwnd,
        backdrop=2 if mica else 0,
    )


def _apply_win11_chrome(hwnd: int, *, backdrop: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    import ctypes
    from ctypes import wintypes

    dwmapi = ctypes.windll.dwmapi
    dwmwa_use_immersive_dark_mode = 20
    dwmwa_window_corner_preference = 33
    dwmwa_border_color = 34
    dwmwa_systembackdrop_type = 38
    dwmwcp_round = 2

    def _set(attr: int, value: int) -> None:
        v = ctypes.c_int(value)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            attr,
            ctypes.byref(v),
            ctypes.sizeof(v),
        )

    try:
        _set(dwmwa_use_immersive_dark_mode, 1)
    except Exception:
        pass
    try:
        _set(dwmwa_window_corner_preference, dwmwcp_round)
    except Exception:
        pass
    try:
        _set(dwmwa_systembackdrop_type, backdrop)
    except Exception:
        pass
    try:
        color = ctypes.c_uint(0x00666666)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            dwmwa_border_color,
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
    except Exception:
        pass


def toplevel_hwnd(win) -> int:
    """tk Toplevel -> HWND / 原生窗口 id。"""
    try:
        win.update_idletasks()
        hwnd = int(win.winfo_id())
        if sys.platform != "win32":
            return hwnd
        import ctypes

        parent = ctypes.windll.user32.GetParent(hwnd)
        return int(parent) if parent else hwnd
    except Exception:
        return 0
