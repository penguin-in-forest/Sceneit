import React from "react";
import "animate.css";
import { AbsoluteFill, Interactive, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import { measureText } from "@remotion/layout-utils";
import { FONT_KEYS, ensureFont, getFont } from "./fonts";
import { IN_FX, EMPH_FX, OUT_FX } from "./animlist";

const opts = (keys: readonly string[]) => Object.fromEntries(keys.map((k) => [k, {}]));

const fx = (name: string, t: number, dur: number): React.CSSProperties =>
  name === "none"
    ? {}
    : {
        animationName: name,
        animationDuration: `${dur}s`,
        animationDelay: `${-t}s`,
        animationPlayState: "paused",
        animationFillMode: "both",
        animationIterationCount: 1,
      };

const Line: React.FC<{ line: string; hi: string }> = ({ line, hi }) => (
  <div>
    {line
      .split(/(\[\[.*?\]\])/)
      .filter(Boolean)
      .map((p, i) => (p.startsWith("[[") ? <span key={i} style={{ color: hi }}>{p.slice(2, -2)}</span> : <span key={i}>{p}</span>))}
  </div>
);

const Clip: React.FC<{
  text: string;
  font: string;
  y: number;
  size: number;
  enter: string;
  emph: string;
  exit: string;
  speed: number;
  fill: string;
  stroke: string;
  hi: string;
  style?: React.CSSProperties;
}> = ({ text, font, y, size, enter, emph, exit, speed, fill, stroke, hi, style }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const f = getFont(font);
  const unit = width / 720;
  const base = 44 * size * f.scale * unit;
  const strokePx = f.sw * size * unit;
  const [fit, setFit] = React.useState(1);
  const [h] = React.useState(() => delayRender(`font-${f.key}`));
  React.useEffect(() => {
    ensureFont(f.key).then(() => {
      const widest = Math.max(
        ...text.split("\n").map(
          (l) =>
            measureText({
              text: l.replace(/\[\[|\]\]/g, ""),
              fontFamily: `"${f.family}"`,
              fontSize: base,
              fontWeight: "normal",
              letterSpacing: "normal",
              validateFontIsLoaded: false,
            }).width,
        ),
      );
      setFit(Math.min(1, (width - 60 * unit - 2 * strokePx) / widest));
      continueRender(h);
    });
  }, [h, f.key, f.family, text, base, width, unit, strokePx]);

  const t = frame / fps;
  const len = durationInFrames / fps;
  const inD = 0.8 / speed;
  const emD = 1.0 / speed;
  const outD = 0.6 / speed;
  return (
    <AbsoluteFill style={style}>
      <div style={{ position: "absolute", left: 0, right: 0, top: y * height, transform: "translateY(-50%)", display: "flex", justifyContent: "center" }}>
        <div style={fx(exit, t - (len - outD), outD)}>
          <div style={fx(emph, t - inD, emD)}>
            <div
              style={{
                ...fx(enter, t, inD),
                fontFamily: `"${f.family}"`,
                fontSize: base * fit,
                lineHeight: 1.25,
                textAlign: "center",
                color: fill,
                WebkitTextStroke: `${strokePx}px ${stroke}`,
                paintOrder: "stroke fill",
                filter: `drop-shadow(0 ${3 * unit}px ${4 * unit}px rgba(0,0,0,0.35))`,
                whiteSpace: "nowrap",
              }}
            >
              {text.split("\n").map((l, i) => (
                <Line key={i} line={l} hi={hi} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const Sub = Interactive.withSchema({
  Component: Clip,
  componentName: "자막",
  wrapInSequence: true,
  schema: {
    text: { type: "text-content", default: "자막", description: "문구 ([[강조]], 줄바꿈 가능)" },
    font: { type: "enum", default: "jua", description: "폰트", variants: opts(FONT_KEYS) },
    enter: { type: "enum", default: "fadeInUp", description: "등장 효과", variants: opts(IN_FX) },
    emph: { type: "enum", default: "none", description: "강조 효과", variants: opts(EMPH_FX) },
    exit: { type: "enum", default: "none", description: "퇴장 효과", variants: opts(OUT_FX) },
    speed: { type: "number", default: 1, min: 0.3, max: 3, step: 0.1, description: "효과 속도", hiddenFromList: false },
    y: { type: "number", default: 0.8, min: 0, max: 1, step: 0.01, description: "세로 위치 (0 위, 1 아래)", hiddenFromList: false },
    size: { type: "number", default: 1, min: 0.4, max: 3, step: 0.05, description: "크기", hiddenFromList: false },
    fill: { type: "color", default: "#ffffff", description: "글자색" },
    stroke: { type: "color", default: "#1b1b1b", description: "테두리색" },
    hi: { type: "color", default: "#ffd23f", description: "강조색 [[ ]]" },
  },
});
