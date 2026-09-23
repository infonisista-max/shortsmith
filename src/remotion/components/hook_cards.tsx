// `hook_cards` (decision 3.4): the hook's second beat. The title sits in the style's
// caption typography at the top of the frame; under it the plan's cards spring in from
// the sides and from below, three across the reference slots or one centred when the
// asset step resolved fewer. The spec places and measures everything (render.hook_spec);
// this file only animates it.
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring } from "remotion";
import type { CaptionStyle, CardBox, HookCardsSpec } from "../types";
import { FONT_FAMILY } from "../fonts";
import { shadow } from "./captions";

// Research section 2: the engine's spring for card fly-ins.
const SPRING = { damping: 14, stiffness: 160, mass: 0.7 } as const;
const TITLE_ENTER_S = 0.3;

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// `hold_s` is how long the card stays on screen after it has sprung in: a wall cell
// takes its Ken Burns over it (027), the hook's and the finale's cards are 1 to 1.
export const PlacedCard: React.FC<{
  card: CardBox;
  frame: number;
  fps: number;
  holdS?: number;
}> = ({ card, frame, fps, holdS }) => {
  const entered = spring({
    frame: frame - Math.round(card.delay_s * fps),
    fps,
    config: SPRING,
  });
  const x = interpolate(entered, [0, 1], [card.from_x, 0]);
  const y = interpolate(entered, [0, 1], [card.from_y, 0]);
  const held = holdS && holdS > 0 ? Math.min(1, frame / fps / holdS) : entered;
  const scale = interpolate(held, [0, 1], [card.scale_from, card.scale_to]);
  return (
    <div
      style={{
        position: "absolute",
        left: card.left,
        top: card.top,
        width: card.box_width,
        height: card.box_height,
        boxSizing: "border-box",
        padding: card.border_px,
        background: "#fff",
        boxShadow: "0 18px 48px rgba(0,0,0,0.55)",
        transform: `translate(${x}px, ${y}px) rotate(${card.rotate_deg}deg)`,
        transformOrigin: "50% 50%",
      }}
    >
      <div style={{ width: card.image_width, height: card.image_height, overflow: "hidden" }}>
        <Img
          src={card.src}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale})`,
          }}
        />
      </div>
      {card.strip_px > 0 ? (
        <div
          style={{
            height: card.strip_px,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: FONT_FAMILY,
            fontWeight: 700,
            fontSize: card.strip_font_px,
            color: "#111",
            whiteSpace: "nowrap",
            overflow: "hidden",
          }}
        >
          {card.label}
        </div>
      ) : null}
    </div>
  );
};

export const HookCards: React.FC<{
  spec: HookCardsSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const t = frame / fps;
  const enter = interpolate(t, [0, TITLE_ENTER_S], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.back(1.7)),
  });
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: spec.title_top,
          width: "100%",
          textAlign: "center",
          fontFamily: style.font_family,
          fontWeight: style.font_weight,
          fontSize: spec.title_font_px,
          lineHeight: `${spec.title_line_px}px`,
          letterSpacing: style.letter_spacing_px,
          color: spec.title_color,
          textShadow: shadow(style),
          opacity: enter,
          transform: `scale(${interpolate(enter, [0, 1], [0.94, 1])})`,
          transformOrigin: "50% 0%",
        }}
      >
        {spec.title_lines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
      {spec.cards.map((card, i) => (
        <PlacedCard key={i} card={card} frame={frame} fps={fps} />
      ))}
    </AbsoluteFill>
  );
};
