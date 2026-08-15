"""系统托盘主逻辑。"""

from __future__ import annotations

import os
import threading
import time
import webbrowser
from datetime import datetime
from typing import Any

import pystray

from config import APP_NAME, load_config, save_config
from cursor_api import (
    BILLING_URL,
    CursorApiError,
    UsageSnapshot,
    fetch_usage_summary,
    is_auth_error_message,
)
from icon_renderer import create_idle_icon, create_progress_icon
from popup_ui import MenuAction, PopupManager, StatusActions, format_summary_text
from platform_util import IS_MAC
from settings_ui import SettingsWindow
import usage_history


class TrayApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.usage: UsageSnapshot | None = None
        self.error_message: str | None = None
        self.updated_at: str | None = None
        self._stop = threading.Event()
        self._refresh_event = threading.Event()
        self._lock = threading.Lock()
        self.popups = PopupManager()
        # 设置窗挂到唯一 popup-ui Tk 线程，禁止再开第二个 Tk（Windows 上极易未响应）
        self.settings = SettingsWindow(on_saved=self._on_config_saved, ui=self.popups)
        self._worker: threading.Thread | None = None
        self._suppress_status_closed_resume = False
        self._status_opening = False

        # Windows：隐藏 default 供左键，右键走自定义矢量菜单。
        # macOS：原生菜单栏菜单；左键 default 打开状态飞出层。
        if IS_MAC:
            menu = pystray.Menu(
                pystray.MenuItem("显示状态", self._action_open_status, default=True),
                pystray.MenuItem("立即刷新", self._action_refresh),
                pystray.MenuItem("打开用量账单", self._action_open_spending),
                pystray.MenuItem("导入 Token…", self._action_open_settings_focus),
                pystray.MenuItem("设置…", self._action_open_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._action_quit),
            )
        else:
            menu = pystray.Menu(
                pystray.MenuItem(
                    "显示状态",
                    self._action_open_status,
                    default=True,
                    visible=False,
                )
            )
        self.icon = pystray.Icon(
            APP_NAME,
            create_idle_icon(mode=self._display_mode()),
            "",
            menu=menu,
        )
        self.popups.bind_tray_icon(self.icon)

    def run(self) -> None:
        if not self.config.get("session_token"):
            threading.Timer(0.8, lambda: self.settings.open(focus_token=True)).start()

        try:
            from autostart import set_autostart

            set_autostart(bool(self.config.get("autostart_enabled", True)))
        except Exception:
            pass

        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()
        self.icon.run(setup=self._on_icon_ready)

    def _on_icon_ready(self, icon: pystray.Icon) -> None:
        if IS_MAC:
            icon.visible = True
            try:
                from AppKit import NSApp, NSApplicationActivationPolicyAccessory

                NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            except Exception:
                pass
            # 先让 NSStatusItem 出现，再创建 Tk，避免抢 NSApplication 导致图标不显示
            def _attach_tk() -> None:
                try:
                    self.popups.attach_main_thread()
                except Exception:
                    pass

            try:
                from PyObjCTools import AppHelper

                AppHelper.callLater(0.4, _attach_tk)
            except Exception:
                _attach_tk()
            return

        from tray_hover import enable_hover_flyout, patch_pystray_uid

        patch_pystray_uid(icon)
        icon.visible = True
        try:
            icon.title = ""
        except Exception:
            pass
        time.sleep(0.2)
        try:
            enable_hover_flyout(
                icon,
                on_left_click=self._open_status_bg,
                on_right_click=self._on_tray_right_click,
            )
        except Exception:
            pass

    def _status_actions(self) -> StatusActions:
        return StatusActions(
            on_open_settings=self._action_open_settings_focus,
            on_refresh=self._action_refresh,
            on_open_spending=self._action_open_spending,
            on_copy_summary=self._copy_summary,
        )

    def _history_payload(self) -> tuple[list[float], float | None]:
        points = usage_history.load_recent(7)
        values = [p.remaining for p in points]
        burn = usage_history.daily_avg_burn(7)
        return values, burn

    def _on_tray_right_click(self) -> None:
        if self.popups.menu_visible or getattr(self, "_menu_opening", False):
            return
        self._menu_opening = True
        watcher = getattr(self.icon, "_hover_watcher", None)
        if watcher is not None:
            watcher.pause()
        self._suppress_status_closed_resume = True

        def _after_menu_closed() -> None:
            self._menu_opening = False
            self._suppress_status_closed_resume = False
            if watcher is not None:
                watcher.notify_closed()
                watcher.resume()

        def open_menu() -> None:
            try:
                self.popups.cancel_hover_close()
                if not self.popups.close_and_wait(2.5):
                    return
                actions = self._vector_menu_actions()
                # 设置窗已挂到同一 Tk 线程，勿再 show_menu_on_host：
                # 宿主 Toplevel 没有 _tray_popup_gen，菜单会被 _watch_gen 立刻关掉
                self.popups.show_menu(actions)
            except Exception:
                pass
            finally:
                _after_menu_closed()

        threading.Thread(target=open_menu, daemon=True, name="tray-menu").start()

    def _vector_menu_actions(self) -> list[MenuAction]:
        return [
            MenuAction("status", "显示状态", "status", self._action_open_status),
            MenuAction("refresh", "立即刷新", "refresh", self._action_refresh),
            MenuAction("web", "打开用量账单", "web", self._action_open_spending),
            MenuAction("import", "导入 Token…", "settings", self._action_open_settings_focus),
            MenuAction("settings", "设置…", "settings", self._action_open_settings),
            MenuAction("sep", "", "", lambda: None),
            MenuAction("quit", "退出", "quit", self._action_quit, danger=True),
        ]

    def _on_status_closed(self) -> None:
        self._status_opening = False
        if self._suppress_status_closed_resume:
            return
        watcher = getattr(self.icon, "_hover_watcher", None)
        if watcher is not None:
            watcher.notify_closed()
            watcher.resume()

    def _open_status_bg(self) -> None:
        self.popups.cancel_hover_close()
        if self._status_opening or self.popups.status_visible or self.popups.busy:
            return
        if self.popups.menu_visible:
            return
        self._status_opening = True
        watcher = getattr(self.icon, "_hover_watcher", None)
        if watcher is not None:
            watcher.pause()
            watcher.notify_opened()
        try:
            hist, burn = self._history_payload()
            usage, err, updated = self._ui_snapshot()
            self.popups.show_status(
                usage=usage,
                error_message=err,
                updated_at=updated,
                from_hover=False,
                on_closed=self._on_status_closed,
                actions=self._status_actions(),
                history_values=hist,
                daily_burn=burn,
            )
        except Exception:
            self._status_opening = False
            if watcher is not None:
                watcher.notify_closed()
                watcher.resume()
            raise

    def stop(self) -> None:
        """可靠退出：先停刷新/悬停/弹窗，再停托盘；兜底强制结束进程。"""
        if getattr(self, "_stopping", False):
            return
        self._stopping = True
        self._stop.set()
        self._refresh_event.set()

        watcher = getattr(self.icon, "_hover_watcher", None)
        if watcher is not None:
            try:
                watcher.stop()
            except Exception:
                pass

        try:
            self.popups.close_and_wait(1.5)
        except Exception:
            try:
                self.popups.close()
            except Exception:
                pass
        if IS_MAC:
            try:
                self.popups.stop_macos_pump()
            except Exception:
                pass

        def _stop_icon() -> None:
            try:
                self.icon.visible = False
            except Exception:
                pass
            try:
                self.icon.stop()
            except Exception:
                pass

        # pystray 在部分环境下从非消息线程 stop 会挂起，超时则强杀本进程
        t = threading.Thread(target=_stop_icon, daemon=True)
        t.start()
        t.join(timeout=2.0)
        try:
            from instance_lock import release

            release()
        except Exception:
            pass
        # 托盘 icon.stop 后消息循环常不退出，必须强退，否则单实例锁占住无法再启动
        os._exit(0)

    def _action_open_status(self, _icon=None, _item=None) -> None:
        threading.Thread(target=self._open_status_bg, daemon=True).start()

    def _action_refresh(self, _icon=None, _item=None) -> None:
        self._refresh_event.set()

    def _action_open_spending(self, _icon=None, _item=None) -> None:
        webbrowser.open(BILLING_URL)

    def _action_open_settings(self, _icon=None, _item=None) -> None:
        self._open_settings_bg(focus_token=False)

    def _action_open_settings_focus(self, _icon=None, _item=None) -> None:
        self._open_settings_bg(focus_token=True)

    def _open_settings_bg(self, *, focus_token: bool = False) -> None:
        """先收起飞出层/菜单，再在同一 Tk 线程打开设置（避免闪一下的空窗）。"""

        def worker() -> None:
            watcher = getattr(self.icon, "_hover_watcher", None)
            if watcher is not None:
                watcher.pause()
            try:
                # 设置已挂到同一 UI 线程，只需关掉飞出层；不必长时间等待
                self.popups.close()
            except Exception:
                pass
            if watcher is not None:
                watcher.notify_closed()
            self.settings.open(focus_token=focus_token)

        threading.Thread(target=worker, daemon=True).start()

    def _action_quit(self, _icon=None, _item=None) -> None:
        # 稍延后，让矢量菜单 Tk 先收尾，避免与 icon.stop 打架
        def _later() -> None:
            time.sleep(0.2)
            self.stop()

        threading.Thread(target=_later, daemon=True).start()

    def _copy_summary(self) -> None:
        usage, err, updated = self._ui_snapshot()
        text = format_summary_text(usage, err, updated)

        def _clip() -> None:
            root = self.popups.tk_root
            if root is None:
                return
            try:
                root.clipboard_clear()
                root.clipboard_append(text)
                root.update_idletasks()
            except Exception:
                pass

        try:
            self.popups.run_on_ui(_clip, wait=False)
        except Exception:
            pass

    def _on_config_saved(self, cfg: dict[str, Any]) -> None:
        """设置已写入磁盘后回调：立刻换托盘图标；Token 变更才触发联网刷新。

        开机自启（PowerShell 写快捷方式）放到后台，避免卡死设置窗口。
        """
        with self._lock:
            prev = dict(self.config)
            self.config = cfg

        prev_token = (prev.get("session_token") or "").strip()
        new_token = (cfg.get("session_token") or "").strip()
        need_api = prev_token != new_token
        interval_changed = int(prev.get("refresh_interval_minutes", 10)) != int(
            cfg.get("refresh_interval_minutes", 10)
        )
        prev_auto = bool(prev.get("autostart_enabled", True))
        new_auto = bool(cfg.get("autostart_enabled", True))

        def bg() -> None:
            if prev_auto != new_auto:
                try:
                    from autostart import is_autostart_enabled, set_autostart

                    if is_autostart_enabled() != new_auto:
                        set_autostart(new_auto)
                except Exception:
                    pass
            try:
                self._apply_ui()
            except Exception:
                pass
            if need_api or interval_changed:
                self._refresh_event.set()

        threading.Thread(target=bg, daemon=True, name="config-apply").start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            # 先 clear 再刷新：刷新期间触发的 set 会保留到 wait
            self._refresh_event.clear()
            self._do_refresh()
            with self._lock:
                minutes = int(self.config.get("refresh_interval_minutes", 10))
            interval_sec = max(60, minutes * 60)
            self._refresh_event.wait(timeout=interval_sec)

    def _ui_snapshot(self) -> tuple[UsageSnapshot | None, str | None, str | None]:
        with self._lock:
            return self.usage, self.error_message, self.updated_at

    def _do_refresh(self) -> None:
        with self._lock:
            cfg = dict(self.config)

        token = (cfg.get("session_token") or "").strip()
        if not token:
            with self._lock:
                self.usage = None
                self.error_message = "未配置 Token，请打开设置粘贴"
                self.updated_at = None
            # 空 Token 不弹系统通知，避免首次启动打扰
            self._apply_ui()
            return

        try:
            snapshot = fetch_usage_summary(token)
            with self._lock:
                self.usage = snapshot
                self.error_message = None
                self.updated_at = datetime.now().strftime("%H:%M:%S")
            self._clear_auth_error_flag(cfg)
            try:
                usage_history.append(
                    remaining=snapshot.remaining_percent,
                    auto=snapshot.auto_percent_used,
                    api=snapshot.api_percent_used,
                )
            except Exception:
                pass
            self._maybe_notify_alerts(cfg, snapshot)
        except CursorApiError as err:
            with self._lock:
                self.usage = None
                self.error_message = str(err)
                self.updated_at = datetime.now().strftime("%H:%M:%S")
            if err.is_auth_error or is_auth_error_message(str(err)):
                self._maybe_notify_auth_error(cfg, str(err))
        except Exception as err:  # noqa: BLE001
            with self._lock:
                self.usage = None
                self.error_message = f"刷新失败: {err}"
                self.updated_at = datetime.now().strftime("%H:%M:%S")

        self._apply_ui()

    def _clear_auth_error_flag(self, cfg: dict[str, Any]) -> None:
        if cfg.get("auth_error_notified"):
            cfg["auth_error_notified"] = False
            save_config(cfg)
            with self._lock:
                self.config = cfg

    def _maybe_notify_auth_error(self, cfg: dict[str, Any], message: str) -> None:
        if not cfg.get("notify_enabled", True):
            return
        if cfg.get("auth_error_notified"):
            return
        self._notify("Token 需要更新", message)
        cfg["auth_error_notified"] = True
        save_config(cfg)
        with self._lock:
            self.config = cfg

    def _maybe_notify_alerts(self, cfg: dict[str, Any], snapshot: UsageSnapshot) -> None:
        if not cfg.get("notify_enabled", True):
            return

        remaining = snapshot.remaining_percent
        thresholds = sorted(
            {int(x) for x in (cfg.get("alert_thresholds") or [50, 20, 5]) if 1 <= int(x) <= 100},
            reverse=True,
        )
        notified = {int(x) for x in (cfg.get("alert_notified_levels") or [])}
        changed = False

        # 剩余回升超过某档 → 清除该档去重，允许再次通知
        still = {lvl for lvl in notified if remaining < lvl}
        if still != notified:
            notified = still
            changed = True

        # 新跌破的档位：只通知「刚跌破」的最高那一档（避免一次刷多条）
        newly = [lvl for lvl in thresholds if remaining < lvl and lvl not in notified]
        if newly:
            hit = max(newly)
            self._notify(
                "额度告警",
                f"套餐剩余 {remaining:.1f}%，已低于 {hit}% 档。",
            )
            notified.add(hit)
            changed = True

        # 耗尽风险
        if cfg.get("notify_exhaustion_risk", True):
            at_risk = self._is_exhaustion_risk(snapshot)
            was = bool(cfg.get("exhaustion_notified", False))
            if at_risk and not was:
                self._notify(
                    "耗尽风险",
                    f"按当前速度可能提前耗尽（剩余 {remaining:.1f}%）。",
                )
                cfg["exhaustion_notified"] = True
                changed = True
            elif not at_risk and was:
                cfg["exhaustion_notified"] = False
                changed = True

        if changed:
            cfg["alert_notified_levels"] = sorted(notified)
            # 兼容旧字段
            min_thr = min(thresholds) if thresholds else 20
            cfg["low_quota_notified"] = remaining < min_thr
            save_config(cfg)
            with self._lock:
                self.config = cfg

    @staticmethod
    def _is_exhaustion_risk(snapshot: UsageSnapshot) -> bool:
        est = snapshot.estimated_usable_days
        reset_left = snapshot.days_remaining
        if est is None or reset_left is None:
            return False
        if est <= 0:
            return True
        return est < reset_left

    def _notify(self, title: str, message: str) -> None:
        try:
            self.icon.notify(message, title)
            return
        except Exception:
            pass
        if IS_MAC:
            try:
                import subprocess

                def _as_quote(text: str) -> str:
                    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f"display notification {_as_quote(message)} with title {_as_quote(title)}",
                    ],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

    def _display_mode(self) -> str:
        with self._lock:
            mode = str(self.config.get("tray_display_mode") or "ring")
        return mode if mode in ("ring", "number", "dot") else "ring"

    def _apply_ui(self) -> None:
        mode = self._display_mode()
        usage, err, updated = self._ui_snapshot()
        if err and str(err).startswith("未配置"):
            image = create_idle_icon(mode=mode)
        elif err:
            image = create_progress_icon(None, error=True, mode=mode)
        elif usage:
            image = create_progress_icon(usage.remaining_percent, mode=mode)
        else:
            image = create_idle_icon(mode=mode)

        self.icon.icon = image
        if IS_MAC:
            if usage is not None:
                self.icon.title = f"{usage.remaining_percent:.0f}%"
            elif err and str(err).startswith("未配置"):
                self.icon.title = "Token"
            else:
                self.icon.title = "Token"
        else:
            self.icon.title = ""

        hist, burn = self._history_payload()
        self.popups.update_status(
            usage=usage,
            error_message=err,
            updated_at=updated,
            history_values=hist,
            daily_burn=burn,
        )
