"""从 app_icon.svg 生成多尺寸 PNG/ICO。

图标：Iconify material-symbols-light:token-outline-rounded（提案 B，边距 10%）。
小尺寸用超采样再缩小，保证任务栏可读。

需要: pip install pymupdf pillow
"""
from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image

ASSETS = Path(__file__).resolve().parent
SVG = ASSETS / "app_icon.svg"
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


def render_size(size: int) -> Image.Image:
    """<=48 超采样 4x 再缩小，减轻细线锯齿。"""
    if size <= 48:
        hi = render_svg(size * 4)
        return hi.resize((size, size), Image.Resampling.LANCZOS)
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
