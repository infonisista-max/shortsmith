// `map` (decisions 9.2, 9.3; ticket 020): the map composed in code, never a picture of
// one. `infographics.resolve_map` projected the bundled Natural Earth land, coast and
// borders into composition pixels, clipped them to the frame and wrote them as SVG
// paths; it placed every marker at the coordinate the gazetteer gave its name and
// measured the label pill beside it. This file draws the base in the style's colours
// over the palette gradient (the water) and fades it in over `draw_s`; the markers
// are static here - 028 drops them in, draws the route on and moves the object.
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { CaptionStyle, MapLayout } from "../types";
import { shadow } from "./captions";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

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
      {spec.markers.map((marker, i) => (
        <React.Fragment key={i}>
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
            }}
          />
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
            }}
          >
            {marker.name}
          </div>
        </React.Fragment>
      ))}
    </AbsoluteFill>
  );
};
