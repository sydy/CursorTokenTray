"""Windows DPI：进程感知 + 单一缩放源，避免 CTk / Tk / 位图各算各的。

关闭 CustomTkinter 自动 DPI 后，必须把同一套 scale 写回：
- ``ctk.set_widget_scaling`` / ``set_window_scaling``（控件与窗口设计尺寸）
- ``tk scaling``（Tk 点阵字体，右键菜单）
- 位图像素（PhotoImage 不会被 CTk 再乘一遍）

飞出层用 ``winfo_reqwidth`` 得到的是**物理像素**，再走 CTk.geometry 会二次放大。
这类尺寸必须用 ``set_physical_geometry``。

CTk 窗口默认 ``_max_width/_max_height = 1_000_000``。``set_window_scaling`` 会把这个
上限写进 Win32 ``ptMaxTrackSize``；GPU/DWM 常按最大纹理边长（约 16384）提交
一块 CPU 几乎不碰的提交内存，表现为工作集不大、提交却到十几 GB。
"""

from __future__ import annotations

import sys
from typing import Any

# 100%–300%。再高对托盘飞出层没有收益，却会把 CTk maxsize / 字体位图放大到危险区。
MIN_UI_SCALE = 1.0
MAX_UI_SCALE = 3.0
MIN_DPI = 96
MAX_DPI = 288
# CTk 设计像素上限（再乘 window_scaling 才是屏幕像素）。4K 最大化设置窗够用。
CTK_MAX_DESIGN_W = 2560
CTK_MAX_DESIGN_H = 1600

_process_scale = 1.0
_ctk_scale: float | None = None


def clamp_ui_scale(scale: float) -> float:
    """把缩放钳在 [1.0, 3.0]，挡住 ctypes 读到的垃圾 DPI。"""
    try:
        value = float(scale)
    except (TypeError, ValueError):
        return MIN_UI_SCALE
    if value != value:  # NaN
        return MIN_UI_SCALE
    return min(MAX_UI_SCALE, max(MIN_UI_SCALE, value))


def clamp_dpi(dpi: int) -> int:
    value = int(dpi or 0)
    if value < MIN_DPI or value > MAX_DPI:
        return MIN_DPI
    return value


def enable_dpi_awareness() -> float:
    """返回系统 DPI 缩放（96dpi = 1.0；macOS 为 backingScaleFactor）。"""
    global _process_scale
    if sys.platform == "darwin":
        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen is not None:
                # 菜单栏按 1x 出图会在 Retina 上被放大发糊，macOS 至少按 2x。
                _process_scale = max(2.0, float(screen.backingScaleFactor()))
                return _process_scale
        except Exception:
            pass
        _process_scale = 2.0
        return _process_scale

    if sys.platform != "win32":
        _process_scale = 1.0
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

        _process_scale = current_dpi_scale()
        return _process_scale
    except Exception:
        _process_scale = 1.0
        return 1.0


def current_dpi_scale(
    *,
    hwnd: int = 0,
    point: tuple[int, int] | None = None,
) -> float:
    """当前显示器有效缩放。Windows 优先光标/窗口所在屏，避免系统 DPI 与外接屏不一致。"""
    if sys.platform != "win32":
        return max(1.0, float(_process_scale if sys.platform == "darwin" else 1.0))
    try:
        dpi = _windows_dpi(hwnd=hwnd, point=point)
        return clamp_ui_scale(float(dpi) / 96.0)
    except Exception:
        return clamp_ui_scale(_process_scale or 1.0)


def scaled_px(base: int, scale: float | None = None) -> int:
    """设计像素 → 物理像素。scale 默认取当前显示器。"""
    s = current_dpi_scale() if scale is None else float(scale)
    s = clamp_ui_scale(s)
    return max(int(base), int(round(int(base) * s)))


def physical_window_size(design_w: int, design_h: int, scale: float | None = None) -> tuple[int, int]:
    """设计尺寸 × 缩放 → 屏幕像素，供居中计算。CTk.geometry 仍应传入设计尺寸。"""
    s = clamp_ui_scale(current_dpi_scale() if scale is None else float(scale))
    return scaled_px(int(design_w), s), scaled_px(int(design_h), s)


def tk_scaling_value(scale: float | None = None) -> float:
    """Tk ``tk scaling``：1.0 表示 72dpi。96dpi 时为 96/72。"""
    s = clamp_ui_scale(current_dpi_scale() if scale is None else float(scale))
    return s * 96.0 / 72.0


def apply_tk_scaling(root: Any, scale: float | None = None) -> None:
    if sys.platform != "win32" or root is None:
        return
    try:
        root.tk.call("tk", "scaling", tk_scaling_value(scale))
    except Exception:
        pass


def apply_ctk_scaling(scale: float | None = None) -> float:
    """把同一套 Windows 缩放写进 CTk。macOS/Linux 不改（系统自己处理 Retina）。"""
    global _ctk_scale
    if sys.platform != "win32":
        return 1.0
    s = clamp_ui_scale(current_dpi_scale() if scale is None else scale)
    if _ctk_scale is not None and abs(_ctk_scale - s) < 0.02:
        return _ctk_scale
    try:
        import customtkinter as ctk

        ctk.set_widget_scaling(s)
        ctk.set_window_scaling(s)
        _ctk_scale = s
    except Exception:
        _ctk_scale = s
    return s


def sync_windows_ui_scale(
    root: Any = None,
    *,
    hwnd: int = 0,
    point: tuple[int, int] | None = None,
) -> float:
    """按当前显示器刷新 CTk + Tk scaling，供飞出层/设置窗打开前调用。"""
    scale = current_dpi_scale(hwnd=hwnd, point=point)
    apply_ctk_scaling(scale)
    apply_tk_scaling(root, scale)
    return scale


def parse_geometry_xy(geom: str) -> tuple[int, int] | None:
    """从 ``WxH+X+Y`` / ``WxH-X-Y`` 取出屏幕坐标。"""
    import re

    match = re.search(r"([+-]\d+)([+-]\d+)$", str(geom).strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def physical_geometry_string(
    width: int,
    height: int,
    x: int | None = None,
    y: int | None = None,
) -> str:
    w = max(1, int(width))
    h = max(1, int(height))
    if x is None or y is None:
        return f"{w}x{h}"
    return f"{w}x{h}+{int(x)}+{int(y)}"


def set_physical_geometry(
    win: Any,
    width: int,
    height: int,
    x: int | None = None,
    y: int | None = None,
) -> None:
    """按屏幕像素设置位置尺寸，绕过 CTk.geometry 的 window_scaling。"""
    import tkinter as tk

    tk.Wm.geometry(win, physical_geometry_string(width, height, x, y))


def ctk_window_scale(win: Any = None) -> float:
    """CTk 窗口当前 window_scaling；读不到则回退 current_dpi_scale。"""
    if win is not None:
        try:
            getter = getattr(win, "_get_window_scaling", None)
            if callable(getter):
                return clamp_ui_scale(getter())
        except Exception:
            pass
    if _ctk_scale is not None:
        return clamp_ui_scale(_ctk_scale)
    return current_dpi_scale()


def cap_ctk_maxsize(win: Any, design_w: int = CTK_MAX_DESIGN_W, design_h: int = CTK_MAX_DESIGN_H) -> None:
    """把 CTk / CTkToplevel 的 100 万像素 maxsize 降到合理上限。

    必须同时改 ``_max_width/_max_height``：CTk 会在 ``set_window_scaling`` 后 1 秒
    用这两个字段再写一次 Win32 maxsize。
    """
    if win is None:
        return
    w = max(1, int(design_w))
    h = max(1, int(design_h))
    try:
        win._max_width = w
        win._max_height = h
    except Exception:
        pass
    try:
        win.maxsize(w, h)
    except Exception:
        pass


def harden_hidden_tk_root(root: Any) -> None:
    """托盘宿主：1×1、已撤回、maxsize 很小，避免 CTk 默认 600×500 / maxsize 1e6。"""
    if root is None:
        return
    import tkinter as tk

    try:
        root.withdraw()
    except tk.TclError:
        pass
    try:
        root.resizable(False, False)
    except tk.TclError:
        pass
    try:
        root.minsize(1, 1)
        root.maxsize(64, 64)
    except tk.TclError:
        pass
    try:
        tk.Wm.geometry(root, "1x1+0+0")
    except tk.TclError:
        pass


def _windows_dpi(*, hwnd: int = 0, point: tuple[int, int] | None = None) -> int:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    MONITOR_DEFAULTTONEAREST = 2
    MDT_EFFECTIVE_DPI = 0

    MonitorFromWindow = user32.MonitorFromWindow
    MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    MonitorFromWindow.restype = ctypes.c_void_p

    MonitorFromPoint = user32.MonitorFromPoint
    MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    MonitorFromPoint.restype = ctypes.c_void_p

    monitor = None
    if hwnd:
        try:
            monitor = MonitorFromWindow(wintypes.HWND(int(hwnd)), MONITOR_DEFAULTTONEAREST)
        except Exception:
            monitor = None
    if not monitor and point is not None:
        try:
            pt = wintypes.POINT(int(point[0]), int(point[1]))
            monitor = MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        except Exception:
            monitor = None
    if not monitor:
        try:
            GetCursorPos = user32.GetCursorPos
            GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            GetCursorPos.restype = wintypes.BOOL
            pt = wintypes.POINT()
            if GetCursorPos(ctypes.byref(pt)):
                monitor = MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        except Exception:
            monitor = None

    if monitor:
        try:
            shcore = ctypes.WinDLL("shcore", use_last_error=True)
            GetDpiForMonitor = shcore.GetDpiForMonitor
            GetDpiForMonitor.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.POINTER(wintypes.UINT),
                ctypes.POINTER(wintypes.UINT),
            ]
            GetDpiForMonitor.restype = ctypes.HRESULT
            x_dpi = wintypes.UINT()
            y_dpi = wintypes.UINT()
            hr = GetDpiForMonitor(
                monitor,
                MDT_EFFECTIVE_DPI,
                ctypes.byref(x_dpi),
                ctypes.byref(y_dpi),
            )
            dpi = int(x_dpi.value or 0)
            if hr == 0 and MIN_DPI <= dpi <= MAX_DPI:
                return dpi
        except Exception:
            pass
        if hwnd:
            try:
                GetDpiForWindow = user32.GetDpiForWindow
                GetDpiForWindow.argtypes = [wintypes.HWND]
                GetDpiForWindow.restype = ctypes.c_uint
                dpi = int(GetDpiForWindow(wintypes.HWND(int(hwnd))) or 0)
                if MIN_DPI <= dpi <= MAX_DPI:
                    return dpi
            except Exception:
                pass

    try:
        GetDpiForSystem = user32.GetDpiForSystem
        GetDpiForSystem.argtypes = []
        GetDpiForSystem.restype = ctypes.c_uint
        return clamp_dpi(int(GetDpiForSystem() or 96))
    except Exception:
        return MIN_DPI
