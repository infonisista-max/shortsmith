// `infographic` (decisions 9.2, 9.3, 5.5): the labelled diagram. The base picture is
// label-free - the generator was told "no text, no labels" - and every label is drawn
// here in code, in a pill at the pixel position `infographics.resolve_diagram` mapped
// from the planner's percentages. The labels fade in on their own stagger over the
// style's `broll.motion.infographic.duration_s`; 029 flies them in from the anchor side.
import React from "react";
import { AbsoluteFill, Img, interpolate } from "remotion";
import type { CaptionStyle, DiagramLayout } from "../types";
import { shadow } from "./captions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Infographic: React.FC<{
  spec: DiagramLayout;
  style: CaptionStyle;
  frame: number;
  fps: number;
  lengthS: number;
}> = ({ spec, style, frame, fps, lengthS }) => {
  const t = frame / fps;
  const scale = interpolate(t, [0, Math.max(lengthS, 1 / fps)], [spec.scale_from, spec.scale_to], clamp);
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.box_width,
          height: spec.box_height,
          overflow: "hidden",
        }}
      >
        <Img
          src={spec.src}
          style={{
            width: spec.box_width,
            height: spec.box_height,
            objectFit: "cover",
            objectPosition: `${spec.focus_x * 100}% ${spec.focus_y * 100}%`,
            transformOrigin: `${spec.focus_x * 100}% ${spec.focus_y * 100}%`,
            transform: `scale(${scale * spec.zoom})`,
          }}
        />
        {spec.dim > 0 ? (
          <AbsoluteFill style={{ background: "#000", opacity: spec.dim }} />
        ) : null}
      </div>
      {spec.labels.map((label, i) => {
        const shown = interpolate(
          t,
          [label.delay_s, label.delay_s + spec.fly_s],
          [0, 1],
          clamp,
        );
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: label.left,
              top: label.top,
              width: label.width,
              height: label.height,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: spec.fill,
              borderRadius: spec.radius_px,
              fontFamily: style.font_family,
              fontWeight: style.font_weight,
              fontSize: label.font_px,
              letterSpacing: style.letter_spacing_px,
              color: spec.text_color,
              textShadow: shadow(style),
              opacity: shown,
              whiteSpace: "nowrap",
            }}
          >
            {label.text}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
