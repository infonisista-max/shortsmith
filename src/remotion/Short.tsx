// The explainer composition (ticket 004): per frame, the beat's presenter mode picks
// full-frame presenter, PIP over the palette gradient, or the gradient alone (`off`),
// with the caption layer on top. Ticket 016 draws the beat's B-roll between the
// gradient and the presenter: a full-bleed `photo` or a framed `card`. A rung-4
// rescue arrives as `pip` with no visual. Ticket 026 adds the two set pieces (the
// hook's cards and the finale) between the B-roll and the presenter, the full-frame
// punch-in, and the two landed overlays (`stamp`, `lower_third`) over the presenter.
// Ticket 027 adds the other three tier-1 set pieces in the same layer: `list` and
// `wall` over the beat's dimmed base still, `split` as the news-card composite.
// Ticket 021 adds the two infographic kinds: `infographic` draws its own label-free base
// with the labels in code over it, `chart` is drawn from the planner's series over the
// gradient. Other kinds arrive with their tickets.
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Captions } from "./components/captions";
import { Card } from "./components/card";
import { Chart } from "./components/chart";
import { Finale } from "./components/finale";
import { HookCards } from "./components/hook_cards";
import { Infographic } from "./components/infographic";
import { List } from "./components/list";
import { LowerThird } from "./components/lower_third";
import { Photo } from "./components/photo";
import { Pip, Presenter } from "./components/pip";
import { Split } from "./components/split";
import { Stamp } from "./components/stamp";
import { Wall } from "./components/wall";
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
  const since = beat ? frame - beat.start_frame : 0;
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
      {beat?.hook ? (
        <HookCards
          spec={beat.hook}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
        />
      ) : null}
      {beat?.finale ? (
        <Finale
          spec={beat.finale}
          render={spec}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
        />
      ) : null}
      {beat?.list ? (
        <List spec={beat.list} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.split ? (
        <Split spec={beat.split} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.wall ? (
        <Wall
          spec={beat.wall}
          frame={since}
          fps={spec.fps}
          lengthS={(beat.end_frame - beat.start_frame) / spec.fps}
        />
      ) : null}
      {beat?.infographic ? (
        <Infographic
          spec={beat.infographic}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
          lengthS={(beat.end_frame - beat.start_frame) / spec.fps}
        />
      ) : null}
      {beat?.chart ? (
        <Chart spec={beat.chart} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.mode === "full" ? <Presenter spec={spec} beat={beat} frame={frame} /> : null}
      {beat?.mode === "pip" ? <Pip spec={spec} /> : null}
      {beat?.stamp ? (
        <Stamp spec={beat.stamp} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.lower_third ? (
        <LowerThird
          spec={beat.lower_third}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
        />
      ) : null}
      <Captions spec={spec} t={t} />
    </AbsoluteFill>
  );
};
