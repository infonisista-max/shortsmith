// `flash` (decision 9.4 as amended by ticket 060): a full-frame colour flash at the cut,
// peaking on the boundary frame and gone `transitions.flash.duration_s` / 2 either side
// of it, in the style's `transitions.flash.color`. The picture itself is a cut (the
// enter below draws the beat's layers plainly from its first frame); the flash is a
// separate layer the composition draws over the picture layers of both beats - rising
// through the previous beat's last frames, falling through this beat's first - and under
// the PIP circle, the landed overlays and the captions, which never blink.
import React from "react";
import { AbsoluteFill } from "remotion";
import type { TransitionStyle } from "../types";
import type { EnterProps } from "./transitions";

export const Flash: React.FC<EnterProps> = ({ children }) => <AbsoluteFill>{children}</AbsoluteFill>;

// The flash's opacity `framesFromBoundary` frames from a flash boundary (negative before
// it): 1 on the boundary frame, linear to 0 at half the duration on either side.
export function flashOpacity(
  framesFromBoundary: number,
  fps: number,
  numbers: TransitionStyle,
): number {
  const half = (numbers.flash.duration_s * fps) / 2;
  if (half <= 0) return 0;
  return Math.max(0, 1 - Math.abs(framesFromBoundary) / half);
}

// The strongest flash sounding at `frame`: this beat's own enter (falling) or the next
// beat's (rising); 0 when neither enters with a flash or the frame is outside both.
export function flashAt(
  frame: number,
  fps: number,
  numbers: TransitionStyle,
  beat: { enter: string; start_frame: number } | undefined,
  next: { enter: string; start_frame: number } | undefined,
): number {
  const own = beat && beat.enter === "flash" ? flashOpacity(frame - beat.start_frame, fps, numbers) : 0;
  const coming =
    next && next.enter === "flash" ? flashOpacity(next.start_frame - frame, fps, numbers) : 0;
  return Math.max(own, coming);
}

export const FlashOverlay: React.FC<{ opacity: number; numbers: TransitionStyle }> = ({
  opacity,
  numbers,
}) => {
  if (opacity <= 0) return null;
  return (
    <AbsoluteFill
      style={{ background: numbers.flash.color, opacity, pointerEvents: "none" }}
    />
  );
};
