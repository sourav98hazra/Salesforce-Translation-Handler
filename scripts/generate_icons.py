#!/usr/bin/env python3
"""Generate multi-resolution .ico and .png icon files from logo.svg.

This script converts the project SVG logo into:
  - src/stx/gui/assets/logo.ico  (multi-resolution: 16, 32, 48, 64, 128, 256 px)
  - src/stx/gui/assets/logo.png  (256x256 for Linux .desktop use)

Requirements:
  pip install cairosvg Pillow

Usage:
  python scripts/generate_icons.py
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "src" / "stx" / "gui" / "assets" / "logo.svg"
ICO_PATH = ROOT / "src" / "stx" / "gui" / "assets" / "logo.ico"
PNG_PATH = ROOT / "src" / "stx" / "gui" / "assets" / "logo.png"

SIZES = [16, 32, 48, 64, 128, 256]


def main() -> int:
    try:
        import cairosvg  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "Error: cairosvg is not installed.\n"
            "Install it with:  pip install cairosvg\n"
        )
        return 1

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "Error: Pillow is not installed.\n"
            "Install it with:  pip install Pillow\n"
        )
        return 1

    if not SVG_PATH.exists():
        sys.stderr.write(f"Error: SVG source not found at {SVG_PATH}\n")
        return 1

    svg_data = SVG_PATH.read_bytes()

    # Render SVG at each resolution
    images: list[Image.Image] = []
    for size in SIZES:
        png_data = cairosvg.svg2png(
            bytestring=svg_data,
            output_width=size,
            output_height=size,
        )
        img = Image.open(BytesIO(png_data)).convert("RGBA")
        images.append(img)

    # Save the 256x256 as standalone PNG (for Linux .desktop)
    images[-1].save(PNG_PATH, format="PNG")
    print(f"Created: {PNG_PATH} (256x256)")

    # Save multi-resolution ICO (Windows icon)
    # PIL's ICO save accepts a list of sizes via the 'sizes' parameter
    # but the most reliable way is to save the largest and append the rest
    images[-1].save(
        ICO_PATH,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[:-1],
    )
    print(f"Created: {ICO_PATH} (sizes: {SIZES})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
