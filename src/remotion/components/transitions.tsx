// The enter transitions (decision 9.4, ticket 030): the six global motions, each a
// registered component that wraps a beat's picture and animates it in from the beat's
// first frame with the numbers the spec carries (`transitions`, from the style front
// matter). `Transition` picks the beat's `enter` and refuses a name the style never
// enabled - the grammar already rejects it, this is the renderer's own guard. Exit is
// always a cut, except under `fade` and `wipe`, where the composition keeps the previous
// beat drawn beneath for the motion's length (`holdsPrevious`, `holdFrames`).
import React from "react";
import type { TransitionStyle } from "../types";
import { Cut } from "./cut";
import { Fade } from "./fade";
import { Spring } from "./spring";
import { Whip } from "./whip";
import { Wipe } from "./wipe";
import { Zoom } from "./zoom";

export type EnterProps = {
  since: number; // frames since the beat started
  fps: number;
  numbers: TransitionStyle;
  width: number;
  height: number;
  children?: React.ReactNode;
};

export const ENTERS: Record<string, React.FC<EnterProps>> = {
  cut: Cut,
  fade: Fade,
  whip: Whip,
  zoom: Zoom,
  spring: Spring,
  wipe: Wipe,
};

// Under these the previous beat's exit is a fade (it stays beneath until the motion
// ends); every other exit is a cut.
export function holdsPrevious(enter: string): boolean {
  return enter === "fade" || enter === "wipe";
}

export function holdFrames(enter: string, numbers: TransitionStyle, fps: number): number {
  if (enter === "fade") return Math.ceil(numbers.fade.duration_s * fps);
  if (enter === "wipe") return Math.ceil(numbers.wipe.duration_s * fps);
  return 0;
}

export const Transition: React.FC<EnterProps & { enter: string }> = ({ enter, ...props }) => {
  if (!props.numbers.enabled.includes(enter)) {
    throw new Error(
      `enter '${enter}' is not in the style's enter_transitions [${props.numbers.enabled}] (9.4)`,
    );
  }
  const Enter = ENTERS[enter];
  if (!Enter) {
    throw new Error(`unknown enter transition '${enter}'; the vocabulary is ${Object.keys(ENTERS)}`);
  }
  return <Enter {...props} />;
};
