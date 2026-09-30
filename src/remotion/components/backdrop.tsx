// `backdrop` (ticket 103): the image sharp across the frame, no border and no tilt, over
// its own blurred, darkened copy filling 9:16 - the card's body with a bare box. The box
// (at most the style's `backdrop.width_px`, never over its upscale, centred between the
// safe top and the card line), the cover's blur and brightness (`cover_blur_px`,
// `cover_brightness`), the cover's push (`cover_scale_from` -> `cover_scale_to`) and the
// image's slow push (`scale_from` -> `scale_to`) all come from the spec
// (render.backdrop_visual); nothing is measured here.
import React from "react";
import type { BeatSpec } from "../types";
import { CardBody } from "./card";

export const Backdrop: React.FC<{
  beat: BeatSpec;
  frame: number;
  fps: number;
  width: number;
  height: number;
}> = ({ beat, frame, fps, width, height }) => {
  const visual = beat.visual;
  const card = visual?.card;
  if (!visual || !card || visual.treatment !== "backdrop") {
    return null;
  }
  return (
    <CardBody
      beat={beat}
      frame={frame}
      fps={fps}
      width={width}
      height={height}
      shadow="0 24px 64px rgba(0,0,0,0.5)"
    />
  );
};
