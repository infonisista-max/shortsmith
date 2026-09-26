// `route_arrow` (decisions 9.2, 9.3; ticket 028): the map's route drawing on from its
// first place to its last over the beat's `route_draw_s`, from `route_start_s` (after
// the pins have landed), with an arrowhead riding the tip and turned to the leg's
// tangent. The polyline is the layout's projected `route_path` (its length measured
// in Python, so the dash trick needs no DOM measurement) and the legs with their
// headings are `segments`; this file only animates them.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { MapLayout, RouteSegment } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export type RoutePoint = { x: number; y: number; heading_deg: number };

// Where a fraction `p` of the route's length falls: the point on its leg and that
// leg's heading. Past the end it is the last point; with no legs there is nothing.
export function pointAlong(segments: RouteSegment[], p: number): RoutePoint | null {
  if (segments.length === 0) return null;
  const at = Math.min(Math.max(p, 0), 1);
  const leg = segments.find((s) => at <= s.t1) ?? segments[segments.length - 1];
  const span = leg.t1 - leg.t0;
  const f = span > 0 ? Math.min(Math.max((at - leg.t0) / span, 0), 1) : 1;
  return {
    x: leg.x0 + (leg.x1 - leg.x0) * f,
    y: leg.y0 + (leg.y1 - leg.y0) * f,
    heading_deg: leg.heading_deg,
  };
}

// How far along the route the draw-on is at `t` seconds into the beat.
export function drawnAt(spec: MapLayout, t: number): number {
  return interpolate(t, [spec.route_start_s, spec.route_start_s + Math.max(spec.route_draw_s, 1e-6)], [0, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
}

export const RouteArrow: React.FC<{
  spec: MapLayout;
  frame: number;
  fps: number;
  width: number;
  height: number;
}> = ({ spec, frame, fps, width, height }) => {
  const p = drawnAt(spec, frame / fps);
  const tip = pointAlong(spec.segments, p);
  const head = spec.arrow_px;
  return (
    <AbsoluteFill>
      <svg width={width} height={height} style={{ position: "absolute", left: 0, top: 0 }}>
        <path
          d={spec.route_path}
          fill="none"
          stroke={spec.marker_color}
          strokeWidth={spec.route_px}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={spec.route_length_px}
          strokeDashoffset={spec.route_length_px * (1 - p)}
        />
        {tip && p > 0 ? (
          <polygon
            points={`0,0 ${-head},${-head * 0.45} ${-head * 0.7},0 ${-head},${head * 0.45}`}
            fill={spec.marker_color}
            transform={`translate(${tip.x} ${tip.y}) rotate(${tip.heading_deg})`}
          />
        ) : null}
      </svg>
    </AbsoluteFill>
  );
};
