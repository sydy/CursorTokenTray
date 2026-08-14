"""从 app_icon.svg 生成多尺寸 PNG/ICO（小尺寸单独加粗绘制）。

需要: pip install pymupdf pillow
"""
from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent
SVG = ASSETS / "app_icon.svg"
BG = (28, 28, 28, 255)
FG = (255, 255, 255, 255)
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_svg(size: int) -> Image.Image:
    doc = fitz.open(SVG)
    page = doc[0]
    zoom = size / max(page.rect.width, page.rect.height, 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
    img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    doc.close()
    if img.size == (size, size):
        return img
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas


def render_pixel(size: int) -> Image.Image:
    """<=32 用几何手绘，保证任务栏像素清晰。"""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = max(1, round(size * 0.06))
    radius = max(2, round(size * 0.22))
    d.rounded_rectangle((pad, pad, size - 1 - pad, size - 1 - pad), radius=radius, fill=BG)

    x0, y0 = pad + 1, pad + 1
    x1, y1 = size - 2 - pad, size - 2 - pad
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    hw = (x1 - x0) * 0.44
    hh = (y1 - y0) * 0.48
    outer = [
        (cx, cy - hh),
        (cx + hw, cy - hh * 0.5),
        (cx + hw, cy + hh * 0.5),
        (cx, cy + hh),
        (cx - hw, cy + hh * 0.5),
        (cx - hw, cy - hh * 0.5),
    ]

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)

    if size <= 20:
        # 极小尺寸：实心六边形 + 圆洞，轮廓最清晰
        md.polygon(outer, fill=255)
        r_hole = max(1.6, size * 0.14)
        md.ellipse((cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole), fill=0)
    else:
        t = max(1.8, size * 0.11)
        scale = 1.0 - (t / max(hw, hh))
        inner_hex = [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in outer]
        md.polygon(outer, fill=255)
        md.polygon(inner_hex, fill=0)
        r_outer = max(2.2, size * 0.16)
        r_inner = max(1.2, size * 0.08)
        md.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer), fill=255)
        md.ellipse((cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner), fill=0)

    white = Image.new("RGBA", (size, size), FG)
    im.paste(white, (0, 0), mask)
    return im


def render_size(size: int) -> Image.Image:
    if size <= 32:
        return render_pixel(size)
    return render_svg(size)


def _png_bytes(im: Image.Image) -> bytes:
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def save_ico(path: Path, images: list[Image.Image]) -> None:
    """手写 ICO：每个尺寸嵌入 PNG（Vista+），避免 Pillow 丢尺寸。"""
    images = sorted(images, key=lambda im: im.width)
    entries = [_png_bytes(im) for im in images]
    count = len(images)
    # ICONDIR + ICONDIRENTRY * n
    offset = 6 + 16 * count
    header = struct.pack("<HHH", 0, 1, count)
    dir_entries = []
    blobs = []
    for im, data in zip(images, entries):
        w = 0 if im.width >= 256 else im.width
        h = 0 if im.height >= 256 else im.height
        dir_entries.append(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    path.write_bytes(header + b"".join(dir_entries) + b"".join(blobs))


def main() -> None:
    rendered: dict[int, Image.Image] = {}
    for s in SIZES:
        im = render_size(s)
        rendered[s] = im
        im.save(ASSETS / f"app_icon_{s}.png")

    rendered[512].save(ASSETS / "app_icon.png")
    save_ico(ASSETS / "app_icon.ico", [rendered[s] for s in ICO_SIZES])

    raw = (ASSETS / "app_icon.ico").read_bytes()
    count = struct.unpack_from("<H", raw, 4)[0]
    sizes = []
    for i in range(count):
        w, h = raw[6 + i * 16], raw[7 + i * 16]
        sizes.append((256 if w == 0 else w, 256 if h == 0 else h))
    print("generated", ASSETS / "app_icon.ico")
    print("entries=", count, "sizes=", sizes)
    print("file_bytes=", len(raw))


if __name__ == "__main__":
    main()
