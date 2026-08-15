"""macOS 菜单栏：Retina 图标 + 左键状态明细面板。

pystray 的 Darwin 后端会把图标缩成 statusBar.thickness()（约 22×22 像素）
并 setTemplate_(YES)。Retina 上会被放大发糊，彩色圆环也会被当成模板图。

另外只要 NSStatusItem 挂了菜单，左键就只弹出菜单，不会走 default 动作，
所以「显示状态」的 NSAlert 既不像明细窗，也经常在 LSUIElement 下不出现。

这里在菜单栏进程里用 AppKit：
- 用 2x/3x 像素重建 NSImage，按 22pt 显示，且不是 template
- 左键打开原生状态面板；右键仍弹出原菜单
不要用 Tk。
"""

from __future__ import annotations

import io
import time
from typing import Any, Callable

from platform_util import app_log
from status_text import build_status_lines

try:
    from AppKit import (  # type: ignore[import-not-found]
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSBackingStoreBuffered,
        NSButton,
        NSColor,
        NSEvent,
        NSFloatingWindowLevel,
        NSFont,
        NSImage,
        NSImageView,
        NSObject,
        NSTextField,
        NSWindow,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorMoveToActiveSpace,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskTitled,
    )
    from Foundation import NSData, NSMakeRect, NSMakeSize
    from PyObjCTools import AppHelper

    _HAS_APPKIT = True
except ImportError:  # Linux CI
    _HAS_APPKIT = False
    NSObject = object  # type: ignore[misc,assignment]
    AppHelper = None
    NSApp = None
    NSEvent = None

_CLICK = None
_STATUS = None
_RIGHT_MONITOR = None
_OUTSIDE_MONITOR = None
_LAST_MENU_AT = 0.0
_INSTALLED_ICON = None

# NSEventType / NSEventMask（避免个别 SDK 常量名差异）
_NS_LEFT_UP = 2
_NS_RIGHT_DOWN = 3
_NS_RIGHT_UP = 4
_NS_MASK_LEFT_UP = 1 << 2
_NS_MASK_RIGHT_DOWN = 1 << 3
_NS_MASK_RIGHT_UP = 1 << 4
_NS_MASK_LEFT_DOWN = 1 << 1
_NS_CONTROL = 1 << 18

PANEL_W = 380.0
PANEL_H = 392.0


def install(icon, *, on_left_click: Callable[[], None] | None = None) -> None:
    """补丁 pystray：Retina 图标、左键明细、右键菜单。"""
    if not _HAS_APPKIT:
        return
    global _INSTALLED_ICON
    _INSTALLED_ICON = icon
    _patch_assert_image(icon)
    apply_retina_icon(icon, getattr(icon, "icon", None))
    _patch_update_menu(icon)
    _detach_menu(icon)
    _install_clicks(icon, on_left_click)
    app_log("menubar retina icon and status panel installed")


def apply_retina_icon(icon, image) -> None:
    """用带 scale 的 NSImage 替换 pystray 的 22px 1x 图。"""
    if not _HAS_APPKIT or icon is None or image is None:
        return
    item = getattr(icon, "_status_item", None)
    if item is None:
        return
    try:
        from AppKit import NSStatusBar

        thickness = float(NSStatusBar.systemStatusBar().thickness() or 22.0)
    except Exception:
        thickness = 22.0
    if thickness <= 0:
        thickness = 22.0

    from dpi_util import enable_dpi_awareness
    from icon_renderer import menubar_icon_pixels

    px = menubar_icon_pixels(thickness, enable_dpi_awareness())
    work = image
    try:
        if work.size != (px, px):
            from PIL import Image

            work = image.resize((px, px), Image.Resampling.LANCZOS)
    except Exception:
        work = image

    ns = _pil_to_nsimage(work, thickness)
    if ns is None:
        return
    try:
        ns.setTemplate_(False)
    except Exception:
        pass
    button = item.button()
    if button is None:
        return
    button.setImage_(ns)
    try:
        button.setImagePosition_(1)  # NSImageOnly
    except Exception:
        pass
    icon._icon_image = ns
    try:
        from AppKit import NSSquareStatusItemLength

        item.setLength_(NSSquareStatusItemLength)
    except Exception:
        try:
            item.setLength_(thickness)
        except Exception:
            pass


def show_status(
    *,
    usage: Any = None,
    error_message: str | None = None,
    updated_at: str | None = None,
    icon=None,
    on_refresh: Callable[[], None] | None = None,
    on_open_spending: Callable[[], None] | None = None,
    on_open_settings: Callable[[], None] | None = None,
    **_unused: Any,
) -> None:
    """打开或切换状态明细面板。可从菜单回调或后台线程调用。"""
    if not _HAS_APPKIT:
        app_log("status panel skipped: no AppKit")
        return

    def start() -> None:
        try:
            _present(
                usage=usage,
                error_message=error_message,
                updated_at=updated_at,
                icon=icon or _INSTALLED_ICON,
                on_refresh=on_refresh,
                on_open_spending=on_open_spending,
                on_open_settings=on_open_settings,
            )
        except Exception as exc:  # noqa: BLE001
            app_log(f"show status failed: {exc}")

    from macos_settings import _on_main

    _on_main(start)


def update_status(
    *,
    usage: Any = None,
    error_message: str | None = None,
    updated_at: str | None = None,
    **_unused: Any,
) -> None:
    ctrl = _STATUS
    if ctrl is None or not _HAS_APPKIT:
        return
    try:
        if not bool(ctrl.window.isVisible()):
            return
    except Exception:
        return

    def apply() -> None:
        try:
            ctrl.apply_data(usage, error_message, updated_at)
        except Exception as exc:
            app_log(f"update status failed: {exc}")

    from macos_settings import _on_main

    _on_main(apply)


def close_status() -> None:
    """退出前关掉状态面板。"""
    global _STATUS, _OUTSIDE_MONITOR
    ctrl = _STATUS
    _STATUS = None
    _remove_outside_monitor()
    if ctrl is None or not _HAS_APPKIT:
        return
    window = getattr(ctrl, "window", None)
    if window is not None:
        try:
            window.close()
        except Exception as exc:
            app_log(f"close status window failed: {exc}")


def is_status_visible() -> bool:
    ctrl = _STATUS
    if ctrl is None:
        return False
    try:
        return bool(ctrl.window.isVisible())
    except Exception:
        return False


def _patch_assert_image(icon) -> None:
    def _assert_image() -> None:
        apply_retina_icon(icon, getattr(icon, "icon", None))

    icon._assert_image = _assert_image


def _patch_update_menu(icon) -> None:
    original = icon._update_menu

    def _update_menu() -> None:
        original()
        _detach_menu(icon)

    icon._update_menu = _update_menu


def _detach_menu(icon) -> None:
    """菜单挂在 NSStatusItem 上时，左键只会弹出菜单。"""
    item = getattr(icon, "_status_item", None)
    if item is None:
        return
    try:
        menu = item.menu()
    except Exception:
        menu = None
    if menu is not None:
        icon._ns_menu = menu
        try:
            item.setMenu_(None)
        except Exception as exc:
            app_log(f"detach status menu failed: {exc}")


def _popup_menu(icon) -> None:
    global _LAST_MENU_AT
    now = time.monotonic()
    if now - _LAST_MENU_AT < 0.25:
        return
    _LAST_MENU_AT = now
    item = getattr(icon, "_status_item", None)
    if item is None:
        return
    handle = getattr(icon, "_menu_handle", None)
    menu = handle[0] if handle else getattr(icon, "_ns_menu", None)
    if menu is None:
        return
    try:
        item.popUpStatusItemMenu_(menu)
    except Exception as exc:
        app_log(f"popup status menu failed: {exc}")


def _install_clicks(icon, on_left_click: Callable[[], None] | None) -> None:
    global _CLICK, _RIGHT_MONITOR
    if not _HAS_APPKIT:
        return
    item = getattr(icon, "_status_item", None)
    if item is None:
        return
    button = item.button()
    if button is None:
        return

    shim = _MenubarClick.alloc().init()
    shim.icon = icon
    shim.on_left_click = on_left_click
    _CLICK = shim
    button.setTarget_(shim)
    button.setAction_(b"handleClick:")
    try:
        button.sendActionOn_(_NS_MASK_LEFT_UP | _NS_MASK_RIGHT_UP)
    except Exception:
        pass

    def handler(event):
        try:
            win = button.window()
            ev_win = event.window() if event is not None else None
            if win is not None and ev_win is not None and ev_win == win:
                _popup_menu(icon)
                return None
        except Exception as exc:
            app_log(f"right-click monitor: {exc}")
        return event

    try:
        _RIGHT_MONITOR = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            _NS_MASK_RIGHT_DOWN, handler
        )
    except Exception as exc:
        app_log(f"right-click monitor failed: {exc}")


def _pil_to_nsimage(image, point_size: float):
    try:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        raw = buf.getvalue()
        data = NSData.dataWithBytes_length_(raw, len(raw))
        ns = NSImage.alloc().initWithData_(data)
        if ns is None:
            return None
        ns.setSize_(NSMakeSize(float(point_size), float(point_size)))
        return ns
    except Exception as exc:
        app_log(f"pil_to_nsimage failed: {exc}")
        return None


def _present(
    *,
    usage: Any,
    error_message: str | None,
    updated_at: str | None,
    icon,
    on_refresh: Callable[[], None] | None,
    on_open_spending: Callable[[], None] | None,
    on_open_settings: Callable[[], None] | None,
) -> None:
    global _STATUS
    ctrl = _STATUS
    if ctrl is not None:
        try:
            if bool(ctrl.window.isVisible()):
                app_log("status panel toggle close")
                close_status()
                return
        except Exception:
            _STATUS = None
            ctrl = None

    from macos_settings import _front_app

    _front_app()
    ctrl = StatusController.alloc().init()
    ctrl._on_refresh = on_refresh
    ctrl._on_open_spending = on_open_spending
    ctrl._on_open_settings = on_open_settings
    ctrl._icon = icon
    ctrl.build()
    ctrl.apply_data(usage, error_message, updated_at)
    _STATUS = ctrl
    _position_panel(ctrl.window, icon)
    _front_panel(ctrl.window)
    _install_outside_monitor(ctrl)
    app_log("status panel shown")


def _position_panel(window, icon) -> None:
    try:
        item = getattr(icon, "_status_item", None) if icon is not None else None
        if item is None:
            window.center()
            return
        button = item.button()
        rect = button.window().convertRectToScreen_(
            button.convertRect_toView_(button.bounds(), None)
        )
        frame = window.frame()
        w = float(frame.size.width)
        h = float(frame.size.height)
        x = float(rect.origin.x) + float(rect.size.width) - w
        if x < 8:
            x = 8.0
        y = float(rect.origin.y) - h - 8.0
        if y < 8:
            y = 8.0
        window.setFrameOrigin_((x, y))
    except Exception as exc:
        app_log(f"position status panel failed: {exc}")
        try:
            window.center()
        except Exception:
            pass


def _front_panel(window) -> None:
    window.setHidesOnDeactivate_(False)
    try:
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorMoveToActiveSpace
        )
    except Exception:
        pass
    try:
        window.setLevel_(NSFloatingWindowLevel)
    except Exception:
        pass
    window.makeKeyAndOrderFront_(None)
    try:
        window.orderFrontRegardless()
    except Exception:
        pass
    try:
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass


def _restore_accessory() -> None:
    try:
        from macos_settings import _CONTROLLER

        if _CONTROLLER is not None:
            return
    except Exception:
        pass
    try:
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass


def _install_outside_monitor(ctrl) -> None:
    global _OUTSIDE_MONITOR
    _remove_outside_monitor()
    if not _HAS_APPKIT:
        return

    def handler(event) -> None:
        try:
            if _click_on_panel_or_item(event, ctrl):
                return
            close_status()
        except Exception:
            pass

    try:
        _OUTSIDE_MONITOR = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            _NS_MASK_LEFT_DOWN | _NS_MASK_RIGHT_DOWN, handler
        )
    except Exception as exc:
        app_log(f"outside click monitor failed: {exc}")


def _remove_outside_monitor() -> None:
    global _OUTSIDE_MONITOR
    mon = _OUTSIDE_MONITOR
    _OUTSIDE_MONITOR = None
    if mon is None or NSEvent is None:
        return
    try:
        NSEvent.removeMonitor_(mon)
    except Exception:
        pass


def _click_on_panel_or_item(event, ctrl) -> bool:
    try:
        ev_win = event.window()
        if ev_win is not None and ctrl.window is not None and ev_win == ctrl.window:
            return True
        icon = getattr(ctrl, "_icon", None)
        item = getattr(icon, "_status_item", None) if icon is not None else None
        if item is None:
            return False
        button = item.button()
        if button is not None and ev_win is not None and ev_win == button.window():
            return True
        if ev_win is not None:
            return False
        # 全局监听里 window 为 None，locationInWindow 实际是屏幕坐标
        loc = event.locationInWindow()
        rect = button.window().convertRectToScreen_(
            button.convertRect_toView_(button.bounds(), None)
        )
        x, y = float(loc.x), float(loc.y)
        return (
            float(rect.origin.x) <= x <= float(rect.origin.x) + float(rect.size.width)
            and float(rect.origin.y) <= y <= float(rect.origin.y) + float(rect.size.height)
        )
    except Exception:
        return False


class _MenubarClick(NSObject):
    def handleClick_(self, _sender=None) -> None:
        try:
            event = NSApp.currentEvent() if NSApp is not None else None
            right = False
            if event is not None:
                t = int(event.type())
                flags = int(event.modifierFlags())
                right = t in (_NS_RIGHT_DOWN, _NS_RIGHT_UP) or bool(flags & _NS_CONTROL)
            if right:
                _popup_menu(getattr(self, "icon", None))
                return
            cb = getattr(self, "on_left_click", None)
            if cb is not None:
                cb()
                return
            icon = getattr(self, "icon", None)
            if icon is not None:
                icon()
        except Exception as exc:  # noqa: BLE001
            app_log(f"menubar click failed: {exc}")


class StatusController(NSObject):
    def build(self) -> None:
        if not hasattr(self, "_on_refresh"):
            self._on_refresh = None
        if not hasattr(self, "_on_open_spending"):
            self._on_open_spending = None
        if not hasattr(self, "_on_open_settings"):
            self._on_open_settings = None
        if not hasattr(self, "_icon"):
            self._icon = None

        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_W, PANEL_H),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("套餐剩余")
        self.window.setReleasedWhenClosed_(False)
        self.window.setHidesOnDeactivate_(False)
        self.window.setDelegate_(self)
        self._host = self.window.contentView()

    def apply_data(self, usage, error_message: str | None, updated_at: str | None) -> None:
        view = self._host
        for sub in list(view.subviews()):
            try:
                sub.removeFromSuperview()
            except Exception:
                pass

        rows = build_status_lines(usage, error_message, updated_at)
        remaining = None if usage is None else getattr(usage, "remaining_percent", None)
        plan = "" if usage is None else str(getattr(usage, "membership_type", "") or "")
        is_error = bool(error_message) and usage is None

        from icon_renderer import create_progress_icon, remaining_color

        icon_img = create_progress_icon(
            remaining,
            error=is_error,
            size=96,
        )
        ns_icon = _pil_to_nsimage(icon_img, 56.0)
        if ns_icon is not None:
            iv = NSImageView.alloc().initWithFrame_(NSMakeRect(20, _y(16, 56), 56, 56))
            iv.setImage_(ns_icon)
            view.addSubview_(iv)

        _label(view, "套餐剩余", 92, _y(18, 18), 260, 18, 12, secondary=True)
        if remaining is not None and not is_error:
            rgb = remaining_color(remaining)
            _label(
                view,
                f"{remaining:.1f}%",
                92,
                _y(38, 28),
                260,
                28,
                22,
                bold=True,
                rgb=rgb,
            )
            _label(view, plan or "—", 92, _y(68, 18), 260, 18, 12, secondary=True)
        else:
            msg = error_message or "等待刷新…"
            _label(view, msg, 92, _y(40, 40), 260, 40, 13)

        top = 100.0
        for title, value in rows:
            _label(view, title, 20, _y(top, 18), 88, 18, 12, secondary=True)
            _label(view, value, 112, _y(top, 18), 248, 18, 12)
            top += 24.0

        _button(view, "刷新", b"refresh:", self, 20, 16, 88)
        _button(view, "打开账单", b"spending:", self, 118, 16, 100)
        _button(view, "设置…", b"settings:", self, 228, 16, 88)

    def windowWillClose_(self, _notification) -> None:
        app_log("status panel closing")
        global _STATUS
        if _STATUS is self:
            _STATUS = None
        _remove_outside_monitor()
        _restore_accessory()

    def refresh_(self, _sender=None) -> None:
        cb = getattr(self, "_on_refresh", None)
        if cb:
            cb()

    def spending_(self, _sender=None) -> None:
        cb = getattr(self, "_on_open_spending", None)
        if cb:
            cb()

    def settings_(self, _sender=None) -> None:
        close_status()
        cb = getattr(self, "_on_open_settings", None)
        if cb and AppHelper is not None:
            AppHelper.callLater(0.2, cb)
        elif cb:
            cb()


def _y(from_top: float, height: float) -> float:
    return PANEL_H - from_top - height


def _label(
    parent,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    size: float,
    *,
    bold: bool = False,
    secondary: bool = False,
    rgb: tuple[int, int, int] | None = None,
):
    lab = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    lab.setStringValue_(text)
    lab.setBezeled_(False)
    lab.setDrawsBackground_(False)
    lab.setEditable_(False)
    lab.setSelectable_(True)
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    lab.setFont_(font)
    if rgb is not None:
        lab.setTextColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(
                rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0
            )
        )
    elif secondary:
        try:
            lab.setTextColor_(NSColor.secondaryLabelColor())
        except Exception:
            pass
    parent.addSubview_(lab)
    return lab


def _button(parent, title: str, action, target, x: float, y: float, w: float, h: float = 28):
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    btn.setTitle_(title)
    btn.setBezelStyle_(1)
    btn.setTarget_(target)
    btn.setAction_(action)
    parent.addSubview_(btn)
    return btn
