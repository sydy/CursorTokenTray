"""从 app_icon.svg 生成多尺寸 PNG/ICO。

图标：Iconify material-symbols-light:token-outline-rounded（提案 B，边距 10%）。
小尺寸用超采样再缩小，保证任务栏可读。

需要: pip install pymupdf pillow
"""
from __future__ import annotations

import argparse
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent
SVG = ASSETS / "app_icon.svg"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256, 512)
# Win32 PE / Explorer: BMP DIB for small sizes, PNG only for 256 (Vista+).
# All-PNG ICO looks fine in PyInstaller but the resource compiler leaves the
# exe with a generic file icon.
ICO_BMP_SIZES = (16, 24, 32, 48, 64)
ICO_PNG_SIZES = (256,)
ICO_SIZES = ICO_BMP_SIZES + ICO_PNG_SIZES


def render_svg(size: int) -> Image.Image:
    import fitz

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


def _bmp_dib(im: Image.Image) -> bytes:
    """32-bit BGRA XOR + 1-bit AND mask, the format rc.exe / Explorer expect."""
    im = im.convert("RGBA")
    width, height = im.size
    pixels = im.load()
    xor = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            xor.extend((blue, green, red, alpha))
    mask_row = ((width + 31) // 32) * 4
    mask = bytearray()
    for y in range(height - 1, -1, -1):
        row = bytearray(mask_row)
        for x in range(width):
            if pixels[x, y][3] == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        mask.extend(row)
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height * 2,
        1,
        32,
        0,
        len(xor) + len(mask),
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor) + bytes(mask)


def save_ico(path: Path, images: list[Image.Image]) -> None:
    """手写 ICO：<256 用 BMP DIB，256 用 PNG，避免 Win32 资源编译丢掉文件图标。"""
    images = sorted(images, key=lambda im: im.width)
    entries: list[bytes] = []
    for im in images:
        if im.width >= 256:
            entries.append(_png_bytes(im))
        else:
            entries.append(_bmp_dib(im))
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


def rebuild_from_pngs() -> None:
    images: list[Image.Image] = []
    for size in ICO_SIZES:
        path = ASSETS / f"app_icon_{size}.png"
        images.append(Image.open(path).convert("RGBA"))
    save_ico(ASSETS / "app_icon.ico", images)
    _print_ico_summary()


def _print_ico_summary() -> None:
    raw = (ASSETS / "app_icon.ico").read_bytes()
    count = struct.unpack_from("<H", raw, 4)[0]
    sizes = []
    kinds = []
    for i in range(count):
        w, h = raw[6 + i * 16], raw[7 + i * 16]
        size, offset = struct.unpack_from("<II", raw, 6 + i * 16 + 8)
        blob = raw[offset : offset + size]
        kind = "PNG" if blob[:8] == b"\x89PNG\r\n\x1a\n" else "BMP"
        sizes.append((256 if w == 0 else w, 256 if h == 0 else h))
        kinds.append(kind)
    print("generated", ASSETS / "app_icon.ico")
    print("entries=", count, "sizes=", sizes, "kinds=", kinds)
    print("file_bytes=", len(raw))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-png", action="store_true", help="rebuild ICO from existing PNG sizes")
    args = parser.parse_args()
    if args.from_png:
        rebuild_from_pngs()
        return

    rendered: dict[int, Image.Image] = {}
    for s in SIZES:
        im = render_size(s)
        rendered[s] = im
        im.save(ASSETS / f"app_icon_{s}.png")

    rendered[512].save(ASSETS / "app_icon.png")
    save_ico(ASSETS / "app_icon.ico", [rendered[s] for s in ICO_SIZES])
    _print_ico_summary()


if __name__ == "__main__":
    main()
