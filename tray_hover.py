"""托盘 / 菜单栏图标点击检测。Windows 轮询图标矩形；macOS 交给 pystray 默认动作。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from platform_util import IS_MAC, IS_WIN, cursor_pos

log = logging.getLogger("tray_hover")

HIT_PAD = 8
VK_RBUTTON = 0x02
VK_LBUTTON = 0x01
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B


def icon_uid(icon) -> int:
    return id(icon) & 0xFFFFFFFF


def patch_pystray_uid(icon) -> None:
    """修复 pystray 误写 hID、实际 uID=0 的问题（须在 NIM_ADD 前调用）。非 Windows 为空操作。"""
    if not IS_WIN:
        return
    import ctypes

    from pystray._util import win32 as win32util

    def _message(code, flags, **kwargs):
        nid = win32util.NOTIFYICONDATAW(
            cbSize=ctypes.sizeof(win32util.NOTIFYICONDATAW),
            hWnd=icon._hwnd,
            uID=icon_uid(icon),
            uFlags=flags,
            **kwargs,
        )
        win32util.Shell_NotifyIcon(code, nid)

    icon._message = _message  # type: ignore[method-assign]


def suppress_native_context_menu(
    icon,
    *,
    on_right_click: Callable[[], None] | None = None,
) -> None:
    """Windows：右键不走 pystray 原生菜单，改调自定义回调。

    托盘菜单只有一项隐藏的 default，TrackPopupMenuEx 会抢前台，
    矢量菜单子进程刚出来就被 FocusOut 关掉，看起来像右键没反应。
    直接挂在 WM_RBUTTONUP 上，不依赖 Shell_NotifyIconGetRect（溢出区经常拿不到）。
    """
    if not IS_WIN:
        return
    original = getattr(icon, "_on_notify", None)

    def _on_notify(wparam, lparam):
        if lparam in (WM_RBUTTONUP, WM_RBUTTONDOWN, WM_CONTEXTMENU):
            if lparam != WM_RBUTTONDOWN and on_right_click is not None:
                threading.Thread(target=on_right_click, daemon=True, name="tray-right").start()
            return 0
        if original is not None:
            return original(wparam, lparam)
        return 0

    icon._on_notify = _on_notify  # type: ignore[method-assign]
    try:
        # 双保险：即便回调没换上，没有 HMENU 也不会弹出原生菜单。
        icon._menu_handle = None  # type: ignore[attr-defined]
    except Exception:
        pass


class HoverWatcher:
    """后台轮询托盘图标上的点击；回调只在后台线程触发。不根据悬停弹出。"""

    def __init__(
        self,
        icon,
        *,
        on_open: Callable[[], None] | None = None,
        on_close: Callable[[], None] | None = None,
        on_right_click: Callable[[], None] | None = None,
        on_left_click: Callable[[], None] | None = None,
        poll_sec: float = 0.12,
        open_delay_sec: float = 0.22,
    ) -> None:
        self.icon = icon
        self.on_open = on_open
        self.on_close = on_close
        self.on_right_click = on_right_click
        self.on_left_click = on_left_click
        self.poll_sec = poll_sec
        self.open_delay_sec = open_delay_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._opened = False
        self._enter_since: float | None = None
        self._suppress_until_leave = False
        self._lock = threading.Lock()
        self._busy = False
        self.enabled = True
        self._rbtn_was_down = False
        self._lbtn_was_down = False

    def start(self) -> None:
        if not IS_WIN:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="tray-hover", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.enabled = False
        self._stop.set()

    def pause(self) -> None:
        self.enabled = False
        with self._lock:
            self._enter_since = None

    def resume(self) -> None:
        self.enabled = True

    def notify_opened(self) -> None:
        with self._lock:
            self._opened = True
            self._suppress_until_leave = False

    def notify_closed(self) -> None:
        """点击关闭后：需移出图标再移入，才会再次悬停打开。"""
        with self._lock:
            self._opened = False
            self._enter_since = None
            self._suppress_until_leave = True

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_sec):
            try:
                over = self._cursor_over_icon()
            except Exception:
                over = False

            r_down = _button_down(VK_RBUTTON)
            l_down = _button_down(VK_LBUTTON)
            just_r_up = self._rbtn_was_down and not r_down
            just_l_up = self._lbtn_was_down and not l_down
            self._rbtn_was_down = r_down
            self._lbtn_was_down = l_down

            # 右键抬起：即使 pause 也要能开菜单（菜单打开期间 enabled=False）
            if just_r_up and over and self.on_right_click is not None:
                threading.Thread(target=self._run_right_click, daemon=True).start()
                continue

            if not self.enabled:
                continue

            if just_l_up and over and self.on_left_click is not None:
                threading.Thread(target=self._run_left_click, daemon=True).start()

    def _run_right_click(self) -> None:
        try:
            if self.on_right_click:
                self.on_right_click()
        except Exception:
            log.exception("right click failed")

    def _run_left_click(self) -> None:
        try:
            if self.on_left_click:
                self.on_left_click()
        except Exception:
            log.exception("left click failed")

    def _cursor_over_icon(self) -> bool:
        rect = get_tray_icon_rect(self.icon)
        if rect is None:
            return False
        left, top, right, bottom = rect
        left -= HIT_PAD
        top -= HIT_PAD
        right += HIT_PAD
        bottom += HIT_PAD
        x, y = cursor_pos()
        return left <= x <= right and top <= y <= bottom


def enable_hover_flyout(
    icon,
    *,
    on_open: Callable[[], None] | None = None,
    on_close: Callable[[], None] | None = None,
    on_right_click: Callable[[], None] | None = None,
    on_left_click: Callable[[], None] | None = None,
) -> HoverWatcher:
    """Windows：轮询点击。macOS：空操作（左键走 pystray 默认项，右键走原生菜单）。"""
    watcher = HoverWatcher(
        icon,
        on_open=on_open,
        on_close=on_close,
        on_right_click=on_right_click,
        on_left_click=on_left_click,
    )
    watcher.start()
    icon._hover_watcher = watcher  # type: ignore[attr-defined]
    return watcher


def get_tray_icon_rect(icon) -> tuple[int, int, int, int] | None:
    if IS_MAC:
        return _get_status_item_rect(icon)
    if not IS_WIN:
        return None
    return _get_notify_icon_rect(icon)


def _get_notify_icon_rect(icon) -> tuple[int, int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    hwnd = getattr(icon, "_hwnd", None)
    if not hwnd:
        return None

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    class NOTIFYICONIDENTIFIER(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("guidItem", GUID),
        ]

    Shell_NotifyIconGetRect = ctypes.windll.shell32.Shell_NotifyIconGetRect
    Shell_NotifyIconGetRect.argtypes = [
        ctypes.POINTER(NOTIFYICONIDENTIFIER),
        ctypes.POINTER(wintypes.RECT),
    ]
    Shell_NotifyIconGetRect.restype = ctypes.HRESULT

    for uid in (icon_uid(icon), 0):
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = hwnd
        ident.uID = uid
        rect = wintypes.RECT()
        hr = Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(rect))
        if hr >= 0 and rect.right > rect.left and rect.bottom > rect.top:
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return None


def _get_status_item_rect(icon) -> tuple[int, int, int, int] | None:
    try:
        from AppKit import NSScreen

        item = getattr(icon, "_status_item", None)
        if item is None:
            return None
        button = item.button()
        if button is None:
            return None
        window = button.window()
        if window is None:
            return None
        rect = window.convertRectToScreen_(button.convertRect_toView_(button.bounds(), None))
        screens = list(NSScreen.screens() or [])
        if not screens:
            return None
        primary_h = float(screens[0].frame().size.height)
        x = float(rect.origin.x)
        y = float(rect.origin.y)
        w = float(rect.size.width)
        h = float(rect.size.height)
        left = int(x)
        top = int(round(primary_h - y - h))
        right = int(round(x + w))
        bottom = int(round(primary_h - y))
        return left, top, right, bottom
    except Exception:
        return None


def cursor_over_hwnd(hwnd: int) -> bool:
    if not hwnd:
        return False
    if IS_WIN:
        try:
            import ctypes
            from ctypes import wintypes

            x, y = cursor_pos()
            rect = wintypes.RECT()
            if not ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
                return False
            return rect.left <= x <= rect.right and rect.top <= y <= rect.bottom
        except Exception:
            return False
    return False


def cursor_over_widget(win) -> bool:
    if win is None:
        return False
    try:
        x, y = cursor_pos()
        left = int(win.winfo_rootx())
        top = int(win.winfo_rooty())
        right = left + int(win.winfo_width())
        bottom = top + int(win.winfo_height())
        return left <= x <= right and top <= y <= bottom
    except Exception:
        return False


def _button_down(vk: int) -> bool:
    if not IS_WIN:
        return False
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False
