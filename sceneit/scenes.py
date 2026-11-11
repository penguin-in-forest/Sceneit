import re
import subprocess


def scene_changes(path, thr=0.35):
    """원본 안에서 화면이 크게 바뀌는 시각(초). 2026-11 로블록스 릴스 조사와 같은 설정(192px 축소, scene > 0.35)."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf", f"scale=192:-2,select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    return [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
