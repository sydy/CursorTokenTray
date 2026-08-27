"""Windows 原生用量飞出层：Pillow 出图 + 分层窗口。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time

from PIL import Image, ImageDraw, ImageFont

from cursor_api import UsageSnapshot, dashboard_button_label
from dpi_util import scaled_px
from icon_renderer import create_progress_icon, create_sparkline, remaining_color
from status_text import build_status_lines, format_summary_text

BG = (32, 32, 32, 252)
FG = (255, 255, 255, 255)
FG_SEC = (197, 197, 197, 255)
FG_TER = (154, 154, 154, 255)
LINE = (63, 63, 63, 255)
BTN = (42, 42, 42, 255)
BTN_BORDER = (70, 70, 70, 255)
ACCENT = (0, 103, 192, 255)


@dataclass
class HitTarget:
    key: str
    box: tuple[int, int, int, int]


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                r"C:\Windows\Fonts\msyhbd.ttc",
                r"C:\Windows\Fonts\segoeuib.ttf",
            ]
        )
    candidates.extend(
        [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose_flyout_image(
    *,
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None,
    account_label: str = "",
    history_values: list[float] | None = None,
    scale: float = 1.0,
) -> tuple[Image.Image, list[HitTarget]]:
    """画飞出层，返回图像和按钮热区。Linux 测试可调用。"""
    width = scaled_px(400, scale)
    pad = scaled_px(16, scale)
    gap = scaled_px(10, scale)
    icon_px = scaled_px(52, scale)
    btn_h = scaled_px(32, scale)
    radius = scaled_px(12, scale)

    font_title = _load_font(scaled_px(12, scale))
    font_hero = _load_font(scaled_px(28, scale), bold=True)
    font_body = _load_font(scaled_px(13, scale))
    font_small = _load_font(scaled_px(11, scale))
    font_btn = _load_font(scaled_px(12, scale))

    rows = build_status_lines(usage, error_message, updated_at, account_label)
    spark_h = scaled_px(44, scale) if history_values and len(history_values) >= 2 else 0

    y = pad
    y += icon_px + gap
    y += len(rows) * scaled_px(22, scale)
    if spark_h:
        y += spark_h + gap
    y += btn_h + pad + scaled_px(8, scale)
    height = max(y, scaled_px(180, scale))

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=BG)

    remaining = None if usage is None else usage.remaining_percent
    if error_message and not str(error_message).startswith("未配置"):
        icon = create_progress_icon(None, error=True, size=icon_px)
    elif usage is not None:
        icon = create_progress_icon(remaining, error=False, size=icon_px)
    else:
        icon = create_progress_icon(None, error=False, size=icon_px)
    img.alpha_composite(icon, (pad, pad))

    text_x = pad + icon_px + gap
    draw.text((text_x, pad), "套餐剩余", font=font_title, fill=FG_SEC)
    if usage is not None and remaining is not None:
        color = remaining_color(remaining) + (255,)
        draw.text((text_x, pad + scaled_px(16, scale)), f"{remaining:.1f}%", font=font_hero, fill=color)
    else:
        draw.text(
            (text_x, pad + scaled_px(18, scale)),
            (error_message or "等待刷新…")[:36],
            font=font_body,
            fill=FG,
        )

    y = pad + icon_px + gap
    draw.line((pad, y, width - pad, y), fill=LINE)
    y += scaled_px(8, scale)
    for label, value in rows:
        draw.text((pad, y), label, font=font_small, fill=FG_TER)
        bbox = draw.textbbox((0, 0), value, font=font_body)
        vw = bbox[2] - bbox[0]
        draw.text((width - pad - vw, y), value, font=font_body, fill=FG)
        y += scaled_px(22, scale)

    if spark_h:
        spark = create_sparkline(
            list(history_values or []),
            width=width - pad * 2,
            height=spark_h,
            bg_rgba=(0, 0, 0, 0),
        )
        img.alpha_composite(spark, (pad, y))
        y += spark_h + gap

    labels = ["复制", "刷新", dashboard_button_label(usage), "设置"]
    keys = ["copy", "refresh", "web", "settings"]
    btn_w = (width - pad * 2 - gap * 3) // 4
    hits: list[HitTarget] = []
    for i, (lab, key) in enumerate(zip(labels, keys)):
        x0 = pad + i * (btn_w + gap)
        box = (x0, y, x0 + btn_w, y + btn_h)
        draw.rounded_rectangle(box, radius=scaled_px(6, scale), fill=BTN, outline=BTN_BORDER)
        tb = draw.textbbox((0, 0), lab, font=font_btn)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text(
            (x0 + (btn_w - tw) / 2, y + (btn_h - th) / 2 - 1),
            lab,
            font=font_btn,
            fill=FG,
        )
        hits.append(HitTarget(key, box))
    return img, hits


_flyout_hwnd = 0
_flyout_hits: list[HitTarget] = []
_flyout_on: dict[str, Callable[[], None]] | None = None
_flyout_bitmap = None
_flyout_proc = None
_flyout_opened = 0.0


def close_status_flyout() -> None:
    import sys

    if sys.platform != "win32":
        return
    import ctypes

    global _flyout_hwnd
    if _flyout_hwnd:
        ctypes.windll.user32.DestroyWindow(_flyout_hwnd)
        _flyout_hwnd = 0


def status_flyout_visible() -> bool:
    return bool(_flyout_hwnd)


def show_status_flyout(
    *,
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None,
    account_label: str = "",
    history_values: list[float] | None = None,
    owner_hwnd: int = 0,
    icon_rect: tuple[int, int, int, int] | None = None,
    on_copy: Callable[[], None] | None = None,
    on_refresh: Callable[[], None] | None = None,
    on_open_spending: Callable[[], None] | None = None,
    on_open_settings: Callable[[], None] | None = None,
) -> None:
    import sys

    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    from dpi_util import current_dpi_scale
    from platform_util import app_log, work_area
    from win_api import (
        HWND_TOPMOST,
        SWP_NOACTIVATE,
        SWP_SHOWWINDOW,
        ULW_ALPHA,
        VK_ESCAPE,
        WM_DESTROY,
        WM_KEYDOWN,
        WM_KILLFOCUS,
        WM_LBUTTONUP,
        WM_TIMER,
        WNDCLASSW,
        WNDPROC,
        WS_EX_LAYERED,
        WS_EX_TOOLWINDOW,
        WS_EX_TOPMOST,
        WS_POPUP,
        AC_SRC_ALPHA,
        AC_SRC_OVER,
        BI_RGB,
        BITMAPINFO,
        BLENDFUNCTION,
        DIB_RGB_COLORS,
        POINT,
        SIZE,
        def_window_proc,
        get_module_handle,
        load_cursor_arrow,
        post_message,
    )
    from win11_style import apply_win11_flyout

    close_status_flyout()
    scale = current_dpi_scale()
    image, hits = compose_flyout_image(
        usage=usage,
        error_message=error_message,
        updated_at=updated_at,
        account_label=account_label,
        history_values=history_values,
        scale=scale,
    )
    global _flyout_hits, _flyout_on, _flyout_proc, _flyout_hwnd, _flyout_opened
    _flyout_hits = hits
    _flyout_on = {
        "copy": on_copy or (lambda: None),
        "refresh": on_refresh or (lambda: None),
        "web": on_open_spending or (lambda: None),
        "settings": on_open_settings or (lambda: None),
    }

    class_name = "CursorTokenFlyout"

    def _proc(hwnd, msg, wparam, lparam):
        if msg == WM_LBUTTONUP:
            x = ctypes.c_short(int(lparam) & 0xFFFF).value
            y = ctypes.c_short((int(lparam) >> 16) & 0xFFFF).value
            for hit in _flyout_hits:
                l, t, r, b = hit.box
                if l <= x <= r and t <= y <= b:
                    cb = (_flyout_on or {}).get(hit.key)
                    close_status_flyout()
                    if cb:
                        cb()
                    return 0
            return 0
        if msg == WM_KEYDOWN and int(wparam) == VK_ESCAPE:
            close_status_flyout()
            return 0
        if msg == WM_KILLFOCUS:
            if time.monotonic() - _flyout_opened < 0.6:
                return 0
            ctypes.windll.user32.SetTimer(hwnd, 1, 160, None)
            return 0
        if msg == WM_TIMER:
            timer_id = int(wparam)
            ctypes.windll.user32.KillTimer(hwnd, timer_id)
            if timer_id == 2:
                close_status_flyout()
                return 0
            fg = int(ctypes.windll.user32.GetForegroundWindow() or 0)
            if fg != hwnd:
                close_status_flyout()
            return 0
        if msg == WM_DESTROY:
            global _flyout_hwnd
            _flyout_hwnd = 0
            return 0
        return def_window_proc(hwnd, msg, wparam, lparam)

    _flyout_proc = WNDPROC(_proc)
    wc = WNDCLASSW()
    wc.lpfnWndProc = _flyout_proc
    wc.hInstance = get_module_handle()
    wc.hCursor = load_cursor_arrow()
    wc.lpszClassName = class_name
    ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))

    hwnd = int(
        ctypes.windll.user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED,
            class_name,
            "CursorToken 状态",
            WS_POPUP,
            0,
            0,
            image.width,
            image.height,
            owner_hwnd or None,
            None,
            get_module_handle(),
            None,
        )
        or 0
    )
    if not hwnd:
        app_log("create flyout window failed")
        return
    _flyout_hwnd = hwnd
    _flyout_opened = time.monotonic()
    _set_layered_image(hwnd, image)
    apply_win11_flyout(hwnd)

    left, top, right, bottom = work_area()
    w, h = image.width, image.height
    if icon_rect:
        cx = (icon_rect[0] + icon_rect[2]) // 2
        px = max(left + 8, min(cx - w // 2, right - w - 8))
        py = icon_rect[1] - h - 12
        if py < top + 8:
            py = icon_rect[3] + 12
    else:
        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        px = max(left + 8, min(int(pt.x) - w // 2, right - w - 8))
        py = bottom - h - 12
    ctypes.windll.user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        int(px),
        int(py),
        w,
        h,
        SWP_SHOWWINDOW,
    )
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    ctypes.windll.user32.SetTimer(hwnd, 2, 25000, None)
    app_log("native status flyout shown")


def _set_layered_image(hwnd: int, image: Image.Image) -> None:
    import ctypes
    from ctypes import wintypes

    from win_api import (
        AC_SRC_ALPHA,
        AC_SRC_OVER,
        BI_RGB,
        BITMAPINFO,
        BLENDFUNCTION,
        DIB_RGB_COLORS,
        POINT,
        SIZE,
        ULW_ALPHA,
        delete_object,
    )

    img = image.convert("RGBA")
    width, height = img.size
    src = img.tobytes()
    premul = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            i = (y * width + x) * 4
            j = ((height - 1 - y) * width + x) * 4
            r, g, b, a = src[i], src[i + 1], src[i + 2], src[i + 3]
            if a != 255:
                r = r * a // 255
                g = g * a // 255
                b = b * a // 255
            premul[j : j + 4] = bytes((b, g, r, a))

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(bmi.bmiHeader)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    hdc_screen = ctypes.windll.user32.GetDC(None)
    dib = ctypes.windll.gdi32.CreateDIBSection(
        hdc_screen,
        ctypes.byref(bmi),
        DIB_RGB_COLORS,
        ctypes.byref(bits),
        None,
        0,
    )
    if bits.value:
        ctypes.memmove(bits, bytes(premul), len(premul))
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)
    old = ctypes.windll.gdi32.SelectObject(hdc_mem, dib)
    blend = BLENDFUNCTION()
    blend.BlendOp = AC_SRC_OVER
    blend.BlendFlags = 0
    blend.SourceConstantAlpha = 255
    blend.AlphaFormat = AC_SRC_ALPHA
    src_pt = POINT(0, 0)
    size = SIZE(width, height)
    dest = POINT()
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    dest.x, dest.y = rect.left, rect.top
    ctypes.windll.user32.UpdateLayeredWindow(
        hwnd,
        hdc_screen,
        ctypes.byref(dest),
        ctypes.byref(size),
        hdc_mem,
        ctypes.byref(src_pt),
        0,
        ctypes.byref(blend),
        ULW_ALPHA,
    )
    ctypes.windll.gdi32.SelectObject(hdc_mem, old)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(None, hdc_screen)
    delete_object(int(dib or 0))
