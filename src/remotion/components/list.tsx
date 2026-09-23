// `list` (decisions 4.1, 9.2): the list set piece of nkb_04 - a header in the style's
// accent over one pill per item, each springing in from an alternating side one after
// another, with the item's asset as a circular icon on its left. The beat's own still
// is drawn behind this by `photo`, dimmed by the style's `broll.motion.list.dim`.
// `render.list_spec` measured and placed everything; this file only animates it.
import React from "react";
import { AbsoluteFill, Img, interpolate, spring } from "remotion";
import type { CaptionStyle, ListRow, ListSpec } from "../types";
import { shadow } from "./captions";

// Research section 2: the engine's spring, the same one the hook's cards use.
const SPRING = { damping: 14, stiffness: 160, mass: 0.7 } as const;

export const Row: React.FC<{
  row: ListRow;
  style: CaptionStyle;
  fill: string;
  radiusPx: number;
  frame: number;
  fps: number;
}> = ({ row, style, fill, radiusPx, frame, fps }) => {
  const entered = spring({ frame: frame - Math.round(row.delay_s * fps), fps, config: SPRING });
  const x = interpolate(entered, [0, 1], [row.from_x, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: row.left,
        top: row.top,
        width: row.width,
        height: row.height,
        background: fill,
        borderRadius: radiusPx,
        opacity: entered,
        transform: `translateX(${x}px)`,
      }}
    >
      {row.icon_size > 0 ? (
        <div
          style={{
            position: "absolute",
            left: row.icon_left,
            top: (row.height - row.icon_size) / 2,
            width: row.icon_size,
            height: row.icon_size,
            borderRadius: "50%",
            overflow: "hidden",
            border: "3px solid #fff",
          }}
        >
          <Img
            src={row.icon_src}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: row.text_left,
          top: 0,
          right: 0,
          height: row.height,
          display: "flex",
          alignItems: "center",
          fontFamily: style.font_family,
          fontWeight: style.font_weight,
          fontSize: row.font_px,
          letterSpacing: style.letter_spacing_px,
          color: "#fff",
          textShadow: shadow(style),
          whiteSpace: "nowrap",
          overflow: "hidden",
        }}
      >
        {row.text}
      </div>
    </div>
  );
};

export const List: React.FC<{
  spec: ListSpec;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const header = interpolate(frame / fps, [0, spec.spring_s], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.header_left,
          top: spec.header_top,
          fontFamily: style.font_family,
          fontWeight: style.font_weight,
          fontSize: spec.header_font_px,
          letterSpacing: style.letter_spacing_px,
          color: spec.header_color,
          textShadow: shadow(style),
          opacity: header,
          whiteSpace: "nowrap",
        }}
      >
        {spec.header}
      </div>
      {spec.rows.map((row, i) => (
        <Row
          key={i}
          row={row}
          style={style}
          fill={spec.row_fill}
          radiusPx={spec.row_radius_px}
          frame={frame}
          fps={fps}
        />
      ))}
    </AbsoluteFill>
  );
};
