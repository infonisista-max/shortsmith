// `stamp` (decision 4.1): the landed annotation. Rotated text in a bordered box that
// drops from `scale_from` to 1 over the style's `broll.motion.stamp.duration_s` with
// back-easing, then shakes for `shake_s` when the style asks for it (research section
// 3). The box is already measured and clamped into the top `stamp_max_y_fraction` of
// the frame, clear of the platform's right rail (render.stamp_spec).
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { CaptionStyle, StampSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const SHAKE_PX = 6; // the land's recoil, in composition pixels
const SHAKE_HZ = 14;

export const Stamp: React.FC<{
  spec: StampSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const t = frame / fps;
  const landed = interpolate(t, [0, spec.land_s], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.back(1.6)),
  });
  const scale = interpolate(landed, [0, 1], [spec.scale_from, 1]);
  const shake =
    spec.shake_s > 0 && t > spec.land_s
      ? Math.sin((t - spec.land_s) * SHAKE_HZ * Math.PI * 2) *
        SHAKE_PX *
        interpolate(t, [spec.land_s, spec.land_s + spec.shake_s], [1, 0], clamp)
      : 0;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.width,
          height: spec.height,
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: `${spec.border_px}px solid ${spec.color}`,
          borderRadius: spec.radius_px,
          background: spec.fill,
          color: spec.color,
          fontFamily: style.font_family,
          fontWeight: style.font_weight,
          fontSize: spec.font_px,
          letterSpacing: style.letter_spacing_px,
          whiteSpace: "nowrap",
          overflow: "hidden",
          opacity: landed === 0 ? 0 : 1,
          transform: `translateX(${shake}px) rotate(${spec.rotate_deg}deg) scale(${scale})`,
          transformOrigin: "50% 50%",
        }}
      >
        {spec.text}
      </div>
    </AbsoluteFill>
  );
};
