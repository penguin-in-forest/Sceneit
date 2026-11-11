# 채팅 편집 화면: 왼쪽 Remotion Studio, 오른쪽 채팅.
# 단계마다 결과를 보여 주고, 사용자가 확인하면 다음 단계로, 의견을 말하면 그 단계를 다시 돌린다.
#   cut  : 원본 보고 구간 고르기(plan) + 자르기(cut)
#   subs : 자막 쓰기 + 편집 화면 등록
#   done : 렌더 끝
import argparse
import atexit
import json
import os
import signal
import socket
import subprocess
import threading
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from . import run

WEB = run.PKG / "web"
STUDIO_PORT = 3000
app = FastAPI()
JOBS = {}
LOCK = threading.Lock()


def pdir(name):
    if not name or name != Path(name).name or name.startswith("."):
        raise HTTPException(400, "이름에 / 를 넣거나 . 으로 시작할 수 없어요")
    return run.WORK / name


def cfg_of(name):
    p = pdir(name) / "project.json"
    if not p.exists():
        raise HTTPException(404, f"프로젝트 없음: {name}")
    return json.loads(p.read_text(encoding="utf-8"))


def chat(name):
    p = pdir(name) / "chat.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def post(name, role, text, **extra):
    with LOCK:
        msgs = chat(name)
        msgs.append({"role": role, "text": text, "t": time.time(), **extra})
        (pdir(name) / "chat.json").write_text(json.dumps(msgs, ensure_ascii=False, indent=1), encoding="utf-8")


def set_stage(name, stage):
    cfg = run.load(name)
    cfg.update(stage=stage, rev=project_status(cfg)[1])
    run.save(cfg)


def progress(name, text):
    JOBS[name]["progress"] = text


def start(name, fn, *args):
    with LOCK:
        if name in JOBS:
            raise HTTPException(409, "아직 작업 중이에요")
        JOBS[name] = {"progress": "준비 중", "since": time.time()}

    def work():
        try:
            fn(name, *args)
        except Exception as e:
            traceback.print_exc()
            post(name, "error", f"오류가 났어요: {e}")
        finally:
            JOBS.pop(name, None)

    threading.Thread(target=work, daemon=True).start()


def spent(cfg, step):
    m = cfg["cost"].get(step, {})
    return {"cost": m.get("cost", 0), "seconds": m.get("seconds", 0)}


def job_cut(name, feedback=None):
    if not (run.WORK / name / "plan" / "index.json").exists():
        progress(name, "원본에서 0.5초마다 화면을 뽑는 중")
        run.cmd_prep(run.load(name))
    progress(name, "의견 반영해서 컷 고치는 중" if feedback else "Claude가 원본을 보고 쓸 구간을 고르는 중")
    plan = run.cmd_plan(run.load(name), feedback)
    progress(name, "컷 자르는 중")
    run.cmd_cut(run.load(name))
    cfg = run.load(name)
    info = cfg["cut_info"]
    cuts = [{k: c.get(k) for k in ("src", "t0", "t1", "scene", "why")} for c in plan["cuts"]]
    text = plan.get("reply") or f"컷 {len(cuts)}개로 {info['duration']:.1f}초 영상을 만들었어요."
    post(name, "ai", text, kind="cut", data={"cuts": cuts, "duration": info["duration"], **spent(cfg, "plan")})


def job_subs(name, feedback=None):
    cfg = run.load(name)
    if feedback or subtitle_status(cfg) != "pending":
        progress(name, "의견 반영해서 자막 고치는 중" if feedback else "Claude가 완성본을 보고 자막 쓰는 중")
        run.cmd_subs(cfg, feedback)
    progress(name, "편집 화면에 올리는 중")
    subs = run.cmd_export(cfg)
    items = [{k: s.get(k) for k in ("t0", "t1", "text", "font")} for s in subs["subs"]]
    text = subs.get("reply") or f"자막 {len(items)}개를 넣었어요."
    post(name, "ai", text, kind="subs", data={"subs": items, **spent(cfg, "subs")})


def job_render(name):
    progress(name, "최종 영상 렌더링 중")
    run.cmd_render(run.load(name))
    post(name, "ai", "완성했어요. 아래에서 보고 받을 수 있어요. 더 고칠 게 있으면 말해 주세요.", kind="done")


def studio_up():
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", STUDIO_PORT)) == 0


def subtitle_status(cfg):
    folder = run.WORK / cfg["name"]
    subs, cut = folder / "subs.json", folder / "cut.mp4"
    if not subs.is_file() or not cut.is_file() or subs.stat().st_mtime_ns < cut.stat().st_mtime_ns:
        return None
    src = run.studio_source(cfg)
    if src.is_file() and src.stat().st_mtime_ns >= subs.stat().st_mtime_ns:
        return "published"
    return "pending"


def project_status(cfg):
    if "stage" in cfg:
        return cfg["stage"], cfg.get("rev", 0) if "cut_info" in cfg else 0

    # 예전 명령줄 프로젝트에는 stage와 rev가 저장되지 않았다.
    src = run.studio_source(cfg)
    media = run.STUDIO / "public" / "media" / f"{cfg['id']}.mp4"
    cut = run.WORK / cfg["name"] / "cut.mp4"
    if not (cut.is_file() and src.is_file() and media.is_file()):
        return "cut", 0
    if min(src.stat().st_mtime_ns, media.stat().st_mtime_ns) < cut.stat().st_mtime_ns:
        return "cut", 0
    final = cut.parent / f"{cfg['id']}.mp4"
    if final.is_file() and final.stat().st_mtime_ns >= src.stat().st_mtime_ns:
        return "done", 1
    return ("subs" if subtitle_status(cfg) == "published" else "cut"), 1


def state(name):
    cfg = cfg_of(name)
    job = JOBS.get(name)
    stage, rev = project_status(cfg)
    return {
        "name": name,
        "id": cfg["id"],
        "stage": stage,
        "rev": rev,
        "spent": cfg.get("spent", 0),
        "ready": {"cut": "cut_info" in cfg, "subs": (run.WORK / name / "subs.json").exists()},
        "busy": job is not None,
        "progress": job and job["progress"],
        "since": job and job["since"],
        "studio": f"http://localhost:{STUDIO_PORT}",
        "studio_up": studio_up(),
        "chat": chat(name),
    }


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/projects")
def projects():
    items = []
    for p in sorted(run.WORK.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        cfg = json.loads(p.read_text(encoding="utf-8"))
        items.append({"name": cfg["name"], "stage": project_status(cfg)[0]})
    return {"projects": items, "studio": f"http://localhost:{STUDIO_PORT}", "studio_up": studio_up()}


@app.get("/api/projects/{name}")
def get_project(name: str):
    with LOCK:
        cfg = cfg_of(name)
        cut = run.WORK / name / "cut.mp4"
        if "stage" not in cfg and "cut_info" in cfg and cut.is_file() and not run.studio_source(cfg).exists():
            run.ensure_unique_id(cfg)
            if subtitle_status(cfg) == "pending":
                run.cmd_export(cfg)
            else:
                run.publish_preview(cfg, [], "cut")
    return state(name)


@app.put("/api/upload/{name}/{fname}")
async def upload(name: str, fname: str, request: Request):
    d = pdir(name)
    if (d / "project.json").exists():
        raise HTTPException(409, "같은 이름의 프로젝트가 있어요")
    fname = Path(fname).name
    if not fname or fname.startswith("."):
        raise HTTPException(400, "파일 이름이 이상해요")
    (d / "src").mkdir(parents=True, exist_ok=True)
    with open(d / "src" / fname, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
    return {"ok": True}


@app.post("/api/projects")
def create(body: dict):
    name = str(body.get("name", "")).strip()
    d = pdir(name)
    if (d / "project.json").exists():
        raise HTTPException(409, "같은 이름의 프로젝트가 있어요")
    files = [d / "src" / Path(f).name for f in body.get("files", [])]
    if not files or not all(f.exists() for f in files):
        raise HTTPException(400, "원본 영상을 먼저 올려 주세요")
    situation = str(body.get("situation", "")).strip()
    if not situation:
        raise HTTPException(400, "상황을 한 줄 적어 주세요")
    a = SimpleNamespace(
        name=name,
        video=[str(f) for f in files],
        situation=situation,
        style=None,
        rules=None,
        cut=body.get("cut") if body.get("cut") in run.CUT_RULES else "minimal",
        layout=body.get("layout") if body.get("layout") in ("auto", "cover", "fit") else "auto",
        length=str(body.get("length") or "15~30"),
        model=body.get("model") or "claude-opus-5-5",
    )
    try:
        cfg = run.cmd_new(a)
    except Exception as e:
        raise HTTPException(400, f"영상을 읽지 못했어요: {e}")
    names = ", ".join(f.name for f in files)
    post(name, "user", situation, kind="start", data={"files": names, "cut": a.cut, "layout": cfg["layout"], "length": a.length})
    start(name, job_cut)
    return state(name)


@app.post("/api/projects/{name}/message")
def message(name: str, body: dict):
    cfg = cfg_of(name)
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "내용이 비었어요")
    if name in JOBS:
        raise HTTPException(409, "아직 작업 중이에요")
    post(name, "user", text)
    if project_status(cfg)[0] == "cut":
        start(name, job_cut, text)
    else:  # subs, done: 자막 단계에서 다시
        set_stage(name, "subs")
        start(name, job_subs, text)
    return state(name)


@app.post("/api/projects/{name}/confirm")
def confirm(name: str):
    cfg = cfg_of(name)
    if name in JOBS:
        raise HTTPException(409, "아직 작업 중이에요")
    stage, rev = project_status(cfg)
    if stage == "cut":
        if "cut_info" not in cfg:
            raise HTTPException(400, "컷이 아직 없어요")
        post(name, "user", "좋아요, 자막 넣어 주세요", kind="confirm")
        if rev and subtitle_status(cfg) == "published":
            # 컷을 다시 돌리지 않고 돌아왔다가 넘어가는 경우: 자막은 그대로
            set_stage(name, "subs")
            post(name, "ai", "컷이 그대로라 자막도 그대로 뒀어요. 고칠 점을 말해 주세요.")
        else:
            start(name, job_subs)
    elif stage == "subs":
        post(name, "user", "좋아요, 영상으로 뽑아 주세요", kind="confirm")
        start(name, job_render)
    else:
        raise HTTPException(400, "이 단계에서는 넘어갈 곳이 없어요")
    return state(name)


@app.post("/api/projects/{name}/back")
def back(name: str):
    cfg = cfg_of(name)
    if name in JOBS:
        raise HTTPException(409, "아직 작업 중이에요")
    if project_status(cfg)[0] not in ("subs", "done"):
        raise HTTPException(400, "이미 컷 단계예요")
    set_stage(name, "cut")
    post(name, "note", "컷 단계로 돌아왔어요. 컷을 다시 고치면 자막은 새로 씁니다.")
    return state(name)


@app.get("/api/projects/{name}/video")
def video(name: str):
    cfg = cfg_of(name)
    p = run.WORK / name / f"{cfg['id']}.mp4"
    if not p.exists():
        raise HTTPException(404, "아직 렌더하지 않았어요")
    return FileResponse(p, media_type="video/mp4", filename=f"{name}.mp4")


def launch_studio():
    if studio_up():
        print(f"스튜디오: 이미 떠 있는 http://localhost:{STUDIO_PORT} 사용")
        return
    if not (run.STUDIO / "node_modules").exists():
        print("스튜디오: studio/node_modules 없음. cd studio && npm install 후 다시 실행하세요")
        return
    p = subprocess.Popen(
        ["npx", "remotion", "studio", "src/index.ts", "--port", str(STUDIO_PORT), "--no-open"],
        cwd=run.STUDIO,
        start_new_session=True,
    )

    def stop():
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    atexit.register(stop)
    print(f"스튜디오: http://localhost:{STUDIO_PORT} 띄우는 중")


def main():
    global STUDIO_PORT
    ap = argparse.ArgumentParser(prog="python -m sceneit.app")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--studio-port", type=int, default=3000)
    ap.add_argument("--no-studio", action="store_true", help="스튜디오를 따로 띄울 때")
    a = ap.parse_args()
    STUDIO_PORT = a.studio_port
    run.WORK.mkdir(exist_ok=True)
    if not a.no_studio:
        launch_studio()
    print(f"Sceneit: http://localhost:{a.port}")
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
