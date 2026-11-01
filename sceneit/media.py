import json
import subprocess


def probe(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", path]
    )
    d = json.loads(out)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    return {
        "duration": float(d["format"]["duration"]),
        "width": int(v["width"]),
        "height": int(v["height"]),
        "audio": any(s["codec_type"] == "audio" for s in d["streams"]),
    }
