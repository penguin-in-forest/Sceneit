import functools
import math
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from .media import probe

# HDR → SDR 톤매핑. 결과는 항상 8비트 yuv420p + bt709 (브라우저에서 재생되는 형식).
HDR_TO_SDR = "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv"
SDR_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]


@functools.cache
def has_hdr_filters():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return " zscale " in out and " tonemap " in out


def ensure_hdr_support(infos):
    if any(info["hdr"] for info in infos) and not has_hdr_filters():
        raise RuntimeError("HDR 영상을 처리하려면 zscale 및 tonemap 필터가 있는 FFmpeg가 필요합니다. 해당 FFmpeg를 설치하거나 SDR 영상으로 다시 시도하세요.")


def target_size(info, layout):
    if layout == "cover":
        return 1080, 1920
    h = round(1080 * info["height"] / info["width"] / 2) * 2
    return 1080, min(h, 1920)


def clamp(cuts, durations):
    if not isinstance(cuts, list):
        return []
    fixed = []
    for c in cuts:
        if not isinstance(c, dict):
            continue
        try:
            source = c.get("src", 0)
            src = int(source)
            t0, t1 = float(c["t0"]), float(c["t1"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if isinstance(source, bool) or (isinstance(source, float) and source != src):
            continue
        if not (0 <= src < len(durations) and math.isfinite(t0) and math.isfinite(t1)):
            continue
        start, end = max(0.0, t0), min(durations[src], t1)
        length = end - start
        if length >= 0.2 or math.isclose(length, 0.2):
            fixed.append({**c, "src": src, "t0": start, "t1": end})
    return fixed


def render_cut(videos, cuts, out, layout):
    infos = [probe(v) for v in videos]
    cuts = clamp(cuts, [info["duration"] for info in infos])
    if not cuts:
        raise ValueError("원본 영상 범위 안에 편집할 수 있는 컷이 없습니다")
    ensure_hdr_support([infos[c["src"]] for c in cuts])
    w, h = target_size(infos[0], layout)
    if layout == "cover":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,setsar=1"
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1"
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent, prefix=".segments-") as tmp_dir:
        tmp = Path(tmp_dir)
        lines = []
        for i, c in enumerate(cuts):
            src, info = videos[c["src"]], infos[c["src"]]
            length = c["t1"] - c["t0"]
            seg = tmp / f"{i:03d}.mp4"
            cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(c["t0"]), "-t", str(length), "-i", str(src)]
            if not info["audio"]:
                cmd += ["-f", "lavfi", "-t", str(length), "-i", "anullsrc=r=48000:cl=stereo"]
            seg_vf = vf + ("," + HDR_TO_SDR if info["hdr"] else "") + ",format=yuv420p"
            cmd += ["-vf", seg_vf, "-map", "0:v:0", "-map", "0:a:0" if info["audio"] else "1:a:0"]
            cmd += ["-c:v", "libx264", "-crf", "16", "-preset", "medium", *SDR_TAGS, "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(seg)]
            subprocess.run(cmd, check=True)
            lines.append(f"file '{seg.name}'")
        (tmp / "list.txt").write_text("\n".join(lines) + "\n")
        rendered = tmp / "cut.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-c", "copy", str(rendered)], check=True)
        duration = probe(rendered)["duration"]
        rendered.replace(out)
    return {"width": w, "height": h, "duration": duration}
