// `split` (decision 5.2): the news-card composite that makes raw web portraits look
// professional - two panes side by side inside one framed card with a thin seam, each
// labelled, a circular badge overlapping the card's top-left corner, and a title strip
// along the bottom whose pane words are boxed in the style's accent. The right pane
// slides in over the style's `broll.motion.split.duration_s` (nkb_08). Every box comes
// from `render.split_spec`; this file measures nothing.
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate } from "remotion";
import type { CaptionStyle, SplitSpec } from "../types";
import { shadow } from "./captions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Split: React.FC<{
  spec: SplitSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const t = frame / fps;
  const slid = interpolate(t, [0, spec.slide_s], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.width,
          height: spec.height,
          boxSizing: "border-box",
          background: "#fff",
          boxShadow: "0 18px 48px rgba(0,0,0,0.55)",
          transform: `rotate(${spec.rotate_deg}deg)`,
          transformOrigin: "50% 50%",
          overflow: "hidden",
        }}
      >
        {spec.panes.map((pane, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              left: pane.left,
              top: pane.top,
              width: pane.pane_width,
              height: pane.pane_height,
              overflow: "hidden",
              background: "#111",
              transform: `translateX(${interpolate(slid, [0, 1], [pane.from_x, 0])}px)`,
            }}
          >
            <Img
              src={pane.src}
              style={{
                width: "100%",
                height: spec.label_px > 0 ? pane.pane_height - spec.label_px : "100%",
                objectFit: "cover",
              }}
            />
            {spec.label_px > 0 ? (
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  bottom: 0,
                  width: "100%",
                  height: spec.label_px,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "rgba(17,17,17,0.82)",
                  fontFamily: style.font_family,
                  fontWeight: 700,
                  fontSize: spec.label_font_px,
                  color: "#fff",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                }}
              >
                {pane.label}
              </div>
            ) : null}
          </div>
        ))}
        <div
          style={{
            position: "absolute",
            left: 0,
            bottom: 0,
            width: "100%",
            height: spec.title_px,
            background: "#111",
          }}
        />
      </div>
      {spec.title_words.map((word, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: word.left,
            top: spec.top + spec.height - spec.title_px / 2 - spec.title_font_px * 0.7,
            width: word.width,
            textAlign: "center",
            fontFamily: style.font_family,
            fontWeight: style.font_weight,
            fontSize: spec.title_font_px,
            letterSpacing: style.letter_spacing_px,
            lineHeight: `${spec.title_font_px * 1.4}px`,
            color: word.highlight ? spec.highlight_fg : spec.title_color,
            background: word.highlight ? spec.highlight_bg : "transparent",
            borderRadius: word.highlight ? spec.highlight_radius_px : 0,
            boxShadow: word.highlight
              ? `0 0 0 ${spec.highlight_pad_px}px ${spec.highlight_bg}`
              : undefined,
            textShadow: word.highlight ? undefined : shadow(style),
            whiteSpace: "nowrap",
          }}
        >
          {word.text}
        </div>
      ))}
      {spec.badge ? (
        <div
          style={{
            position: "absolute",
            left: spec.badge.left,
            top: spec.badge.top,
            width: spec.badge.diameter,
            height: spec.badge.diameter,
            boxSizing: "border-box",
            borderRadius: "50%",
            overflow: "hidden",
            border: `${spec.badge.ring_px}px solid ${spec.badge.ring_color}`,
            boxShadow: "0 10px 28px rgba(0,0,0,0.6)",
            background: "#111",
          }}
        >
          <Img
            src={spec.badge.src}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
