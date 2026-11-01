import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"


def main():
    out = ROOT / "public" / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    fonts = json.loads((ROOT / "fonts.json").read_text(encoding="utf-8"))
    failed = []
    for f in fonts:
        dest = out / f["file"]
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = f"{BASE}/{f['dir']}/{urllib.parse.quote(f['file'])}"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                dest.write_bytes(r.read())
            print(f"ok   {f['file']}")
        except Exception as e:
            failed.append(f["file"])
            print(f"fail {f['file']}: {e}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
