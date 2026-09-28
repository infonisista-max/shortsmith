// `text_pop` (decision 4.1 as amended by ticket 061): 1-4 bold words pinned on the
// picture near the thing they name, popping in on the spoken word. Every pop of the beat
// is already placed, sized and timed by `render.text_pop_spec` (inside the safe area,
// off the PIP circle, the captions and any detected face); this file only animates it:
// hidden until `at_s` seconds into the beat, a back-eased overshoot from `scale_from` to
// 1 over `pop_s`, held until `until_s`, tilted by `rotate_deg`. The type is the style's
// caption family at the spec's weight, in the pop's fill with a dark outline and drop
// shadow, so it reads over any picture.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { CaptionStyle, TextPopSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const OVERSHOOT = 2.0; // the back-easing's overshoot: a punchy land, like the references

export const TextPop: React.FC<{
  pops: TextPopSpec[];
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ pops, style, frame, fps }) => {
  const t = frame / fps;
  return (
    <AbsoluteFill>
      {pops.map((pop, i) => {
        if (t < pop.at_s || t >= pop.until_s) {
          return null;
        }
        const landed = interpolate(t, [pop.at_s, pop.at_s + pop.pop_s], [0, 1], {
          ...clamp,
          easing: Easing.out(Easing.back(OVERSHOOT)),
        });
        const scale = interpolate(landed, [0, 1], [pop.scale_from, 1]);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: pop.left,
              top: pop.top,
              width: pop.width,
              height: pop.height,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: style.font_family,
              fontWeight: pop.font_weight,
              fontSize: pop.font_px,
              letterSpacing: style.letter_spacing_px,
              color: pop.color,
              WebkitTextStroke: `${pop.stroke_px}px #000`,
              paintOrder: "stroke fill",
              textShadow: `0 ${pop.drop_px}px 0 #000, 0 ${pop.drop_px}px ${pop.drop_px * 3}px rgba(0,0,0,0.6)`,
              whiteSpace: "nowrap",
              transform: `rotate(${pop.rotate_deg}deg) scale(${scale})`,
              transformOrigin: "50% 50%",
            }}
          >
            {pop.text}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
