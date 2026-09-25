// `wipe` (decision 9.4): the beat's picture is uncovered left to right over the style's
// `transitions.wipe.duration_s` (the map's region change); the composition keeps the
// previous beat drawn beneath for that long, so the wipe has something to uncover.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { EnterProps } from "./transitions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Wipe: React.FC<EnterProps> = ({ since, fps, numbers, children }) => {
  const p = interpolate(since / fps, [0, numbers.wipe.duration_s], [0, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
  return (
    <AbsoluteFill style={{ clipPath: `inset(0 ${(1 - p) * 100}% 0 0)` }}>{children}</AbsoluteFill>
  );
};
