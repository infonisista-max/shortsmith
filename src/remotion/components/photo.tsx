// `photo` (decisions 4.1, 5.3): a full-bleed image covering the frame, always moving.
// The spec gives the Ken Burns scales (in or out, alternating per beat), the drift
// across the margin the smaller scale leaves, and the framing (`zoom` around the
// focus point; a re-dressed reuse differs here, 4.4). Nothing is measured here.
import React from "react";
import { AbsoluteFill, Img, interpolate } from "remotion";
import type { BeatSpec, VisualSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// 0 at the beat's first frame, 1 at its last.
export function beatProgress(beat: BeatSpec, frame: number): number {
  const last = Math.max(beat.start_frame + 1, beat.end_frame - 1);
  return interpolate(frame, [beat.start_frame, last], [0, 1], clamp);
}

// The image fitted to cover a box, pushed to `scale` around the framing's focus.
export const Framed: React.FC<{
  visual: VisualSpec;
  width: number;
  height: number;
  scale: number;
  shiftX?: number;
  style?: React.CSSProperties;
}> = ({ visual, width, height, scale, shiftX = 0, style }) => (
  <div style={{ position: "absolute", left: 0, top: 0, width, height, overflow: "hidden" }}>
    <Img
      src={visual.src}
      style={{
        width,
        height,
        objectFit: "cover",
        objectPosition: `${visual.focus_x * 100}% ${visual.focus_y * 100}%`,
        transformOrigin: `${visual.focus_x * 100}% ${visual.focus_y * 100}%`,
        transform: `translateX(${shiftX}px) scale(${scale * visual.zoom})`,
        ...style,
      }}
    />
  </div>
);

export const Photo: React.FC<{ beat: BeatSpec; frame: number; width: number; height: number }> = ({
  beat,
  frame,
  width,
  height,
}) => {
  const visual = beat.visual;
  if (!visual) {
    return null;
  }
  const p = beatProgress(beat, frame);
  const scale = interpolate(p, [0, 1], [visual.scale_from, visual.scale_to]);
  const shiftX = interpolate(p, [0, 1], [-visual.pan_px / 2, visual.pan_px / 2]);
  return (
    <AbsoluteFill>
      <Framed visual={visual} width={width} height={height} scale={scale} shiftX={shiftX} />
    </AbsoluteFill>
  );
};
