import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import ai
from .cut import clamp, render_cut
from .export import project_id, write_project
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
    (d / "project.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def copy_texts(cfg, dest):
    shutil.copyfile(cfg["style"], dest / "style.md")
    shutil.copyfile(cfg["rules"], dest / "rules.md")


def cmd_new(a):
    videos = [str(Path(v).resolve()) for v in a.video]
    info = probe(videos[0])
    layout = a.layout
    if layout == "auto":
        layout = "cover" if info["width"] / info["height"] < 0.7 else "fit"
    cfg = {
        "name": a.name,
        "id": project_id(a.name),
        "videos": videos,
        "situation": a.situation,
        "style": str(Path(a.style or PKG / "assets" / "style.md").resolve()),
        "rules": str(Path(a.rules or PKG / "assets" / "rules.md").resolve()),
        "cut": a.cut,
        "layout": layout,
        "length": a.length,
        "model": a.model,
        "cost": {},
    }
    save(cfg)
    print(f"프로젝트 {a.name}: 영상 {len(videos)}개, 레이아웃 {layout}, 컷 {a.cut}")
    return cfg


def cmd_prep(cfg):
    idx = make_sheets(cfg["videos"], WORK / cfg["name"] / "plan")
    print(f"원본 시트 {len(idx)}장")


def cmd_plan(cfg):
    d = WORK / cfg["name"] / "plan"
    idx = json.loads((d / "index.json").read_text())
    copy_texts(cfg, d)
    prompt = fill("plan.txt", situation=cfg["situation"], sheets=describe(idx), length=cfg["length"], cut_rule=CUT_RULES[cfg["cut"]])
    (d / "prompt.txt").write_text(prompt, encoding="utf-8")
    plan, meta = ai.ask(prompt, d, cfg["model"])
    durations = [probe(v)["duration"] for v in cfg["videos"]]
    plan["cuts"] = clamp(plan["cuts"], durations)
    (WORK / cfg["name"] / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    cfg["cost"]["plan"] = meta
    save(cfg)
    total = sum(c["t1"] - c["t0"] for c in plan["cuts"])
    print(f"1단계: 컷 {len(plan['cuts'])}개, {total:.1f}초, ${meta['cost']:.3f}, {meta['seconds']:.0f}초 걸림")
    for c in plan["cuts"]:
        print(f"  v{c['src']} {c['t0']:>6.1f}~{c['t1']:>6.1f}  {c.get('scene', '')}")


def cmd_cut(cfg):
    plan = json.loads((WORK / cfg["name"] / "plan.json").read_text(encoding="utf-8"))
    info = render_cut(cfg["videos"], plan["cuts"], WORK / cfg["name"] / "cut.mp4", cfg["layout"])
    cfg["cut_info"] = info
    save(cfg)
    print(f"컷 영상 {info['width']}x{info['height']}, {info['duration']:.1f}초")


def layout_note(cfg):
    if cfg["layout"] != "fit":
        return ""
    info = cfg["cut_info"]
    h = 1080 * info["height"] / info["width"]
    top = (1920 - h) / 2 / 1920
    return f"\n  원본 영상은 화면 가운데(y={top:.2f}~{1 - top:.2f})에 있고 위아래는 흐린 배경입니다. 자막을 위아래 빈 공간에 두면 영상을 가리지 않습니다."


def cmd_subs(cfg):
    w = WORK / cfg["name"]
    d = w / "subs"
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
    (d / "prompt.txt").write_text(prompt, encoding="utf-8")
    subs, meta = ai.ask(prompt, d, cfg["model"])
    (w / "subs.json").write_text(json.dumps(subs, ensure_ascii=False, indent=1), encoding="utf-8")
    cfg["cost"]["subs"] = meta
    save(cfg)
    print(f"2단계: 자막 {len(subs['subs'])}개, ${meta['cost']:.3f}, {meta['seconds']:.0f}초 걸림")
    for s in subs["subs"]:
        print(f"  {s['t0']:>5.1f}~{s['t1']:>5.1f} {s.get('font')} {s.get('enter')}  {s['text'].replace(chr(10), ' / ')}")


def cmd_export(cfg):
    w = WORK / cfg["name"]
    subs = json.loads((w / "subs.json").read_text(encoding="utf-8"))["subs"]
    info = cfg["cut_info"]
    write_project(STUDIO, cfg["id"], w / "cut.mp4", subs, cfg["layout"], info["width"] / info["height"], info["duration"])
    print(f"스튜디오에 등록: {cfg['id']}")


def cmd_render(cfg):
    out = (WORK / cfg["name"] / f"{cfg['id']}.mp4").resolve()
    subprocess.run(["npx", "remotion", "render", "src/index.ts", cfg["id"], str(out), "--image-format=png", "--crf=16", "--log=error"], cwd=STUDIO, check=True)
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
        p.add_argument("--style")
        p.add_argument("--rules")
        p.add_argument("--cut", choices=["minimal", "paced"], default="minimal")
        p.add_argument("--layout", choices=["auto", "cover", "fit"], default="auto")
        p.add_argument("--length", default="15~30")
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
