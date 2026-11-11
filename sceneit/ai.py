# LLM은 API 대신 Claude Code 헤드리스 에이전트(claude -p)로 호출한다. API로 바꿀 땐 ask()만 교체.
# resume에 이전 session_id를 주면 같은 대화를 이어 간다(이미 본 시트를 다시 읽지 않아 빠르고 싸다).
import json
import os
import subprocess


def extract_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no json in response")
    return json.loads(text[i : j + 1])


def ask(prompt, cwd, model, tries=3, resume=None):
    cmd = [os.environ.get("SCENEIT_CLAUDE", "claude"), "-p", prompt, "--model", model, "--allowedTools", "Read", "--output-format", "json"]
    if resume:
        cmd += ["--resume", resume]
    last = None
    for _ in range(tries):
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        try:
            meta = json.loads(r.stdout)
            data = extract_json(meta.get("result", ""))
            return data, {
                "cost": meta.get("total_cost_usd", 0),
                "seconds": meta.get("duration_ms", 0) / 1000,
                "session": meta.get("session_id"),
            }
        except (ValueError, json.JSONDecodeError) as e:
            last = r.stdout[-500:] or r.stderr[-500:] or str(e)
    raise RuntimeError(f"claude failed: {last}")
