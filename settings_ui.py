"""设置窗口：CustomTkinter 内容 + Windows 原生标题栏外壳。

macOS：设置必须在独立进程里跑（`--settings`）。菜单栏进程里的
AppKit + Tk 同线程一旦改 ActivationPolicy / 遍历 NSWindow 就会卡死崩溃。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from app_icon import apply_window_icon
from config import load_config, save_config
from dpi_util import enable_dpi_awareness, physical_window_size, sync_windows_ui_scale
from platform_util import (
    IS_MAC,
    app_log,
    become_foreground_app,
    set_dock_visible,
    show_error_alert,
    window_center_pos,
)
from settings_launch import open_settings_async, settings_flags, settings_process_running
from ui_ctk import (
    ACCENT,
    BG,
    CTkNavItem,
    CTkSettingsRow,
    FG,
    FG_SEC,
    FG_TER,
    LINE,
    SURFACE_ALT,
    apply_native_window_chrome,
    init_ctk,
    make_ghost_button,
    make_switch,
)


def run_settings_main() -> int:
    """`python main.py --settings` / 打包后 `CursorTokenTray --settings` 的入口。"""
    focus_token, start_import = settings_flags()
    app_log(f"settings ui start focus={focus_token} import={start_import}")
    become_foreground_app()
    enable_dpi_awareness()
    try:
        from app_icon import set_app_user_model_id

        set_app_user_model_id()
    except Exception:
        pass
    win = SettingsWindow(on_saved=None, ui=None)
    win._focus_token = focus_token
    win._start_import = start_import
    try:
        win._build_ui(host=None, owns_loop=True)
    except Exception as exc:  # noqa: BLE001
        app_log(f"settings standalone failed: {exc}")
        show_error_alert("设置", f"无法打开设置窗口：{exc}")
        return 1
    return 0


def _present_settings_window(win: tk.Misc, win_w: int = 760, win_h: int = 560) -> None:
    """居中并前置设置窗。不碰托盘进程的 NSWindow 列表。"""
    try:
        win.deiconify()
    except tk.TclError:
        pass
    try:
        win.update_idletasks()
    except tk.TclError:
        pass
    try:
        sw = int(win.winfo_screenwidth() or 1440)
        sh = int(win.winfo_screenheight() or 900)
        # CTk.geometry 会按 window_scaling 放大宽高，定位要用放大后的物理尺寸。
        scale = 1.0
        try:
            getter = getattr(win, "_get_window_scaling", None)
            if callable(getter):
                scale = max(1.0, float(getter()))
        except Exception:
            scale = 1.0
        phys_w, phys_h = physical_window_size(win_w, win_h, scale)
        px, py = window_center_pos(sw, sh, phys_w, phys_h)
        win.geometry(f"{win_w}x{win_h}+{px}+{py}")
    except tk.TclError:
        try:
            win.geometry(f"{win_w}x{win_h}")
        except tk.TclError:
            pass
    try:
        win.minsize(640, 420)
    except tk.TclError:
        pass
    try:
        win.lift()
        win.focus_force()
        win.attributes("-topmost", True)
        win.after(1200, lambda: _relax_topmost(win))
    except tk.TclError:
        pass


def _relax_topmost(win: tk.Misc) -> None:
    try:
        if win.winfo_exists():
            win.attributes("-topmost", False)
            win.lift()
    except tk.TclError:
        pass


_DISPLAY_MODE_LABELS = (
    ("ring", "圆环百分比"),
    ("number", "纯数字"),
    ("dot", "仅色点"),
)

_G_ACCOUNT = "👤" if IS_MAC else "\ue77b"
_G_KEY = "🔑" if IS_MAC else "\ue72e"
_G_GLOBE = "🌐" if IS_MAC else "\ue774"
_G_NOTIFY = "🔔" if IS_MAC else "\uea8f"
_G_CLOCK = "⏱" if IS_MAC else "\ue121"
_G_ALERT = "⚠" if IS_MAC else "\ue7ba"
_G_TRAY = "📊" if IS_MAC else "\ue770"
_G_POWER = "⏻" if IS_MAC else "\ue7e8"
_G_SETTINGS = "⚙" if IS_MAC else "\ue713"


class SettingsWindow:
    def __init__(
        self,
        on_saved: Callable[[dict], None] | None = None,
        *,
        ui: Any | None = None,
    ):
        self.on_saved = on_saved
        self._ui = ui
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._focus_token = False
        self._start_import = False
        self._root: tk.Misc | None = None
        self._owns_loop = False

    @property
    def is_open(self) -> bool:
        if IS_MAC:
            with self._lock:
                waiting = bool(self._thread and self._thread.is_alive())
            return waiting or settings_process_running()
        with self._lock:
            win = self._root
        if win is None:
            return False
        try:
            return bool(win.winfo_exists())
        except tk.TclError:
            return False

    @property
    def root(self) -> tk.Misc | None:
        with self._lock:
            return self._root

    def open(self, *, focus_token: bool = False, start_import: bool = False) -> None:
        self._focus_token = bool(focus_token)
        self._start_import = bool(start_import)
        if IS_MAC:
            self._open_via_subprocess()
            return
        if self._ui is not None:
            self._ui.run_on_ui(self._show_on_ui_thread, wait=False)
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run_standalone, daemon=True, name="settings-ui")
            self._thread.start()

    def _open_via_subprocess(self) -> None:
        open_settings_async(
            on_saved=self.on_saved,
            focus_token=self._focus_token,
            start_import=self._start_import,
        )

    def _show_on_ui_thread(self) -> None:
        try:
            win = self._root
            if win is not None and win.winfo_exists():
                if self._focus_token:
                    self._focus_token_field()
                _present_settings_window(win, 760, 560)
                return
        except tk.TclError:
            with self._lock:
                self._root = None

        host = getattr(self._ui, "tk_root", None) if self._ui is not None else None
        if host is None:
            app_log("settings: no tk host")
            show_error_alert("设置", "界面尚未就绪，请再点一次菜单栏图标后的「设置…」。")
            return
        try:
            self._build_ui(host=host, owns_loop=False)
        except Exception as exc:  # noqa: BLE001
            app_log(f"settings build failed: {exc}")
            try:
                messagebox.showerror("设置", f"无法打开设置窗口：{exc}")
            except Exception:
                show_error_alert("设置", f"无法打开设置窗口：{exc}")

    def _focus_token_field(self) -> None:
        entry = getattr(self, "_token_entry", None)
        win = self._root
        if entry is None or win is None:
            return
        try:
            self._show_page("account")
            entry.focus()
            try:
                entry.select_range(0, "end")
            except Exception:
                pass
            _present_settings_window(win)
        except tk.TclError:
            pass

    def _run_standalone(self) -> None:
        try:
            self._build_ui(host=None, owns_loop=True)
        except Exception as exc:  # noqa: BLE001
            try:
                err_root = tk.Tk()
                err_root.withdraw()
                messagebox.showerror("设置", f"无法打开设置窗口：{exc}", parent=err_root)
                err_root.destroy()
            except Exception:
                pass
        finally:
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None
                self._root = None

    def _build_ui(self, *, host: tk.Misc | None, owns_loop: bool) -> None:
        enable_dpi_awareness()
        init_ctk()
        if not IS_MAC:
            sync_windows_ui_scale()
        cfg = load_config()
        focus_token = self._focus_token
        self._owns_loop = owns_loop

        if host is None:
            root: tk.Misc = ctk.CTk()
        else:
            root = ctk.CTkToplevel(host)
            if not IS_MAC:
                try:
                    root.withdraw()
                except tk.TclError:
                    pass

        with self._lock:
            self._root = root
        root.title("设置")
        root.resizable(True, True)

        nav_w = 188
        page_pad = 18
        win_w, win_h = 760, 560

        _on_close_hooks: list = []

        def _close_window() -> None:
            for hook in _on_close_hooks:
                try:
                    hook()
                except Exception:
                    pass
            with self._lock:
                if self._root is root:
                    self._root = None
            set_dock_visible(False)
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.grid_columnconfigure(2, weight=1)
        root.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(root, fg_color=BG, width=nav_w, corner_radius=0)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sidebar.grid_propagate(False)

        ctk.CTkFrame(root, fg_color=LINE, width=1, corner_radius=0).grid(
            row=0, column=1, rowspan=2, sticky="ns"
        )

        content_col = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
        content_col.grid(row=0, column=2, sticky="nsew")
        content_col.grid_columnconfigure(0, weight=1)
        content_col.grid_rowconfigure(0, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=14, pady=(16, 12))
        ctk.CTkLabel(
            brand,
            text=f"{_G_SETTINGS}  CursorToken",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(brand, text="剩余进度", text_color=FG_TER, font=ctk.CTkFont(size=12), anchor="w").pack(
            fill="x"
        )

        nav_wrap = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 12))

        pages: dict[str, ctk.CTkFrame] = {}
        nav_items: dict[str, CTkNavItem] = {}
        page_meta = {
            "account": {"title": "账户与登录", "desc": "粘贴或导入会话 Token。"},
            "notify": {"title": "刷新与通知", "desc": "刷新频率与额度提醒。"},
            "tray": {
                "title": "菜单栏与启动" if IS_MAC else "托盘与启动",
                "desc": "菜单栏图标与登录自启。" if IS_MAC else "托盘样式与开机自启。",
            },
        }
        self._current_page = "account"

        scroll = ctk.CTkScrollableFrame(content_col, fg_color=BG, corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        scroll.grid_columnconfigure(0, weight=1)

        def _show_page(key: str) -> None:
            for k, frame in pages.items():
                if k == key:
                    frame.grid(row=0, column=0, sticky="nsew")
                else:
                    frame.grid_remove()
            for k, item in nav_items.items():
                item.set_selected(k == key)
            self._current_page = key
            try:
                scroll._parent_canvas.yview_moveto(0)  # type: ignore[attr-defined]
            except Exception:
                pass

        self._show_page = _show_page

        def make_page(key: str) -> ctk.CTkFrame:
            frame = ctk.CTkFrame(scroll, fg_color="transparent")
            frame.grid_columnconfigure(0, weight=1)
            meta = page_meta[key]
            head = ctk.CTkFrame(frame, fg_color="transparent")
            head.grid(row=0, column=0, sticky="ew", padx=page_pad, pady=(10, 0))
            ctk.CTkLabel(
                head, text=meta["title"], font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
            ).pack(fill="x")
            ctk.CTkLabel(
                head,
                text=meta["desc"],
                text_color=FG_TER,
                font=ctk.CTkFont(size=12),
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=(4, 10))
            body = ctk.CTkFrame(frame, fg_color="transparent")
            body.grid(row=1, column=0, sticky="ew", padx=page_pad, pady=(0, 8))
            body.grid_columnconfigure(0, weight=1)
            pages[key] = frame
            return body

        def add_nav(key: str, label: str, glyph: str) -> None:
            item = CTkNavItem(
                nav_wrap,
                label,
                glyph,
                lambda k=key: _show_page(k),
                selected=(key == "account"),
            )
            item.pack(fill="x", pady=3)
            nav_items[key] = item

        add_nav("account", "账户与登录", _G_ACCOUNT)
        add_nav("notify", "刷新与通知", _G_NOTIFY)
        add_nav("tray", "菜单栏与启动" if IS_MAC else "托盘与启动", _G_TRAY)

        # ========== 账户页 ==========
        account_body = make_page("account")
        token_var = tk.StringVar(value=cfg.get("session_token", ""))
        show_var = tk.BooleanVar(value=False)

        token_exp = CTkSettingsRow(account_body, title="会话 Token", description="用于读取用量，请勿分享。", glyph=_G_KEY)
        token_exp.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        show_host = ctk.CTkFrame(token_exp.control_host, fg_color="transparent")
        show_host.pack()
        ctk.CTkLabel(show_host, text="显示", text_color=FG_TER, font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(0, 8)
        )
        make_switch(show_host, show_var).pack(side="left")
        token_exp.show_body()
        token_entry = ctk.CTkEntry(token_exp.body_host, textvariable=token_var, show="*", height=36)
        token_entry.pack(fill="x")
        self._token_entry = token_entry

        def toggle_show(*_args: object) -> None:
            try:
                token_entry.configure(show="" if show_var.get() else "*")
            except tk.TclError:
                pass

        show_var.trace_add("write", toggle_show)

        ctk.CTkLabel(account_body, text="浏览器导入", text_color=FG_TER, font=ctk.CTkFont(size=12), anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(10, 6)
        )

        import_exp = CTkSettingsRow(
            account_body,
            title="从浏览器导入",
            description=(
                "优先 Safari / Firefox（Chrome 常因 Cookie 加密读不到）。"
                if IS_MAC
                else "优先 Firefox；部分新版 Chrome 因 App-Bound 加密无法读取。"
            ),
            glyph=_G_GLOBE,
        )
        import_exp.grid(row=2, column=0, sticky="ew")
        import_exp.show_body()

        auth_status = tk.StringVar(value="")
        cancel_flag = {"value": False}
        importing = {"value": False}
        import_events: queue.Queue[tuple[str, Any]] = queue.Queue()

        status_lbl = ctk.CTkLabel(
            import_exp.body_host,
            textvariable=auth_status,
            text_color="#60CDFF",
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=520,
        )

        def set_auth_status_ui(text: str) -> None:
            try:
                auth_status.set(text)
                if text.strip():
                    status_lbl.pack(fill="x", pady=(0, 8))
                else:
                    status_lbl.pack_forget()
            except tk.TclError:
                pass

        def apply_imported_token(token: str, msg: str) -> None:
            token_var.set(token)
            show_var.set(False)
            set_auth_status_ui(msg)
            new_cfg = load_config()
            new_cfg["session_token"] = token
            new_cfg["auth_error_notified"] = False
            save_config(new_cfg)

            def notify_saved() -> None:
                if self.on_saved:
                    try:
                        self.on_saved(new_cfg)
                    except Exception:
                        pass

            try:
                root.after(1, notify_saved)
            except tk.TclError:
                notify_saved()

        def _drain_import_events() -> None:
            try:
                while True:
                    kind, payload = import_events.get_nowait()
                    if kind == "progress":
                        set_auth_status_ui(str(payload))
                    elif kind == "done":
                        _finish_import(payload)
            except queue.Empty:
                pass
            try:
                if importing["value"] or not import_events.empty():
                    root.after(100, _drain_import_events)
            except tk.TclError:
                pass

        def _set_import_btns(*, idle: bool) -> None:
            st_on = "normal" if idle else "disabled"
            st_off = "disabled" if idle else "normal"
            try:
                btn_login.configure(state=st_on)
                btn_firefox.configure(state=st_on)
                btn_import.configure(state=st_on)
                btn_cancel_import.configure(state=st_off)
            except tk.TclError:
                pass

        def _finish_import(payload: dict[str, Any]) -> None:
            importing["value"] = False
            _set_import_btns(idle=True)
            error = payload.get("error")
            result = payload.get("result")
            if error is not None:
                set_auth_status_ui(f"导入异常：{error}")
                messagebox.showerror("导入异常", str(error), parent=root)
                return
            if result is None:
                set_auth_status_ui("导入已结束")
                return
            if result.ok:
                apply_imported_token(result.token, result.message)

                def _ok_dialog() -> None:
                    try:
                        messagebox.showinfo("导入成功", result.message, parent=root)
                    except tk.TclError:
                        pass

                root.after(10, _ok_dialog)
                return
            short = result.message.split("\n")[0]
            set_auth_status_ui(short)
            if short == "已取消":
                return
            messagebox.showwarning("导入失败", result.message, parent=root)

        btn_block = ctk.CTkFrame(import_exp.body_host, fg_color="transparent")
        btn_block.pack(fill="x", pady=(0, 4))

        def run_import(*, open_browser: bool, prefer: str | None = None) -> None:
            if importing["value"]:
                return
            importing["value"] = True
            cancel_flag["value"] = False
            _set_import_btns(idle=False)
            if open_browser and prefer == "firefox":
                set_auth_status_ui("正在打开 Firefox…")
            else:
                set_auth_status_ui("正在打开浏览器…" if open_browser else "正在读取 Cookie…")
            root.after(50, _drain_import_events)

            def worker() -> None:
                result = None
                error: Exception | None = None
                try:
                    from browser_auth import import_and_validate, start_browser_login_and_import

                    def on_progress(text: str) -> None:
                        import_events.put(("progress", text))

                    cancel_cb = lambda: cancel_flag["value"]
                    if open_browser:
                        result = start_browser_login_and_import(
                            timeout_sec=180.0,
                            prefer=prefer,
                            should_cancel=cancel_cb,
                            on_progress=on_progress,
                        )
                    else:
                        result = import_and_validate(
                            should_cancel=cancel_cb,
                            on_progress=on_progress,
                        )
                except Exception as exc:  # noqa: BLE001
                    error = exc
                import_events.put(("done", {"result": result, "error": error}))

            root.after(
                1,
                lambda: threading.Thread(target=worker, daemon=True, name="cookie-import").start(),
            )

        def on_cancel_import() -> None:
            if not importing["value"]:
                return
            cancel_flag["value"] = True
            set_auth_status_ui("正在取消…")

        btn_login = ctk.CTkButton(
            btn_block,
            text="Safari 登录导入" if IS_MAC else "浏览器登录并导入",
            command=lambda: run_import(open_browser=True, prefer="safari" if IS_MAC else None),
            height=32,
        )
        btn_login.pack(side="left", padx=(0, 8))
        btn_firefox = make_ghost_button(
            btn_block, "Firefox 登录导入", lambda: run_import(open_browser=True, prefer="firefox")
        )
        btn_firefox.pack(side="left", padx=(0, 8))
        btn_import = make_ghost_button(btn_block, "仅导入 Cookie", lambda: run_import(open_browser=False))
        btn_import.pack(side="left", padx=(0, 8))
        btn_cancel_import = ctk.CTkButton(
            btn_block,
            text="取消等待",
            command=on_cancel_import,
            fg_color="transparent",
            hover_color=SURFACE_ALT,
            text_color=FG_SEC,
            height=32,
            state="disabled",
        )
        btn_cancel_import.pack(side="left")

        # ========== 通知页 ==========
        notify_body = make_page("notify")
        interval_var = tk.IntVar(value=int(cfg.get("refresh_interval_minutes", 10)))
        interval_exp = CTkSettingsRow(notify_body, title="刷新间隔", description="最小 1 分钟。", glyph=_G_CLOCK)
        interval_exp.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        interval_host = ctk.CTkFrame(interval_exp.control_host, fg_color="transparent")
        interval_host.pack()
        ctk.CTkEntry(interval_host, textvariable=interval_var, width=64, height=32, justify="center").pack(
            side="left"
        )
        ctk.CTkLabel(interval_host, text="分钟", text_color=FG_SEC, font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(8, 0)
        )

        thresholds = cfg.get("alert_thresholds") or [50, 20, 5]
        threshold_var = tk.StringVar(value=",".join(str(int(x)) for x in thresholds))
        thr_exp = CTkSettingsRow(notify_body, title="告警阈值", description="例如 50,20,5。", glyph=_G_ALERT)
        thr_exp.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkEntry(thr_exp.control_host, textvariable=threshold_var, width=110, height=32, justify="center").pack()

        ctk.CTkLabel(notify_body, text="通知选项", text_color=FG_TER, font=ctk.CTkFont(size=12), anchor="w").grid(
            row=2, column=0, sticky="ew", pady=(10, 6)
        )

        notify_var = tk.BooleanVar(value=bool(cfg.get("notify_enabled", True)))
        notify_exp = CTkSettingsRow(
            notify_body,
            title="启用用量通知",
            description="跌破阈值时系统通知。",
            glyph=_G_NOTIFY,
            on_click=lambda: notify_var.set(not notify_var.get()),
        )
        notify_exp.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        make_switch(notify_exp.control_host, notify_var).pack()

        exhaust_var = tk.BooleanVar(value=bool(cfg.get("notify_exhaustion_risk", True)))
        exhaust_exp = CTkSettingsRow(
            notify_body,
            title="启用耗尽风险通知",
            description="可能提前耗尽时提醒。",
            glyph=_G_ALERT,
            on_click=lambda: exhaust_var.set(not exhaust_var.get()),
        )
        exhaust_exp.grid(row=4, column=0, sticky="ew")
        make_switch(exhaust_exp.control_host, exhaust_var).pack()

        # ========== 托盘页 ==========
        tray_body = make_page("tray")
        mode_map = dict(_DISPLAY_MODE_LABELS)
        rev_map = {v: k for k, v in _DISPLAY_MODE_LABELS}
        cur_mode = str(cfg.get("tray_display_mode") or "ring")
        mode_var = tk.StringVar(value=mode_map.get(cur_mode, "圆环百分比"))
        mode_exp = CTkSettingsRow(
            tray_body,
            title="菜单栏图标" if IS_MAC else "托盘显示",
            description="圆环 / 数字 / 色点。",
            glyph=_G_TRAY,
        )
        mode_exp.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkComboBox(
            mode_exp.control_host,
            variable=mode_var,
            values=[label for _, label in _DISPLAY_MODE_LABELS],
            width=130,
            height=32,
            state="readonly",
        ).pack()

        ctk.CTkLabel(tray_body, text="相关设置", text_color=FG_TER, font=ctk.CTkFont(size=12), anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(10, 6)
        )

        autostart_var = tk.BooleanVar(value=bool(cfg.get("autostart_enabled", True)))
        auto_exp = CTkSettingsRow(
            tray_body,
            title="开机自启",
            description="登录后自动运行。",
            glyph=_G_POWER,
            on_click=lambda: autostart_var.set(not autostart_var.get()),
        )
        auto_exp.grid(row=2, column=0, sticky="ew")
        make_switch(auto_exp.control_host, autostart_var).pack()

        footer = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
        footer.grid(row=1, column=2, sticky="ew", padx=page_pad, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(footer, fg_color=LINE, height=1, corner_radius=0).grid(row=0, column=0, sticky="ew")
        footer_bar = ctk.CTkFrame(footer, fg_color="transparent")
        footer_bar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        footer_bar.grid_columnconfigure(0, weight=1)
        footer_hint = tk.StringVar(value="")
        ctk.CTkLabel(footer_bar, textvariable=footer_hint, text_color=FG_TER, font=ctk.CTkFont(size=12), anchor="w").grid(
            row=0, column=0, sticky="w"
        )

        def persist_settings(*, close: bool) -> bool:
            from cursor_api import normalize_workos_token

            token = normalize_workos_token(token_var.get().strip())
            token_var.set(token)
            try:
                interval = int(interval_var.get())
            except (tk.TclError, ValueError):
                messagebox.showerror("错误", "刷新间隔必须是数字", parent=root)
                return False
            if interval < 1:
                messagebox.showerror("错误", "刷新间隔至少为 1 分钟", parent=root)
                return False

            raw_thr = threshold_var.get().strip().replace("，", ",")
            parts = [p.strip() for p in raw_thr.split(",") if p.strip()]
            try:
                parsed = sorted(
                    {int(float(p)) for p in parts if 1 <= int(float(p)) <= 100},
                    reverse=True,
                )
            except ValueError:
                messagebox.showerror("错误", "告警阈值格式无效，请使用如 50,20,5", parent=root)
                return False
            if not parsed:
                messagebox.showerror("错误", "请至少填写一个 1–100 的告警阈值", parent=root)
                return False

            display_mode = rev_map.get(mode_var.get(), "ring")
            new_cfg = load_config()
            old_token = str(new_cfg.get("session_token") or "").strip()
            old_thr = list(new_cfg.get("alert_thresholds") or [])
            if parsed != old_thr:
                new_cfg["alert_notified_levels"] = []
                new_cfg["low_quota_notified"] = False
            new_cfg["session_token"] = token
            new_cfg["refresh_interval_minutes"] = interval
            new_cfg["alert_thresholds"] = parsed
            new_cfg["low_quota_threshold"] = min(parsed) if parsed else 20
            new_cfg["notify_enabled"] = bool(notify_var.get())
            new_cfg["notify_exhaustion_risk"] = bool(exhaust_var.get())
            new_cfg["tray_display_mode"] = display_mode
            new_cfg["autostart_enabled"] = bool(autostart_var.get())
            if token != old_token:
                new_cfg["auth_error_notified"] = False
            save_config(new_cfg)

            def notify() -> None:
                if self.on_saved:
                    try:
                        self.on_saved(new_cfg)
                    except Exception:
                        pass

            try:
                root.after(1, notify)
            except tk.TclError:
                notify()

            if close:
                _close_window()
            else:
                footer_hint.set("已应用")
                try:
                    root.after(2500, lambda: footer_hint.set(""))
                except tk.TclError:
                    pass
            return True

        def on_cancel() -> None:
            cancel_flag["value"] = True
            _close_window()

        actions = ctk.CTkFrame(footer_bar, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            actions,
            text="取消",
            command=on_cancel,
            fg_color="transparent",
            hover_color=SURFACE_ALT,
            text_color=FG_SEC,
            width=72,
            height=32,
        ).pack(side="right", padx=(8, 0))
        make_ghost_button(actions, "应用", lambda: persist_settings(close=False), width=72).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(
            actions, text="保存", command=lambda: persist_settings(close=True), fg_color=ACCENT, width=72, height=32
        ).pack(side="right")

        _show_page("account")

        try:
            root.bind("<Escape>", lambda _e: _close_window())
        except tk.TclError:
            pass
        _present_settings_window(root, win_w, win_h)

        apply_window_icon(root)
        apply_native_window_chrome(root)

        if focus_token:
            self._focus_token_field()
        if getattr(self, "_start_import", False):
            try:
                root.after(400, lambda: run_import(open_browser=True))
            except tk.TclError:
                run_import(open_browser=True)

        if owns_loop:
            try:
                root.mainloop()
            finally:
                with self._lock:
                    if self._root is root:
                        self._root = None
