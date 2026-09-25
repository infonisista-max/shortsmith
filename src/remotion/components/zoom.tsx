// `zoom` (decision 9.4): the beat's picture starts pushed in at the style's
// `transitions.zoom.scale_from` and settles to 1 over `duration_s`, easing out. The
// previous beat is cut.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { EnterProps } from "./transitions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Zoom: React.FC<EnterProps> = ({ since, fps, numbers, children }) => {
  const { duration_s, scale_from } = numbers.zoom;
  const scale = interpolate(since / fps, [0, duration_s], [scale_from, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  return (
    <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: "50% 50%" }}>
      {children}
    </AbsoluteFill>
  );
};
