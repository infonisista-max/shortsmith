// `label_flyin` (decisions 9.2, 9.3; ticket 029): the labelled diagram's labels, drawn
// in code over the label-free base `infographic` draws. Each label springs in from the
// frame edge nearest it (`from_x` / `from_y`) and grows from its anchored edge, one after
// another on the stagger `infographics.resolve_diagram` worked out from the beat's
// length. Every box is already placed and measured; this file only animates it.
import React from "react";
import { AbsoluteFill, interpolate, spring } from "remotion";
import type { CaptionStyle, DiagramLayout } from "../types";
import { shadow } from "./captions";

// The engine's fly-in spring (research section 2), with the scale the pill grows from.
const SPRING = { damping: 14, stiffness: 170, mass: 0.6 } as const;
const GROW_FROM = 0.7;
const ORIGIN = { left: "0% 50%", center: "50% 50%", right: "100% 50%" } as const;

export const LabelFlyin: React.FC<{
  spec: DiagramLayout;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => (
  <AbsoluteFill>
    {spec.labels.map((label, i) => {
      const local = frame - Math.round(label.delay_s * fps);
      const entered =
        local < 0
          ? 0
          : spring({
              frame: local,
              fps,
              config: SPRING,
              durationInFrames: Math.max(1, Math.round(spec.fly_s * fps)),
            });
      const x = interpolate(entered, [0, 1], [label.from_x, 0]);
      const y = interpolate(entered, [0, 1], [label.from_y, 0]);
      const scale = interpolate(entered, [0, 1], [GROW_FROM, 1]);
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
            whiteSpace: "nowrap",
            opacity: local < 0 ? 0 : 1,
            transform: `translate(${x}px, ${y}px) scale(${scale})`,
            transformOrigin: ORIGIN[label.anchor],
          }}
        >
          {label.text}
        </div>
      );
    })}
  </AbsoluteFill>
);
