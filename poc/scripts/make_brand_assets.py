"""Build the JobsHub brand images from the aavartlabs logo. Run once when the logo changes:

    python3 scripts/make_brand_assets.py ~/Downloads/aavartlabs_logo.png

Needs Pillow (the system python3 has it; the app's venv deliberately doesn't). The source
file is a JPEG (despite .png) on an off-white background: the A-arrow mark is cropped from
above the wordmark, its background made transparent, and exported as the header mark,
favicons and an Apple touch icon (on the plum header colour, since iOS shows no alpha).
Outputs land in jobhub_poc/webapp/static/brand/ and are committed.
"""
import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "jobhub_poc" / "webapp" / "static" / "brand"
PLUM = (42, 18, 56)  # --header in style.css (#2A1238)


def transparent_mark(path):
    image = Image.open(path).convert("RGB")
    pixels = image.load()
    background = pixels[5, 5]

    def distance(p):
        return sum(abs(a - b) for a, b in zip(p, background))

    width, height = image.size
    # The mark is the first block of ink from the top; it ends at the first blank row,
    # which separates it from the wordmark underneath.
    ink, seen_ink = [], False
    for y in range(height):
        row = [(x, y) for x in range(width) if distance(pixels[x, y]) > 40]
        if row:
            ink.extend(row)
            seen_ink = True
        elif seen_ink:
            break
    xs, ys = [p[0] for p in ink], [p[1] for p in ink]
    mark = image.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1)).convert("RGBA")

    data = mark.load()
    for y in range(mark.size[1]):
        for x in range(mark.size[0]):
            r, g, b, _ = data[x, y]
            d = distance((r, g, b))
            # Hard cut-off near the background, a soft ramp over the anti-aliased edge.
            alpha = 0 if d < 25 else 255 if d >= 70 else int(255 * (d - 25) / 45)
            data[x, y] = (r, g, b, alpha)
    return mark


def fit(mark, size, background=None):
    canvas = Image.new("RGBA", (size, size), background + (255,) if background else (0, 0, 0, 0))
    scaled = mark.copy()
    padding = size // 8 if background else 0
    scaled.thumbnail((size - 2 * padding, size - 2 * padding), Image.LANCZOS)
    canvas.paste(scaled, ((size - scaled.size[0]) // 2, (size - scaled.size[1]) // 2), scaled)
    return canvas


def main(source):
    OUT.mkdir(parents=True, exist_ok=True)
    mark = transparent_mark(source)
    for height in (64, 128):
        scaled = mark.copy()
        scaled.thumbnail((height, height), Image.LANCZOS)
        scaled.save(OUT / f"mark-{height}.png", optimize=True)
    fit(mark, 32).save(OUT / "favicon-32.png", optimize=True)
    fit(mark, 48).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    fit(mark, 180, background=PLUM).convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)
    for f in sorted(OUT.iterdir()):
        print(f"{f.name}: {f.stat().st_size} bytes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "Downloads" / "aavartlabs_logo.png")
