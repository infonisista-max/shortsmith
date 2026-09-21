// The explainer composition (ticket 004): per frame, the beat's presenter mode picks
// full-frame presenter, PIP over the palette gradient, or the gradient alone (`off`),
// with the caption layer on top. B-roll kinds arrive with their tickets (016+).
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Captions } from "./components/captions";
import { Pip, Presenter } from "./components/pip";
import { fontsReady } from "./fonts";
import type { RenderSpec } from "./types";

void fontsReady;

export const Short: React.FC<RenderSpec> = (spec) => {
  const frame = useCurrentFrame();
  const t = frame / spec.fps;
  const beat =
    spec.beats.find((b) => frame >= b.start_frame && frame < b.end_frame) ??
    spec.beats[spec.beats.length - 1];
  const [from, to] = spec.palette.gradient;
  return (
    <AbsoluteFill
      style={{ background: `linear-gradient(${spec.palette.angle_deg}deg, ${from}, ${to})` }}
    >
      {beat?.mode === "full" ? <Presenter spec={spec} /> : null}
      {beat?.mode === "pip" ? <Pip spec={spec} /> : null}
      <Captions spec={spec} t={t} />
    </AbsoluteFill>
  );
};
