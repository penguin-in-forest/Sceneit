"""내장 프리셋: 말투(style) + 규칙(rules) + 기본값 + 자동 검사.

roblox_ko / roblox_en 은 2026-11 인스타 로블록스 릴스 조사(~/roblox-reels) 결과다.
검사에 걸리면 문제 목록을 붙여 Claude에게 한 번 다시 만들게 하고, 문제가 더 적은 쪽을 쓴다.
"""
import json
from pathlib import Path

from . import ai
from .checks import check_cuts, check_subs, close_gaps
from .cut import clamp
from .export import normalize_subs
from .scenes import scene_changes

DIR = Path(__file__).resolve().parent / "presets"
MAX_LISTED = 300


def names():
    return sorted(p.name for p in DIR.iterdir() if (p / "preset.json").exists())


def load(name):
    if not name:
        return {}
    d = DIR / name
    if not (d / "preset.json").exists():
        raise SystemExit(f"프리셋 없음: {name} (있는 것: {', '.join(names())})")
    meta = json.loads((d / "preset.json").read_text(encoding="utf-8"))
    return {**meta, "name": name, "style": str(d / "style.md"), "rules": str(d / "rules.md")}


def feedback(problems, previous=None):
    text = "[자동 검사 결과] 방금 출력이 아래 규칙을 어겼습니다. 고쳐서 같은 형식의 JSON 전체를 다시 출력하세요.\n" + "\n".join(f"- {p}" for p in problems)
    if previous is not None:
        shown = {k: v for k, v in previous.items() if k != "checks"}
        text += "\n[방금 출력]\n```json\n" + json.dumps(shown, ensure_ascii=False) + "\n```"
    return text


def retry_ask(cfg, problems, previous, meta, prompt, d):
    """검사에 걸렸을 때 한 번 더 묻는다. 같은 대화를 이어 갈 수 있으면 문제 목록만 보내고(시트를 다시 읽지 않음),
    아니면 처음 프롬프트에 붙여 새로 묻는다. 실패하면 (None, 원래 meta)."""
    sess = meta.get("session")
    try:
        if sess:
            data, m2 = ai.ask(feedback(problems), d, cfg["model"], resume=sess)
        else:
            data, m2 = ai.ask(prompt + "\n\n" + feedback(problems, previous), d, cfg["model"])
    except RuntimeError as e:
        print(f"  다시 만들기 실패, 처음 결과를 씁니다: {e}")
        return None, meta
    if not sess or m2.get("session") != sess:
        # 새 대화면 비용이 누적되지 않으니 직접 더한다(같은 대화를 이어 가면 claude -p가 누적 비용을 준다)
        m2 = {**m2, "cost": round(meta.get("cost", 0) + m2.get("cost", 0), 6)}
    return data, m2


def load_scenes(w):
    p = Path(w) / "scenes.json"
    return {int(k): v for k, v in json.loads(p.read_text()).items()} if p.exists() else {}


def after_prep(cfg, w):
    """장면 전환 리듬을 쓰는 설정이면 원본의 장면 전환 시각을 재서 scenes.json과 plan/scenes.txt로 남긴다."""
    if cfg.get("cut") != "rhythm" and not cfg.get("checks", {}).get("rhythm"):
        return
    w = Path(w)
    scenes = {i: scene_changes(v) for i, v in enumerate(cfg["videos"])}
    (w / "scenes.json").write_text(json.dumps(scenes))
    lines = ["원본 안에서 화면이 크게 바뀌는 시각(초)입니다. 컷 경계와 똑같이 장면 전환으로 셉니다."]
    for i, ts in scenes.items():
        shown = ", ".join(f"{t:.1f}" for t in ts[:MAX_LISTED]) or "없음"
        lines.append(f"- v{i} ({len(ts)}개): {shown}" + (" …" if len(ts) > MAX_LISTED else ""))
    (w / "plan" / "scenes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("원본 장면 전환: " + ", ".join(f"v{i} {len(ts)}개" for i, ts in scenes.items()))


def after_plan(cfg, plan, meta, prompt, d, durations):
    """1단계 결과(컷 목록) 검사. 돌려주는 meta는 다시 물었으면 그 호출의 것(비용·대화 id 포함)."""
    rules = cfg.get("checks") or {}
    if not rules:
        return plan, meta
    scenes = load_scenes(Path(d).parent)
    problems, m = check_cuts(plan["cuts"], scenes, cfg["length"], rules)
    retried = False
    if problems:
        print("  검사에 걸림: " + " / ".join(problems))
        retry, meta = retry_ask(cfg, problems, plan, meta, prompt, d)
        retry = retry or {}
        cuts = clamp(retry.get("cuts"), durations)
        retried = True
        if cuts:
            p2, m2 = check_cuts(cuts, scenes, cfg["length"], rules)
            if len(p2) <= len(problems):
                plan, problems, m = {**retry, "cuts": cuts}, p2, m2
    plan["checks"] = {"metrics": m, "problems": problems, "retried": retried}
    line = f"  검사: 길이 {m['total']:.1f}초"
    if rules.get("rhythm"):
        line += f", 장면 전환 {m['transitions']}번(10초당 {m['per10s']}), 가장 긴 무전환 {m['longest'][1] - m['longest'][0]:.1f}초"
    print(line + (" — 통과" if not problems else f" — 남은 문제 {len(problems)}개"))
    return plan, meta


def after_subs(cfg, subs, meta, prompt, d):
    """2단계 결과(자막) 검사와 설명란 저장. 돌려주는 meta는 다시 물었으면 그 호출의 것."""
    rules = cfg.get("checks") or {}
    duration = cfg["cut_info"]["duration"]
    if rules.get("subs") or rules.get("title_check"):
        limit = (rules.get("subs") or {}).get("close_gap", 1.0)
        if rules.get("subs"):
            close_gaps(subs.get("subs", []), duration, limit)
        problems, m = check_subs(subs, duration, rules)
        retried = False
        if problems:
            print("  검사에 걸림: " + " / ".join(problems))
            retry, meta = retry_ask(cfg, problems, subs, meta, prompt, d)
            retry = retry or {}
            retried = True
            try:
                retry["subs"] = normalize_subs(retry.get("subs"), duration)
            except ValueError:
                retry["subs"] = []
            if retry["subs"]:
                if rules.get("subs"):
                    close_gaps(retry["subs"], duration, limit)
                p2, m2 = check_subs(retry, duration, rules)
                if len(p2) <= len(problems):
                    subs, problems, m = retry, p2, m2
        subs["checks"] = {"metrics": m, "problems": problems, "retried": retried}
        line = "  검사:"
        if "coverage" in m:
            line += f" 본문 자막 {m['coverage']:.0%}, 3초 넘는 빈 구간 {len(m['holes'])}개"
        elif subs.get("showcase"):
            line += " 쇼케이스라 자막 비율 검사는 건너뜀"
        print(line + (" — 통과" if not problems else f" — 남은 문제 {len(problems)}개: " + " / ".join(problems)))
    caption = str(subs.get("caption") or "").strip()
    if caption:
        (Path(d).parent / "caption.txt").write_text(caption + "\n", encoding="utf-8")
        print("  설명란: " + caption.replace("\n", " / "))
    return subs, meta
