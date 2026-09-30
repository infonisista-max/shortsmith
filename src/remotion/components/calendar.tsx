// `calendar` (ticket 108; 083: calendar_flip, calendar_page_peel): a year or date beat's
// calendar page, in place of a stamp. It pops in at `appear_s` showing `from_text`; from
// `flip_start_s` the page peels up and away about its binding (the header strip) while
// `to_text` shows beneath, and it lands flat on `to_text` at `land_s` - the spoken word -
// then holds until `until_s`. Every box, colour and time is `render.calendar_spec`'s.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { CalendarSpec, CaptionStyle } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const POP_S = 0.2; // the card entrances' pop (0.2 s), as the stamp lands
const PEEL_DEG = 110; // past upright, so the peeled page is gone edge-on and beyond

// How far the old page has peeled `t` seconds into the beat: 0 until the flip starts, 1
// from the landing on.
export function peel(spec: CalendarSpec, t: number): number {
  if (t <= spec.flip_start_s) return 0;
  if (t >= spec.land_s || spec.land_s <= spec.flip_start_s) return 1;
  return interpolate(t, [spec.flip_start_s, spec.land_s], [0, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
}

// One page face under the header: `top` is 0 inside the peeling layer, else the header.
const Face: React.FC<{ spec: CalendarSpec; style: CaptionStyle; text: string; top: number }> = ({
  spec,
  style,
  text,
  top,
}) => (
  <div
    style={{
      position: "absolute",
      left: 0,
      top,
      width: spec.width,
      height: spec.height - spec.header_px,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: spec.page,
      color: spec.ink,
      fontFamily: style.font_family,
      fontWeight: spec.font_weight,
      fontSize: spec.font_px,
      letterSpacing: style.letter_spacing_px,
      whiteSpace: "nowrap",
      borderRadius: "0 0 14px 14px",
    }}
  >
    {text}
  </div>
);

export const Calendar: React.FC<{
  spec: CalendarSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const t = frame / fps;
  if (t < spec.appear_s || t >= spec.until_s) {
    return null;
  }
  const pop = interpolate(t, [spec.appear_s, spec.appear_s + POP_S], [0.6, 1], {
    ...clamp,
    easing: Easing.back(2),
  });
  const peeled = peel(spec, t);
  const ring = spec.header_px * 0.28;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.width,
          height: spec.height,
          transform: `scale(${pop})`,
          boxShadow: "0 14px 34px rgba(0,0,0,0.45)",
          borderRadius: 14,
          perspective: spec.height * 3,
        }}
      >
        <Face spec={spec} style={style} text={spec.to_text} top={spec.header_px} />
        {peeled < 1 ? (
          <div
            style={{
              position: "absolute",
              left: 0,
              top: spec.header_px,
              width: spec.width,
              height: spec.height - spec.header_px,
              transformOrigin: "50% 0",
              transform: `rotateX(${peeled * PEEL_DEG}deg)`,
              backfaceVisibility: "hidden",
              filter: `brightness(${1 - 0.35 * peeled})`,
            }}
          >
            <Face spec={spec} style={style} text={spec.from_text} top={0} />
          </div>
        ) : null}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: spec.width,
            height: spec.header_px,
            background: spec.header,
            borderRadius: "14px 14px 0 0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-around",
          }}
        >
          {[0, 1].map((i) => (
            <div
              key={i}
              style={{ width: ring, height: ring, borderRadius: ring, background: spec.header_ink }}
            />
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
