"""Windows 原生托盘图标：Shell_NotifyIcon + 本进程消息循环。"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from PIL import Image

from platform_util import app_log
from win_api import (
    NIF_ICON,
    NIF_INFO,
    NIF_MESSAGE,
    NIF_SHOWTIP,
    NIF_TIP,
    NIIF_INFO,
    NIIF_NOSOUND,
    NIM_ADD,
    NIM_DELETE,
    NIM_MODIFY,
    NIM_SETVERSION,
    NIN_KEYSELECT,
    NIN_SELECT,
    NOTIFYICON_VERSION_4,
    NOTIFYICONDATAW,
    NOTIFYICONIDENTIFIER,
    WM_CONTEXTMENU,
    WM_DESTROY,
    WM_INVOKE,
    WM_LBUTTONUP,
    WM_QUIT,
    WM_RBUTTONUP,
    WM_APPLY_ICON,
    WM_APPLY_NOTIFY,
    WM_TRAYICON,
    WNDCLASSW,
    WNDPROC,
    WS_EX_TOOLWINDOW,
    WS_POPUP,
    def_window_proc,
    destroy_icon,
    get_module_handle,
    load_cursor_arrow,
    post_message,
    post_quit_message,
)


TRAY_UID = 1
_CLASS = "CursorTokenTrayNativeWnd"


def _hicon_from_image(image: Image.Image) -> int:
    import ctypes
    from ctypes import wintypes

    from win_api import (
        BI_RGB,
        BITMAPINFO,
        DIB_RGB_COLORS,
        ICONINFO,
        delete_object,
    )

    img = image.convert("RGBA")
    width, height = img.size
    raw = img.tobytes()
    bgra = bytearray(width * height * 4)
    for y in range(height):
        src_row = y * width * 4
        dst_row = (height - 1 - y) * width * 4
        for x in range(width):
            i = src_row + x * 4
            j = dst_row + x * 4
            r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
            bgra[j : j + 4] = bytes((b, g, r, a))

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(bmi.bmiHeader)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    hdc = ctypes.windll.user32.GetDC(None)
    color = ctypes.windll.gdi32.CreateDIBSection(
        hdc,
        ctypes.byref(bmi),
        DIB_RGB_COLORS,
        ctypes.byref(bits),
        None,
        0,
    )
    ctypes.windll.user32.ReleaseDC(None, hdc)
    if not color or not bits.value:
        return 0
    ctypes.memmove(bits, bytes(bgra), len(bgra))
    mask = ctypes.windll.gdi32.CreateBitmap(width, height, 1, 1, None)
    info = ICONINFO()
    info.fIcon = True
    info.xHotspot = 0
    info.yHotspot = 0
    info.hbmMask = mask
    info.hbmColor = color
    handle = int(ctypes.windll.user32.CreateIconIndirect(ctypes.byref(info)) or 0)
    delete_object(int(color))
    if mask:
        delete_object(int(mask))
    return handle


class NativeTray:
    """系统托盘。左键/右键都在拥有消息循环的线程里回调。"""

    def __init__(
        self,
        image: Image.Image,
        *,
        on_left_click: Callable[[], None] | None = None,
        on_right_click: Callable[[], None] | None = None,
        tooltip: str = "",
    ) -> None:
        self.on_left_click = on_left_click
        self.on_right_click = on_right_click
        self._tooltip = tooltip
        self._image = image
        self.hwnd = 0
        self._hicon = 0
        self._added = False
        self._wndproc = None
        self._invoke_q: queue.Queue[Callable[[], Any]] = queue.Queue()
        self._win_tid = 0
        self._thread_id = 0
        self._pending_notify: tuple[str, str] | None = None
        self._last_left = 0.0
        self._last_right = 0.0

    def run(self, setup: Callable[["NativeTray"], None] | None = None) -> None:
        import ctypes
        from ctypes import wintypes

        from win_api import MSG

        self._thread_id = threading.get_ident()
        self._win_tid = int(ctypes.windll.kernel32.GetCurrentThreadId())
        self._register_class()
        # 必须是可前置的隐藏顶层窗，不能用 HWND_MESSAGE。
        # 否则 TrackPopupMenuEx / SetForegroundWindow 会立刻失败，右键看起来没反应。
        self.hwnd = int(
            ctypes.windll.user32.CreateWindowExW(
                WS_EX_TOOLWINDOW,
                _CLASS,
                "CursorTokenTray",
                WS_POPUP,
                0,
                0,
                0,
                0,
                None,
                None,
                get_module_handle(),
                None,
            )
            or 0
        )
        if not self.hwnd:
            raise RuntimeError("CreateWindowExW for tray host failed")
        self._apply_icon(self._image)
        self._nid_message(NIM_ADD, NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        self._nid_message(NIM_SETVERSION, 0, version=NOTIFYICON_VERSION_4)
        self._added = True
        app_log("native tray icon added")
        if setup is not None:
            try:
                setup(self)
            except Exception as exc:
                app_log(f"native tray setup failed: {exc}")
        msg = MSG()
        user32 = ctypes.windll.user32
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self._cleanup()

    def stop(self) -> None:
        import ctypes

        if self._win_tid:
            ctypes.windll.user32.PostThreadMessageW(int(self._win_tid), WM_QUIT, 0, 0)

    def invoke(self, fn: Callable[[], Any]) -> None:
        self._invoke_q.put(fn)
        if self.hwnd:
            post_message(self.hwnd, WM_INVOKE, 0, 0)

    @property
    def icon(self) -> Image.Image:
        return self._image

    @icon.setter
    def icon(self, image: Image.Image) -> None:
        self._image = image
        if threading.get_ident() == self._thread_id and self.hwnd:
            self._apply_icon(image)
            self._nid_message(NIM_MODIFY, NIF_ICON | NIF_TIP | NIF_SHOWTIP)
            return
        if self.hwnd:
            post_message(self.hwnd, WM_APPLY_ICON, 0, 0)

    @property
    def title(self) -> str:
        return self._tooltip

    @title.setter
    def title(self, value: str) -> None:
        self._tooltip = value or ""

    @property
    def visible(self) -> bool:
        return self._added

    @visible.setter
    def visible(self, value: bool) -> None:
        if not value:
            self._remove()

    def notify(self, message: str, title: str = "") -> None:
        self._pending_notify = (title or "", message or "")
        if threading.get_ident() == self._thread_id and self.hwnd:
            self._show_balloon()
            return
        if self.hwnd:
            post_message(self.hwnd, WM_APPLY_NOTIFY, 0, 0)

    def icon_rect(self) -> tuple[int, int, int, int] | None:
        import ctypes
        from ctypes import wintypes

        from win_api import RECT

        if not self.hwnd:
            return None
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = self.hwnd
        ident.uID = TRAY_UID
        rect = RECT()
        hr = ctypes.windll.shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(rect))
        if hr >= 0 and rect.right > rect.left:
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        return None

    def _register_class(self) -> None:
        import ctypes

        self._wndproc = WNDPROC(self._wnd_proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = get_module_handle()
        wc.hCursor = load_cursor_arrow()
        wc.lpszClassName = _CLASS
        atom = ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            if err not in (0, 1410):  # already registered
                app_log(f"RegisterClassW failed err={err}")

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAYICON:
                # NOTIFYICON_VERSION_4：LOWORD=事件，HIWORD=图标 ID
                event = int(lparam) & 0xFFFF
                now = time.monotonic()
                if event in (WM_LBUTTONUP, NIN_SELECT, NIN_KEYSELECT):
                    if now - self._last_left < 0.25:
                        return 0
                    self._last_left = now
                    if self.on_left_click:
                        self.on_left_click()
                    return 0
                if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    if now - self._last_right < 0.25:
                        return 0
                    self._last_right = now
                    if self.on_right_click:
                        self.on_right_click()
                    return 0
                return 0
            if msg == WM_INVOKE:
                while True:
                    try:
                        fn = self._invoke_q.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        fn()
                    except Exception as exc:
                        app_log(f"tray invoke failed: {exc}")
                return 0
            if msg == WM_APPLY_ICON:
                self._apply_icon(self._image)
                self._nid_message(NIM_MODIFY, NIF_ICON | NIF_TIP | NIF_SHOWTIP)
                return 0
            if msg == WM_APPLY_NOTIFY:
                self._show_balloon()
                return 0
            if msg == WM_DESTROY:
                self._remove()
                return 0
        except Exception as exc:
            app_log(f"tray wndproc failed: {exc}")
        return def_window_proc(hwnd, msg, wparam, lparam)

    def _apply_icon(self, image: Image.Image) -> None:
        handle = _hicon_from_image(image)
        old = self._hicon
        self._hicon = handle
        if old:
            destroy_icon(old)

    def _nid(self, *, flags: int, version: int | None = None) -> NOTIFYICONDATAW:
        import ctypes

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = TRAY_UID
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon
        tip = (self._tooltip or "")[:127]
        nid.szTip = tip
        if version is not None:
            nid.uVersion = version
        return nid

    def _nid_message(self, code: int, flags: int, *, version: int | None = None) -> None:
        import ctypes

        nid = self._nid(flags=flags, version=version)
        ctypes.windll.shell32.Shell_NotifyIconW(int(code), ctypes.byref(nid))

    def _show_balloon(self) -> None:
        pending = self._pending_notify
        self._pending_notify = None
        if not pending or not self.hwnd:
            return
        title, message = pending
        import ctypes

        nid = self._nid(flags=NIF_INFO | NIF_SHOWTIP | NIF_TIP)
        nid.szInfoTitle = (title or "")[:63]
        nid.szInfo = (message or "")[:255]
        nid.dwInfoFlags = NIIF_INFO | NIIF_NOSOUND
        nid.uVersion = NOTIFYICON_VERSION_4
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _remove(self) -> None:
        if self._added and self.hwnd:
            self._nid_message(NIM_DELETE, NIF_MESSAGE)
            self._added = False
        if self._hicon:
            destroy_icon(self._hicon)
            self._hicon = 0

    def _cleanup(self) -> None:
        import ctypes

        self._remove()
        if self.hwnd:
            ctypes.windll.user32.DestroyWindow(self.hwnd)
            self.hwnd = 0
        app_log("native tray cleaned up")
