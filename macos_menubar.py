"""macOS 菜单栏：Retina 图标 + 左键状态明细面板。

pystray 的 Darwin 后端会把图标缩成 statusBar.thickness()（约 22×22 像素）
并 setTemplate_(YES)。Retina 上会被放大发糊，彩色圆环也会被当成模板图。

另外只要 NSStatusItem 挂了菜单，左键就只弹出菜单，不会走 default 动作，
所以「显示状态」的 NSAlert 既不像明细窗，也经常在 LSUIElement 下不出现。

这里在菜单栏进程里用 AppKit：
- 用 drawingHandler 按目标 scale 矢量重画，或嵌入 2x+3x 位图；禁止 1x 22px
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
        NSBitmapImageRep,
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
_ICON_STATE: dict[str, Any] = {
    "remaining": None,
    "error": False,
    "mode": "ring",
}
_LAST_ICON_LOG: tuple[Any, ...] | None = None

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
    _patch_icon_updates(icon)
    _patch_update_menu(icon)
    _detach_menu(icon)
    _install_clicks(icon, on_left_click)
    set_menubar_icon(icon, remaining=None, error=False, mode="ring")
    app_log("menubar retina icon and status panel installed")


def apply_retina_icon(icon, image=None, **kwargs: Any) -> None:
    """兼容旧入口：改走矢量 / 2x+3x 图标。"""
    set_menubar_icon(icon, image=image, **kwargs)


def set_menubar_icon(
    icon,
    *,
    remaining: float | None = None,
    error: bool = False,
    mode: str = "ring",
    image=None,
) -> None:
    """在主线程设置菜单栏图标。不要把小图放大，也不要走 pystray 的 22px 路径。"""
    _ICON_STATE["remaining"] = remaining
    _ICON_STATE["error"] = bool(error)
    _ICON_STATE["mode"] = (mode or "ring").strip().lower()
    if image is not None:
        _ICON_STATE["image"] = image
    if not _HAS_APPKIT or icon is None:
        return

    def go() -> None:
        _apply_icon_now(icon)

    try:
        from macos_settings import _on_main

        _on_main(go)
    except Exception:
        go()


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


def _patch_icon_updates(icon) -> None:
    """彻底接管 pystray 设图，避免它再 resize 成 22×22 并 setTemplate。"""

    def _assert_image() -> None:
        _apply_icon_now(icon)

    def _update_icon() -> None:
        def go() -> None:
            _apply_icon_now(icon)
            icon._icon_valid = True

        try:
            from macos_settings import _on_main

            _on_main(go)
        except Exception:
            go()

    icon._assert_image = _assert_image
    icon._update_icon = _update_icon


def _menubar_point_size(icon) -> float:
    try:
        from AppKit import NSStatusBar

        thickness = float(NSStatusBar.systemStatusBar().thickness() or 22.0)
        if thickness > 0:
            return thickness
    except Exception:
        pass
    return 22.0


def _menubar_scale(icon) -> float:
    scales = [2.0]
    try:
        item = getattr(icon, "_status_item", None)
        if item is not None:
            win = item.button().window()
            if win is not None:
                scales.append(float(win.backingScaleFactor()))
    except Exception:
        pass
    try:
        from AppKit import NSScreen

        for screen in list(NSScreen.screens() or []):
            scales.append(float(screen.backingScaleFactor()))
        main = NSScreen.mainScreen()
        if main is not None:
            scales.append(float(main.backingScaleFactor()))
    except Exception:
        pass
    return max(scales)


def _apply_icon_now(icon) -> None:
    if not _HAS_APPKIT or icon is None:
        return
    item = getattr(icon, "_status_item", None)
    if item is None:
        return
    button = item.button()
    if button is None:
        return

    point = _menubar_point_size(icon)
    scale = _menubar_scale(icon)
    remaining = _ICON_STATE.get("remaining")
    error = bool(_ICON_STATE.get("error"))
    mode = str(_ICON_STATE.get("mode") or "ring")

    ns = _make_status_nsimage(remaining, error, mode, point, scale)
    if ns is None:
        return
    try:
        ns.setTemplate_(False)
    except Exception:
        pass
    try:
        from AppKit import NSImageCacheNever

        ns.setCacheMode_(NSImageCacheNever)
    except Exception:
        try:
            ns.setCacheMode_(3)
        except Exception:
            pass

    button.setImage_(ns)
    try:
        button.setImagePosition_(1)  # NSImageOnly
    except Exception:
        pass
    try:
        button.setImageScaling_(2)  # NSImageScaleNone
    except Exception:
        pass
    icon._icon_image = ns
    try:
        from AppKit import NSSquareStatusItemLength

        item.setLength_(NSSquareStatusItemLength)
    except Exception:
        try:
            item.setLength_(point)
        except Exception:
            pass

    global _LAST_ICON_LOG
    key = (
        None if remaining is None else int(round(float(remaining))),
        error,
        mode,
        round(point, 1),
        round(scale, 2),
    )
    if key != _LAST_ICON_LOG:
        _LAST_ICON_LOG = key
        app_log(f"menubar icon applied pt={point:.1f} scale={scale:.2f} mode={mode} remaining={remaining}")


def _make_status_nsimage(
    remaining: float | None,
    error: bool,
    mode: str,
    point: float,
    scale: float,
):
    size = NSMakeSize(float(point), float(point))
    try:
        def handler(rect) -> bool:
            try:
                _draw_status_icon(rect, remaining, error, mode)
            except Exception as exc:  # noqa: BLE001
                app_log(f"draw menubar icon failed: {exc}")
            return True

        img = NSImage.imageWithSize_flipped_drawingHandler_(size, False, handler)
        if img is not None:
            img.setTemplate_(False)
            return img
    except Exception as exc:
        app_log(f"vector menubar icon failed, using bitmap reps: {exc}")
    return _bitmap_status_nsimage(remaining, error, mode, point)


def _draw_status_icon(rect, remaining: float | None, error: bool, mode: str) -> None:
    from AppKit import NSBezierPath
    from icon_renderer import remaining_color

    w = float(rect.size.width)
    h = float(rect.size.height)
    cx = float(rect.origin.x) + w / 2.0
    cy = float(rect.origin.y) + h / 2.0
    box = min(w, h)
    inset = max(1.0, box * 0.08)
    outer = box / 2.0 - inset
    if mode == "dot":
        r = box * 0.38
        if error:
            rgb = (231, 76, 60)
        elif remaining is None:
            rgb = (100, 116, 139)
        else:
            rgb = remaining_color(remaining)
        _ns_color(*rgb).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - r, cy - r, r * 2.0, r * 2.0)
        ).fill()
        if error:
            _draw_centered_text("!", cx, cy, box * 0.42, (255, 255, 255))
        return

    ring_w = outer * (0.12 if mode == "number" else 0.28)
    mid_r = outer - ring_w / 2.0

    disc_r = outer - ring_w * 0.08
    _ns_color(255, 255, 255, 0.16).setFill()
    NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(cx - disc_r, cy - disc_r, disc_r * 2.0, disc_r * 2.0)
    ).fill()

    track = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(cx - mid_r, cy - mid_r, mid_r * 2.0, mid_r * 2.0)
    )
    track.setLineWidth_(ring_w)
    _ns_color(236, 236, 240).setStroke()
    track.stroke()

    label = "–"
    rgb = (148, 163, 184)
    if error:
        rgb = (248, 113, 113)
        label = "!"
        _stroke_arc(cx, cy, mid_r, ring_w, 0.0, 360.0, rgb)
    elif remaining is None:
        _stroke_arc(cx, cy, mid_r, ring_w, 0.0, 360.0, rgb)
    else:
        pct = min(100.0, max(0.0, float(remaining)))
        rgb = remaining_color(pct)
        if pct >= 99.95:
            _stroke_arc(cx, cy, mid_r, ring_w, 0.0, 360.0, rgb)
        elif pct > 0.05:
            _stroke_arc(cx, cy, mid_r, ring_w, 90.0, 90.0 - pct / 100.0 * 360.0, rgb)
        label = "100" if pct >= 99.5 else str(int(round(pct)))

    if mode == "dot":
        return
    font_box = box * (0.40 if label == "100" else 0.50 if len(label) >= 2 else 0.58)
    _draw_centered_text(label, cx, cy, font_box, rgb)


def _stroke_arc(
    cx: float,
    cy: float,
    radius: float,
    width: float,
    start: float,
    end: float,
    rgb: tuple[int, int, int],
) -> None:
    from AppKit import NSBezierPath

    path = NSBezierPath.bezierPath()
    path.setLineWidth_(width)
    try:
        path.setLineCapStyle_(1)  # round
    except Exception:
        pass
    if abs(abs(end - start) - 360.0) < 0.5:
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (cx, cy), radius, 0.0, 360.0, False
        )
    else:
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (cx, cy), radius, float(start), float(end), True
        )
    _ns_color(*rgb).setStroke()
    path.stroke()


def _ns_color(r: int, g: int, b: int, a: float = 1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        r / 255.0, g / 255.0, b / 255.0, a
    )


def _draw_centered_text(
    text: str,
    cx: float,
    cy: float,
    size: float,
    rgb: tuple[int, int, int],
) -> None:
    from AppKit import (
        NSColor,
        NSFont,
        NSFontAttributeName,
        NSForegroundColorAttributeName,
        NSStrokeColorAttributeName,
        NSStrokeWidthAttributeName,
    )
    from Foundation import NSAttributedString

    try:
        font = NSFont.monospacedDigitSystemFontOfSize_weight_(size, 0.5)
    except Exception:
        font = NSFont.boldSystemFontOfSize_(size)
    attrs = {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: _ns_color(*rgb),
        NSStrokeColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.92),
        NSStrokeWidthAttributeName: -10.0,
    }
    s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    ts = s.size()
    s.drawAtPoint_((cx - float(ts.width) / 2.0, cy - float(ts.height) / 2.0))


def _bitmap_status_nsimage(
    remaining: float | None,
    error: bool,
    mode: str,
    point: float,
):
    from icon_renderer import create_progress_icon, menubar_icon_rep_sizes

    img = NSImage.alloc().initWithSize_(NSMakeSize(float(point), float(point)))
    img.setTemplate_(False)
    for px in menubar_icon_rep_sizes(point):
        pil = create_progress_icon(remaining, error=error, size=int(px), mode=mode)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        raw = buf.getvalue()
        data = NSData.dataWithBytes_length_(raw, len(raw))
        rep = NSBitmapImageRep.alloc().initWithData_(data)
        if rep is None:
            continue
        rep.setSize_(NSMakeSize(float(point), float(point)))
        img.addRepresentation_(rep)
    return img


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
