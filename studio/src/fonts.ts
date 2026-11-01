import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";
import FONTS from "../fonts.json";

export type Font = { key: string; family: string; file: string; dir: string; scale: number; sw: number };

export const FONT_LIST = FONTS as Font[];
export const FONT_KEYS = FONT_LIST.map((f) => f.key);
const byKey = new Map(FONT_LIST.map((f) => [f.key, f]));
export const getFont = (key: string): Font => byKey.get(key) ?? FONT_LIST[0];

const cache = new Map<string, Promise<void>>();
export const ensureFont = (key: string): Promise<void> => {
  const f = getFont(key);
  if (!cache.has(f.family)) {
    cache.set(f.family, loadFont({ family: f.family, url: staticFile(`fonts/${f.file}`) }).then(() => undefined));
  }
  return cache.get(f.family)!;
};
