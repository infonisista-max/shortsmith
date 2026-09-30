// `polaroid` (ticket 103): a white-bordered print with a thick bottom (where the beat's
// lower-third label is written) over the image's own blurred, darkened copy. It drops
// `drop_px` from above and settles in `drop_s` with a small overshoot, its tilt
// (`rotate_deg`, varied per use within the style's range) swinging in from a little
// further, under a soft `shadow_px` shadow; then it takes the card's slow push
// (`scale_from` -> `scale_to`). Every box and number is the spec's
// (render.polaroid_visual); a print carried on by a number beat has `drop_px` 0.
import React from "react";
import { Easing, interpolate } from "remotion";
import type { BeatSpec } from "../types";
import { CardBody } from "./card";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Polaroid: React.FC<{
  beat: BeatSpec;
  frame: number;
  fps: number;
  width: number;
  height: number;
}> = ({ beat, frame, fps, width, height }) => {
  const visual = beat.visual;
  const card = visual?.card;
  if (!visual || !card || visual.treatment !== "polaroid") {
    return null;
  }
  const t = (frame - beat.start_frame) / fps;
  const land =
    card.drop_px > 0 && card.drop_s > 0
      ? interpolate(t, [0, card.drop_s], [0, 1], { ...clamp, easing: Easing.out(Easing.back(1.4)) })
      : 1;
  const drop = (1 - land) * card.drop_px;
  // the print swings in from twice its tilt as it lands
  const swing = (1 - land) * card.rotate_deg;
  const lift = `translateY(${-drop}px) rotate(${swing}deg)`;
  const depth = card.shadow_px;
  // the shadow grows as the print nears the table
  const shadow = `0 ${depth * (0.4 + 0.6 * land)}px ${depth * 2}px rgba(0,0,0,${0.35 + 0.2 * land})`;
  return (
    <CardBody
      beat={beat}
      frame={frame}
      fps={fps}
      width={width}
      height={height}
      lift={lift}
      shadow={shadow}
    />
  );
};
