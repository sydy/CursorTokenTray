"""托盘圆形进度图标（矢量路径 + 超采样抗锯齿）。"""

from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# 固定高分辨率输出，由系统缩放到托盘；内部再 4× 超采样
DEFAULT_SIZE = 256
SUPERSAMPLE = 4


def remaining_color(remaining_percent: float) -> tuple[int, int, int]:
    if remaining_percent > 50:
        return (46, 204, 113)
    if remaining_percent >= 20:
        return (241, 196, 15)
    return (231, 76, 60)


def _macos_menubar() -> bool:
    import sys

    return sys.platform == "darwin"


def _disc_fill() -> tuple[int, int, int, int] | None:
    """Windows 托盘用深色底；macOS 菜单栏深色模式下深色底会隐形，改半透明浅底。"""
    if _macos_menubar():
        return (255, 255, 255, 42)
    return (16, 18, 22, 230)


def _track_color() -> tuple[int, int, int, int]:
    if _macos_menubar():
        return (236, 236, 240, 255)
    return (72, 76, 84, 255)


def menubar_icon_pixels(point_size: float = 22.0, scale: float = 2.0) -> int:
    """菜单栏约 22pt。macOS 至少按 2x 出像素，禁止 22×22 的 1x 位图。"""
    return max(44, int(round(float(point_size) * max(2.0, float(scale)))))


def menubar_icon_rep_sizes(point_size: float = 22.0) -> tuple[int, int]:
    """嵌入 2x / 3x 两套像素，让 2x 和 3x 屏都不用放大 1x 图。"""
    pt = float(point_size)
    return (int(round(pt * 2.0)), int(round(pt * 3.0)))


@lru_cache(maxsize=1)
def tray_icon_size() -> int:
    """尽量用大图，系统缩放到托盘 / 菜单栏时更清晰。"""
    try:
        import sys

        if sys.platform == "darwin":
            return menubar_icon_rep_sizes(22.0)[1]
        import ctypes

        sm = int(ctypes.windll.user32.GetSystemMetrics(49))  # SM_CXSMICON
        return max(256, min(512, sm * 16))
    except Exception:
        return DEFAULT_SIZE


def create_progress_icon(
    remaining_percent: float | None,
    *,
    error: bool = False,
    size: int | None = None,
    mode: str = "ring",
) -> Image.Image:
    mode = (mode or "ring").strip().lower()
    if mode not in ("ring", "number", "dot"):
        mode = "ring"

    if mode == "dot":
        return _create_dot_icon(remaining_percent, error=error, size=size)
    if mode == "number":
        return _create_number_icon(remaining_percent, error=error, size=size)
    return _create_ring_icon(remaining_percent, error=error, size=size)


def create_idle_icon(size: int | None = None, mode: str = "ring") -> Image.Image:
    """启动/等待刷新：灰色占位，不用红色叹号（避免像已失败）。"""
    return create_progress_icon(None, error=False, size=size, mode=mode)


def create_sparkline(
    values: list[float],
    *,
    width: int = 200,
    height: int = 48,
    line_rgb: tuple[int, int, int] = (96, 165, 250),
    fill_rgba: tuple[int, int, int, int] = (59, 130, 246, 55),
    bg_rgba: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Image.Image:
    """迷你折线：values 为剩余百分比序列（旧→新）。"""
    img = Image.new("RGBA", (width, height), bg_rgba)
    if len(values) < 2:
        return img
    draw = ImageDraw.Draw(img)
    lo = min(values)
    hi = max(values)
    span = max(1.0, hi - lo)
    pad_x, pad_y = 2, 4
    usable_w = max(1, width - pad_x * 2)
    usable_h = max(1, height - pad_y * 2)

    pts: list[tuple[float, float]] = []
    n = len(values)
    for i, v in enumerate(values):
        x = pad_x + usable_w * (i / (n - 1))
        y = pad_y + usable_h * (1.0 - (v - lo) / span)
        pts.append((x, y))

    area = [(pad_x, height - pad_y)] + pts + [(pad_x + usable_w, height - pad_y)]
    draw.polygon(area, fill=fill_rgba)
    draw.line(pts, fill=line_rgb + (255,), width=2, joint="curve")
    # 末端圆点
    lx, ly = pts[-1]
    r = 2.5
    draw.ellipse((lx - r, ly - r, lx + r, ly + r), fill=line_rgb + (255,))
    return img


def _create_ring_icon(
    remaining_percent: float | None,
    *,
    error: bool = False,
    size: int | None = None,
) -> Image.Image:
    out = size or tray_icon_size()
    scale = SUPERSAMPLE
    canvas = out * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    inset = max(scale * 1.5, canvas * 0.012)
    cx = cy = canvas / 2.0
    outer_r = (canvas / 2.0) - inset
    ring_w = outer_r * 0.30
    inner_r = max(outer_r - ring_w, outer_r * 0.45)

    bg_r = outer_r - ring_w * 0.08
    disc = _disc_fill()
    if disc is not None:
        draw.ellipse((cx - bg_r, cy - bg_r, cx + bg_r, cy + bg_r), fill=disc)
    if _macos_menubar():
        halo = max(scale * 1.2, outer_r * 0.06)
        _draw_ring(
            draw,
            cx,
            cy,
            inner_r - halo,
            outer_r + halo,
            0.0,
            360.0,
            (20, 20, 22, 90),
        )

    track = _track_color()
    _draw_ring(draw, cx, cy, inner_r, outer_r, 0.0, 360.0, track)

    if error:
        muted = (248, 113, 113, 255)
        _draw_ring(draw, cx, cy, inner_r, outer_r, 0.0, 360.0, muted)
        _draw_center_glyph(draw, cx, cy, inner_r, "!", muted[:3])
        return _downsample(img, out)

    if remaining_percent is None:
        muted = (148, 163, 184, 255)
        _draw_ring(draw, cx, cy, inner_r, outer_r, 0.0, 360.0, muted)
        _draw_center_glyph(draw, cx, cy, inner_r, "–", muted[:3])
        return _downsample(img, out)

    pct = min(100.0, max(0.0, float(remaining_percent)))
    color = remaining_color(pct) + (255,)
    extent = pct / 100.0 * 360.0

    if pct >= 99.95:
        _draw_ring(draw, cx, cy, inner_r, outer_r, 0.0, 360.0, color)
    elif pct > 0.05:
        _draw_ring(draw, cx, cy, inner_r, outer_r, -90.0, -90.0 + extent, color)
        mid_r = (inner_r + outer_r) / 2.0
        cap_r = ring_w / 2.0
        _draw_cap(draw, cx, cy, mid_r, -90.0, cap_r, color)
        _draw_cap(draw, cx, cy, mid_r, -90.0 + extent, cap_r, color)

    label = "100" if pct >= 99.5 else str(int(round(pct)))
    _draw_center_glyph(draw, cx, cy, inner_r, label, color[:3])
    return _downsample(img, out)


def _create_number_icon(
    remaining_percent: float | None,
    *,
    error: bool = False,
    size: int | None = None,
) -> Image.Image:
    out = size or tray_icon_size()
    scale = SUPERSAMPLE
    canvas = out * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    inset = max(scale * 1.5, canvas * 0.012)
    cx = cy = canvas / 2.0
    outer_r = (canvas / 2.0) - inset
    ring_w = outer_r * 0.12
    inner_r = outer_r - ring_w

    disc = _disc_fill()
    if disc is not None:
        draw.ellipse(
            (cx - outer_r * 0.92, cy - outer_r * 0.92, cx + outer_r * 0.92, cy + outer_r * 0.92),
            fill=disc,
        )
    track = _track_color()
    _draw_ring(draw, cx, cy, inner_r, outer_r, 0.0, 360.0, track)

    if error:
        muted = (248, 113, 113)
        _draw_center_glyph(draw, cx, cy, inner_r * 0.95, "!", muted)
        return _downsample(img, out)

    if remaining_percent is None:
        muted = (148, 163, 184)
        _draw_center_glyph(draw, cx, cy, inner_r * 0.95, "–", muted)
        return _downsample(img, out)

    pct = min(100.0, max(0.0, float(remaining_percent)))
    color = remaining_color(pct)
    extent = pct / 100.0 * 360.0
    if pct > 0.05:
        _draw_ring(
            draw,
            cx,
            cy,
            inner_r,
            outer_r,
            -90.0,
            -90.0 + (360.0 if pct >= 99.95 else extent),
            color + (255,),
        )
    label = "100" if pct >= 99.5 else str(int(round(pct)))
    _draw_center_glyph(draw, cx, cy, inner_r * 0.95, label, color)
    return _downsample(img, out)


def _create_dot_icon(
    remaining_percent: float | None,
    *,
    error: bool = False,
    size: int | None = None,
) -> Image.Image:
    out = size or tray_icon_size()
    scale = SUPERSAMPLE
    canvas = out * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = canvas / 2.0
    r = canvas * 0.38

    if error:
        color = (231, 76, 60, 255)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        inner = r * 0.55
        _draw_center_glyph(draw, cx, cy, inner, "!", (255, 255, 255))
        return _downsample(img, out)

    if remaining_percent is None:
        color = (100, 116, 139, 255)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        return _downsample(img, out)

    pct = min(100.0, max(0.0, float(remaining_percent)))
    color = remaining_color(pct) + (255,)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    # 轻微内圈提升立体感
    ir = r * 0.55
    draw.ellipse(
        (cx - ir, cy - ir, cx + ir, cy + ir),
        fill=(255, 255, 255, 40),
    )
    return _downsample(img, out)


def _downsample(img: Image.Image, out: int) -> Image.Image:
    sharp = img.filter(ImageFilter.UnsharpMask(radius=max(1, SUPERSAMPLE // 2), percent=120, threshold=1))
    return sharp.resize((out, out), Image.Resampling.LANCZOS)


def _draw_ring(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    inner_r: float,
    outer_r: float,
    start_deg: float,
    end_deg: float,
    fill: tuple[int, int, int, int],
) -> None:
    sweep = end_deg - start_deg
    if abs(sweep) < 1e-6:
        return
    if abs(abs(sweep) - 360.0) < 1e-3:
        outer = _arc_points(cx, cy, outer_r, 0.0, 360.0, 240)
        inner = _arc_points(cx, cy, inner_r, 360.0, 0.0, 240)
        draw.polygon(outer + inner, fill=fill)
        return

    steps = max(64, int(abs(sweep) * 1.2))
    outer = _arc_points(cx, cy, outer_r, start_deg, end_deg, steps)
    inner = _arc_points(cx, cy, inner_r, end_deg, start_deg, steps)
    draw.polygon(outer + inner, fill=fill)


def _draw_cap(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    mid_r: float,
    angle_deg: float,
    cap_r: float,
    fill: tuple[int, int, int, int],
) -> None:
    rad = math.radians(angle_deg)
    x = cx + mid_r * math.cos(rad)
    y = cy + mid_r * math.sin(rad)
    draw.ellipse((x - cap_r, y - cap_r, x + cap_r, y + cap_r), fill=fill)


def _arc_points(
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
    steps: int,
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        a = math.radians(start_deg + (end_deg - start_deg) * t)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _draw_center_glyph(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    inner_r: float,
    text: str,
    rgb: tuple[int, int, int],
) -> None:
    target = inner_r * 1.72
    font = _fit_font(text, target)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = cx - tw / 2 - bbox[0]
    y = cy - th / 2 - bbox[1] - inner_r * 0.02

    stroke = max(1, int(inner_r * 0.035))
    # 菜单栏深色背景下，深色描边会把数字吃掉；改用浅色描边
    stroke_fill = (255, 255, 255, 230) if _macos_menubar() else (8, 10, 14, 255)
    draw.text(
        (x, y),
        text,
        font=font,
        fill=rgb + (255,),
        stroke_width=stroke if not _macos_menubar() else max(stroke, int(inner_r * 0.06)),
        stroke_fill=stroke_fill,
    )


@lru_cache(maxsize=32)
def _fit_font(text: str, target_px: float):
    paths = (
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "seguisb.ttf",
        "arialbd.ttf",
        "Arial.ttf",
    )
    base = None
    for path in paths:
        try:
            ImageFont.truetype(path, 32)
            base = path
            break
        except OSError:
            continue
    if base is None:
        return ImageFont.load_default()

    probe = ImageDraw.Draw(Image.new("L", (4, 4)))
    lo, hi = 10, max(16, int(target_px * 2.2))
    best = ImageFont.truetype(base, lo)
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(base, mid)
        bbox = probe.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if max(w, h) <= target_px:
            best = font
            lo = mid + 1
        else:
            hi = mid - 1
    return best
