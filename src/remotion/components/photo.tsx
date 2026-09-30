// `photo` (decisions 4.1, 5.3): a full-bleed image covering the frame, always moving.
// The spec gives the Ken Burns scales (in or out, alternating per beat), the drift
// across the margin the smaller scale leaves, and the framing (`zoom` around the
// focus point; a re-dressed reuse differs here, 4.4). Ticket 102: the planner's camera
// move (render.moved) arrives as the same scales plus a vertical drift (`pan_y_px`) and,
// where the push closes in on a face, its `origin_x` / `origin_y`; a pick the era judge
// found `timeless` carries the style's film `grade`. Nothing is measured here.
import React from "react";
import { AbsoluteFill, Img, interpolate } from "remotion";
import type { BeatSpec, VisualSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// 0 at the beat's first frame, 1 at its last.
export function beatProgress(beat: BeatSpec, frame: number): number {
  const last = Math.max(beat.start_frame + 1, beat.end_frame - 1);
  return interpolate(frame, [beat.start_frame, last], [0, 1], clamp);
}

// 102: the era grade as a CSS filter (every strength from the spec), or "" when none.
export function gradeFilter(visual: VisualSpec): string {
  const grade = visual.grade;
  if (!grade) {
    return "";
  }
  return `sepia(${grade.sepia}) saturate(${grade.saturate}) contrast(${grade.contrast})`;
}

// 102: the drift at progress `p`, from -travel/2 to +travel/2 over the beat.
export function drift(p: number, travel: number): number {
  return interpolate(p, [0, 1], [-travel / 2, travel / 2]);
}

// The image fitted to cover a box, pushed to `scale` around the framing's focus (102: or
// the spec's origin, a crop_fill's face), drifted by `shiftX` / `shiftY`, graded.
export const Framed: React.FC<{
  visual: VisualSpec;
  width: number;
  height: number;
  scale: number;
  shiftX?: number;
  shiftY?: number;
  style?: React.CSSProperties;
}> = ({ visual, width, height, scale, shiftX = 0, shiftY = 0, style }) => {
  const ox = visual.origin_x ?? visual.focus_x;
  const oy = visual.origin_y ?? visual.focus_y;
  const filter = [gradeFilter(visual), style?.filter ?? ""].filter(Boolean).join(" ");
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width, height, overflow: "hidden" }}>
      <Img
        src={visual.src}
        style={{
          width,
          height,
          objectFit: "cover",
          objectPosition: `${visual.focus_x * 100}% ${visual.focus_y * 100}%`,
          transformOrigin: `${ox * 100}% ${oy * 100}%`,
          transform: `translateX(${shiftX}px) translateY(${shiftY}px) scale(${scale * visual.zoom})`,
          ...style,
          filter: filter || undefined,
        }}
      />
    </div>
  );
};

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
  const shiftX = drift(p, visual.pan_px);
  const shiftY = drift(p, visual.pan_y_px);
  return (
    <AbsoluteFill>
      <Framed visual={visual} width={width} height={height} scale={scale} shiftX={shiftX} shiftY={shiftY} />
      {visual.dim > 0 ? (
        // 027: a set piece's base still is dimmed so its rows or cells read over it.
        <AbsoluteFill style={{ background: "#000", opacity: visual.dim }} />
      ) : null}
    </AbsoluteFill>
  );
};
