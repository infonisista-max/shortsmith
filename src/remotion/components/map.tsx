// `map` (decisions 9.2, 9.3; ticket 020): the map composed in code, never a picture of
// one. `infographics.resolve_map` projected the bundled Natural Earth land, coast and
// borders into composition pixels, clipped them to the frame and wrote them as SVG
// paths; it placed every marker at the coordinate the gazetteer gave its name and
// measured the label pill beside it. This file draws the base in the style's colours
// over the palette gradient (the water) and fades it in over `draw_s`. The markers are
// drawn here, static, only when the beat has no `pin_drop` overlay; with one, 028's
// `PinDrop` drops the same `MarkerDot` and `MarkerPill` in (`route_arrow` draws the route on and
// `object_path` moves the object, each its own component over this base).
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { CaptionStyle, MapLayout, MapMarkerLayout } from "../types";
import { shadow } from "./captions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// The label grows in from the scale a diagram label does (029) and the splash ring the
// pin's landing sends out reaches this many times the dot before it fades.
const LABEL_GROW_FROM = 0.7;
const SPLASH_SCALE_TO = 2.6;

// One marker is two parts, already placed and measured, drawn in two passes: every
// label pill first, then every dot over them, so a pill never hides a dot (072).
// `lift` is how far above its point the pin still is (0 once it has landed; `shown` is
// false before it starts falling), `labelIn` the pill's pop, `splash` the landing
// ring's spread; a static marker is 0, true, 1, 1.
export const MarkerDot: React.FC<{
  marker: MapMarkerLayout;
  spec: MapLayout;
  lift: number;
  shown: boolean;
  splash: number;
}> = ({ marker, spec, lift, shown, splash }) => {
  const splashScale = interpolate(splash, [0, 1], [1, SPLASH_SCALE_TO], clamp);
  const splashAlpha = splash > 0 && splash < 1 ? interpolate(splash, [0, 1], [0.6, 0], clamp) : 0;
  return (
    <>
      {splashAlpha > 0 ? (
        <div
          style={{
            position: "absolute",
            left: marker.x - spec.dot_px / 2,
            top: marker.y - spec.dot_px / 2,
            width: spec.dot_px,
            height: spec.dot_px,
            borderRadius: "50%",
            border: `${spec.ring_px}px solid ${spec.marker_color}`,
            boxSizing: "border-box",
            opacity: splashAlpha,
            transform: `scale(${splashScale})`,
            transformOrigin: "50% 50%",
          }}
        />
      ) : null}
      <div
        style={{
          position: "absolute",
          left: marker.x - spec.dot_px / 2,
          top: marker.y - spec.dot_px / 2,
          width: spec.dot_px,
          height: spec.dot_px,
          borderRadius: "50%",
          background: spec.marker_color,
          boxShadow: `0 0 0 ${spec.ring_px}px rgba(255,255,255,0.35)`,
          opacity: shown ? 1 : 0,
          transform: `translateY(${-lift}px)`,
        }}
      />
    </>
  );
};

// The pill carries the name the planner wrote (072), never the gazetteer's.
export const MarkerPill: React.FC<{
  marker: MapMarkerLayout;
  spec: MapLayout;
  style: CaptionStyle;
  labelIn: number;
}> = ({ marker, spec, style, labelIn }) => {
  const labelScale = interpolate(labelIn, [0, 1], [LABEL_GROW_FROM, 1], clamp);
  return (
    <div
      style={{
        position: "absolute",
        left: marker.label_left,
        top: marker.label_top,
        width: marker.label_width,
        height: marker.label_height,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: spec.label_fill,
        borderRadius: spec.label_radius_px,
        fontFamily: style.font_family,
        fontWeight: style.font_weight,
        fontSize: marker.label_font_px,
        letterSpacing: style.letter_spacing_px,
        color: spec.text_color,
        textShadow: shadow(style),
        whiteSpace: "nowrap",
        opacity: labelIn > 0 ? 1 : 0,
        transform: `scale(${labelScale})`,
        // the pill grows out from the side the dot is on
        transformOrigin: marker.label_left > marker.x ? "0% 50%" : "100% 50%",
      }}
    >
      {marker.name}
    </div>
  );
};

export const MapBase: React.FC<{
  spec: MapLayout;
  style: CaptionStyle;
  frame: number;
  fps: number;
  width: number;
  height: number;
}> = ({ spec, style, frame, fps, width, height }) => {
  const t = frame / fps;
  const drawn = interpolate(t, [0, Math.max(spec.draw_s, 1 / fps)], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ opacity: drawn }}>
      <svg width={width} height={height} style={{ position: "absolute", left: 0, top: 0 }}>
        <g fill={spec.land_color} stroke="none">
          {spec.land.map((d, i) => (
            <path key={`l${i}`} d={d} />
          ))}
        </g>
        <g
          fill="none"
          stroke={spec.border_color}
          strokeWidth={spec.border_px}
          strokeLinejoin="round"
          strokeLinecap="round"
        >
          {spec.borders.map((d, i) => (
            <path key={`b${i}`} d={d} />
          ))}
        </g>
        <g
          fill="none"
          stroke={spec.coast_color}
          strokeWidth={spec.coast_px}
          strokeLinejoin="round"
          strokeLinecap="round"
        >
          {spec.coast.map((d, i) => (
            <path key={`c${i}`} d={d} />
          ))}
        </g>
      </svg>
      {spec.pin_drop ? null : (
        <>
          {spec.markers.map((marker, i) => (
            <MarkerPill key={`p${i}`} marker={marker} spec={spec} style={style} labelIn={1} />
          ))}
          {spec.markers.map((marker, i) => (
            <MarkerDot key={`d${i}`} marker={marker} spec={spec} lift={0} shown splash={1} />
          ))}
        </>
      )}
    </AbsoluteFill>
  );
};
