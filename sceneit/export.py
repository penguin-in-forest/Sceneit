import json
import math
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


def project_id(name):
    pid = re.sub(r"[^A-Za-z0-9-]+", "-", name).strip("-")
    return f"{pid[:80] or 'project'}-{uuid4().hex}"


def normalize_subs(subs, duration):
    if not isinstance(subs, list):
        raise ValueError("자막 목록(subs)이 없습니다")
    normalized = []
    for i, s in enumerate(subs, 1):
        if not isinstance(s, dict) or not isinstance(s.get("text"), str):
            raise ValueError(f"자막 {i}번의 문구가 올바르지 않습니다")
        try:
            t0, t1 = float(s["t0"]), float(s["t1"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError(f"자막 {i}번의 시간 형식이 올바르지 않습니다") from None
        start, end = max(0.0, t0), min(duration, t1)
        if not (math.isfinite(t0) and math.isfinite(t1) and start < end):
            raise ValueError(f"자막 {i}번의 시간이 영상 범위를 벗어났습니다")
        normalized.append({**s, "t0": start, "t1": end})
    return normalized


BOXES = ("none", "black", "yellow", "white")  # studio/src/SubClip.tsx 의 BOX_KEYS 와 같아야 한다
STYLE_TEXT = {
    "font": "jua", "enter": "fadeInUp", "emph": "none", "exit": "none",
    "fill": "#ffffff", "stroke": "#1b1b1b", "hi": "#ffd23f",
}
STYLE_NUMBERS = {"speed": (1, 0.3, 3), "y": (0.8, 0, 1), "size": (1, 0.4, 3)}


def sub_line(i, s, frames):
    text = s["text"]
    label = f"{i + 1} " + re.sub(r"\[\[|\]\]", "", text).replace("\n", " ")[:16]
    start = min(frames - 1, round(s["t0"] * 30))
    end = min(frames, max(start + 1, round(s["t1"] * 30)))
    attrs = {"name": label, "from": start, "durationInFrames": end - start, "text": text}
    for key, default in STYLE_TEXT.items():
        value = s.get(key)
        attrs[key] = value if isinstance(value, str) else default
    for key, (default, minimum, maximum) in STYLE_NUMBERS.items():
        try:
            value = float(s.get(key, default))
        except (TypeError, ValueError, OverflowError):
            value = default
        attrs[key] = value if minimum <= value <= maximum else default
    attrs["box"] = s["box"] if s.get("box") in BOXES else "none"
    props = " ".join(f"{key}={{{json.dumps(value, ensure_ascii=False)}}}" for key, value in attrs.items())
    return f"    <Sub {props} />"


def write_project(studio, pid, video, subs, layout, aspect, duration, frame="blur"):
    studio = Path(studio)
    frames = max(1, round(duration * 30))
    subs = normalize_subs(subs, duration)
    body = "\n".join(sub_line(i, s, frames) for i, s in enumerate(subs))
    media = studio / "public" / "media"
    media.mkdir(parents=True, exist_ok=True)
    tsx = f'''import React from "react";
import {{ AbsoluteFill }} from "remotion";
import {{ Frame }} from "../Frame";
import {{ Sub }} from "../SubClip";

export const meta = {{ id: "{pid}", frames: {frames} }};

export const Component: React.FC = () => (
  <AbsoluteFill>
    <Frame src="media/{pid}.mp4" layout="{layout}" aspect={{{aspect:.4f}}} bg="{"black" if frame == "black" else "blur"}" />
{body}
  </AbsoluteFill>
);
'''
    with TemporaryDirectory(dir=studio, prefix=".preview-") as temp:
        temp = Path(temp)
        (temp / "project.tsx").write_text(tsx, encoding="utf-8")
        shutil.copyfile(video, temp / "video.mp4")
        (temp / "video.mp4").replace(media / f"{pid}.mp4")
        (temp / "project.tsx").replace(studio / "src" / "projects" / f"{pid}.tsx")
    return subs
