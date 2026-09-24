// `counter` (decisions 4.2, 7.1, 9.2; ticket 029): the animated number of a number beat.
// The box is the stamp's (render.counter_spec measured it on the widest text it shows
// and clamped it into the top of the frame); the digits for every frame of the beat
// are already written in the style's grouping (`texts`). From `land_frame` the target
// lands: a pop from `scale_from` over the stamp's `land_s` with its shake, the moment
// the sound director fires the stamp's floor hit.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { CaptionStyle, CounterSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const SHAKE_PX = 6; // the stamp's recoil, in composition pixels
const SHAKE_HZ = 14;

export const Counter: React.FC<{
  spec: CounterSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const text = spec.texts[Math.min(Math.max(frame, 0), spec.texts.length - 1)] ?? spec.text;
  const since = (frame - spec.land_frame) / fps;
  const landed = interpolate(since, [0, spec.land_s], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.back(1.6)),
  });
  const scale = since < 0 ? 1 : interpolate(landed, [0, 1], [spec.scale_from, 1]);
  const shake =
    spec.shake_s > 0 && since >= 0
      ? Math.sin(since * SHAKE_HZ * Math.PI * 2) *
        SHAKE_PX *
        interpolate(since, [0, spec.shake_s], [1, 0], clamp)
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
          transform: `translateX(${shake}px) rotate(${spec.rotate_deg}deg) scale(${scale})`,
          transformOrigin: "50% 50%",
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
