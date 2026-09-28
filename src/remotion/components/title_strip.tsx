// `title_strip` (ticket 059): the fixed bar a recipe style (`fastfacts`) keeps at the top of
// the frame for the whole short - the plan's topic in a few words, ink on the style's fill,
// sliding down over `slide_s` on the first frames and gone from `until_frame` (the finale's
// first frame) on. Every box comes from `render.title_strip_spec`; this file measures nothing.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { CaptionStyle, TitleStripSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const TitleStrip: React.FC<{
  spec: TitleStripSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  if (frame >= spec.until_frame) {
    return null;
  }
  const entered =
    spec.slide_s > 0
      ? interpolate(frame / fps, [0, spec.slide_s], [0, 1], {
          ...clamp,
          easing: Easing.out(Easing.cubic),
        })
      : 1;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.width,
          height: spec.height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: spec.fill,
          borderRadius: 10,
          boxShadow: "0 10px 28px rgba(0,0,0,0.45)",
          fontFamily: style.font_family,
          fontWeight: spec.font_weight,
          fontSize: spec.font_px,
          letterSpacing: style.letter_spacing_px,
          color: spec.ink,
          whiteSpace: "nowrap",
          overflow: "hidden",
          opacity: entered,
          transform: `translateY(${interpolate(entered, [0, 1], [-spec.height, 0])}px)`,
        }}
      >
        {spec.text}
      </div>
    </AbsoluteFill>
  );
};
