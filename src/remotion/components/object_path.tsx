// `object_path` (decisions 9.2, 9.3; ticket 028): the plan's object - a plane, a ship
// or an arrow - travelling the map's route from `object_start_s` (once the route has
// drawn on) over `object_travel_s`, its heading following the leg's tangent so it
// always points where it is going. The sprites are drawn here as SVG silhouettes
// pointing east in a 100-unit box, so no picture is sourced for them; the layout's
// `segments` give every position and heading, and `object_px` the size.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { MapLayout } from "../types";
import { pointAlong } from "./route_arrow";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Silhouettes pointing east (+x), centred on (50, 50) of a 100-unit box.
const SPRITES: Record<"plane" | "ship" | "arrow", string[]> = {
  plane: [
    "M 96 50 L 72 42 L 44 18 L 33 22 L 50 45 L 22 45 L 12 34 L 5 36 L 11 50 L 5 64 L 12 66 " +
      "L 22 55 L 50 55 L 33 78 L 44 82 L 72 58 Z",
  ],
  ship: [
    "M 8 58 L 78 58 L 96 66 L 84 84 L 16 84 Z",
    "M 28 40 L 68 40 L 68 58 L 28 58 Z",
    "M 42 26 L 54 26 L 54 40 L 42 40 Z",
  ],
  arrow: ["M 5 38 L 58 38 L 58 20 L 96 50 L 58 80 L 58 62 L 5 62 Z"],
};

export const ObjectPath: React.FC<{
  spec: MapLayout;
  frame: number;
  fps: number;
}> = ({ spec, frame, fps }) => {
  const t = frame / fps;
  const p = interpolate(
    t,
    [spec.object_start_s, spec.object_start_s + Math.max(spec.object_travel_s, 1e-6)],
    // 104: it stops short of the endpoint dot, beside it, never over it
    [0, spec.object_end_t ?? 1],
    { ...clamp, easing: Easing.inOut(Easing.cubic) },
  );
  const at = pointAlong(spec.segments, p);
  if (!at || !spec.object || t < spec.object_start_s) return null;
  // Heading west would draw the sprite upside down; mirror it across its own axis so a
  // ship's cabin stays up (a plane and an arrow are symmetric, so it costs nothing).
  const upright = Math.abs(at.heading_deg) > 90 ? -1 : 1;
  const size = spec.object_px;
  return (
    <AbsoluteFill>
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        style={{
          position: "absolute",
          left: at.x - size / 2,
          top: at.y - size / 2,
          transform: `rotate(${at.heading_deg}deg) scaleY(${upright})`,
          transformOrigin: "50% 50%",
          filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.55))",
        }}
      >
        {SPRITES[spec.object].map((d, i) => (
          <path key={i} d={d} fill={spec.text_color} stroke={spec.border_color} strokeWidth={3} />
        ))}
      </svg>
    </AbsoluteFill>
  );
};
