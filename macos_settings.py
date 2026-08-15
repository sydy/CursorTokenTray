"""macOS 设置窗：纯 AppKit，在菜单栏进程的主线程里用模态窗打开。

不要另起同 bundle 子进程：LSUIElement 下子进程经常建了窗却不显示。
不要用 Tk：打包的 Tk 8.6 在 macOS 26 会秒崩。
不要在后台线程 AppHelper.callLater：定时器挂在子线程 run loop 上，永远不会触发。
"""

from __future__ import annotations

import ctypes
import threading
from typing import Any, Callable

from platform_util import app_log, show_error_alert
from settings_launch import settings_flags

try:
    from AppKit import (  # type: ignore[import-not-found]
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSApplicationActivationPolicyRegular,
        NSBackingStoreBuffered,
        NSButton,
        NSButtonTypeSwitch,
        NSFloatingWindowLevel,
        NSFont,
        NSNormalWindowLevel,
        NSObject,
        NSPopUpButton,
        NSTextField,
        NSWindow,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorMoveToActiveSpace,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskMiniaturizable,
        NSWindowStyleMaskTitled,
    )
    from Foundation import NSMakeRect, NSOperationQueue, NSThread
    from PyObjCTools import AppHelper

    _HAS_APPKIT = True
except ImportError:  # Linux CI
    _HAS_APPKIT = False
    NSObject = object  # type: ignore[misc,assignment]
    AppHelper = None
    NSApp = None
    NSOperationQueue = None
    NSThread = None

_CONTROLLER = None
_PENDING_MAIN: list[Any] = []


class _MainCall(NSObject):
    """把 Python 回调投递到 AppKit 主线程。"""

    def run_(self, _obj=None) -> None:
        fn = getattr(self, "_fn", None)
        try:
            if fn is not None:
                fn()
        except Exception as exc:  # noqa: BLE001
            app_log(f"main-thread call failed: {exc}")
            show_error_alert("设置", f"无法打开设置：{exc}")
        finally:
            try:
                _PENDING_MAIN.remove(self)
            except ValueError:
                pass


def _on_main(fn: Callable[[], None]) -> None:
    """务必在 NSApplication 主线程执行。后台线程的 NSTimer 不会被泵。"""
    if not _HAS_APPKIT:
        fn()
        return
    try:
        if bool(NSThread.isMainThread()):
            fn()
            return
    except Exception:
        pass
    try:
        NSOperationQueue.mainQueue().addOperationWithBlock_(fn)
        app_log("settings dispatched via main NSOperationQueue")
        return
    except Exception as exc:
        app_log(f"NSOperationQueue dispatch failed: {exc}")
    invoker = _MainCall.alloc().init()
    invoker._fn = fn
    _PENDING_MAIN.append(invoker)
    invoker.performSelectorOnMainThread_withObject_waitUntilDone_("run:", None, False)
    app_log("settings dispatched via performSelectorOnMainThread")


def close_settings() -> None:
    """退出前关掉设置模态窗，否则主循环停不下来。"""
    global _CONTROLLER
    app_log("close_settings")
    ctrl = _CONTROLLER
    _CONTROLLER = None
    if not _HAS_APPKIT:
        return
    try:
        NSApplication.sharedApplication().abortModal()
    except Exception:
        pass
    try:
        NSApplication.sharedApplication().stopModal()
    except Exception:
        pass
    window = getattr(ctrl, "window", None) if ctrl is not None else None
    if window is not None:
        try:
            window.close()
        except Exception as exc:
            app_log(f"close settings window failed: {exc}")


def show_settings(
    *,
    focus_token: bool = False,
    start_import: bool = False,
    on_saved: Callable[[dict[str, Any]], None] | None = None,
    owns_loop: bool = False,
) -> None:
    """打开设置。可从菜单回调或后台线程调用。"""
    app_log(f"show_settings focus={focus_token} import={start_import} owns_loop={owns_loop}")
    if not _HAS_APPKIT:
        show_error_alert("设置", "当前环境没有 AppKit。")
        return

    def start() -> None:
        try:
            if owns_loop:
                _present(
                    focus_token=focus_token,
                    start_import=start_import,
                    on_saved=on_saved,
                    owns_loop=True,
                )
                return
            # 等菜单栏菜单收起后再模态展示，否则窗会被菜单压住或立刻失焦。
            AppHelper.callLater(
                0.25,
                lambda: _present(
                    focus_token=focus_token,
                    start_import=start_import,
                    on_saved=on_saved,
                    owns_loop=False,
                ),
            )
            app_log("settings scheduled on main run loop")
        except Exception as exc:  # noqa: BLE001
            app_log(f"show_settings start failed: {exc}")
            show_error_alert("设置", f"无法打开设置：{exc}")

    _on_main(start)


def run_macos_settings() -> int:
    """`CursorTokenTray --settings` 独立入口（开发调试用）。"""
    if not _HAS_APPKIT:
        show_error_alert("设置", "缺少 AppKit / PyObjC。")
        return 1
    focus_token, start_import = settings_flags()
    app_log(f"native settings standalone focus={focus_token} import={start_import}")
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    try:
        app.finishLaunching()
    except Exception:
        pass
    show_settings(focus_token=focus_token, start_import=start_import, owns_loop=True)
    app.activateIgnoringOtherApps_(True)
    AppHelper.runEventLoop()
    app_log("native settings standalone exit")
    return 0


def _transform_foreground() -> None:
    """LSUIElement 进程转成前台应用，窗口才能成为 Key。"""
    try:
        class _PSN(ctypes.Structure):
            _fields_ = [("high", ctypes.c_uint32), ("low", ctypes.c_uint32)]

        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        psn = _PSN(0, 2)  # kCurrentProcess
        lib.TransformProcessType(ctypes.byref(psn), ctypes.c_int32(1))
    except Exception as exc:
        app_log(f"TransformProcessType skipped: {exc}")


def _front_app() -> None:
    _transform_foreground()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    try:
        app.finishLaunching()
    except Exception:
        pass
    app.activateIgnoringOtherApps_(True)
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

        NSRunningApplication.currentApplication().activateWithOptions_(
            NSApplicationActivateIgnoringOtherApps
        )
    except Exception:
        pass
    try:
        app.arrangeInFront_(None)
    except Exception:
        pass


def _front_window(window) -> None:
    window.setHidesOnDeactivate_(False)
    try:
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorMoveToActiveSpace
        )
    except Exception:
        pass
    window.center()
    window.makeKeyAndOrderFront_(None)
    try:
        window.makeMainWindow()
    except Exception:
        pass
    try:
        window.orderFrontRegardless()
    except Exception:
        pass
    try:
        window.setLevel_(NSFloatingWindowLevel)
        AppHelper.callLater(1.2, lambda: window.setLevel_(NSNormalWindowLevel))
    except Exception:
        pass
    try:
        visible = bool(window.isVisible())
        key = bool(window.isKeyWindow())
        app_log(f"settings window fronted visible={visible} key={key}")
    except Exception as exc:
        app_log(f"settings window state read failed: {exc}")


def _present(
    *,
    focus_token: bool,
    start_import: bool,
    on_saved: Callable[[dict[str, Any]], None] | None,
    owns_loop: bool,
) -> None:
    global _CONTROLLER
    try:
        _front_app()
        ctrl = _CONTROLLER
        reused = False
        if ctrl is not None and getattr(ctrl, "window", None) is not None:
            try:
                if ctrl.window.isVisible() or getattr(ctrl, "_in_modal", False):
                    app_log("settings window already open, raising")
                    ctrl._on_saved = on_saved
                    ctrl._owns_loop = owns_loop
                    _front_window(ctrl.window)
                    reused = True
            except Exception as exc:
                app_log(f"reuse settings window failed: {exc}")
                _CONTROLLER = None
                ctrl = None

        if not reused:
            ctrl = SettingsController.alloc().init()
            ctrl._on_saved = on_saved
            ctrl._owns_loop = owns_loop
            ctrl._in_modal = False
            ctrl.build()
            _CONTROLLER = ctrl
            _front_window(ctrl.window)
            app_log("settings window created")

        if focus_token:
            ctrl.focusTokenField()
        if start_import and not reused:
            AppHelper.callLater(0.4, ctrl.cursorImport_, None)

        if owns_loop:
            return
        if getattr(ctrl, "_in_modal", False):
            app_log("settings already in modal session")
            return

        app = NSApplication.sharedApplication()
        ctrl._in_modal = True
        app_log("settings runModal begin")
        try:
            app.runModalForWindow_(ctrl.window)
        finally:
            ctrl._in_modal = False
            app_log("settings runModal end")
            try:
                app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        app_log(f"present settings failed: {exc}")
        show_error_alert("设置", f"无法打开设置：{exc}")


class SettingsController(NSObject):
    def build(self) -> None:
        from config import load_config

        cfg = load_config()
        self._cancel_import = False
        self._importing = False
        if not hasattr(self, "_on_saved"):
            self._on_saved = None
        if not hasattr(self, "_owns_loop"):
            self._owns_loop = False
        if not hasattr(self, "_in_modal"):
            self._in_modal = False

        width, height = 640.0, 600.0
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
        self.window.setReleasedWhenClosed_(False)
        self.window.setHidesOnDeactivate_(False)
        self.window.setDelegate_(self)
        view = self.window.contentView()

        _label(view, "账户与登录", 24, 560, 400, 22, 16)
        _label(view, "会话 Token（请勿分享）", 24, 532, 300, 16, 12)
        self.tokenField = _field(view, str(cfg.get("session_token") or ""), 24, 502, 592, 26)
        _label(view, "已登录 Cursor 时可直接导入。浏览器 Cookie 仅作备选。", 24, 474, 592, 16, 11)

        self.btnCursor = _button(view, "从 Cursor 导入", b"cursorImport:", self, 24, 438, 140)
        self.btnSafari = _button(view, "Safari 登录", b"safariImport:", self, 174, 438, 110)
        self.btnFirefox = _button(view, "Firefox 登录", b"firefoxImport:", self, 294, 438, 120)
        self.btnCookie = _button(view, "仅扫描 Cookie", b"cookieImport:", self, 24, 404, 130)
        self.btnCancelImp = _button(view, "取消等待", b"cancelImport:", self, 164, 404, 100)
        self.btnCancelImp.setEnabled_(False)
        self.status = _label(view, "", 24, 376, 592, 22, 12)

        _label(view, "刷新与通知", 24, 340, 400, 22, 16)
        _label(view, "刷新间隔（分钟）", 24, 314, 160, 16, 12)
        self.intervalField = _field(view, str(int(cfg.get("refresh_interval_minutes", 10))), 190, 310, 64, 24)
        _label(view, "告警阈值，例如 50,20,5", 24, 282, 220, 16, 12)
        thresholds = cfg.get("alert_thresholds") or [50, 20, 5]
        self.thresholdField = _field(view, ",".join(str(int(x)) for x in thresholds), 250, 278, 140, 24)
        self.notifyBox = _checkbox(view, "启用用量通知", bool(cfg.get("notify_enabled", True)), 24, 246, 220)
        self.exhaustBox = _checkbox(
            view, "启用耗尽风险通知", bool(cfg.get("notify_exhaustion_risk", True)), 250, 246, 220
        )

        _label(view, "菜单栏与启动", 24, 208, 400, 22, 16)
        _label(view, "菜单栏图标", 24, 182, 120, 16, 12)
        self.modePopup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(150, 176, 160, 26), False
        )
        self._modes = [("ring", "圆环百分比"), ("number", "纯数字"), ("dot", "仅色点")]
        for _key, title in self._modes:
            self.modePopup.addItemWithTitle_(title)
        cur = str(cfg.get("tray_display_mode") or "ring")
        idx = next((i for i, (k, _) in enumerate(self._modes) if k == cur), 0)
        self.modePopup.selectItemAtIndex_(idx)
        view.addSubview_(self.modePopup)
        self.autostartBox = _checkbox(
            view, "开机自启（下次登录生效）", bool(cfg.get("autostart_enabled", True)), 24, 146, 280
        )

        self.hint = _label(view, "", 24, 90, 360, 18, 12)
        _button(view, "取消", b"cancel:", self, 300, 28, 90)
        _button(view, "应用", b"apply:", self, 400, 28, 90)
        _button(view, "保存", b"save:", self, 500, 28, 90)

    def focusTokenField(self) -> None:
        try:
            self.window.makeFirstResponder_(self.tokenField)
        except Exception:
            pass

    def windowWillClose_(self, _notification) -> None:
        app_log("settings window closing")
        global _CONTROLLER
        if _CONTROLLER is self:
            _CONTROLLER = None
        if getattr(self, "_in_modal", False):
            try:
                NSApplication.sharedApplication().stopModal()
            except Exception:
                pass
        if getattr(self, "_owns_loop", False) and AppHelper is not None:
            AppHelper.stopEventLoop()
            return
        try:
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
        except Exception:
            pass

    def cursorImport_(self, _sender=None) -> None:
        self._run_import(open_browser=False, prefer="cursor-app")

    def safariImport_(self, _sender=None) -> None:
        self._run_import(open_browser=True, prefer="safari")

    def firefoxImport_(self, _sender=None) -> None:
        self._run_import(open_browser=True, prefer="firefox")

    def loginImport_(self, _sender=None) -> None:
        self._run_import(open_browser=True, prefer="safari")

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
        idle = not busy
        for btn in (
            getattr(self, "btnCursor", None),
            getattr(self, "btnSafari", None),
            getattr(self, "btnFirefox", None),
            self.btnCookie,
        ):
            if btn is not None:
                btn.setEnabled_(idle)
        self.btnCancelImp.setEnabled_(busy)

    def _run_import(self, *, open_browser: bool, prefer: str | None = None) -> None:
        if self._importing:
            return
        self._cancel_import = False
        self._set_importing(True)
        if prefer == "cursor-app":
            self.status.setStringValue_("正在读取 Cursor 应用登录态…")
        elif open_browser and prefer == "safari":
            self.status.setStringValue_("正在打开 Safari…")
        elif open_browser and prefer == "firefox":
            self.status.setStringValue_("正在打开 Firefox…")
        else:
            self.status.setStringValue_("正在打开浏览器…" if open_browser else "正在读取登录态…")

        def worker() -> None:
            result = None
            error = None
            try:
                from browser_auth import import_and_validate, start_browser_login_and_import

                def on_progress(text: str) -> None:
                    message = text
                    _on_main(lambda: self.status.setStringValue_(message))

                cancel = lambda: self._cancel_import
                if open_browser:
                    result = start_browser_login_and_import(
                        timeout_sec=180.0,
                        prefer=prefer,
                        should_cancel=cancel,
                        on_progress=on_progress,
                    )
                else:
                    from browser_auth import _default_prefer_browsers

                    result = import_and_validate(
                        prefer_browsers=_default_prefer_browsers(prefer) if prefer else None,
                        should_cancel=cancel,
                        on_progress=on_progress,
                    )
            except Exception as exc:  # noqa: BLE001
                error = exc
            done_result, done_error = result, error
            _on_main(lambda: self._finish_import(done_result, done_error))

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
        from config import load_config, save_config
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
            parsed = sorted({int(float(p)) for p in parts if 1 <= int(float(p)) <= 100}, reverse=True)
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
        cb = getattr(self, "_on_saved", None)
        if cb:
            try:
                cb(new_cfg)
            except Exception as exc:
                app_log(f"on_saved failed: {exc}")
        return True


def _label(parent, text: str, x: float, y: float, w: float, h: float = 18, size: float = 13):
    lab = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    lab.setStringValue_(text)
    lab.setBezeled_(False)
    lab.setDrawsBackground_(False)
    lab.setEditable_(False)
    lab.setSelectable_(False)
    lab.setFont_(NSFont.systemFontOfSize_(size))
    parent.addSubview_(lab)
    return lab


def _field(parent, value: str, x: float, y: float, w: float, h: float = 24):
    box = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    box.setStringValue_(value)
    parent.addSubview_(box)
    return box


def _button(parent, title: str, action, target, x: float, y: float, w: float, h: float = 28):
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    btn.setTitle_(title)
    btn.setBezelStyle_(1)
    btn.setTarget_(target)
    btn.setAction_(action)
    parent.addSubview_(btn)
    return btn


def _checkbox(parent, title: str, checked: bool, x: float, y: float, w: float):
    box = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 22))
    box.setButtonType_(NSButtonTypeSwitch)
    box.setTitle_(title)
    box.setState_(1 if checked else 0)
    parent.addSubview_(box)
    return box
