"""应用图标：任务栏 / 窗口 / 资源路径。"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image

# 独立于 pythonw.exe，避免任务栏一直显示 Python 文档图标
APP_USER_MODEL_ID = "Harker.CursorTokenTray"


def resource_dir() -> Path:
    """开发目录或 PyInstaller 解包目录。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def icon_file(*parts: str) -> Path:
    return resource_dir().joinpath("assets", *parts)


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> None:
    """进程级 AppUserModelID：任务栏不再归到 Python 组。须尽早调用。"""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


@lru_cache(maxsize=4)
def load_app_icon_image(size: int = 256) -> Image.Image:
    """加载应用图标 PIL 图（优先精确尺寸 PNG）。"""
    exact = icon_file(f"app_icon_{size}.png")
    if exact.is_file():
        return Image.open(exact).convert("RGBA")
    png = icon_file("app_icon.png")
    if png.is_file():
        im = Image.open(png).convert("RGBA")
        if im.size != (size, size):
            return im.resize((size, size), Image.Resampling.LANCZOS)
        return im
    return Image.new("RGBA", (size, size), (28, 28, 28, 255))


def _hwnd_of(win) -> int:
    try:
        from win11_style import toplevel_hwnd

        return int(toplevel_hwnd(win) or 0)
    except Exception:
        pass
    try:
        win.update_idletasks()
        return int(win.winfo_id())
    except Exception:
        return 0


def _set_win32_icons(hwnd: int) -> None:
    """通过 WM_SETICON 设置大小图标，任务栏才会换掉 Python 图标。"""
    if not hwnd or not sys.platform.startswith("win"):
        return
    ico = icon_file("app_icon.ico")
    if not ico.is_file():
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        SM_CXICON = 11
        SM_CXSMICON = 49

        LoadImageW = user32.LoadImageW
        LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        LoadImageW.restype = wintypes.HANDLE

        # 按系统 DPI 取实际像素（150% 时常为 24/48，而不是 16/32）
        cx_big = int(user32.GetSystemMetrics(SM_CXICON) or 32)
        cx_small = int(user32.GetSystemMetrics(SM_CXSMICON) or 16)

        path = str(ico.resolve())
        h_big = LoadImageW(None, path, IMAGE_ICON, cx_big, cx_big, LR_LOADFROMFILE)
        h_small = LoadImageW(None, path, IMAGE_ICON, cx_small, cx_small, LR_LOADFROMFILE)
        if not h_big:
            h_big = LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not h_small:
            h_small = h_big
        if h_big:
            user32.SendMessageW(wintypes.HWND(hwnd), WM_SETICON, ICON_BIG, h_big)
        if h_small:
            user32.SendMessageW(wintypes.HWND(hwnd), WM_SETICON, ICON_SMALL, h_small)
    except Exception:
        pass


def hide_from_taskbar(win) -> None:
    """隐藏根窗口的任务栏按钮（避免出现 Python 幽灵图标）。"""
    if not sys.platform.startswith("win"):
        return
    hwnd = _hwnd_of(win)
    if not hwnd:
        return
    try:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


def show_on_taskbar(win) -> None:
    """确保普通窗口出现在任务栏。"""
    if not sys.platform.startswith("win"):
        return
    hwnd = _hwnd_of(win)
    if not hwnd:
        return
    try:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


def apply_window_icon(win) -> None:
    """给 Tk / Toplevel 设置窗口与任务栏图标。"""
    try:
        import tkinter as tk
        from PIL import ImageTk
    except Exception:
        return

    ico = icon_file("app_icon.ico")
    try:
        if ico.is_file() and sys.platform.startswith("win"):
            try:
                win.iconbitmap(default=str(ico.resolve()))
            except tk.TclError:
                try:
                    win.iconbitmap(str(ico.resolve()))
                except tk.TclError:
                    pass
    except Exception:
        pass

    try:
        photos: list = []
        for s in (16, 20, 24, 32, 40, 48, 64):
            photos.append(ImageTk.PhotoImage(load_app_icon_image(s)))
        if photos:
            win._app_icon_photos = photos  # type: ignore[attr-defined]
            win.iconphoto(True, *photos)
    except Exception:
        pass

    try:
        win.update_idletasks()
    except Exception:
        pass
    show_on_taskbar(win)
    _set_win32_icons(_hwnd_of(win))

    # 显示后再设一次，确保任务栏缓存刷新
    try:
        win.after(50, lambda: _set_win32_icons(_hwnd_of(win)))
        win.after(200, lambda: _set_win32_icons(_hwnd_of(win)))
    except Exception:
        pass
