// The explainer composition (ticket 004): per frame, the beat's presenter mode picks
// full-frame presenter, PIP over the palette gradient, or the gradient alone (`off`),
// with the caption layer on top. Ticket 016 draws the beat's B-roll between the
// gradient and the presenter: a full-bleed `photo` or a framed `card`. A rung-4
// rescue arrives as `pip` with no visual. Other kinds arrive with their tickets.
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Captions } from "./components/captions";
import { Card } from "./components/card";
import { Photo } from "./components/photo";
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
  const visual = beat?.mode === "full" ? null : beat?.visual;
  return (
    <AbsoluteFill
      style={{ background: `linear-gradient(${spec.palette.angle_deg}deg, ${from}, ${to})` }}
    >
      {beat && visual?.treatment === "photo" ? (
        <Photo beat={beat} frame={frame} width={spec.width} height={spec.height} />
      ) : null}
      {beat && visual?.treatment === "card" ? (
        <Card beat={beat} frame={frame} fps={spec.fps} width={spec.width} height={spec.height} />
      ) : null}
      {beat?.mode === "full" ? <Presenter spec={spec} /> : null}
      {beat?.mode === "pip" ? <Pip spec={spec} /> : null}
      <Captions spec={spec} t={t} />
    </AbsoluteFill>
  );
};
