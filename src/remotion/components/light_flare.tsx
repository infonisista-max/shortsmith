// `light_flare` (ticket 107; the QjwDTLPLJ6c flare cuts, 083): a warm light burst over the
// cut. Like `flash` (060) the picture itself is a cut - the enter below draws the beat's
// layers plainly - and the burst is a separate layer the composition draws over both
// beats' picture layers and under the PIP circle, the overlays and the captions, which
// never blink. Its strength rises through the previous beat's last frames, peaks on the
// boundary frame and falls through this beat's first (`transitions.light_flare.duration_s`
// in all); its centre travels from `from_x` to `to_x` across the frame at height `y`
// meanwhile, a white-hot `core` inside a warm `glow`, screened over the picture so it
// burns out to light. Every number is the style's `broll.transitions.light_flare` row.
import React from "react";
import { AbsoluteFill } from "remotion";
import type { LightFlareNumbers, TransitionStyle } from "../types";
import type { EnterProps } from "./transitions";

export const LightFlare: React.FC<EnterProps> = ({ children }) => (
  <AbsoluteFill>{children}</AbsoluteFill>
);

export type FlareState = { strength: number; progress: number };

// The burst `framesFromBoundary` frames from the cut (negative before it): its strength
// (1 on the boundary frame, linear to 0 at half the duration either side) and how far
// across its travel it is (0 at the start of the duration, 1 at its end).
export function flareState(
  framesFromBoundary: number,
  fps: number,
  numbers: LightFlareNumbers,
): FlareState {
  const half = (numbers.duration_s * fps) / 2;
  if (half <= 0) return { strength: 0, progress: 0 };
  const strength = Math.max(0, 1 - Math.abs(framesFromBoundary) / half);
  const progress = Math.min(1, Math.max(0, (framesFromBoundary + half) / (2 * half)));
  return { strength, progress };
}

// The strongest flare burning at `frame`: this beat's own enter (falling) or the next
// beat's (rising); none when neither enters with `light_flare` or the style has no row.
export function lightFlareAt(
  frame: number,
  fps: number,
  numbers: TransitionStyle,
  beat: { enter: string; start_frame: number } | undefined,
  next: { enter: string; start_frame: number } | undefined,
): FlareState {
  const row = numbers.light_flare;
  const none = { strength: 0, progress: 0 };
  if (!row) return none;
  const own = beat && beat.enter === "light_flare" ? flareState(frame - beat.start_frame, fps, row) : none;
  const coming =
    next && next.enter === "light_flare" ? flareState(frame - next.start_frame, fps, row) : none;
  return own.strength >= coming.strength ? own : coming;
}

export const LightFlareOverlay: React.FC<{
  state: FlareState;
  numbers: TransitionStyle;
  width: number;
  height: number;
}> = ({ state, numbers, width, height }) => {
  const row = numbers.light_flare;
  if (!row || state.strength <= 0) return null;
  const x = (row.from_x + (row.to_x - row.from_x) * state.progress) * 100;
  const y = row.y * 100;
  // the burst widens as it peaks: at full strength its glow reaches past every corner
  const reach = Math.hypot(width, height) * (0.35 + 0.65 * state.strength);
  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        mixBlendMode: "screen",
        opacity: state.strength,
        background: `radial-gradient(circle ${reach}px at ${x}% ${y}%, ${row.core} 0%, ${row.core} 22%, ${row.glow} 55%, transparent 100%)`,
      }}
    />
  );
};
