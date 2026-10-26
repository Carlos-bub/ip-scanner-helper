"""Rasterize the application's geometric network mark for Windows and Tk.

The mark is defined by three outlined nodes and their connecting lines, not fonts.
No external fonts, image library or network access is required.
"""

from pathlib import Path
import struct
import zlib

ASSETS = Path(__file__).resolve().parents[1] / "ui" / "assets"
BACKGROUND = (36, 49, 47)
FOREGROUND = (235, 241, 230)


def inside_mark(x, y):
    for cx, cy in ((16, 7), (7, 25), (25, 25)):
        if abs(x - cx) <= 3.8 and abs(y - cy) <= 3.8:
            return abs(x - cx) >= 2.25 or abs(y - cy) >= 2.25
    return ((abs(x - 16) <= .8 and 10.8 <= y <= 17)
            or (7 <= x <= 25 and abs(y - 17) <= .8)
            or ((abs(x - 7) <= .8 or abs(x - 25) <= .8) and 17 <= y <= 21.2))


def png(size):
    pixels = bytearray()
    for row in range(size):
        pixels.append(0)
        for column in range(size):
            coverage = sum(inside_mark((column + dx / 2 + .25) * 32 / size,
                                      (row + dy / 2 + .25) * 32 / size)
                           for dx in range(2) for dy in range(2)) / 4
            pixels.extend(round(a * (1 - coverage) + b * coverage) for a, b in zip(BACKGROUND, FOREGROUND))
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def main():
    ASSETS.mkdir(exist_ok=True)
    sizes = (16, 32, 48, 256)
    images = [png(size) for size in sizes]
    offset = 6 + len(sizes) * 16
    entries = []
    for size, data in zip(sizes, images):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 24, len(data), offset))
        offset += len(data)
    (ASSETS / "app.ico").write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries + images))
    (ASSETS / "app.png").write_bytes(images[1])
    print("Ícones geométricos gerados em ui/assets.")


if __name__ == "__main__":
    main()
