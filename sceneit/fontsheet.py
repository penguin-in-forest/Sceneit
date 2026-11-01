import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SAMPLE = "숏폼 자막 미리보기!! 123"


def make_font_sheets(studio, out, per_sheet=18):
    studio, out = Path(studio), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fonts = json.loads((studio / "fonts.json").read_text(encoding="utf-8"))
    label = ImageFont.load_default(size=22)
    cw, ch, cols = 720, 110, 2
    names = []
    for n, s in enumerate(range(0, len(fonts), per_sheet)):
        chunk = fonts[s : s + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        img = Image.new("RGB", (cw * cols, ch * rows), "#2f6db3")
        d = ImageDraw.Draw(img)
        for k, f in enumerate(chunk):
            x, y = (k % cols) * cw, (k // cols) * ch
            if (k // cols) % 2:
                d.rectangle([x, y, x + cw, y + ch], fill="#3a78bd")
            d.text((x + 12, y + 4), f"{f['key']}  ·  {f['family']}", fill="#ffe680", font=label)
            ft = ImageFont.truetype(str(studio / "public" / "fonts" / f["file"]), int(48 * f["scale"]))
            d.text((x + 14, y + 34), SAMPLE, fill="white", font=ft, stroke_width=3, stroke_fill="#111111")
        name = f"fonts_{n + 1}.jpg"
        img.save(out / name, quality=88)
        names.append(name)
    return names
