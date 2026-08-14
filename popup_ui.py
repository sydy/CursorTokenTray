"""左键状态悬浮框 + 矢量风格右键菜单。"""

from __future__ import annotations

import math
import queue
import threading
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from config import APP_NAME
from cursor_api import UsageSnapshot, format_token_count, is_auth_error_message
from dpi_util import enable_dpi_awareness
from icon_renderer import create_progress_icon, create_sparkline, remaining_color
from ui_ctk import init_ctk

DPI_SCALE = enable_dpi_awareness()


@dataclass
class MenuAction:
    key: str
    label: str
    icon: str  # refresh | web | settings | quit | status
    callback: Callable[[], None]
    danger: bool = False


@dataclass
class StatusActions:
    on_open_settings: Callable[[], None] | None = None
    on_refresh: Callable[[], None] | None = None
    on_open_spending: Callable[[], None] | None = None
    on_copy_summary: Callable[[], None] | None = None


class PopupManager:
    """状态飞出层管理：单一 Tk 常驻线程承载 Toplevel，避免反复创建 Tk 崩溃。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._show_lock = threading.Lock()
        self._cmd_queue: queue.Queue[
            tuple[Callable[[], Any], threading.Event | None, list[BaseException | None] | None]
        ] = queue.Queue()
        self._ui_thread: threading.Thread | None = None
        self._ui_ready = threading.Event()
        self._closing = threading.Event()
        self._root: tk.Tk | None = None
        self._generation = 0
        self._kind: str | None = None
        self._status_hwnd = 0
        self._hover_close_gen = 0
        self._tray_icon = None
        self._status_card: _StatusCard | None = None
        self._popup_menu: _VectorMenu | None = None
        self._host_menu: _VectorMenu | None = None
        self._host_closed = threading.Event()
        self._start_ui_thread()

    def bind_tray_icon(self, icon) -> None:
        self._tray_icon = icon

    def _start_ui_thread(self) -> None:
        if self._ui_thread is not None and self._ui_thread.is_alive():
            return
        self._ui_ready.clear()
        t = threading.Thread(target=self._ui_loop, daemon=True, name="popup-ui")
        self._ui_thread = t
        t.start()
        self._ui_ready.wait(timeout=5.0)

    def _ui_loop(self) -> None:
        root: tk.Tk | None = None
        try:
            init_ctk()
            root = ctk.CTk()
            root.withdraw()
            _apply_tk_scaling(root)
            try:
                from app_icon import hide_from_taskbar

                # 隐藏根窗口，避免任务栏出现 Python 默认图标
                root.update_idletasks()
                hide_from_taskbar(root)
            except Exception:
                pass
            with self._lock:
                self._root = root
                root._tray_popup_gen = self._generation  # type: ignore[attr-defined]

            def pump() -> None:
                self._drain_commands()
                try:
                    if root is not None and root.winfo_exists():
                        root.after(16, pump)
                except tk.TclError:
                    pass

            pump()
            self._ui_ready.set()
            root.mainloop()
        except Exception:
            self._ui_ready.set()
        finally:
            with self._lock:
                if self._root is root:
                    self._root = None
                    self._status_card = None
                    self._popup_menu = None
                    self._kind = None
                    self._status_hwnd = 0

    def _drain_commands(self) -> None:
        while True:
            try:
                fn, done, err_box = self._cmd_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as exc:
                if err_box is not None:
                    err_box[0] = exc
            finally:
                if done is not None:
                    done.set()

    def _run_on_ui(
        self,
        fn: Callable[[], Any],
        *,
        wait: bool = True,
        timeout: float = 3.0,
    ) -> bool:
        self._start_ui_thread()
        if threading.current_thread() is self._ui_thread:
            fn()
            return True
        done = threading.Event() if wait else None
        err_box: list[BaseException | None] | None = [None] if wait else None
        self._cmd_queue.put((fn, done, err_box))
        if not wait:
            return True
        return done.wait(timeout=timeout)

    def run_on_ui(
        self,
        fn: Callable[[], Any],
        *,
        wait: bool = False,
        timeout: float = 3.0,
    ) -> bool:
        """供设置窗等模块把 UI 工作投递到唯一 Tk 线程。"""
        return self._run_on_ui(fn, wait=wait, timeout=timeout)

    @property
    def tk_root(self) -> tk.Tk | None:
        with self._lock:
            return self._root

    @property
    def status_visible(self) -> bool:
        with self._lock:
            card = self._status_card
            return card is not None and not getattr(card, "_closing", False)

    @property
    def menu_visible(self) -> bool:
        with self._lock:
            for menu in (self._host_menu, self._popup_menu):
                if menu is not None and not getattr(menu, "_closing", False):
                    return True
            return False

    @property
    def busy(self) -> bool:
        return self._closing.is_set()

    def toggle_status(
        self,
        *,
        usage: UsageSnapshot | None,
        error_message: str | None,
        updated_at: str | None = None,
        actions: StatusActions | None = None,
    ) -> bool:
        if self.status_visible or self.busy:
            return True
        self.show_status(
            usage=usage,
            error_message=error_message,
            updated_at=updated_at,
            from_hover=False,
            actions=actions,
        )
        return True

    def show_status(
        self,
        *,
        usage: UsageSnapshot | None,
        error_message: str | None,
        updated_at: str | None = None,
        from_hover: bool = False,
        on_closed: Callable[[], None] | None = None,
        actions: StatusActions | None = None,
        history_values: list[float] | None = None,
        daily_burn: float | None = None,
    ) -> None:
        if self.menu_visible:
            if not self.close_and_wait(1.5):
                return
        if self.status_visible:
            return
        manager = self
        act = actions or StatusActions()

        def work() -> None:
            self._close_popups_unlocked(notify=False)
            root = self._root
            if root is None:
                return
            with self._lock:
                self._generation += 1
                gen = self._generation
                root._tray_popup_gen = gen  # type: ignore[attr-defined]
            card = _StatusCard(
                root,
                usage=usage,
                error_message=error_message,
                updated_at=updated_at,
                on_hwnd=self._set_status_hwnd,
                on_pointer_enter=self.cancel_hover_close,
                on_closed=on_closed,
                from_hover=from_hover,
                manager=manager,
                actions=act,
                history_values=history_values,
                daily_burn=daily_burn,
            )
            with self._lock:
                self._status_card = card
                self._kind = "status"

        self._run_on_ui(work, wait=False)

    def update_status(
        self,
        *,
        usage: UsageSnapshot | None,
        error_message: str | None,
        updated_at: str | None = None,
        history_values: list[float] | None = None,
        daily_burn: float | None = None,
    ) -> None:
        with self._lock:
            if self._kind != "status" or self._root is None:
                return
            card = self._status_card
            root = self._root
            gen = self._generation
        if card is None or root is None:
            return
        if getattr(card, "_closing", False):
            return

        def _apply() -> None:
            try:
                if not self.is_current(gen):
                    return
                if getattr(card, "_closing", False):
                    return
                card.update_data(
                    usage=usage,
                    error_message=error_message,
                    updated_at=updated_at,
                    history_values=history_values,
                    daily_burn=daily_burn,
                )
            except Exception:
                pass

        try:
            root.after(0, _apply)
        except Exception:
            pass

    def show_menu(self, actions: list[MenuAction]) -> None:
        with self._show_lock:
            if self.status_visible or self.menu_visible:
                if not self.close_and_wait(2.5):
                    return
            closed = threading.Event()

            def work() -> None:
                self._close_popups_unlocked(notify=False)
                root = self._root
                if root is None:
                    closed.set()
                    return
                with self._lock:
                    self._generation += 1
                    gen = self._generation
                    root._tray_popup_gen = gen  # type: ignore[attr-defined]
                menu = _VectorMenu(
                    root,
                    actions,
                    manager=self,
                    quit_root_on_close=False,
                    on_closed=closed.set,
                )
                with self._lock:
                    self._popup_menu = menu
                    self._kind = "menu"

            if not self._run_on_ui(work, timeout=3.0):
                return
            closed.wait(timeout=300.0)

    def show_menu_on_host(self, host_root: tk.Misc, actions: list[MenuAction]) -> None:
        """附着到已有 Tk（设置窗）显示菜单，避免 Windows 上双 Tk 冲突。"""
        with self._show_lock:
            if self.status_visible or self.menu_visible:
                if not self.close_and_wait(2.5):
                    return
            self.close_host_menu()
            self._host_closed.clear()
            ready = threading.Event()

            def _open() -> None:
                try:
                    if self._host_menu is not None:
                        try:
                            self._host_menu._close()
                        except Exception:
                            pass
                    with self._lock:
                        self._generation += 1
                        gen = self._generation
                    try:
                        host_root._tray_popup_gen = gen  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    menu = _VectorMenu(
                        host_root,
                        actions,
                        manager=self,
                        quit_root_on_close=False,
                        on_closed=self._host_closed.set,
                    )
                    with self._lock:
                        self._host_menu = menu
                        self._kind = "menu"
                finally:
                    ready.set()

            try:
                host_root.after(0, _open)
            except tk.TclError:
                return
            if not ready.wait(timeout=2.0):
                return
            self._host_closed.wait(timeout=300.0)

    def _on_menu_closed(self, menu: _VectorMenu) -> None:
        with self._lock:
            if self._host_menu is menu:
                self._host_menu = None
            if self._popup_menu is menu:
                self._popup_menu = None
            if self._status_card is None and self._host_menu is None and self._popup_menu is None:
                self._kind = None

    def _on_status_closed(self, card: _StatusCard) -> None:
        with self._lock:
            if self._status_card is card:
                self._status_card = None
                self._status_hwnd = 0
            if self._status_card is None and self._host_menu is None and self._popup_menu is None:
                self._kind = None

    def close_host_menu(self) -> None:
        with self._lock:
            menu = self._host_menu
        if menu is None:
            return
        root = menu.root
        done = threading.Event()

        def _do() -> None:
            try:
                menu._close()
            except Exception:
                pass
            done.set()

        try:
            root.after(0, _do)
        except tk.TclError:
            with self._lock:
                if self._host_menu is menu:
                    self._host_menu = None
            return
        done.wait(timeout=1.0)

    def schedule_hover_close(self, delay_sec: float = 0.25) -> None:
        self._hover_close_gen += 1
        gen = self._hover_close_gen

        def _later() -> None:
            if gen != self._hover_close_gen:
                return
            if not self.status_visible:
                return
            from tray_hover import cursor_over_hwnd

            if cursor_over_hwnd(self._status_hwnd):
                return
            if self.cursor_over_tray():
                return
            self.close()

        threading.Timer(delay_sec, _later).start()

    def cancel_hover_close(self) -> None:
        self._hover_close_gen += 1

    def close(self) -> None:
        """请求关闭飞出层与弹出菜单。"""
        self._run_on_ui(lambda: self._close_popups_unlocked(notify=True), wait=False)

    def _close_popups_unlocked(self, *, notify: bool) -> None:
        with self._lock:
            self._generation += 1
            gen = self._generation
            root = self._root
            card = self._status_card
            menu = self._popup_menu
            self._status_card = None
            self._popup_menu = None
            if self._host_menu is None:
                self._kind = None
            self._status_hwnd = 0
        if root is not None:
            try:
                root._tray_popup_gen = gen  # type: ignore[attr-defined]
            except Exception:
                pass
        if card is not None and not getattr(card, "_closing", False):
            card._closing = True
            try:
                card.win.destroy()
            except tk.TclError:
                pass
            if notify and card._on_closed is not None:
                try:
                    card._on_closed()
                except Exception:
                    pass
        if menu is not None and not getattr(menu, "_closing", False):
            menu._close()

    def close_and_wait(self, timeout: float = 2.0) -> bool:
        """关闭并等待 UI 线程完成销毁，避免叠层冲突。"""
        self.close_host_menu()
        self._closing.set()
        try:
            ok = self._run_on_ui(
                lambda: self._close_popups_unlocked(notify=True),
                timeout=max(0.1, timeout),
            )
            deadline = time.monotonic() + max(0.1, timeout)
            while time.monotonic() < deadline:
                if not self.status_visible and not self.menu_visible:
                    break
                time.sleep(0.02)
            return ok and not self.status_visible and not self.menu_visible
        finally:
            self._closing.clear()

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def is_current(self, gen: int) -> bool:
        with self._lock:
            return gen == self._generation

    def cursor_over_tray(self) -> bool:
        icon = self._tray_icon
        if icon is None:
            return False
        try:
            from tray_hover import get_tray_icon_rect

            rect = get_tray_icon_rect(icon)
            if rect is None:
                return False
            left, top, right, bottom = rect
            pad = 12
            x, y = _cursor_pos()
            return left - pad <= x <= right + pad and top - pad <= y <= bottom + pad
        except Exception:
            return False

    def _set_status_hwnd(self, hwnd: int) -> None:
        with self._lock:
            self._status_hwnd = int(hwnd or 0)


def build_status_lines(
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None = None,
) -> list[tuple[str, str]]:
    if error_message:
        return [("状态", error_message)]
    if usage is None:
        return [("状态", "等待刷新…")]

    rows: list[tuple[str, str]] = [
        ("剩余", f"{usage.remaining_percent:.1f}%（已用 {usage.used_percent:.1f}%）"),
        ("计划", usage.membership_type),
    ]
    if usage.total_tokens:
        rows.append(("消耗 Token", format_token_count(usage.total_tokens)))
    if usage.auto_percent_used is not None or usage.api_percent_used is not None:
        auto = "—" if usage.auto_percent_used is None else f"{usage.auto_percent_used:.1f}%"
        api = "—" if usage.api_percent_used is None else f"{usage.api_percent_used:.1f}%"
        rows.append(("明细", f"First-party {auto} · API {api}"))

    if usage.billing_cycle_end:
        end_text = _format_date(usage.billing_cycle_end)
        if usage.days_remaining is not None:
            rows.append(("重置", f"{end_text}（还剩 {usage.days_remaining} 天）"))
        else:
            rows.append(("重置", end_text))
        rows.append(("预计可用", format_estimated_days(usage)))
    elif usage.estimated_usable_days is not None:
        rows.append(("预计可用", format_estimated_days(usage)))

    rows.append(("更新", updated_at or datetime.now().strftime("%H:%M:%S")))
    return rows


def format_summary_text(
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None,
) -> str:
    if error_message:
        return f"状态: {error_message} | 更新 {updated_at or '—'}"
    if usage is None:
        return "状态: 等待刷新…"
    auto = "—" if usage.auto_percent_used is None else f"{usage.auto_percent_used:.1f}%"
    api = "—" if usage.api_percent_used is None else f"{usage.api_percent_used:.1f}%"
    est = format_estimated_days(usage)
    tokens = ""
    if usage.total_tokens:
        tokens = f"消耗 {format_token_count(usage.total_tokens)} Token | "
    return (
        f"剩余 {usage.remaining_percent:.1f}% | 计划 {usage.membership_type} | "
        f"{tokens}First-party {auto} | API {api} | 预计可用 {est} | 更新 {updated_at or '—'}"
    )


def format_estimated_days(usage: UsageSnapshot) -> str:
    est = usage.estimated_usable_days
    if est is None:
        if usage.used_percent < 0.2:
            return "用量过低，暂无法估算"
        if usage.days_elapsed is not None and usage.days_elapsed < 0.04:
            return "周期刚开始，统计中"
        return "暂无法估算"

    if est <= 0:
        text = "已耗尽"
    elif est < 1:
        text = f"约 {max(1, int(est * 24))} 小时"
    else:
        text = f"约 {est:.1f} 天".replace(".0 天", " 天")

    reset_left = usage.days_remaining
    if reset_left is not None and est > 0:
        if est >= reset_left:
            text += "  ·  可撑过本周期"
        else:
            text += "  ·  可能提前耗尽"
    return text


def _format_date(iso_value: str) -> str:
    try:
        text = iso_value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return f"{dt.month}月{dt.day}日"
    except ValueError:
        return iso_value


def _apply_tk_scaling(root: tk.Misc) -> None:
    try:
        import ctypes

        dpi = int(ctypes.windll.user32.GetDpiForSystem())
        root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        try:
            root.tk.call("tk", "scaling", DPI_SCALE * 96 / 72.0)
        except Exception:
            pass


def _cursor_pos() -> tuple[int, int]:
    try:
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)
    except Exception:
        return 100, 100


def _work_area() -> tuple[int, int, int, int]:
    """当前光标所在显示器的工作区（排除任务栏），支持多屏。"""
    try:
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
        monitor = user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r = info.rcWork
            return int(r.left), int(r.top), int(r.right), int(r.bottom)

        rect = wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    except Exception:
        return 0, 0, 1920, 1040


def _place_above_taskbar(win: tk.Toplevel, width: int, height: int, gap: int = 10) -> None:
    cx, _cy = _cursor_pos()
    left, top, right, bottom = _work_area()

    px = cx - width // 2
    px = max(left + 8, min(px, right - width - 8))
    py = bottom - height - gap
    if py < top + 8:
        py = top + 8

    win.geometry(f"{width}x{height}+{px}+{py}")


def _ui_font(size: int, bold: bool = False) -> tuple:
    family = "Microsoft YaHei UI"
    return (family, size, "bold") if bold else (family, size)


class _StatusCard:
    """Win11 风格用量飞出层。"""

    BG = "#202020"
    FG = "#FFFFFF"
    FG_SEC = "#C5C5C5"
    FG_TER = "#9A9A9A"
    LINE = "#3F3F3F"
    TRACK = "#3A3A3A"
    BTN_BG = "#2A2A2A"
    BTN_HOVER = "#3A3A3A"

    def __init__(
        self,
        root: tk.Tk,
        *,
        usage: UsageSnapshot | None,
        error_message: str | None,
        updated_at: str | None,
        on_hwnd: Callable[[int], None] | None = None,
        on_pointer_enter: Callable[[], None] | None = None,
        on_closed: Callable[[], None] | None = None,
        from_hover: bool = False,
        manager: PopupManager | None = None,
        actions: StatusActions | None = None,
        history_values: list[float] | None = None,
        daily_burn: float | None = None,
    ) -> None:
        from win11_style import apply_win11_flyout, toplevel_hwnd

        self.root = root
        self._manager = manager
        self._gen = int(getattr(root, "_tray_popup_gen", 0) or 0)
        self._closing = False
        self._photos: list[ImageTk.PhotoImage] = []
        self._from_hover = from_hover
        self._on_hwnd = on_hwnd
        self._on_pointer_enter = on_pointer_enter
        self._on_closed = on_closed
        self._actions = actions or StatusActions()
        self._lbtn_was_down = False
        self._usage = usage
        self._error_message = error_message
        self._updated_at = updated_at
        self._history_values = list(history_values or [])
        self._daily_burn = daily_burn
        root._tray_on_closed = on_closed  # type: ignore[attr-defined]

        win = ctk.CTkToplevel(root)
        self.win = win
        try:
            win.withdraw()
        except tk.TclError:
            pass
        win.title(APP_NAME)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(fg_color=self.BG)

        self._body_host = ctk.CTkFrame(win, fg_color=self.BG, corner_radius=0)
        self._body_host.pack(fill="both", expand=True)

        self._rebuild_content()

        win.update_idletasks()
        width = max(win.winfo_reqwidth(), 420)
        height = win.winfo_reqheight()
        _place_above_taskbar(win, width, height, gap=14)

        win.update()
        hwnd = toplevel_hwnd(win)
        apply_win11_flyout(hwnd)
        if self._on_hwnd:
            self._on_hwnd(hwnd)
        try:
            win.deiconify()
        except tk.TclError:
            pass

        win.bind("<Escape>", lambda _e: self._request_close())
        win.bind("<Enter>", self._on_enter)
        self._opened_at = time.monotonic()
        self._hwnd = hwnd
        win.after(120, self._watch_tick)
        # 悬停更短；点击打开可多看一会；移入卡片会重置计时
        self._auto_close_ms = 8000 if from_hover else 25000
        self._auto_close_job = win.after(self._auto_close_ms, self._request_close)

    def update_data(
        self,
        *,
        usage: UsageSnapshot | None,
        error_message: str | None,
        updated_at: str | None = None,
        history_values: list[float] | None = None,
        daily_burn: float | None = None,
    ) -> None:
        if self._closing:
            return
        if self._manager is not None and not self._manager.is_current(self._gen):
            return
        new_hist = list(history_values) if history_values is not None else self._history_values
        new_burn = daily_burn if (daily_burn is not None or history_values is not None) else self._daily_burn
        # 数据未变则跳过整页重建，减少闪烁
        same = (
            usage is self._usage
            and error_message == self._error_message
            and updated_at == self._updated_at
            and new_hist == self._history_values
            and new_burn == self._daily_burn
        )
        if same:
            return
        self._usage = usage
        self._error_message = error_message
        self._updated_at = updated_at
        self._history_values = new_hist
        self._daily_burn = new_burn
        try:
            self._rebuild_content()
        except tk.TclError:
            return
        try:
            self.win.update_idletasks()
            width = max(self.win.winfo_reqwidth(), 420)
            height = self.win.winfo_reqheight()
            geo = self.win.geometry()
            parts = geo.split("+")
            pos = "+" + "+".join(parts[1:]) if len(parts) >= 3 else ""
            self.win.geometry(f"{width}x{height}{pos}")
        except tk.TclError:
            pass

    def _rebuild_content(self) -> None:
        for child in self._body_host.winfo_children():
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._photos.clear()

        usage = self._usage
        error_message = self._error_message
        updated_at = self._updated_at
        card = self._body_host

        unconfigured = bool(error_message) and str(error_message).startswith("未配置")
        has_usage = usage is not None
        is_error = bool(error_message) and not unconfigured and not has_usage
        remaining = None if usage is None else usage.remaining_percent

        hero = ctk.CTkFrame(card, fg_color="transparent")
        hero.pack(fill="x", padx=16, pady=(14, 10))

        icon_px = max(52, int(round(52 * DPI_SCALE)))
        if has_usage:
            icon_img = create_progress_icon(remaining, error=False, size=icon_px)
        elif is_error:
            icon_img = create_progress_icon(None, error=True, size=icon_px)
        else:
            icon_img = create_progress_icon(None, error=False, size=icon_px)
        photo = ImageTk.PhotoImage(icon_img)
        self._photos.append(photo)
        ctk.CTkLabel(hero, image=photo, text="").pack(side="left", padx=(0, 12))

        text_col = ctk.CTkFrame(hero, fg_color="transparent")
        text_col.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(text_col, text="套餐剩余", text_color=self.FG_SEC, font=ctk.CTkFont(size=12), anchor="w").pack(
            fill="x"
        )

        if has_usage and remaining is not None:
            accent = "#%02x%02x%02x" % remaining_color(remaining)
            pct_row = ctk.CTkFrame(text_col, fg_color="transparent")
            pct_row.pack(anchor="w", pady=(2, 4))
            ctk.CTkLabel(
                pct_row,
                text=f"{remaining:.1f}",
                text_color=accent,
                font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                pct_row,
                text="%",
                text_color=accent,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                anchor="sw",
            ).pack(side="left", padx=(2, 0), pady=(0, 4))

            bar = ctk.CTkProgressBar(
                text_col, height=6, progress_color=accent, fg_color=self.TRACK, corner_radius=3
            )
            bar.set(min(1.0, max(0.0, remaining / 100.0)))
            bar.pack(fill="x")
            memb = (usage.membership_type or "").strip()
            sub = f"已用 {usage.used_percent:.1f}%"
            if usage.total_tokens:
                sub = f"{sub} · {format_token_count(usage.total_tokens)} Token"
            if memb:
                sub = f"{sub} · {memb}"
            ctk.CTkLabel(text_col, text=sub, text_color=self.FG_TER, font=ctk.CTkFont(size=11), anchor="w").pack(
                fill="x", pady=(5, 0)
            )
        else:
            msg = error_message or "等待刷新…"
            ctk.CTkLabel(
                text_col,
                text=msg,
                text_color=self.FG,
                font=ctk.CTkFont(size=13),
                anchor="w",
                justify="left",
                wraplength=260,
            ).pack(fill="x", pady=(4, 0))
            if (is_auth_error_message(error_message) or unconfigured) and self._actions.on_open_settings:
                self._add_text_button(
                    text_col,
                    "去设置配置 Token",
                    self._actions.on_open_settings,
                    pady=(8, 0),
                )

        if has_usage:
            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=8, pady=(2, 2))
            added = 0
            if self._add_token_breakdown(body, usage):
                added += 1
            rows = self._detail_rows(usage, error_message, updated_at)
            for label, value in rows:
                if added:
                    self._sep(body)
                self._add_settings_row(body, label, value)
                added += 1

        if len(self._history_values) >= 2 and has_usage:
            chart = ctk.CTkFrame(card, fg_color="transparent")
            chart.pack(fill="x", padx=16, pady=(4, 2))
            burn = (
                f"近 7 日 · 日均消耗 {self._daily_burn:.1f}%"
                if self._daily_burn is not None
                else "近 7 日剩余趋势"
            )
            ctk.CTkLabel(chart, text=burn, text_color=self.FG_TER, font=ctk.CTkFont(size=11), anchor="w").pack(
                fill="x"
            )
            spark_w = max(200, int(round(220 * DPI_SCALE)))
            spark_h = max(36, int(round(40 * DPI_SCALE)))
            spark = create_sparkline(self._history_values, width=spark_w, height=spark_h)
            sph = ImageTk.PhotoImage(spark)
            self._photos.append(sph)
            ctk.CTkLabel(chart, image=sph, text="").pack(anchor="w", pady=(3, 0))

        self._sep(card, padx=12, pady=(6, 0))
        actions_row = ctk.CTkFrame(card, fg_color="transparent")
        actions_row.pack(fill="x", padx=10, pady=(8, 10))
        for i in range(4):
            actions_row.grid_columnconfigure(i, weight=1)
        self._copy_btn = self._add_action_btn(actions_row, "复制", self._on_copy, col=0)
        self._add_action_btn(actions_row, "刷新", self._actions.on_refresh, col=1)
        self._add_action_btn(actions_row, "账单", self._actions.on_open_spending, col=2)
        self._add_action_btn(actions_row, "设置", self._actions.on_open_settings, col=3)
        tip = updated_at or datetime.now().strftime("%H:%M:%S")
        ctk.CTkLabel(
            card,
            text=f"更新于 {tip}",
            text_color=self.FG_TER,
            font=ctk.CTkFont(size=11),
            anchor="e",
        ).pack(fill="x", padx=14, pady=(0, 10))

    def _on_copy(self) -> None:
        if self._actions.on_copy_summary:
            self._actions.on_copy_summary()
        else:
            text = format_summary_text(self._usage, self._error_message, self._updated_at)
            try:
                self.win.clipboard_clear()
                self.win.clipboard_append(text)
            except tk.TclError:
                pass
        btn = getattr(self, "_copy_btn", None)
        if btn is not None:
            try:
                prev = btn.cget("text")
                btn.configure(text="已复制")
                self.win.after(1200, lambda: btn.configure(text=prev) if btn.winfo_exists() else None)
            except tk.TclError:
                pass

    def _add_text_button(
        self,
        parent,
        text: str,
        command: Callable[[], None] | None,
        *,
        pady: tuple[int, int] = (0, 0),
    ) -> None:
        if command is None:
            return
        btn = ctk.CTkButton(
            parent,
            text=text,
            fg_color="transparent",
            hover_color=self.BTN_BG,
            text_color="#60A5FA",
            anchor="w",
            height=28,
            command=lambda: threading.Thread(target=command, daemon=True).start(),
        )
        btn.pack(fill="x", pady=pady)

    def _add_action_btn(
        self,
        parent,
        text: str,
        command: Callable[[], None] | None,
        *,
        col: int | None = None,
    ) -> ctk.CTkButton:
        def _run() -> None:
            if command is not None:
                threading.Thread(target=command, daemon=True).start()

        btn = ctk.CTkButton(
            parent,
            text=text,
            fg_color=self.BTN_BG,
            hover_color=self.BTN_HOVER,
            text_color=self.FG if command else self.FG_TER,
            height=32,
            corner_radius=6,
            command=_run if command else None,
            state="normal" if command else "disabled",
        )
        if col is not None:
            btn.grid(row=0, column=col, sticky="ew", padx=2)
        else:
            btn.pack(side="left", padx=3)
        return btn

    def _on_enter(self, _event=None) -> None:
        if self._on_pointer_enter:
            try:
                self._on_pointer_enter()
            except Exception:
                pass
        # 指针在卡片内时重置自动关闭，避免读趋势图被掐断
        try:
            job = getattr(self, "_auto_close_job", None)
            if job is not None:
                self.win.after_cancel(job)
            ms = int(getattr(self, "_auto_close_ms", 30000))
            self._auto_close_job = self.win.after(ms, self._request_close)
        except tk.TclError:
            pass

    def _watch_tick(self) -> None:
        if self._closing:
            return
        try:
            if self._manager is not None and not self._manager.is_current(self._gen):
                self._request_close()
                return
            if self._should_close_on_outside_click():
                self._request_close()
                return
            self.win.after(120, self._watch_tick)
        except tk.TclError:
            pass

    def _should_close_on_outside_click(self) -> bool:
        if time.monotonic() - getattr(self, "_opened_at", 0) < 0.45:
            return False
        try:
            import ctypes

            down = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:
            return False
        just_pressed = down and not self._lbtn_was_down
        self._lbtn_was_down = down
        if not just_pressed:
            return False
        from tray_hover import cursor_over_hwnd

        if cursor_over_hwnd(getattr(self, "_hwnd", 0)):
            return False
        if self._manager is not None and self._manager.cursor_over_tray():
            return False
        return True

    def _detail_rows(
        self,
        usage: UsageSnapshot | None,
        error_message: str | None,
        updated_at: str | None,
    ) -> list[tuple[str, str]]:
        if error_message:
            return [("状态", error_message)]
        if usage is None:
            return [("状态", "等待刷新…")]

        rows: list[tuple[str, str]] = []
        has_token_breakdown = bool(usage.model_usages) or bool(usage.total_tokens)
        if not has_token_breakdown:
            if usage.auto_percent_used is not None:
                rows.append(("套餐用量", f"{usage.auto_percent_used:.1f}%"))
            if usage.api_percent_used is not None:
                rows.append(("API 用量", f"{usage.api_percent_used:.1f}%"))
        if usage.billing_cycle_end:
            end_text = _format_date(usage.billing_cycle_end)
            if usage.days_remaining is not None:
                rows.append(("重置", f"{end_text} · 剩 {usage.days_remaining} 天"))
            else:
                rows.append(("重置", end_text))
            rows.append(("预计可用", format_estimated_days(usage)))
        elif usage.estimated_usable_days is not None:
            rows.append(("预计可用", format_estimated_days(usage)))
        return rows

    def _sep(self, parent, *, padx: int = 10, pady: tuple[int, int] | int = 0) -> None:
        ctk.CTkFrame(parent, fg_color=self.LINE, height=1, corner_radius=0).pack(
            fill="x", padx=padx, pady=pady
        )

    def _add_token_breakdown(self, parent, usage: UsageSnapshot | None) -> bool:
        if usage is None:
            return False
        models = list(usage.model_usages or ())
        total = usage.total_tokens or 0
        if not models and total <= 0:
            return False

        self._add_settings_row(parent, "消耗 Token", format_token_count(total or sum(m.tokens for m in models)))

        groups: list[tuple[str, list, float | None]] = []
        cursor_models = [m for m in models if m.is_cursor_model]
        other_models = [m for m in models if not m.is_cursor_model]
        if cursor_models:
            groups.append(("Cursor 模型", cursor_models, usage.auto_percent_used))
        if other_models:
            groups.append(("其他模型", other_models, usage.api_percent_used))

        for group_label, group_models, group_pct in groups:
            self._sep(parent)
            group_tokens = sum(m.tokens for m in group_models)
            value = format_token_count(group_tokens)
            if group_pct is not None:
                value = f"{value} · {group_pct:.1f}%"
            self._add_settings_row(parent, group_label, value)

            shown = group_models[:8]
            rest = group_models[8:]
            for model in shown:
                self._sep(parent)
                mv = format_token_count(model.tokens)
                if model.usage_percent is not None:
                    mv = f"{mv} · {model.usage_percent:.1f}%"
                self._add_settings_row(
                    parent,
                    model.name,
                    mv,
                    indent=14,
                    label_fg=self.FG_TER,
                    value_fg=self.FG_SEC,
                    compact=True,
                )
            if rest:
                self._sep(parent)
                rest_tokens = sum(m.tokens for m in rest)
                self._add_settings_row(
                    parent,
                    f"其余 {len(rest)} 个模型",
                    format_token_count(rest_tokens),
                    indent=14,
                    label_fg=self.FG_TER,
                    value_fg=self.FG_SEC,
                    compact=True,
                )
        return True

    def _add_settings_row(
        self,
        parent,
        label: str,
        value: str,
        *,
        indent: int = 0,
        label_fg: str | None = None,
        value_fg: str | None = None,
        compact: bool = False,
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=2 if compact else 4)
        ctk.CTkLabel(
            row,
            text=label,
            text_color=label_fg or self.FG_SEC,
            font=ctk.CTkFont(size=12 if compact else 13),
            anchor="w",
        ).pack(side="left", padx=(10 + indent, 12))
        ctk.CTkLabel(
            row,
            text=value,
            text_color=value_fg or self.FG,
            font=ctk.CTkFont(size=12 if compact else 13),
            anchor="e",
            justify="right",
        ).pack(side="right", fill="x", expand=True, padx=(8, 10))

    def _request_close(self, _event=None) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            job = getattr(self, "_auto_close_job", None)
            if job is not None:
                self.win.after_cancel(job)
                self._auto_close_job = None
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self._manager is not None:
            try:
                self._manager._on_status_closed(self)
            except Exception:
                pass
        if self._on_closed is not None:
            try:
                self._on_closed()
            except Exception:
                pass

    def _close(self) -> None:
        self._request_close()


def _menu_layout(root: tk.Misc | None = None) -> tuple[int, int, int, int, int]:
    """菜单逻辑尺寸（字号固定 pt，行高随 tk scaling 计算）。"""
    import tkinter.font as tkfont

    from win11_theme import MENU_ITEM_RADIUS, font as win11_font

    font_size = 10
    item_radius = MENU_ITEM_RADIUS
    min_width = 248
    icon_px = max(16, int(round(16 * DPI_SCALE)))

    row_h = 36
    if root is not None:
        try:
            f = tkfont.Font(root=root, font=win11_font(font_size))
            row_h = max(32, int(f.metrics("linespace")) + 6)
        except tk.TclError:
            pass

    return row_h, font_size, icon_px, item_radius, min_width


class _Win11MenuItem(tk.Frame):
    """Win11 原生右键菜单行：圆角悬停高亮 + 左侧线框图标。"""

    def __init__(
        self,
        parent: tk.Misc,
        action: MenuAction,
        *,
        menu: _VectorMenu,
        photos: list[ImageTk.PhotoImage],
        row_h: int,
        icon_size: int,
        label_font: tuple,
        item_radius: int,
    ) -> None:
        from win11_theme import DANGER, FG, MENU_BG, MENU_HOVER

        super().__init__(parent, bg=MENU_BG, cursor="hand2")
        self._menu = menu
        self._action = action
        self._hover = False
        self._row_h = row_h
        self._icon_size = icon_size
        self._item_radius = item_radius
        self._hover_bg = MENU_HOVER
        self._fg = DANGER if action.danger else FG
        self._label = action.label
        self._font = label_font
        self._hover_img: ImageTk.PhotoImage | None = None
        self._hover_key: tuple[int, int, int] | None = None

        icon = _menu_icon(action.icon, danger=action.danger, size=icon_size)
        photo = ImageTk.PhotoImage(icon)
        photos.append(photo)
        self._photo = photo

        self._canvas = tk.Canvas(
            self,
            bg=MENU_BG,
            height=row_h,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(fill=tk.X, expand=True)
        self._canvas.bind("<Configure>", lambda _e: self._paint())
        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<Button-1>", self._on_click)

    def _paint(self) -> None:
        c = self._canvas
        c.delete("all")
        w = max(int(c.winfo_width()), 1)
        h = self._row_h
        if self._hover:
            key = (w, h, self._item_radius)
            if self._hover_key != key or self._hover_img is None:
                hover = _menu_hover_image(w, h, self._item_radius, self._hover_bg)
                self._hover_img = ImageTk.PhotoImage(hover)
                self._hover_key = key
            c.create_image(0, 0, anchor="nw", image=self._hover_img)
        ix = 10
        iy = h // 2
        c.create_image(ix, iy, image=self._photo, anchor="w")
        c.create_text(
            ix + self._icon_size + 12,
            iy,
            text=self._label,
            anchor="w",
            fill=self._fg,
            font=self._font,
        )

    def _on_enter(self, _e=None) -> None:
        self._hover = True
        self._paint()

    def _on_leave(self, _e=None) -> None:
        self._hover = False
        self._paint()

    def _on_click(self, _e=None) -> None:
        self._menu._invoke_action(self._action)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return 61, 61, 61
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _menu_hover_image(w: int, h: int, radius: int, fill_hex: str) -> Image.Image:
    """圆角悬停底 + 圆角柔化阴影（PIL 抗锯齿，避免方角光晕）。"""
    from PIL import ImageDraw, ImageFilter

    w = max(1, w)
    h = max(1, h)
    r = max(1, min(radius, (w - 2) // 2, (h - 2) // 2))
    fill = _hex_to_rgb(fill_hex)

    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((1, 2, w - 2, h), radius=r, fill=(0, 0, 0, 36))
    shadow = shadow.filter(ImageFilter.GaussianBlur(1.8))
    base = Image.alpha_composite(base, shadow)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=fill + (255,))
    return Image.alpha_composite(base, overlay)


class _VectorMenu:
    def __init__(
        self,
        root: tk.Tk,
        actions: list[MenuAction],
        manager: PopupManager | None = None,
        *,
        quit_root_on_close: bool = True,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        import tkinter.font as tkfont

        from win11_style import apply_win11_menu_popup, toplevel_hwnd
        from win11_theme import (
            MENU_BG,
            MENU_CORNER_RADIUS,
            MENU_ITEM_RADIUS,
            MENU_PAD,
            MENU_SEP,
            font as win11_font,
        )

        self.root = root
        self.actions = actions
        self._manager = manager
        self._quit_root_on_close = quit_root_on_close
        self._on_closed = on_closed
        self._photos: list[ImageTk.PhotoImage] = []
        self._closing = False
        # 必须以 PopupManager 的 generation 为准；设置 Toplevel 上没有该标记
        if manager is not None:
            self._gen = manager.generation()
        else:
            self._gen = int(getattr(root, "_tray_popup_gen", 0) or 0)

        win = tk.Toplevel(root)
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=MENU_BG)

        row_h, font_size, icon_size, item_radius, min_width = _menu_layout(root)
        label_font = win11_font(font_size)
        measure = tkfont.Font(root=root, font=label_font)

        shell = tk.Frame(win, bg=MENU_BG)
        shell.pack(fill=tk.BOTH, expand=True, padx=MENU_PAD, pady=MENU_PAD)

        max_label = 0
        for action in actions:
            if action.key == "sep":
                continue
            max_label = max(max_label, measure.measure(action.label))
        inner_w = MENU_PAD * 2 + 10 + icon_size + 12 + max_label + 16
        menu_w = max(min_width, inner_w)

        for action in actions:
            if action.key == "sep":
                sep_wrap = tk.Frame(shell, bg=MENU_BG)
                sep_wrap.pack(fill=tk.X, padx=8, pady=(4, 4))
                tk.Frame(sep_wrap, bg=MENU_SEP, height=1).pack(fill=tk.X)
                continue

            item = _Win11MenuItem(
                shell,
                action,
                menu=self,
                photos=self._photos,
                row_h=row_h,
                icon_size=icon_size,
                label_font=label_font,
                item_radius=item_radius,
            )
            item.pack(fill=tk.X, padx=4, pady=1)

        win.update_idletasks()
        height = win.winfo_reqheight()
        _place_above_taskbar(win, menu_w, height, gap=10)
        win.update()
        try:
            apply_win11_menu_popup(
                toplevel_hwnd(win),
                menu_w,
                height,
                corner_radius=MENU_CORNER_RADIUS,
            )
        except Exception:
            pass
        win.bind("<Escape>", lambda _e: self._close())
        win.after(450, lambda: win.bind("<FocusOut>", self._on_focus_out))
        win.after(80, win.focus_force)
        if self._manager is not None:
            win.after(120, self._watch_gen)

    def _invoke_action(self, action: MenuAction) -> None:
        self._close()
        delay = 0.25 if action.key == "quit" else 0.05

        def _run() -> None:
            time.sleep(delay)
            try:
                action.callback()
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _watch_gen(self) -> None:
        if self._closing:
            return
        try:
            if self._manager is not None and not self._manager.is_current(self._gen):
                self._close()
                return
            self.win.after(120, self._watch_gen)
        except tk.TclError:
            pass

    def _on_focus_out(self, _event=None) -> None:
        # 延迟确认，避免与 focus_force / 设置窗抢焦点时的瞬时 FocusOut
        def _check() -> None:
            if self._closing:
                return
            try:
                if self.win.focus_displayof() is not None:
                    return
            except tk.TclError:
                pass
            self._close()

        try:
            self.win.after(80, _check)
        except tk.TclError:
            self._close()

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._quit_root_on_close:
            try:
                self.root.quit()
            except tk.TclError:
                pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self._manager is not None:
            try:
                self._manager._on_menu_closed(self)
            except Exception:
                pass
        if self._on_closed is not None:
            try:
                self._on_closed()
            except Exception:
                pass


def _menu_icon(kind: str, *, danger: bool = False, size: int = 16) -> Image.Image:
    from win11_theme import DANGER, MENU_BG

    scale = 4
    canvas = size * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if danger:
        color = tuple(int(DANGER[i : i + 2], 16) for i in (1, 3, 5)) + (255,)
    else:
        color = (255, 255, 255, 255)
    hole_rgb = tuple(int(MENU_BG[i : i + 2], 16) for i in (1, 3, 5))
    cx = cy = canvas / 2
    stroke = max(scale, canvas // 12)

    if kind == "refresh":
        r = canvas * 0.30
        bbox = (cx - r, cy - r, cx + r, cy + r)
        draw.arc(bbox, start=50, end=310, fill=color, width=stroke)
        ang = math.radians(50)
        tip = (cx + r * math.cos(ang), cy + r * math.sin(ang))
        left = (tip[0] - stroke * 1.6, tip[1] - stroke * 0.1)
        right = (tip[0] + stroke * 0.2, tip[1] - stroke * 1.6)
        draw.polygon([tip, left, right], fill=color)
    elif kind == "web":
        r = canvas * 0.32
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=stroke)
        draw.ellipse(
            (cx - r * 0.42, cy - r, cx + r * 0.42, cy + r),
            outline=color,
            width=max(1, stroke - 1),
        )
        draw.line((cx - r, cy, cx + r, cy), fill=color, width=max(1, stroke - 1))
        draw.line((cx, cy - r, cx, cy + r), fill=color, width=max(1, stroke - 1))
    elif kind == "settings":
        r = canvas * 0.28
        teeth = 8
        pts: list[tuple[float, float]] = []
        for i in range(teeth * 2):
            ang = math.radians(i * 180 / teeth - 90)
            rr = r * (1.12 if i % 2 == 0 else 0.80)
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        draw.polygon(pts, outline=color, fill=None, width=stroke)
        hole = r * 0.36
        draw.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), outline=color, width=stroke)
        draw.ellipse(
            (cx - hole * 0.55, cy - hole * 0.55, cx + hole * 0.55, cy + hole * 0.55),
            fill=hole_rgb + (255,),
        )
    elif kind == "quit":
        r = canvas * 0.24
        draw.rounded_rectangle(
            (cx - r, cy - r * 1.0, cx + r, cy + r * 1.0),
            radius=r * 0.35,
            outline=color,
            width=stroke,
        )
        draw.line((cx, cy - r * 1.1, cx, cy - r * 0.1), fill=color, width=stroke)
    elif kind == "status":
        r = canvas * 0.28
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=stroke)
        draw.arc(
            (cx - r * 0.55, cy - r * 0.75, cx + r * 0.55, cy + r * 0.35),
            start=200,
            end=340,
            fill=color,
            width=stroke,
        )
    else:
        r = canvas * 0.22
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=stroke)

    return img.resize((size, size), Image.Resampling.LANCZOS)
