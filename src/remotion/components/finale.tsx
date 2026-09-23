// `finale` (decision 3.4): the last beat. The style gradient carries a ringed centre
// circle with the presenter cut in it, the hook's cards around it and the payoff word
// under it; the pager has already hidden every caption from this beat's start (6.1).
// The whole card fades in over the style's `broll.motion.finale.duration_s`.
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { CaptionStyle, FinaleCardSpec, RenderSpec } from "../types";
import { shadow } from "./captions";
import { PlacedCard } from "./hook_cards";
import { PresenterCircle } from "./pip";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Finale: React.FC<{
  spec: FinaleCardSpec;
  render: RenderSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, render, style, frame, fps }) => {
  const opacity = interpolate(frame / fps, [0, spec.fade_s], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ opacity }}>
      {spec.cards.map((card, i) => (
        <PlacedCard key={i} card={card} frame={frame} fps={fps} />
      ))}
      <PresenterCircle
        spec={render}
        left={spec.circle_left}
        top={spec.circle_top}
        diameter={spec.circle_diameter}
        ringPx={spec.ring_px}
        ringColor={spec.ring_color}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: spec.text_top,
          width: "100%",
          textAlign: "center",
          fontFamily: style.font_family,
          fontWeight: style.font_weight,
          fontSize: spec.text_font_px,
          letterSpacing: style.letter_spacing_px,
          color: spec.text_color,
          textShadow: shadow(style),
        }}
      >
        {spec.text}
      </div>
    </AbsoluteFill>
  );
};
