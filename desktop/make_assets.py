"""Draw the app icon and the installer artwork (run once; the results are committed).

    uv run python desktop/make_assets.py

Writes desktop/app/build/: icon.png (1024), icon.icns (macOS only), icon.ico,
dmg-background.png (+@2x), installer-sidebar.bmp.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent / "app" / "build"
VIOLET, BLUE, INK = (124, 92, 255), (59, 130, 246), (11, 11, 18)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def gradient(size: tuple[int, int], a, b, diagonal: bool = True) -> Image.Image:
    """Smooth two-colour ramp (top-left to bottom-right, or top to bottom)."""
    n = 96  # drawn small, then scaled up bicubically: no banding, no edge artefacts
    small = Image.new("RGB", (n, n))
    px = small.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * n - 2) if diagonal else y / (n - 1)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return small.resize(size, Image.BICUBIC)


def icon(size: int = 1024) -> Image.Image:
    """A rounded square, violet-to-blue, with a slide (rounded page) and a bold P."""
    tile = gradient((size, size), VIOLET, BLUE)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=int(size * 0.225), fill=255)
    tile = tile.convert("RGBA")
    d = ImageDraw.Draw(tile)
    # the "slide"
    pad = size * 0.2
    d.rounded_rectangle(
        (pad, pad + size * 0.06, size - pad, size - pad - size * 0.02),
        radius=size * 0.07,
        fill=(255, 255, 255, 235),
    )
    f = font(int(size * 0.5))
    box = d.textbbox((0, 0), "P", font=f)
    d.text(
        ((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1] + size * 0.02),
        "P",
        font=f,
        fill=(*INK, 255),
    )
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(tile, (0, 0), mask)
    return out


def dmg_background(w: int = 660, h: int = 420) -> Image.Image:
    scale = 2  # retina-sharp
    img = gradient((w * scale, h * scale), (18, 16, 46), (52, 38, 132)).convert("RGBA")
    d = ImageDraw.Draw(img)
    d.text((w * scale / 2, 46 * scale), "Preza", font=font(30 * scale), fill=(255, 255, 255, 255), anchor="mm")
    d.text(
        (w * scale / 2, 82 * scale),
        "Перетащите Preza в «Программы»",
        font=font(15 * scale),
        fill=(255, 255, 255, 170),
        anchor="mm",
    )
    # arrow between the app and the Applications shortcut
    y = 210 * scale
    x0, x1 = 270 * scale, 390 * scale
    d.line((x0, y, x1, y), fill=(255, 255, 255, 190), width=5 * scale)
    d.polygon([(x1 + 14 * scale, y), (x1 - 6 * scale, y - 14 * scale), (x1 - 6 * scale, y + 14 * scale)], fill=(255, 255, 255, 190))
    return img.resize((w * 2, h * 2), Image.LANCZOS)


def installer_sidebar(w: int = 164, h: int = 314) -> Image.Image:
    img = gradient((w, h), (52, 38, 132), (14, 12, 34), diagonal=False).convert("RGB")
    small = icon(512).resize((96, 96), Image.LANCZOS)
    img.paste(small, ((w - 96) // 2, 46), small)
    d = ImageDraw.Draw(img)
    d.text((w / 2, 170), "Preza", font=font(26), fill=(255, 255, 255), anchor="mm")
    d.text((w / 2, 200), "Цифровой дизайнер", font=font(11), fill=(200, 196, 255), anchor="mm")
    d.text((w / 2, 216), "презентаций", font=font(11), fill=(200, 196, 255), anchor="mm")
    return img


def banner(w: int = 1600, h: int = 560) -> Image.Image:
    """README header."""
    img = gradient((w, h), (20, 16, 58), (74, 52, 190)).convert("RGBA")
    d = ImageDraw.Draw(img)
    mark = icon(512).resize((200, 200), Image.LANCZOS)
    img.paste(mark, (120, (h - 200) // 2 - 20), mark)
    d.text((370, h // 2 - 70), "Preza", font=font(120), fill=(255, 255, 255, 255), anchor="lm")
    d.text((376, h // 2 + 30), "Цифровой дизайнер презентаций", font=font(44), fill=(226, 222, 255, 255), anchor="lm")
    d.text((376, h // 2 + 92), "шаблон + бриф  →  3 варианта  →  аудит  →  .pptx", font=font(30), fill=(190, 184, 255, 255), anchor="lm")
    # a fan of slide silhouettes on the right
    for i, (dx, angle) in enumerate(((-90, -12), (-30, -4), (30, 5))):
        card = Image.new("RGBA", (300, 190), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, 299, 189), radius=18, fill=(255, 255, 255, 235 - i * 30))
        cd.rounded_rectangle((22, 24, 170, 46), radius=6, fill=(*INK, 230))
        cd.rounded_rectangle((22, 62, 240, 74), radius=5, fill=(160, 160, 190, 255))
        cd.rounded_rectangle((22, 84, 210, 96), radius=5, fill=(190, 190, 210, 255))
        cd.rounded_rectangle((190, 120, 276, 170), radius=10, fill=(*VIOLET, 255))
        card = card.resize((216, 137), Image.LANCZOS).rotate(angle, expand=True, resample=Image.BICUBIC)
        img.paste(card, (w - 400 + dx + i * 50, 170 + i * 40), card)
    return img.convert("RGB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    big = icon(1024)
    big.save(OUT / "icon.png")
    big.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    retina = dmg_background()
    retina.save(OUT / "dmg-background@2x.png")
    retina.resize((660, 420), Image.LANCZOS).save(OUT / "dmg-background.png")
    installer_sidebar().save(OUT / "installer-sidebar.bmp")
    docs = OUT.parents[2] / "docs"
    docs.mkdir(exist_ok=True)
    banner().save(docs / "banner.png")
    if platform.system() == "Darwin" and shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for base in (16, 32, 128, 256, 512):
                big.resize((base, base), Image.LANCZOS).save(iconset / f"icon_{base}x{base}.png")
                big.resize((base * 2, base * 2), Image.LANCZOS).save(iconset / f"icon_{base}x{base}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)
    print("assets:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
