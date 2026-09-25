// `whip` (decision 9.4): the beat's picture whips in from the right over the style's
// `transitions.whip.duration_s`, fastest at the start, under a horizontal-only blur of
// `blur_px` that clears as it lands - the directional blur of a whip pan, drawn with an
// SVG Gaussian whose second deviation is zero (CSS blur is round). The previous beat
// is cut: a whip never dissolves.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { EnterProps } from "./transitions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const FILTER_ID = "shortsmith-whip-blur";

export const Whip: React.FC<EnterProps> = ({ since, fps, numbers, width, children }) => {
  const { duration_s, blur_px } = numbers.whip;
  const p = interpolate(since / fps, [0, duration_s], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  const blur = blur_px * (1 - p);
  const moving = p < 1;
  return (
    <>
      {moving ? (
        <svg width={0} height={0} style={{ position: "absolute" }} aria-hidden>
          <defs>
            <filter id={FILTER_ID} x="-20%" y="0%" width="140%" height="100%">
              <feGaussianBlur stdDeviation={`${blur} 0`} />
            </filter>
          </defs>
        </svg>
      ) : null}
      <AbsoluteFill
        style={{
          transform: `translateX(${(1 - p) * width}px)`,
          filter: moving ? `url(#${FILTER_ID})` : undefined,
        }}
      >
        {children}
      </AbsoluteFill>
    </>
  );
};
