#!/usr/bin/env python3
"""Convert an image to ASCII art via a brightness ramp.

Usage: python demo/img2ascii.py PATH [cols] [--invert]
Transparent images are composited onto white first, so a dark subject on a
transparent background (e.g. an OpenMoji black glyph) renders as the dense end
of the ramp.
"""
import sys
from PIL import Image

RAMP = " .:-=+*#%@"


def to_ascii(path: str, cols: int = 42, invert: bool = False) -> str:
    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img.convert("RGBA"))
    g = img.convert("L")
    rows = max(1, int(cols * (g.height / g.width) * 0.50))
    g = g.resize((cols, rows))
    px = g.load()
    ramp = RAMP[::-1] if invert else RAMP
    lines = []
    for y in range(rows):
        lines.append(
            "".join(
                ramp[int((255 - px[x, y]) / 255 * (len(ramp) - 1))] for x in range(cols)
            ).rstrip()
        )
    return "\n".join(lines)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--invert"]
    print(to_ascii(args[0], int(args[1]) if len(args) > 1 else 42, "--invert" in sys.argv))
