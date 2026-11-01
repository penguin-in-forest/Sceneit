import json
import re
import shutil
from pathlib import Path


def project_id(name):
    pid = re.sub(r"[^A-Za-z0-9-]+", "-", name).strip("-")
    return pid or "project"


def sub_line(i, s):
    text = s["text"]
    label = f"{i + 1} " + re.sub(r"\[\[|\]\]", "", text).replace("\n", " ")[:16]
    f = round(float(s["t0"]) * 30)
    d = max(1, round((float(s["t1"]) - float(s["t0"])) * 30))
    attrs = [
        f"name={json.dumps(label, ensure_ascii=False)}",
        f"from={{{f}}}",
        f"durationInFrames={{{d}}}",
        f"text={{{json.dumps(text, ensure_ascii=False)}}}",
        f'font="{s.get("font", "jua")}"',
        f'enter="{s.get("enter", "fadeInUp")}"',
        f'emph="{s.get("emph", "none")}"',
        f'exit="{s.get("exit", "none")}"',
        f"speed={{{float(s.get('speed', 1))}}}",
        f"y={{{float(s.get('y', 0.8))}}}",
        f"size={{{float(s.get('size', 1))}}}",
        f'fill="{s.get("fill", "#ffffff")}"',
        f'stroke="{s.get("stroke", "#1b1b1b")}"',
        f'hi="{s.get("hi", "#ffd23f")}"',
    ]
    return "    <Sub " + " ".join(attrs) + " />"


def write_project(studio, pid, video, subs, layout, aspect, duration):
    studio = Path(studio)
    media = studio / "public" / "media"
    media.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(video, media / f"{pid}.mp4")
    frames = max(1, round(duration * 30))
    body = "\n".join(sub_line(i, s) for i, s in enumerate(subs))
    tsx = f'''import React from "react";
import {{ AbsoluteFill }} from "remotion";
import {{ Frame }} from "../Frame";
import {{ Sub }} from "../SubClip";

export const meta = {{ id: "{pid}", frames: {frames} }};

export const Component: React.FC = () => (
  <AbsoluteFill>
    <Frame src="media/{pid}.mp4" layout="{layout}" aspect={{{aspect:.4f}}} />
{body}
  </AbsoluteFill>
);
'''
    (studio / "src" / "projects" / f"{pid}.tsx").write_text(tsx, encoding="utf-8")
    write_index(studio)


def write_index(studio):
    pdir = Path(studio) / "src" / "projects"
    names = sorted(p.stem for p in pdir.glob("*.tsx"))
    imports = "\n".join(f'import * as p{i} from "./{n}";' for i, n in enumerate(names))
    mods = ", ".join(f"p{i}" for i in range(len(names)))
    ts = f'''import type React from "react";
{imports}

type Mod = {{ meta: {{ id: string; frames: number }}; Component: React.FC }};
const MODS: Mod[] = [{mods}];

export const PROJECTS = MODS.map((m) => ({{ ...m.meta, component: m.Component }}));
'''
    (pdir / "index.ts").write_text(ts, encoding="utf-8")
