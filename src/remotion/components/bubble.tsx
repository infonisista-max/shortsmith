// `bubble` (decision 4.1 as amended by ticket 063): a comic speech bubble (a rounded
// box with a tail) or thought bubble (a rounded body with a trail of dots) carrying words
// the recording itself said. Every bubble of the beat is already wrapped, placed and
// timed by `render.bubble_spec` (inside the safe area, off the PIP circle, the captions,
// the stamp, any detected face and the beat's other bubble; the tail tip is the planner's
// anchor); this file only draws and animates it: hidden until `at_s` seconds into the
// beat, a back-eased overshoot from `scale_from` to 1 over `pop_s` about the body's
// centre, held until `until_s`. The outline `path` is one shape (body and tail), so the
// fill and the dark stroke meet with no seam; the lines of text sit centred in the body
// in the style's caption family at the spec's weight and ink.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { BubbleSpec, CaptionStyle } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const OVERSHOOT = 1.6; // the back-easing's overshoot: a soft comic pop, under the text pop's
const LINE_HEIGHT = 1.2; // render.BUBBLE_LINE_HEIGHT: the body was measured at this

export const Bubble: React.FC<{
  bubbles: BubbleSpec[];
  style: CaptionStyle;
  frame: number;
  fps: number;
  width: number;
  height: number;
}> = ({ bubbles, style, frame, fps, width, height }) => {
  const t = frame / fps;
  return (
    <AbsoluteFill>
      {bubbles.map((bubble, i) => {
        if (t < bubble.at_s || t >= bubble.until_s) {
          return null;
        }
        const landed = interpolate(t, [bubble.at_s, bubble.at_s + bubble.pop_s], [0, 1], {
          ...clamp,
          easing: Easing.out(Easing.back(OVERSHOOT)),
        });
        const scale = interpolate(landed, [0, 1], [bubble.scale_from, 1]);
        const cx = bubble.left + bubble.width / 2;
        const cy = bubble.top + bubble.height / 2;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              width,
              height,
              transform: `scale(${scale})`,
              transformOrigin: `${cx}px ${cy}px`,
            }}
          >
            <svg
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              style={{ position: "absolute", left: 0, top: 0 }}
            >
              {bubble.dots.map((dot, j) => (
                <circle
                  key={j}
                  cx={dot.cx}
                  cy={dot.cy}
                  r={dot.r}
                  fill={bubble.fill}
                  stroke={bubble.ink}
                  strokeWidth={Math.max(2, bubble.stroke_px - 2)}
                />
              ))}
              <path
                d={bubble.path}
                fill={bubble.fill}
                stroke={bubble.ink}
                strokeWidth={bubble.stroke_px}
                strokeLinejoin="round"
              />
            </svg>
            <div
              style={{
                position: "absolute",
                left: bubble.left,
                top: bubble.top,
                width: bubble.width,
                height: bubble.height,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: style.font_family,
                fontWeight: bubble.font_weight,
                fontSize: bubble.font_px,
                lineHeight: LINE_HEIGHT,
                letterSpacing: style.letter_spacing_px,
                color: bubble.ink,
                textAlign: "center",
                whiteSpace: "nowrap",
              }}
            >
              {bubble.lines.map((line, j) => (
                <div key={j}>{line}</div>
              ))}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
