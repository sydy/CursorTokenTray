"""精确截取设置窗（按 HWND），避免抓到其它窗口。"""

from __future__ import annotations

import ctypes
import time
from pathlib import Path

from dpi_util import enable_dpi_awareness
from settings_ui import SettingsWindow


def grab_hwnd(hwnd: int, path: Path) -> tuple[int, int]:
    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    PW_RENDERFULLCONTENT = 0x00000002

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = int(rect.right - rect.left), int(rect.bottom - rect.top)
    if w < 8 or h < 8:
        raise RuntimeError(f"client too small: {w}x{h}")

    hdc_win = user32.GetDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    old = gdi32.SelectObject(hdc_mem, hbmp)
    ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    if not ok:
        # fallback BitBlt
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_win, 0, 0, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0
    buf = (ctypes.c_char * (w * h * 4))()
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

    img = Image.frombuffer("RGB", (w, h), bytes(buf), "raw", "BGRX", 0, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)

    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_win)
    return w, h


def main() -> None:
    enable_dpi_awareness()
    out = Path(__file__).resolve().parent / "_preview_out"
    win = SettingsWindow()
    # 同线程构建，避免跨线程操作 Tk
    win._build_ui(host=None, owns_loop=False)
    root = win.root
    if root is None:
        raise SystemExit("settings window did not open")

    root.update()
    root.update_idletasks()
    time.sleep(0.25)
    root.update()

    hwnd = int(root.winfo_id())
    user32 = ctypes.windll.user32
    # 爬到顶层 HWND（Tk winfo_id 常为子容器）
    top = hwnd
    for _ in range(8):
        parent = int(user32.GetParent(top) or 0)
        if not parent:
            break
        top = parent
    ga = int(user32.GetAncestor(hwnd, 2) or 0)  # GA_ROOT
    if ga:
        top = ga

    pages = [
        ("account", "01_account.png"),
        ("notify", "02_notify.png"),
        ("tray", "03_tray.png"),
    ]
    for key, name in pages:
        try:
            win._show_page(key)  # type: ignore[attr-defined]
        except Exception:
            pass
        root.update()
        root.update_idletasks()
        time.sleep(0.45)
        root.update()
        root.update_idletasks()

        # ImageGrab 在多屏/DPI 下易抓到桌面，坚持 HWND PrintWindow
        w, h = grab_hwnd(int(top), out / name)
        print(
            f"saved {name} {w}x{h} geom={root.geometry()} "
            f"tk={root.winfo_width()}x{root.winfo_height()} hwnd={top}"
        )

    try:
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
