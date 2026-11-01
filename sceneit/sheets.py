import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LABEL = 30


def make_sheets(videos, out, width=360, per=4, pad916=False):
    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    font = ImageFont.load_default(size=22)
    index = []
    for vi, video in enumerate(videos):
        tmp = out / f"_f{vi}"
        tmp.mkdir()
        vf = "fps=2"
        if pad916:
            vf += ",pad=w=max(iw\\,ceil(ih*9/16/2)*2):h=max(ih\\,ceil(iw*16/9/2)*2):x=(ow-iw)/2:y=(oh-ih)/2:color=black"
        vf += f",scale={width}:-2"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf, "-q:v", "3", str(tmp / "%05d.jpg")], check=True)
        frames = sorted(tmp.iterdir())
        times = [i * 0.5 for i in range(len(frames))]
        for s in range(0, len(frames), per):
            chunk = frames[s : s + per]
            ims = [Image.open(p).convert("RGB") for p in chunk]
            ch = ims[0].height
            sheet = Image.new("RGB", (width * per, ch + LABEL), "white")
            d = ImageDraw.Draw(sheet)
            for k, im in enumerate(ims):
                sheet.paste(im, (k * width, LABEL))
                d.text((k * width + 6, 3), f"v{vi}  {times[s + k]:.1f}s", fill="black", font=font)
                if k:
                    d.line([(k * width, 0), (k * width, ch + LABEL)], fill="white", width=3)
            name = f"v{vi}_{s // per:03d}.jpg"
            sheet.save(out / name, quality=85)
            index.append({"file": name, "video": vi, "t_from": times[s], "t_to": times[s + len(chunk) - 1]})
        shutil.rmtree(tmp)
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    return index


def describe(index):
    parts = []
    for vi in sorted({x["video"] for x in index}):
        files = [x["file"] for x in index if x["video"] == vi]
        end = max(x["t_to"] for x in index if x["video"] == vi)
        parts.append(f"- 영상 {vi}: {files[0]} ~ {files[-1]} ({len(files)}장, 약 {end:.1f}초)")
    return "\n".join(parts)
