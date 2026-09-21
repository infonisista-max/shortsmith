// `captions` (decision 6.2): draws the word boxes the spec gives it. Each word sits
// centred in its fixed box, so the active-word scale never moves a neighbour; the
// page enters with the 0.94 -> 1 back-eased scale and a short opacity ramp.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { CaptionStyle, RenderSpec, WordBox } from "../types";

const ACTIVE_LEAD_S = 0.02; // spoken this long before the word's start
const ACTIVE_HOLD_S = 0.06; // stays active this long after its end

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

function shadow(style: CaptionStyle): string {
  const s = style.stroke_px;
  const ring = [
    `-${s}px 0 #000`, `${s}px 0 #000`, `0 -${s}px #000`, `0 ${s}px #000`,
    `-${s}px -${s}px #000`, `${s}px -${s}px #000`, `-${s}px ${s}px #000`, `${s}px ${s}px #000`,
  ];
  return [...ring, `0 ${style.drop_px}px 0 #000`, `0 0 ${style.glow_px}px #000`].join(", ");
}

const Word: React.FC<{ word: WordBox; t: number; style: CaptionStyle }> = ({
  word,
  t,
  style,
}) => {
  const onset = word.start - ACTIVE_LEAD_S;
  const release = word.end + ACTIVE_HOLD_S;
  const spoken = t >= onset;
  const active = spoken && t < release;
  const scale = active
    ? interpolate(t, [onset, onset + style.active_scale_s], [1, style.active_scale], clamp)
    : 1;
  const boxed = word.keyword && spoken && !active;
  const color = boxed
    ? style.keyword_fg
    : active
      ? style.active_color
      : spoken
        ? "#fff"
        : `rgba(255,255,255,${style.unspoken_alpha})`;
  return (
    <div
      style={{
        position: "absolute",
        left: word.x,
        top: word.y,
        width: word.width,
        height: word.height,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: boxed ? style.keyword_bg : "transparent",
        borderRadius: boxed ? style.keyword_radius_px : 0,
      }}
    >
      <span
        style={{
          display: "inline-block",
          transform: `scale(${scale})`,
          transformOrigin: "center bottom",
          color,
          textShadow: boxed ? "none" : shadow(style),
          whiteSpace: "nowrap",
        }}
      >
        {word.text}
      </span>
    </div>
  );
};

export const Captions: React.FC<{ spec: RenderSpec; t: number }> = ({ spec, t }) => {
  const style = spec.caption_style;
  const page = spec.captions.find((p) => t >= p.start && t < p.end);
  if (!page || page.words.length === 0) {
    return null;
  }
  const age = t - page.start;
  const enterScale = interpolate(age, [0, style.enter_s], [style.enter_scale_from, 1], {
    ...clamp,
    easing: Easing.out(Easing.back(1.7)),
  });
  const opacity = interpolate(age, [0, style.enter_opacity_s], [0, 1], clamp);
  const bottom = Math.max(...page.words.map((w) => w.y + w.height));
  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `scale(${enterScale})`,
        transformOrigin: `${spec.width / 2}px ${bottom}px`,
        fontFamily: style.font_family,
        fontWeight: style.font_weight,
        fontSize: style.size_px,
        lineHeight: style.line_height,
        letterSpacing: style.letter_spacing_px,
      }}
    >
      {page.words.map((word, i) => (
        <Word key={`${page.index}-${i}`} word={word} t={t} style={style} />
      ))}
    </AbsoluteFill>
  );
};
