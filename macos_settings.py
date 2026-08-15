"""macOS 设置窗：只用 AppKit，禁止导入 Tk / CustomTkinter。

打包进 .app 的 Tk 8.6 在 macOS 26 上初始化就会
`-[NSApplication %s]: unrecognized selector` 然后 SIGABRT。
"""

from __future__ import annotations

import threading
from typing import Any

from platform_util import app_log, show_error_alert
from settings_launch import settings_flags

_CONTROLLER = None


def run_macos_settings() -> int:
    focus_token, start_import = settings_flags()
    app_log(f"native settings start focus={focus_token} import={start_import}")
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular
        from PyObjCTools import AppHelper
    except ImportError as exc:
        app_log(f"native settings AppKit missing: {exc}")
        show_error_alert("设置", "缺少 AppKit / PyObjC，无法打开设置。")
        return 1

    controller_cls = _make_controller_class()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    global _CONTROLLER
    _CONTROLLER = controller_cls.alloc().init()
    _CONTROLLER.buildWindow_startImport_(bool(start_import))
    if focus_token:
        _CONTROLLER.focusTokenField()
    app.activateIgnoringOtherApps_(True)
    AppHelper.runEventLoop()
    app_log("native settings exit")
    return 0


def _make_controller_class() -> type:
    from AppKit import (
        NSBackingStoreBuffered,
        NSButton,
        NSButtonTypeSwitch,
        NSFont,
        NSObject,
        NSPopUpButton,
        NSTextField,
        NSWindow,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskMiniaturizable,
        NSWindowStyleMaskTitled,
    )
    from Foundation import NSMakeRect
    from PyObjCTools import AppHelper

    from config import load_config, save_config

    def label(parent, text: str, x: float, y: float, w: float, h: float = 18, size: float = 13):
        lab = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        lab.setStringValue_(text)
        lab.setBezeled_(False)
        lab.setDrawsBackground_(False)
        lab.setEditable_(False)
        lab.setSelectable_(False)
        lab.setFont_(NSFont.systemFontOfSize_(size))
        parent.addSubview_(lab)
        return lab

    def field(parent, value: str, x: float, y: float, w: float, h: float = 24):
        box = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        box.setStringValue_(value)
        parent.addSubview_(box)
        return box

    def button(parent, title: str, action, target, x: float, y: float, w: float, h: float = 28):
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        btn.setTitle_(title)
        btn.setBezelStyle_(1)
        btn.setTarget_(target)
        btn.setAction_(action)
        parent.addSubview_(btn)
        return btn

    def checkbox(parent, title: str, checked: bool, x: float, y: float, w: float):
        box = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 22))
        box.setButtonType_(NSButtonTypeSwitch)
        box.setTitle_(title)
        box.setState_(1 if checked else 0)
        parent.addSubview_(box)
        return box

    class SettingsController(NSObject):
        def buildWindow_startImport_(self, start_import) -> None:
            cfg = load_config()
            self._cancel_import = False
            self._importing = False
            width, height = 640.0, 540.0
            style = (
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskMiniaturizable
            )
            self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, width, height),
                style,
                NSBackingStoreBuffered,
                False,
            )
            self.window.setTitle_("Cursor Token 设置")
            self.window.center()
            self.window.setReleasedWhenClosed_(False)
            self.window.setDelegate_(self)
            view = self.window.contentView()

            label(view, "账户与登录", 24, 500, 400, 22, 16)
            label(view, "会话 Token（请勿分享）", 24, 472, 300, 16, 12)
            self.tokenField = field(view, str(cfg.get("session_token") or ""), 24, 442, 592, 26)

            self.btnLogin = button(view, "浏览器登录并导入", b"loginImport:", self, 24, 376, 160)
            self.btnCookie = button(view, "仅导入 Cookie", b"cookieImport:", self, 192, 376, 130)
            self.btnCancelImp = button(view, "取消等待", b"cancelImport:", self, 330, 376, 100)
            self.btnCancelImp.setEnabled_(False)

            self.status = label(view, "", 24, 348, 592, 22, 12)

            label(view, "刷新与通知", 24, 312, 400, 22, 16)
            label(view, "刷新间隔（分钟）", 24, 286, 160, 16, 12)
            self.intervalField = field(view, str(int(cfg.get("refresh_interval_minutes", 10))), 190, 282, 64, 24)
            label(view, "告警阈值，例如 50,20,5", 24, 254, 220, 16, 12)
            thresholds = cfg.get("alert_thresholds") or [50, 20, 5]
            self.thresholdField = field(
                view, ",".join(str(int(x)) for x in thresholds), 250, 250, 140, 24
            )
            self.notifyBox = checkbox(view, "启用用量通知", bool(cfg.get("notify_enabled", True)), 24, 218, 220)
            self.exhaustBox = checkbox(
                view, "启用耗尽风险通知", bool(cfg.get("notify_exhaustion_risk", True)), 250, 218, 220
            )

            label(view, "菜单栏与启动", 24, 180, 400, 22, 16)
            label(view, "菜单栏图标", 24, 154, 120, 16, 12)
            self.modePopup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                NSMakeRect(150, 148, 160, 26), False
            )
            self._modes = [("ring", "圆环百分比"), ("number", "纯数字"), ("dot", "仅色点")]
            for _key, title in self._modes:
                self.modePopup.addItemWithTitle_(title)
            cur = str(cfg.get("tray_display_mode") or "ring")
            idx = next((i for i, (k, _) in enumerate(self._modes) if k == cur), 0)
            self.modePopup.selectItemAtIndex_(idx)
            view.addSubview_(self.modePopup)
            self.autostartBox = checkbox(
                view, "开机自启（下次登录生效）", bool(cfg.get("autostart_enabled", True)), 24, 118, 280
            )

            self.hint = label(view, "", 24, 70, 360, 18, 12)
            button(view, "取消", b"cancel:", self, 300, 28, 90)
            button(view, "应用", b"apply:", self, 400, 28, 90)
            button(view, "保存", b"save:", self, 500, 28, 90)

            self.window.makeKeyAndOrderFront_(None)
            if start_import:
                AppHelper.callLater(0.4, self.loginImport_, None)

        def focusTokenField(self) -> None:
            try:
                self.window.makeFirstResponder_(self.tokenField)
            except Exception:
                pass

        def windowWillClose_(self, _notification) -> None:
            AppHelper.stopEventLoop()

        def loginImport_(self, _sender=None) -> None:
            self._run_import(open_browser=True)

        def cookieImport_(self, _sender=None) -> None:
            self._run_import(open_browser=False)

        def cancelImport_(self, _sender=None) -> None:
            self._cancel_import = True
            self.status.setStringValue_("正在取消…")

        def cancel_(self, _sender=None) -> None:
            self._cancel_import = True
            self.window.close()

        def apply_(self, _sender=None) -> None:
            if self._save():
                self.hint.setStringValue_("已应用")

        def save_(self, _sender=None) -> None:
            if self._save():
                self.window.close()

        def _set_importing(self, busy: bool) -> None:
            self._importing = busy
            self.btnLogin.setEnabled_(not busy)
            self.btnCookie.setEnabled_(not busy)
            self.btnCancelImp.setEnabled_(busy)

        def _run_import(self, *, open_browser: bool) -> None:
            if self._importing:
                return
            self._cancel_import = False
            self._set_importing(True)
            self.status.setStringValue_("正在打开浏览器…" if open_browser else "正在读取 Cookie…")

            def worker() -> None:
                result = None
                error = None
                try:
                    from browser_auth import import_and_validate, start_browser_login_and_import

                    def on_progress(text: str) -> None:
                        AppHelper.callAfter(self.status.setStringValue_, text)

                    cancel = lambda: self._cancel_import
                    if open_browser:
                        result = start_browser_login_and_import(
                            timeout_sec=180.0,
                            should_cancel=cancel,
                            on_progress=on_progress,
                        )
                    else:
                        result = import_and_validate(
                            should_cancel=cancel,
                            on_progress=on_progress,
                        )
                except Exception as exc:  # noqa: BLE001
                    error = exc
                AppHelper.callAfter(self._finish_import, result, error)

            threading.Thread(target=worker, daemon=True, name="cookie-import").start()

        def _finish_import(self, result: Any, error: Exception | None) -> None:
            self._set_importing(False)
            if error is not None:
                self.status.setStringValue_(f"导入异常：{error}")
                show_error_alert("导入异常", str(error))
                return
            if result is None:
                self.status.setStringValue_("导入已结束")
                return
            if result.ok:
                self.tokenField.setStringValue_(result.token)
                self.status.setStringValue_(result.message)
                self._save()
                return
            short = (result.message or "导入失败").split("\n")[0]
            self.status.setStringValue_(short)
            if short != "已取消":
                show_error_alert("导入失败", result.message)

        def _save(self) -> bool:
            from cursor_api import normalize_workos_token

            token = normalize_workos_token(self.tokenField.stringValue().strip())
            self.tokenField.setStringValue_(token)
            try:
                interval = int(self.intervalField.stringValue().strip())
            except ValueError:
                show_error_alert("错误", "刷新间隔必须是数字")
                return False
            if interval < 1:
                show_error_alert("错误", "刷新间隔至少为 1 分钟")
                return False
            raw_thr = self.thresholdField.stringValue().strip().replace("，", ",")
            parts = [p.strip() for p in raw_thr.split(",") if p.strip()]
            try:
                parsed = sorted(
                    {int(float(p)) for p in parts if 1 <= int(float(p)) <= 100},
                    reverse=True,
                )
            except ValueError:
                show_error_alert("错误", "告警阈值格式无效，请使用如 50,20,5")
                return False
            if not parsed:
                show_error_alert("错误", "请至少填写一个 1–100 的告警阈值")
                return False
            mode_idx = int(self.modePopup.indexOfSelectedItem())
            display_mode = self._modes[mode_idx][0] if 0 <= mode_idx < len(self._modes) else "ring"
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
            new_cfg["notify_enabled"] = bool(self.notifyBox.state())
            new_cfg["notify_exhaustion_risk"] = bool(self.exhaustBox.state())
            new_cfg["tray_display_mode"] = display_mode
            new_cfg["autostart_enabled"] = bool(self.autostartBox.state())
            if token != old_token:
                new_cfg["auth_error_notified"] = False
            save_config(new_cfg)
            app_log("native settings saved")
            return True

    return SettingsController
