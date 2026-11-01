import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";

export const Frame: React.FC<{ src: string; layout: "cover" | "fit"; aspect: number }> = ({ src, layout, aspect }) => {
  const url = staticFile(src);
  if (layout === "cover") {
    return (
      <AbsoluteFill style={{ backgroundColor: "black" }}>
        <OffthreadVideo src={url} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </AbsoluteFill>
    );
  }
  const h = 1080 / aspect;
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <OffthreadVideo src={url} muted style={{ width: "100%", height: "100%", objectFit: "cover", filter: "blur(40px) brightness(0.45)", transform: "scale(1.15)" }} />
      <OffthreadVideo src={url} style={{ position: "absolute", left: 0, top: (1920 - h) / 2, width: 1080, height: h }} />
    </AbsoluteFill>
  );
};
