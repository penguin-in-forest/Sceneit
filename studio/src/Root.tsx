import React from "react";
import { Composition } from "remotion";
import { PROJECTS } from "./projects";

export const RemotionRoot: React.FC = () => (
  <>
    {PROJECTS.map((p) => (
      <Composition key={p.id} id={p.id} component={p.component} fps={30} width={1080} height={1920} durationInFrames={p.frames} />
    ))}
  </>
);
