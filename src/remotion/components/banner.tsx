// `banner` (ticket 107; 083: banner_slide_down, date_banner_slide, text_banner_pop): a bar
// of the recording's own words across the safe band, at the top of the frame or low
// (above the speaker's circle or the captions). It slides in from its outer edge - down
// from above for a top banner, up from below for a low one - over `slide_s` from `at_s`
// seconds into the beat, clipped to its own box so it never crosses the circle, the
// captions or the top zone, and is gone from `until_s`. A `bar_px` edge in `bar` marks
// the side it came from. Every box, colour and time is `render.banner_spec`'s.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { BannerSpec, CaptionStyle } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// How far into its slide the banner is `t` seconds into the beat: 0 before `at_s`, 1 once
// `slide_s` has passed; eased out like the title strip.
export function bannerIn(spec: BannerSpec, t: number): number {
  if (t < spec.at_s) return 0;
  if (spec.slide_s <= 0) return 1;
  return interpolate(t, [spec.at_s, spec.at_s + spec.slide_s], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
}

export const Banner: React.FC<{
  spec: BannerSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const t = frame / fps;
  if (t < spec.at_s || t >= spec.until_s) {
    return null;
  }
  const entered = bannerIn(spec, t);
  const offset = (1 - entered) * spec.height * (spec.from_top ? -1 : 1);
  const edge = `${spec.bar_px}px solid ${spec.bar}`;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.width,
          height: spec.height,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            boxSizing: "border-box",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: spec.fill,
            borderTop: spec.from_top ? edge : undefined,
            borderBottom: spec.from_top ? undefined : edge,
            fontFamily: style.font_family,
            fontWeight: spec.font_weight,
            fontSize: spec.font_px,
            letterSpacing: style.letter_spacing_px,
            color: spec.ink,
            whiteSpace: "nowrap",
            transform: `translateY(${offset}px)`,
          }}
        >
          {spec.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};
