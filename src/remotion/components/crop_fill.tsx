// `crop_fill` (ticket 103): a still that cannot fill the frame as it is, drawn full screen
// cropped round its detected face - `focus_x` / `focus_y` are the objectPosition that put
// the face across the middle at the style's `crop_fill.face_y` (render.crop_fill_visual,
// the split pane's framing) - pushing slowly toward it (`scale_from` -> `scale_to`, the
// transform origin at the same point). Ticket 102: the push is centred on the face as
// drawn (`origin_x` / `origin_y`) and the planner's camera move arrives as the scales and
// both drifts. Nothing is measured here.
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { BeatSpec } from "../types";
import { Framed, beatProgress, drift } from "./photo";

export const CropFill: React.FC<{
  beat: BeatSpec;
  frame: number;
  width: number;
  height: number;
}> = ({ beat, frame, width, height }) => {
  const visual = beat.visual;
  if (!visual || visual.treatment !== "crop_fill") {
    return null;
  }
  const p = beatProgress(beat, frame);
  const scale = interpolate(p, [0, 1], [visual.scale_from, visual.scale_to]);
  return (
    <AbsoluteFill>
      <Framed
        visual={visual}
        width={width}
        height={height}
        scale={scale}
        shiftX={drift(p, visual.pan_px)}
        shiftY={drift(p, visual.pan_y_px)}
      />
    </AbsoluteFill>
  );
};
