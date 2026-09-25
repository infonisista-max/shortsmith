// `spring` (decision 9.4): the beat's picture flies in from below the frame on
// Remotion's spring with the style's `transitions.spring` damping, stiffness and mass
// (14 / 160 / 0.7 under-damps, so it overshoots a touch and settles). The previous
// beat is cut.
import React from "react";
import { AbsoluteFill, spring } from "remotion";
import type { EnterProps } from "./transitions";

export const Spring: React.FC<EnterProps> = ({ since, fps, numbers, height, children }) => {
  const { damping, stiffness, mass } = numbers.spring;
  const s = spring({ frame: since, fps, config: { damping, stiffness, mass } });
  return (
    <AbsoluteFill style={{ transform: `translateY(${(1 - s) * height}px)` }}>
      {children}
    </AbsoluteFill>
  );
};
