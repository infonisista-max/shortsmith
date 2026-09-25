// `fade` (decision 9.4): the beat's picture rises from transparent over the style's
// `transitions.fade.duration_s`; the composition keeps the previous beat drawn beneath
// for that long, so the exit reads as a fade too (the cross-dissolve).
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { EnterProps } from "./transitions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Fade: React.FC<EnterProps> = ({ since, fps, numbers, children }) => {
  const opacity = interpolate(since / fps, [0, numbers.fade.duration_s], [0, 1], clamp);
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};
