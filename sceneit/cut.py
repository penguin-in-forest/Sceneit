import shutil
import subprocess
from pathlib import Path

from .media import probe


def target_size(info, layout):
    if layout == "cover":
        return 1080, 1920
    h = round(1080 * info["height"] / info["width"] / 2) * 2
    return 1080, min(h, 1920)


def clamp(cuts, durations):
    fixed = []
    for c in cuts:
        src = int(c.get("src", 0))
        dur = durations[src]
        t0, t1 = float(c["t0"]), float(c["t1"])
        if t1 > dur:
            length = t1 - t0
            t1 = dur
            t0 = max(0.0, dur - length)
        if t1 - t0 >= 0.2:
            fixed.append({**c, "src": src, "t0": round(t0, 2), "t1": round(t1, 2)})
    return fixed


def render_cut(videos, cuts, out, layout):
    infos = [probe(v) for v in videos]
    w, h = target_size(infos[0], layout)
    if layout == "cover":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,setsar=1"
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1"
    out = Path(out)
    tmp = out.parent / "_segments"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    lines = []
    for i, c in enumerate(cuts):
        src = videos[c["src"]]
        length = c["t1"] - c["t0"]
        seg = tmp / f"{i:03d}.mp4"
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(c["t0"]), "-t", str(length), "-i", str(src)]
        if not infos[c["src"]]["audio"]:
            cmd += ["-f", "lavfi", "-t", str(length), "-i", "anullsrc=r=48000:cl=stereo"]
        cmd += ["-vf", vf, "-map", "0:v:0", "-map", "0:a:0" if infos[c["src"]]["audio"] else "1:a:0"]
        cmd += ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(seg)]
        subprocess.run(cmd, check=True)
        lines.append(f"file '{seg.name}'")
    (tmp / "list.txt").write_text("\n".join(lines) + "\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-c", "copy", str(out.resolve())], check=True, cwd=tmp)
    shutil.rmtree(tmp)
    return {"width": w, "height": h, "duration": probe(out)["duration"]}
