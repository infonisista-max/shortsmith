// `lower_third` (decision 6.3): the name-and-role label. A dark panel with the style's
// accent bar down its left edge, the name over the role, faded in over the style's
// `broll.motion.lower_third.duration_s` in the band the front matter gives. The spec
// builder suppresses it under a two-line caption page and where the beat's card strip
// already shows the same text, so this file only draws what it is handed.
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { CaptionStyle, LowerThirdSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const RISE_PX = 16;

export const LowerThird: React.FC<{
  spec: LowerThirdSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const entered = interpolate(frame / fps, [0, spec.fade_s], [0, 1], clamp);
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
          alignItems: "stretch",
          background: spec.fill,
          borderRadius: 6,
          overflow: "hidden",
          fontFamily: style.font_family,
          opacity: entered,
          transform: `translateY(${interpolate(entered, [0, 1], [RISE_PX, 0])}px)`,
        }}
      >
        <div style={{ width: spec.bar_px, background: spec.accent }} />
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            paddingLeft: 24,
            paddingRight: 24,
            minWidth: 0,
          }}
        >
          <span
            style={{
              fontWeight: 700,
              fontSize: spec.name_font_px,
              color: "#fff",
              whiteSpace: "nowrap",
              overflow: "hidden",
            }}
          >
            {spec.name}
          </span>
          {spec.role ? (
            <span
              style={{
                fontWeight: 600,
                fontSize: spec.role_font_px,
                color: spec.accent,
                whiteSpace: "nowrap",
                overflow: "hidden",
              }}
            >
              {spec.role}
            </span>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
