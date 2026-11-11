import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from . import ai, presets
from .cut import clamp, ensure_hdr_support, render_cut
from .export import normalize_subs, project_id, write_project
from .fontsheet import make_font_sheets
from .media import probe
from .sheets import describe, make_sheets

ROOT = Path(__file__).resolve().parent.parent
PKG = Path(__file__).resolve().parent
STUDIO = ROOT / "studio"
WORK = ROOT / "work"

CUT_RULES = {
    "minimal": "   - **컷 편집은 최소한으로.** 원본을 최대한 길게 이어서 쓰고, 꼭 빼야 하는 부분(흔들림, 의미 없는 구간, 화면이 가려진 구간 등)만 잘라낸다.\n   - 원본 순서를 바꾸지 않는다. 컷 수는 가능한 한 적게.",
    "paced": "   - **모든 컷은 최소 1.5초 이상.** 그보다 짧은 컷은 만들지 않는다. 컷 길이는 1.5~4초 사이에서 장면에 맞게.\n   - 흐름은 전체 → 디테일 → 전체",
    # 로블록스 한국어 릴스 조사: 10~20초마다 장면 전환일 때 조회수가 가장 높았고, 원테이크와 10초에 4번 이상은 낮았다.
    "rhythm": "   - **10~20초마다 한 번 장면이 바뀌게 고른다.** 원본을 통으로 이어 쓰지 말고 하이라이트 구간만 골라 이어 붙인다. 한 컷은 5~20초.\n   - 컷 수는 최소 ⌈목표 길이 ÷ 20초⌉개(30초면 2~3컷). scenes.txt에 적힌 원본 장면 전환 시각도 장면 전환으로 센다.\n   - 10초 안에 장면이 4번 이상 바뀌는 빠른 편집(2.5초보다 짧은 컷 연속)은 하지 않는다.\n   - 원본 순서는 되도록 지킨다.",
    # 로블록스 영어 릴스 관습(약 5초마다 전환). 컷 속도는 조회수와 관계가 없었다.
    "flow": "   - **내용 흐름대로 자른다.** 늘어지는 구간은 버리고, 장면은 보통 3~8초마다 바뀌게 고른다.\n   - 원본 순서는 되도록 지킨다.",
}


def fill(template, **kw):
    text = (PKG / "prompts" / template).read_text(encoding="utf-8")
    for k, v in kw.items():
        text = text.replace(f"<<{k}>>", str(v))
    return text


def load(name):
    p = WORK / name / "project.json"
    if not p.exists():
        sys.exit(f"프로젝트 없음: {name} (먼저 new 또는 all)")
    return json.loads(p.read_text(encoding="utf-8"))


def save(cfg):
    d = WORK / cfg["name"]
    d.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=d) as temp:
        path = Path(temp) / "project.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        path.replace(d / "project.json")


def studio_source(cfg):
    return STUDIO / "src" / "projects" / f"{cfg['id']}.tsx"


def ensure_unique_id(cfg):
    own = (WORK / cfg["name"] / "project.json").resolve()
    for path in WORK.glob("*/project.json"):
        if path.resolve() == own:
            continue
        other = json.loads(path.read_text(encoding="utf-8"))
        if other["id"].casefold() == cfg["id"].casefold():
            raise ValueError(f"'{other['name']}' 프로젝트와 편집 ID가 겹칩니다. 다른 이름으로 새 프로젝트를 만들어 주세요.")


def publish_preview(cfg, subs, stage):
    info = cfg["cut_info"]
    cut = WORK / cfg["name"] / "cut.mp4"
    rev = cfg.get("rev", int(studio_source(cfg).is_file()))
    subs = write_project(STUDIO, cfg["id"], cut, subs, cfg["layout"], info["width"] / info["height"], info["duration"], frame=cfg.get("frame", "blur"))
    cfg.update(stage=stage, rev=rev + 1)
    save(cfg)
    return subs


def copy_texts(cfg, dest):
    shutil.copyfile(cfg["style"], dest / "style.md")
    shutil.copyfile(cfg["rules"], dest / "rules.md")


def cmd_new(a):
    pre = presets.load(getattr(a, "preset", None))  # 직접 준 옵션 > 프리셋 > 기본값
    videos = [str(Path(v).resolve()) for v in a.video]
    infos = [probe(v) for v in videos]
    ensure_hdr_support(infos)
    info = infos[0]
    existing = load(a.name) if (WORK / a.name / "project.json").exists() else None
    if existing and existing["name"] != a.name:
        raise ValueError("같은 이름의 프로젝트가 있어요")
    layout = a.layout
    if layout == "auto":
        layout = "cover" if info["width"] / info["height"] < 0.7 else "fit"
    cut = a.cut or pre.get("cut", "minimal")
    cfg = {
        "name": a.name,
        "id": existing["id"] if existing else project_id(a.name),
        "videos": videos,
        "situation": a.situation,
        "style": str(Path(a.style or pre.get("style") or PKG / "assets" / "style.md").resolve()),
        "rules": str(Path(a.rules or pre.get("rules") or PKG / "assets" / "rules.md").resolve()),
        "cut": cut,
        "layout": layout,
        "frame": pre.get("frame", "blur") if layout == "fit" else "blur",
        "length": a.length or pre.get("length", "15~30"),
        "model": a.model,
        "preset": pre.get("name"),
        "checks": pre.get("checks", {}),
        "cost": {},
        "stage": "cut",
        "rev": existing.get("rev", 0) if existing else 0,
    }
    ensure_unique_id(cfg)
    save(cfg)
    print(f"프로젝트 {a.name}: 영상 {len(videos)}개, 레이아웃 {layout}, 컷 {cut}, 길이 {cfg['length']}초" + (f", 프리셋 {cfg['preset']}" if cfg["preset"] else ""))
    return cfg


def cmd_prep(cfg):
    idx = make_sheets(cfg["videos"], WORK / cfg["name"] / "plan")
    print(f"원본 시트 {len(idx)}장")
    presets.after_prep(cfg, WORK / cfg["name"])


def revise(feedback, current):
    return fill("revise.txt", feedback=feedback, current=current)


def record(cfg, step, meta, resumed=False):
    # claude -p는 --resume 하면 대화 전체 누적 비용을 준다. 이번 호출 비용은 이전 누적값을 빼서 구한다.
    prev = cfg["cost"].get(step, {})
    meta["total"] = meta["cost"]
    if resumed and prev.get("session") == meta["session"]:
        meta["cost"] = round(max(0.0, meta["total"] - prev.get("total", prev.get("cost", 0))), 6)
    cfg["cost"][step] = meta
    cfg.setdefault("session", {})[step] = meta["session"]
    cfg["spent"] = round(cfg.get("spent", 0) + meta["cost"], 4)


def plan_now(cfg):
    p = WORK / cfg["name"] / "plan.json"
    return f"```json\n{p.read_text(encoding='utf-8')}\n```" if p.exists() else "(아직 없음)"


def cmd_plan(cfg, feedback=None):
    infos = [probe(v) for v in cfg["videos"]]
    ensure_hdr_support(infos)
    durations = [info["duration"] for info in infos]
    d = WORK / cfg["name"] / "plan"
    sess = cfg.get("session", {}).get("plan") if feedback else None
    if sess:
        prompt = revise(feedback, plan_now(cfg))
    else:
        idx = json.loads((d / "index.json").read_text())
        copy_texts(cfg, d)
        prompt = fill("plan.txt", situation=cfg["situation"], sheets=describe(idx), length=cfg["length"], cut_rule=CUT_RULES[cfg["cut"]])
        if feedback:
            prompt += "\n\n" + revise(feedback, plan_now(cfg))
    (d / ("prompt_revise.txt" if feedback else "prompt.txt")).write_text(prompt, encoding="utf-8")
    plan, meta = ai.ask(prompt, d, cfg["model"], resume=sess)
    plan["cuts"] = clamp(plan.get("cuts"), durations)
    if not plan["cuts"]:
        raise RuntimeError("Claude가 고른 컷 중 원본 범위 안에 편집할 수 있는 구간이 없습니다")
    plan, meta = presets.after_plan(cfg, plan, meta, prompt, d, durations)
    (WORK / cfg["name"] / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    record(cfg, "plan", meta, resumed=bool(sess))
    save(cfg)
    total = sum(c["t1"] - c["t0"] for c in plan["cuts"])
    print(f"1단계: 컷 {len(plan['cuts'])}개, {total:.1f}초, ${meta['cost']:.3f}, {meta['seconds']:.0f}초 걸림")
    for c in plan["cuts"]:
        print(f"  v{c['src']} {c['t0']:>6.1f}~{c['t1']:>6.1f}  {c.get('scene', '')}")
    return plan


def cmd_cut(cfg):
    plan = json.loads((WORK / cfg["name"] / "plan.json").read_text(encoding="utf-8"))
    ensure_unique_id(cfg)
    info = render_cut(cfg["videos"], plan.get("cuts"), WORK / cfg["name"] / "cut.mp4", cfg["layout"])
    cfg["cut_info"] = info
    cfg.get("session", {}).pop("subs", None)  # 컷이 바뀌면 자막 대화는 새로 시작
    publish_preview(cfg, [], "cut")
    print(f"컷 영상 {info['width']}x{info['height']}, {info['duration']:.1f}초")


def layout_note(cfg):
    if cfg["layout"] != "fit":
        return ""
    info = cfg["cut_info"]
    h = 1080 * info["height"] / info["width"]
    top = (1920 - h) / 2 / 1920
    if cfg.get("frame") == "black":
        return f"\n  원본 영상은 화면 가운데(y={top:.2f}~{1 - top:.2f})에 있고 위아래는 검은 여백입니다. 제목은 위 여백에 두고, 본문 자막 위치는 규칙 파일을 따르세요."
    return f"\n  원본 영상은 화면 가운데(y={top:.2f}~{1 - top:.2f})에 있고 위아래는 흐린 배경입니다. 자막을 위아래 빈 공간에 두면 영상을 가리지 않습니다."


def subs_now(cfg):
    tsx = studio_source(cfg)
    if tsx.exists() and "<Sub" in tsx.read_text(encoding="utf-8"):
        return (
            "편집 화면 파일입니다. 사용자가 편집 화면에서 직접 고친 내용이 들어 있을 수 있으니 이것을 기준으로 고치세요. "
            "from·durationInFrames는 30fps 프레임 단위입니다.\n```tsx\n" + tsx.read_text(encoding="utf-8") + "\n```"
        )
    p = WORK / cfg["name"] / "subs.json"
    return f"```json\n{p.read_text(encoding='utf-8')}\n```" if p.exists() else "(아직 없음)"


def cmd_subs(cfg, feedback=None):
    w = WORK / cfg["name"]
    d = w / "subs"
    sess = cfg.get("session", {}).get("subs") if feedback else None
    if sess:
        prompt = revise(feedback, subs_now(cfg))
    else:
        idx = make_sheets([w / "cut.mp4"], d, pad916=cfg["layout"] == "fit")
        copy_texts(cfg, d)
        shutil.copyfile(w / "plan.json", d / "plan.json")
        fonts = make_font_sheets(STUDIO, d)
        anim = (STUDIO / "src" / "animlist.ts").read_text()
        (d / "effects.txt").write_text(anim.replace("export const ", "").replace("_FX", "").replace(" as const;", ""), encoding="utf-8")
        prompt = fill(
            "subs.txt",
            situation=cfg["situation"],
            duration=f"{cfg['cut_info']['duration']:.1f}",
            sheets=describe(idx),
            layout_note=layout_note(cfg),
            font_sheets=", ".join(fonts),
        )
        if feedback:
            prompt += "\n\n" + revise(feedback, subs_now(cfg))
    (d / ("prompt_revise.txt" if feedback else "prompt.txt")).write_text(prompt, encoding="utf-8")
    subs, meta = ai.ask(prompt, d, cfg["model"], resume=sess)
    subs["subs"] = normalize_subs(subs.get("subs"), cfg["cut_info"]["duration"])
    subs, meta = presets.after_subs(cfg, subs, meta, prompt, d)
    (w / "subs.json").write_text(json.dumps(subs, ensure_ascii=False, indent=1), encoding="utf-8")
    record(cfg, "subs", meta, resumed=bool(sess))
    save(cfg)
    print(f"2단계: 자막 {len(subs['subs'])}개, ${meta['cost']:.3f}, {meta['seconds']:.0f}초 걸림")
    for s in subs["subs"]:
        print(f"  {s['t0']:>5.1f}~{s['t1']:>5.1f} {s.get('font')} {s.get('enter')}  {s['text'].replace(chr(10), ' / ')}")
    return subs


def cmd_export(cfg):
    w = WORK / cfg["name"]
    data = json.loads((w / "subs.json").read_text(encoding="utf-8"))
    ensure_unique_id(cfg)
    data["subs"] = publish_preview(cfg, data.get("subs"), "subs")
    print(f"스튜디오에 등록: {cfg['id']}")
    return data


def cmd_render(cfg):
    ensure_unique_id(cfg)
    out = (WORK / cfg["name"] / f"{cfg['id']}.mp4").resolve()
    with TemporaryDirectory(dir=out.parent, prefix=".render-") as temp:
        rendered = Path(temp) / out.name
        subprocess.run(["npx", "remotion", "render", "src/index.ts", cfg["id"], str(rendered), "--image-format=png", "--crf=16", "--log=error"], cwd=STUDIO, check=True)
        rendered.replace(out)
    cfg["stage"] = "done"
    save(cfg)
    print(f"완성: {out}")


STEPS = {"prep": cmd_prep, "plan": cmd_plan, "cut": cmd_cut, "subs": cmd_subs, "export": cmd_export, "render": cmd_render}


def main():
    ap = argparse.ArgumentParser(prog="python -m sceneit.run")
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("new", "all"):
        p = sp.add_parser(name)
        p.add_argument("name")
        p.add_argument("--video", action="append", required=True)
        p.add_argument("--situation", required=True)
        p.add_argument("--preset", choices=presets.names(), help="말투·규칙·기본값 묶음 (예: roblox_ko, roblox_en)")
        p.add_argument("--style")
        p.add_argument("--rules")
        p.add_argument("--cut", choices=list(CUT_RULES), help="기본 minimal (프리셋이 있으면 프리셋 값)")
        p.add_argument("--layout", choices=["auto", "cover", "fit"], default="auto")
        p.add_argument("--length", help="목표 길이(초), 예: 20~30. 기본 15~30 (프리셋이 있으면 프리셋 값)")
        p.add_argument("--model", default="claude-opus-5-5")
        if name == "all":
            p.add_argument("--no-render", action="store_true")
    for step in STEPS:
        p = sp.add_parser(step)
        p.add_argument("name")
    a = ap.parse_args()
    if a.cmd in ("new", "all"):
        cfg = cmd_new(a)
        if a.cmd == "all":
            for step in STEPS:
                if step == "render" and a.no_render:
                    break
                STEPS[step](cfg)
                cfg = load(a.name)
        return
    STEPS[a.cmd](load(a.name))


if __name__ == "__main__":
    main()
