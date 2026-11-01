import json
import os
import subprocess


def extract_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no json in response")
    return json.loads(text[i : j + 1])


def ask(prompt, cwd, model, tries=3):
    cmd = [os.environ.get("SCENEIT_CLAUDE", "claude"), "-p", prompt, "--model", model, "--allowedTools", "Read", "--output-format", "json"]
    last = None
    for _ in range(tries):
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        try:
            meta = json.loads(r.stdout)
            data = extract_json(meta.get("result", ""))
            return data, {"cost": meta.get("total_cost_usd", 0), "seconds": meta.get("duration_ms", 0) / 1000}
        except (ValueError, json.JSONDecodeError) as e:
            last = r.stdout[-500:] or r.stderr[-500:] or str(e)
    raise RuntimeError(f"claude failed: {last}")
