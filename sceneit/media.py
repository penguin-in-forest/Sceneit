import json
import subprocess


def probe(path):
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height,color_transfer:stream_side_data=rotation:stream_tags=rotate",
            "-of", "json", str(path),
        ]
    )
    d = json.loads(out)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    # 폰 세로 영상은 가로로 저장하고 회전값만 붙인다. ffmpeg는 디코딩할 때 돌려 주므로 크기도 맞춰 바꾼다.
    rot = v.get("tags", {}).get("rotate") or next((s["rotation"] for s in v.get("side_data_list", []) if "rotation" in s), 0)
    if round(float(rot)) % 180:
        w, h = h, w
    return {
        "duration": float(d["format"]["duration"]),
        "width": w,
        "height": h,
        "audio": any(s["codec_type"] == "audio" for s in d["streams"]),
        # 아이폰 기본 촬영은 HDR(HLG). 그대로 두면 10비트 H.264가 돼서 브라우저(편집 화면)가 못 튼다.
        "hdr": v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
    }
