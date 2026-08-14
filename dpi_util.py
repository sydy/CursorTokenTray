"""进程 DPI 感知，避免托盘弹窗被系统拉伸发糊。"""

from __future__ import annotations

import sys


def enable_dpi_awareness() -> float:
    """返回系统 DPI 缩放（96dpi = 1.0；macOS 为 backingScaleFactor）。"""
    if sys.platform == "darwin":
        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen is not None:
                return max(1.0, float(screen.backingScaleFactor()))
        except Exception:
            pass
        return 2.0

    if sys.platform != "win32":
        return 1.0

    try:
        import ctypes

        try:
            # Per-monitor v2
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()

        try:
            dpi = int(ctypes.windll.user32.GetDpiForSystem())
        except Exception:
            dpi = 96
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0
