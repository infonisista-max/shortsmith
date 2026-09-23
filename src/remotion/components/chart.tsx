// `chart` (decisions 9.2, 9.3): the chart drawn in code from the planner's series -
// never a picture of a chart and never text inside a generated image. Bars grow from
// the baseline, a line chart draws its dots and the segments between them, and a
// comparison is two wide bars in two colours; every mark starts on its own stagger and
// takes the style's `broll.motion.chart.duration_s` to reach its value.
// `infographics.resolve_chart` measured and placed everything, including the formatted
// value text and the axis labels under the baseline; this file only animates it.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { CaptionStyle, ChartLayout, ChartMark } from "../types";
import { shadow } from "./captions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

function grown(mark: ChartMark, spec: ChartLayout, t: number): number {
  return interpolate(t, [mark.delay_s, mark.delay_s + spec.grow_s], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
}

// The polyline through the marks' points, drawn left to right as the marks appear.
const Line: React.FC<{ spec: ChartLayout; t: number }> = ({ spec, t }) => (
  <svg
    width={spec.plot_left + spec.plot_width}
    height={spec.baseline_y}
    style={{ position: "absolute", left: 0, top: 0 }}
  >
    {spec.marks.slice(1).map((mark, i) => {
      const from = spec.marks[i];
      const p = grown(mark, spec, t);
      return (
        <line
          key={i}
          x1={from.point_x}
          y1={from.point_y}
          x2={from.point_x + (mark.point_x - from.point_x) * p}
          y2={from.point_y + (mark.point_y - from.point_y) * p}
          stroke={spec.marks[spec.marks.length - 1].color}
          strokeWidth={spec.baseline_px}
          strokeLinecap="round"
        />
      );
    })}
  </svg>
);

const Mark: React.FC<{
  spec: ChartLayout;
  mark: ChartMark;
  style: CaptionStyle;
  t: number;
}> = ({ spec, mark, style, t }) => {
  const p = grown(mark, spec, t);
  const dot = spec.form === "line";
  const height = dot ? mark.bar_height : mark.bar_height * p;
  const top = dot ? mark.bar_top : spec.baseline_y - height;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: mark.bar_left,
          top,
          width: mark.bar_width,
          height,
          background: mark.color,
          borderRadius: dot ? "50%" : 8,
          opacity: dot ? p : 1,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: mark.left,
          top: mark.point_y - spec.value_font_px * 1.4,
          width: mark.width,
          textAlign: "center",
          fontFamily: style.font_family,
          fontWeight: style.font_weight,
          fontSize: spec.value_font_px,
          letterSpacing: style.letter_spacing_px,
          color: "#fff",
          textShadow: shadow(style),
          opacity: p,
          whiteSpace: "nowrap",
        }}
      >
        {mark.value_text}
      </div>
      <div
        style={{
          position: "absolute",
          left: mark.left,
          top: spec.label_top,
          width: mark.width,
          textAlign: "center",
          fontFamily: style.font_family,
          fontWeight: style.font_weight,
          fontSize: spec.label_font_px,
          letterSpacing: style.letter_spacing_px,
          color: spec.axis_color,
          textShadow: shadow(style),
          opacity: p,
          whiteSpace: "nowrap",
        }}
      >
        {mark.label}
      </div>
    </>
  );
};

export const Chart: React.FC<{
  spec: ChartLayout;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => {
  const t = frame / fps;
  const title = interpolate(t, [0, spec.grow_s], [0, 1], clamp);
  return (
    <AbsoluteFill>
      {spec.title ? (
        <div
          style={{
            position: "absolute",
            left: spec.plot_left,
            top: spec.title_top,
            width: spec.plot_width,
            fontFamily: style.font_family,
            fontWeight: style.font_weight,
            fontSize: spec.title_font_px,
            letterSpacing: style.letter_spacing_px,
            color: spec.title_color,
            textShadow: shadow(style),
            opacity: title,
            whiteSpace: "nowrap",
          }}
        >
          {spec.title}
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: spec.plot_left,
          top: spec.baseline_y,
          width: spec.plot_width,
          height: spec.baseline_px,
          background: spec.axis_color,
        }}
      />
      {spec.form === "line" ? <Line spec={spec} t={t} /> : null}
      {spec.marks.map((mark, i) => (
        <Mark key={i} spec={spec} mark={mark} style={style} t={t} />
      ))}
    </AbsoluteFill>
  );
};
