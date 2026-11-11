import type React from "react";

// 프로젝트 파일(*.tsx)은 sceneit이 만들고 git에는 올리지 않는다.
// 이 폴더의 .tsx를 전부 읽어 오므로 프로젝트가 늘어도 이 파일은 바뀌지 않는다.
type Mod = { meta: { id: string; frames: number }; Component: React.FC };
type Ctx = { keys(): string[]; (key: string): Mod };

const ctx = (require as unknown as { context(dir: string, deep: boolean, re: RegExp): Ctx }).context("./", false, /\.tsx$/);
// webpack은 같은 파일을 경로 두 가지로 줄 때가 있어 id로 한 번 거른다.
const mods = new Map(ctx.keys().map((k) => [ctx(k).meta.id, ctx(k)] as const));

export const PROJECTS = [...mods.values()].map((m) => ({ ...m.meta, component: m.Component }));
